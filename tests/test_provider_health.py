"""Чи ловимо двигун, що масово падає, поки решта моніторингу зелена.

Мотив із проду 2026-08: `OpenAI DALL-E 3` дав 20 провалів на 20 генерацій (модель
вилучили з API 2026-05-12), а `Flux.1 (Replicate)` — 27.7% проти 0.3% у
gpt-image-1. Кредити за збій повертаються, тож ані баланс, ані health-ендпоінти
не сигналили — обидва випадки знайшли постфактум із ручного розбору transactions.
"""

from datetime import datetime, timedelta, timezone

from services import db
from services.provider_health import (
    DEBIT_NOTE,
    FAILURE_NOTE,
    check_engines,
    failure_threshold_pct,
    min_attempts,
    summary_text,
)

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def _make_db(tmp_path, rows):
    """БД з мінімальною таблицею transactions. rows: (engine, note, hours_ago)."""
    path = tmp_path / "users.db"
    conn = db.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS transactions ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " wallet_address TEXT NOT NULL,"
        " kind TEXT NOT NULL,"
        " credits INTEGER NOT NULL DEFAULT 0,"
        " engine TEXT NOT NULL DEFAULT '',"
        " note TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL)"
    )
    for engine, note, hours_ago in rows:
        kind = "refund" if note == FAILURE_NOTE else "debit"
        conn.execute(
            "INSERT INTO transactions (wallet_address, kind, credits, engine, note, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("0xw", kind, 1, engine, note, (NOW - timedelta(hours=hours_ago)).isoformat()),
        )
    conn.commit()
    conn.close()
    return path


def _attempts(engine, n, hours_ago=1):
    return [(engine, DEBIT_NOTE, hours_ago)] * n


def _failures(engine, n, hours_ago=1):
    return [(engine, FAILURE_NOTE, hours_ago)] * n


def test_healthy_engine_ok(tmp_path):
    """0.4% збоїв — норма живого двигуна, алерту немає."""
    path = _make_db(tmp_path, _attempts("Stability AI (Core / SD3)", 250) + _failures("Stability AI (Core / SD3)", 1))
    st = check_engines(path, now=NOW)
    assert st.ok is True
    assert st.checked is True
    assert st.engines[0].attempts == 250
    assert st.engines[0].failures == 1
    assert st.engines[0].unhealthy is False
    assert "✅" in summary_text(st)


def test_dead_engine_flagged(tmp_path):
    """Мертва модель (100% збоїв) — саме той випадок, який пропустили з DALL-E 3."""
    path = _make_db(tmp_path, _attempts("OpenAI DALL-E 3", 20) + _failures("OpenAI DALL-E 3", 20))
    st = check_engines(path, now=NOW)
    assert st.ok is False
    assert st.engines[0].failure_pct == 100.0
    assert st.engines[0].unhealthy is True
    text = summary_text(st)
    assert "❌" in text and "OpenAI DALL-E 3" in text and "100%" in text


def test_flux_rate_above_threshold_flagged(tmp_path):
    """27.7% — реальна частка Flux у проді; має перевищувати поріг 20%."""
    path = _make_db(tmp_path, _attempts("Flux.1 (Replicate)", 65) + _failures("Flux.1 (Replicate)", 18))
    st = check_engines(path, now=NOW)
    assert st.ok is False
    assert round(st.engines[0].failure_pct, 1) == 27.7


def test_small_sample_never_flagged(tmp_path):
    """1 збій із 3 — це 33%, але не сигнал: вибірка нижче min_attempts."""
    path = _make_db(tmp_path, _attempts("Flux.1 (Replicate)", 3) + _failures("Flux.1 (Replicate)", 1))
    st = check_engines(path, now=NOW)
    assert st.ok is True
    assert st.checked is False
    assert st.engines[0].unhealthy is False
    assert "замало генерацій" in summary_text(st)


def test_window_excludes_old_failures(tmp_path):
    """Учорашня аварія за межами вікна не тримає алерт піднятим вічно."""
    rows = _attempts("Flux.1 (Replicate)", 30, hours_ago=1)
    rows += _failures("Flux.1 (Replicate)", 30, hours_ago=48)  # позавчора
    path = _make_db(tmp_path, rows)
    st = check_engines(path, window_hours=24, now=NOW)
    assert st.ok is True
    assert st.engines[0].failures == 0


def test_engines_ranked_by_failure_rate(tmp_path):
    """Найгірший двигун — першим у звіті."""
    rows = _attempts("OpenAI gpt-image-1", 300) + _failures("OpenAI gpt-image-1", 1)
    rows += _attempts("Flux.1 (Replicate)", 60) + _failures("Flux.1 (Replicate)", 18)
    path = _make_db(tmp_path, rows)
    st = check_engines(path, now=NOW)
    assert [e.engine for e in st.engines] == ["Flux.1 (Replicate)", "OpenAI gpt-image-1"]


def test_missing_table_is_not_an_alert(tmp_path):
    """Порожнє розгортання без історії — «не можу перевірити», а не «двигуни хворі»."""
    st = check_engines(tmp_path / "absent.db", now=NOW)
    assert st.ok is True
    assert st.checked is False
    assert st.engines == ()


def test_thresholds_from_env(monkeypatch):
    monkeypatch.delenv("PROVIDER_FAILURE_THRESHOLD_PCT", raising=False)
    monkeypatch.delenv("PROVIDER_MIN_ATTEMPTS", raising=False)
    assert failure_threshold_pct() == 20.0
    assert min_attempts() == 5
    monkeypatch.setenv("PROVIDER_FAILURE_THRESHOLD_PCT", "5")
    monkeypatch.setenv("PROVIDER_MIN_ATTEMPTS", "50")
    assert failure_threshold_pct() == 5.0
    assert min_attempts() == 50
    # Порожнє/сміттєве значення не має вимикати перевірку (пастка `get(key, default)`).
    monkeypatch.setenv("PROVIDER_FAILURE_THRESHOLD_PCT", "")
    monkeypatch.setenv("PROVIDER_MIN_ATTEMPTS", "bad")
    assert failure_threshold_pct() == 20.0
    assert min_attempts() == 5


def test_custom_threshold_applies(tmp_path):
    """Суворіший поріг ловить те, що дефолтний пропускає."""
    path = _make_db(tmp_path, _attempts("Flux.1 (Replicate)", 100) + _failures("Flux.1 (Replicate)", 10))
    assert check_engines(path, now=NOW).ok is True            # 10% < 20%
    assert check_engines(path, threshold=5.0, now=NOW).ok is False
