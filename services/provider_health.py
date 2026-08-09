"""provider_health.py — чи не почав двигун генерації масово падати.

Навіщо окрема перевірка: health-ендпоінти й бекапи можуть бути зеленими, поки
конкретний постачальник зображень тихо відмовляє. Кредити при збої повертаються,
тож ані баланс, ані виручка не сигналять — страждає лише користувач, у якого
кожен N-ий клік дає помилку.

Історія, що це довела (дані проду, 2026-08): `OpenAI DALL-E 3` набрав 20 провалів
на 20 генерацій (модель вилучили з API 2026-05-12), а `Flux.1 (Replicate)` —
27.7% проти 0.3% у gpt-image-1. Обидва випадки помітили постфактум із ручного
розбору `transactions`, а не з моніторингу.

Тут — чиста функція (без Streamlit і без мережі): рахує пари
`debit note='image generation'` / `refund note='refund: generation failed'` за
двигуном у вікні. Викликається зі `scripts/daily_health_check.py`, який шле
Telegram-алерт.

Обидва боки пари несуть ЗАПИТАНИЙ двигун (`pipeline_batch._generate_one` пише
`engine=engine` і в списання, і в повернення), тож частка рахується коректно
навіть коли B2-каскад підмінив виконавця: провал каскаду означає, що впали всі.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services import db

# Нота списання за генерацію і нота повернення при збої — пишуться в
# services/pipeline_batch._generate_one. Зміниш там — зміни тут.
DEBIT_NOTE = "image generation"
FAILURE_NOTE = "refund: generation failed"

# Поріг частки збоїв, за яким двигун вважається хворим. 20% — свідомо високо:
# здорові двигуни в проді тримають 0.3–0.4%, тож поріг ловить катастрофу
# (мертва модель, протухлий ключ, вичерпаний баланс), а не звичайний шум.
DEFAULT_FAILURE_THRESHOLD_PCT = 20.0

# Менша вибірка статистично порожня: 1 збій із 3 — це 33%, але не сигнал.
DEFAULT_MIN_ATTEMPTS = 5

DEFAULT_WINDOW_HOURS = 24


@dataclass(frozen=True)
class EngineHealth:
    engine: str
    attempts: int
    failures: int
    failure_pct: float
    unhealthy: bool


@dataclass(frozen=True)
class ProviderStatus:
    ok: bool
    engines: tuple[EngineHealth, ...]
    window_hours: float
    checked: bool  # False — вибірки не набралось, вердикту немає


def failure_threshold_pct() -> float:
    raw = os.environ.get("PROVIDER_FAILURE_THRESHOLD_PCT") or ""
    try:
        val = float(raw)
    except ValueError:
        return DEFAULT_FAILURE_THRESHOLD_PCT
    return val if val > 0 else DEFAULT_FAILURE_THRESHOLD_PCT


def min_attempts() -> int:
    raw = os.environ.get("PROVIDER_MIN_ATTEMPTS") or ""
    try:
        val = int(raw)
    except ValueError:
        return DEFAULT_MIN_ATTEMPTS
    return val if val > 0 else DEFAULT_MIN_ATTEMPTS


def check_engines(
    db_path: Path,
    *,
    window_hours: float = DEFAULT_WINDOW_HOURS,
    threshold: float | None = None,
    minimum: int | None = None,
    now: datetime | None = None,
) -> ProviderStatus:
    """Частка збоїв кожного двигуна у вікні. `checked=False` — даних замало для вердикту.

    Двигуни з `attempts < minimum` потрапляють у звіт (щоб було видно обсяг), але
    ніколи не позначаються `unhealthy` — інакше перший же невдалий кадр після
    тижня простою підняв би хибний алерт.
    """
    limit = threshold if threshold is not None else failure_threshold_pct()
    floor = minimum if minimum is not None else min_attempts()
    moment = now or datetime.now(timezone.utc)
    since = (moment - timedelta(hours=window_hours)).isoformat()

    conn = db.connect(db_path)
    try:
        rows = conn.execute(
            db.q(
                "SELECT engine,"
                " SUM(CASE WHEN kind = 'debit' AND note = ? THEN 1 ELSE 0 END),"
                " SUM(CASE WHEN kind = 'refund' AND note = ? THEN 1 ELSE 0 END)"
                " FROM transactions"
                " WHERE created_at >= ? AND note IN (?, ?)"
                " GROUP BY engine"
            ),
            (DEBIT_NOTE, FAILURE_NOTE, since, DEBIT_NOTE, FAILURE_NOTE),
        ).fetchall()
    except Exception:
        # Таблиці ще немає (свіже розгортання, порожня БД) — це «не можу перевірити»,
        # а не «двигуни хворі». Health-check не має падати через відсутність історії.
        return ProviderStatus(True, (), window_hours, checked=False)
    finally:
        conn.close()

    engines: list[EngineHealth] = []
    for engine, attempts, failures in rows:
        attempts = int(attempts or 0)
        failures = int(failures or 0)
        if attempts <= 0:
            continue
        pct = failures * 100.0 / attempts
        engines.append(EngineHealth(
            engine=engine or "(без двигуна)",
            attempts=attempts,
            failures=failures,
            failure_pct=pct,
            unhealthy=attempts >= floor and pct >= limit,
        ))

    engines.sort(key=lambda e: e.failure_pct, reverse=True)
    checked = any(e.attempts >= floor for e in engines)
    return ProviderStatus(
        ok=not any(e.unhealthy for e in engines),
        engines=tuple(engines),
        window_hours=window_hours,
        checked=checked,
    )


def summary_text(status: ProviderStatus) -> str:
    """Рядок для Telegram-алерту / логу."""
    if not status.checked:
        return f"➖ Двигуни: за {status.window_hours:.0f} год замало генерацій для вердикту"
    if status.ok:
        best = ", ".join(
            f"{e.engine} {e.failure_pct:.0f}% ({e.failures}/{e.attempts})"
            for e in status.engines
        )
        return f"✅ Двигуни ({status.window_hours:.0f} год): {best}"
    bad = "; ".join(
        f"{e.engine} — {e.failure_pct:.0f}% збоїв ({e.failures}/{e.attempts})"
        for e in status.engines if e.unhealthy
    )
    return f"❌ Двигуни ({status.window_hours:.0f} год): {bad}"
