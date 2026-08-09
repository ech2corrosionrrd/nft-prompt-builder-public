"""Тести алертів: поріг/повідомлення низького балансу + денний дайджест."""

import pytest

from services import alerts, payment_service, provider_status

A = "0x" + "ab" * 20


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")


def test_threshold_default_override_and_bad(monkeypatch):
    monkeypatch.delenv("STABILITY_LOW_BALANCE", raising=False)
    assert alerts.stability_threshold() == 100.0
    monkeypatch.setenv("STABILITY_LOW_BALANCE", "250")
    assert alerts.stability_threshold() == 250.0
    monkeypatch.setenv("STABILITY_LOW_BALANCE", "notanumber")
    assert alerts.stability_threshold() == 100.0  # некоректне → дефолт


def test_low_balance_messages_with_explicit_value(monkeypatch):
    monkeypatch.delenv("STABILITY_LOW_BALANCE", raising=False)  # поріг 100
    below = alerts.low_balance_messages(50)
    assert below and "Stability" in below[0] and "50" in below[0]
    assert alerts.low_balance_messages(150) == []     # вище порога — без алерту
    assert alerts.low_balance_messages(None) == []     # балансу нема — без алерту й без мережі


def test_low_balance_fetches_when_not_passed(monkeypatch):
    monkeypatch.delenv("STABILITY_LOW_BALANCE", raising=False)
    monkeypatch.setattr(provider_status, "stability_balance", lambda: 10.0)
    msgs = alerts.low_balance_messages()               # без аргументу → дістає з мережі
    assert msgs and "10" in msgs[0]


def test_digest_text_includes_stats_and_balance(monkeypatch):
    monkeypatch.setattr(provider_status, "stability_balance", lambda: 500.0)
    payment_service.complete_wallet_sign_in(A)
    payment_service.record_payment("t1", A, 100, 4.99)
    payment_service.deduct_credits(A, 4, engine="OpenAI DALL-E 3")
    txt = alerts.digest_text()
    assert "дайджест" in txt.lower()
    assert "4.99" in txt                  # дохід
    assert "500" in txt                   # баланс Stability
    assert "OpenAI DALL-E 3" in txt       # генерації за двигуном


def test_digest_includes_break_even_when_fixed_set(monkeypatch):
    monkeypatch.setattr(provider_status, "stability_balance", lambda: None)
    monkeypatch.setenv("FIXED_MONTHLY_USD", "25")
    payment_service.complete_wallet_sign_in(A)
    payment_service.record_payment("t1", A, 100, 4.99)
    payment_service.deduct_credits(A, 1, engine="Flux")
    assert "🎯" in alerts.digest_text()          # рядок беззбитковості присутній


def test_digest_no_break_even_when_self_host(monkeypatch):
    monkeypatch.setattr(provider_status, "stability_balance", lambda: None)
    monkeypatch.setenv("FIXED_MONTHLY_USD", "0")
    payment_service.complete_wallet_sign_in(A)
    payment_service.record_payment("t1", A, 100, 4.99)
    assert "🎯" not in alerts.digest_text()       # фікс=0 → без рядка


def test_quality_threshold_defaults(monkeypatch):
    monkeypatch.delenv("QUALITY_ALERT_MIN_RATING", raising=False)
    monkeypatch.delenv("QUALITY_ALERT_MIN_SAVE_EXPORT_PCT", raising=False)
    assert alerts.quality_min_rating() == 3.5
    assert alerts.quality_min_save_export_pct() == 30.0


def test_quality_alert_low_rating():
    qs = {"avg_curator_rating": 3.0}
    fn = {"curator_save_wallets": 1, "conversion_save_to_export_pct": 50.0}
    items = alerts.quality_alert_items(qs, fn, min_rating=3.5, min_save_export=30.0)
    assert len(items) == 1
    assert items[0]["code"] == "low_rating"


def test_quality_alert_low_save_export():
    qs = {"avg_curator_rating": 4.5}
    fn = {"curator_save_wallets": 2, "conversion_save_to_export_pct": 10.0}
    items = alerts.quality_alert_items(qs, fn, min_rating=3.5, min_save_export=30.0)
    assert len(items) == 1
    assert items[0]["code"] == "low_save_export"


def test_quality_alert_skips_when_no_saves():
    qs = {"avg_curator_rating": 4.0}
    fn = {"curator_save_wallets": 0, "conversion_save_to_export_pct": 0.0}
    assert alerts.quality_alert_items(qs, fn) == []
