"""Тести quality_metrics та quality_summary (D4)."""

import pytest

from services import payment_service, quality_metrics, stats

A = "0x" + "ab" * 20


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")


def _seed_generator():
    payment_service.complete_wallet_sign_in(A)
    payment_service.deduct_credits(A, 4, engine="Flux.1 (Replicate)", note="img")


def test_build_curator_save_payload():
    items = [
        {"curator_rating": 5, "engine": "Flux.1 (Replicate)"},
        {"curator_rating": 3, "engine": "OpenAI DALL-E 3"},
        {"curator_rating": 0, "engine": "OpenAI DALL-E 3"},
    ]
    p = quality_metrics.build_curator_save_payload(items)
    assert p["items"] == 3
    assert p["avg_rating"] == 4.0
    assert p["engines"]["Flux.1"] == 1
    assert p["engines"]["OpenAI DALL-E 3"] == 2


def test_quality_summary_aggregates_payloads():
    _seed_generator()
    quality_metrics.record_curator_save(A, [
        {"curator_rating": 5, "engine": "Flux.1 (Replicate)"},
        {"curator_rating": 4, "engine": "Flux.1 (Replicate)"},
    ])
    quality_metrics.record_curator_save(A, [
        {"curator_rating": 3, "engine": "OpenAI DALL-E 3"},
    ])
    qs = stats.quality_summary(30)
    assert qs["save_events"] == 2
    assert qs["total_items_saved"] == 3
    assert qs["avg_curator_rating"] == 4.0  # (4.5*2 + 3*1) / 3
    assert qs["top_engine_by_saves"] == "Flux.1"


def test_funnel_save_conversions():
    _seed_generator()
    quality_metrics.record_curator_save(A, [{"curator_rating": 4, "engine": "Flux.1"}])
    payment_service.record_funnel_event(A, "export")
    fn = stats.funnel(30)
    assert fn["curator_save_wallets"] == 1
    assert fn["conversion_generate_to_save_pct"] == 100.0
    assert fn["conversion_save_to_export_pct"] == 100.0


def test_record_batch_generate_payload():
    payment_service.complete_wallet_sign_in(A)
    quality_metrics.record_batch_generate(A, 5, "Flux.1 (Replicate)")
    with payment_service._connect() as c:
        row = c.execute(
            "SELECT event, payload FROM funnel_events WHERE wallet_address = ?", (A.lower(),),
        ).fetchone()
    assert row[0] == "generate"
    assert "Flux.1" in row[1]


def test_regenerate_rate_and_save_without_regen():
    payment_service.complete_wallet_sign_in(A)
    quality_metrics.record_batch_generate(A, 3, "Flux.1")
    quality_metrics.record_regenerate(A, 0, "Flux.1")
    quality_metrics.record_curator_save(A, [{"curator_rating": 5, "engine": "Flux.1"}])
    qs = stats.quality_summary(30)
    assert qs["generate_events"] == 1
    assert qs["regenerate_events"] == 1
    assert qs["regenerate_rate_pct"] == 100.0
    assert qs["save_without_regen_pct"] == 0.0


def test_save_without_regen_clean_path():
    payment_service.complete_wallet_sign_in(A)
    quality_metrics.record_batch_generate(A, 2, "Flux.1")
    quality_metrics.record_curator_save(A, [{"curator_rating": 4, "engine": "Flux.1"}])
    qs = stats.quality_summary(30)
    assert qs["save_without_regen_pct"] == 100.0
    assert qs["regenerate_rate_pct"] == 0.0


def test_median_export_minutes():
    payment_service.complete_wallet_sign_in(A)
    quality_metrics.record_batch_generate(A, 1, "Flux.1")
    payment_service.record_funnel_event(A, "export")
    qs = stats.quality_summary(30)
    assert qs["median_export_minutes"] is not None
    assert qs["median_export_minutes"] >= 0


def test_median_export_uses_nearest_generate_not_first():
    """Регресія крос-сесійного спотворення: export рахується від ОСТАННЬОЇ генерації
    перед ним, не від ПЕРШОЇ. Стара формула: оператор генерував давно → export зранку =
    746хв (спотворення до 387); нова: останній generate за 3хв до export."""
    import sqlite3
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    payment_service.complete_wallet_sign_in(A)
    con = sqlite3.connect(payment_service.DB_PATH)
    for ev, ts in [
        ("generate", now - timedelta(minutes=600)),  # давня сесія
        ("generate", now - timedelta(minutes=3)),     # свіжа генерація перед export
        ("export", now),
    ]:
        con.execute(
            "INSERT INTO funnel_events(wallet_address, event, created_at) VALUES(?,?,?)",
            (A, ev, ts.isoformat()),
        )
    con.commit()
    con.close()
    qs = stats.quality_summary(30)
    assert qs["median_export_minutes"] < 15                      # не ~600 (стара формула)
    assert qs["median_export_minutes"] == pytest.approx(3, abs=1)  # від найближчого generate


def test_generate_source_default_pipeline():
    """Без явного source подія мітиться pipeline (зворотна сумісність викликів)."""
    payment_service.complete_wallet_sign_in(A)
    quality_metrics.record_batch_generate(A, 3, "Flux.1")
    with payment_service._connect() as c:
        payload = c.execute(
            "SELECT payload FROM funnel_events WHERE wallet_address = ?", (A.lower(),),
        ).fetchone()[0]
    assert '"source": "pipeline"' in payload
    assert '"style_bible": false' in payload


def test_generate_source_invalid_normalized_to_pipeline():
    payment_service.complete_wallet_sign_in(A)
    quality_metrics.record_batch_generate(A, 1, "Flux.1", source="garbage")
    qs = stats.quality_summary(30)
    assert qs["generate_source_images"]["pipeline"] == 1
    assert qs["generate_source_images"]["classic"] == 0


def test_classic_and_style_bible_shares():
    payment_service.complete_wallet_sign_in(A)
    quality_metrics.record_batch_generate(A, 6, "gpt-image-1", source="classic")
    quality_metrics.record_batch_generate(A, 4, "Flux.1", source="pipeline", style_bible=True)
    qs = stats.quality_summary(30)
    src = qs["generate_source_images"]
    assert src == {"pipeline": 4, "classic": 6, "untracked": 0}
    assert qs["classic_share_pct"] == 60.0          # 6 / (6+4)
    assert qs["style_bible_images"] == 4
    assert qs["style_bible_share_pct"] == 40.0       # 4 / 10


def test_legacy_generate_event_untracked():
    """Подія без поля source (legacy) → untracked, не псує частку."""
    payment_service.complete_wallet_sign_in(A)
    payment_service.record_funnel_event(A, "generate", {"count": 5, "engine": "Flux.1"})
    quality_metrics.record_batch_generate(A, 5, "gpt-image-1", source="classic")
    qs = stats.quality_summary(30)
    assert qs["generate_source_images"]["untracked"] == 5
    assert qs["classic_share_pct"] == 100.0          # лише tracked рахується


def test_shares_none_when_no_tracked():
    payment_service.complete_wallet_sign_in(A)
    payment_service.record_funnel_event(A, "generate", {"count": 2, "engine": "Flux.1"})
    qs = stats.quality_summary(30)
    assert qs["classic_share_pct"] is None
    assert qs["style_bible_share_pct"] is None
