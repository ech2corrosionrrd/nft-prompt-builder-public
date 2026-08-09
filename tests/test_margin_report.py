"""Тести оцінки валової маржі (services.margin_report)."""

import pytest

from services import margin_report, payment_service, provider_spend, stats
from services.ai_service import ENGINE_FLUX, ENGINE_STABILITY, ENGINE_GPT_IMAGE

A = "0x" + "ab" * 20


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(provider_spend, "DB_PATH", tmp_path / "provider_spend.db")


def _seed():
    payment_service.complete_wallet_sign_in(A)
    payment_service.record_payment("tx1", A, 100, 4.99)
    payment_service.deduct_credits(A, 4, engine=ENGINE_GPT_IMAGE, note="img")
    payment_service.deduct_credits(A, 1, engine="LLM", note="build")
    payment_service.deduct_credits(A, 1, engine=ENGINE_FLUX, note="flux")


def test_api_usd_per_op_known_and_default():
    assert margin_report.api_usd_per_op(ENGINE_FLUX) == 0.003
    assert margin_report.api_usd_per_op(ENGINE_STABILITY) == 0.030
    assert margin_report.api_usd_per_op("невідомий") == margin_report.DEFAULT_API_USD


def test_estimated_api_cost():
    gens = [
        {"engine": ENGINE_GPT_IMAGE, "count": 1, "credits_spent": 4},
        {"engine": "LLM", "count": 1, "credits_spent": 1},
    ]
    cost = margin_report.estimated_api_cost_usd(gens)
    assert cost == pytest.approx(0.042 + 0.0003, rel=1e-3)


def test_gross_margin_report_after_seed():
    _seed()
    r = margin_report.gross_margin_report()
    assert r["revenue_usd"] == 4.99
    assert r["credits_sold"] == 100
    assert r["credits_debited"] == 6
    assert r["avg_usd_per_credit"] == pytest.approx(0.0499, rel=1e-3)
    assert r["estimated_api_usd"] > 0
    assert r["gross_margin_pct"] is not None
    assert r["gross_margin_pct"] > 50
    assert r["stability_share_pct"] == 0.0
    assert len(r["by_engine_cost"]) == 3


def test_stability_share_warning_threshold():
    payment_service.complete_wallet_sign_in(A)
    payment_service.record_payment("tx2", A, 100, 4.99)
    for _ in range(8):
        payment_service.deduct_credits(A, 1, engine=ENGINE_STABILITY, note="s")
    payment_service.deduct_credits(A, 2, engine=ENGINE_FLUX, note="f")
    r = margin_report.gross_margin_report()
    assert r["stability_share_pct"] == pytest.approx(80.0, rel=1e-2)
    assert r["gross_margin_pct"] is not None
    assert r["gross_margin_pct"] < 60  # stability-heavy мікс тягне маржу вниз


def test_format_report_text_contains_margin():
    _seed()
    txt = margin_report.format_report_text()
    assert "Маржа" in txt
    assert "4.99" in txt


def test_generations_for_period_empty_without_debits():
    payment_service.complete_wallet_sign_in(A)
    assert margin_report.generations_for_period(7) == []
    assert margin_report.credits_debited_for_period(7) == 0
    r = margin_report.gross_margin_report(7)
    assert r["credits_debited"] == 0
    assert r["gross_margin_pct"] is None


def test_report_arpu_and_welcome_and_count():
    _seed()
    r = margin_report.gross_margin_report()
    assert r["payments_count"] == 1
    assert r["arpu_usd"] == pytest.approx(4.99, rel=1e-3)
    # complete_wallet_sign_in нараховує welcome (conftest WELCOME_REQUIRE_BALANCE=0)
    assert r["welcome_credits_net"] == stats.credits_by_kind().get("welcome", 0)
    assert r["welcome_credits_net"] > 0


def test_report_no_payments_arpu_none():
    payment_service.complete_wallet_sign_in(A)
    r = margin_report.gross_margin_report()
    assert r["payments_count"] == 0
    assert r["arpu_usd"] is None


def test_api_delta_with_actual_import():
    from datetime import datetime, timezone

    _seed()
    today = datetime.now(timezone.utc).date().isoformat()
    provider_spend.add_manual("openai", today, today, 1.50, note="тест")
    r = margin_report.gross_margin_report()
    assert r["has_actual_imports"] is True
    assert r["actual_api_usd"] == pytest.approx(1.50, rel=1e-3)
    assert r["api_delta_usd"] == pytest.approx(1.50 - r["estimated_api_usd"], rel=1e-3)
    assert r["actual_gross_margin_pct"] is not None


def test_api_delta_none_without_imports():
    _seed()
    r = margin_report.gross_margin_report()
    assert r["has_actual_imports"] is False
    assert r["api_delta_usd"] is None


def test_digest_can_include_margin(monkeypatch):
    from services import alerts, provider_status

    monkeypatch.setattr(provider_status, "stability_balance", lambda: None)
    _seed()
    txt = alerts.digest_text()
    assert "📈" in txt and "%" in txt


# ── Чиста маржа ───────────────────────────────────────────────────────────────

def test_net_margin_subtracts_fees_and_fixed(monkeypatch):
    monkeypatch.setenv("PAYMENT_FEE_PCT", "1.0")
    monkeypatch.setenv("FX_FEE_PCT", "2.0")
    monkeypatch.setenv("FIXED_MONTHLY_USD", "30.0")
    _seed()
    nm = margin_report.net_margin_report(30)  # 30д → фікс = 30×30/30 = $30
    assert nm["payment_fee_usd"] == round(4.99 * 0.01, 2)
    assert nm["fx_fee_usd"] == round(4.99 * 0.02, 2)
    assert nm["fixed_cost_usd"] == 30.0
    # внутрішня узгодженість розкладу
    expected = round(nm["revenue_usd"] - nm["api_cost_usd"]
                     - nm["payment_fee_usd"] - nm["fx_fee_usd"] - nm["fixed_cost_usd"], 2)
    assert nm["net_profit_usd"] == expected
    assert nm["net_margin_pct"] < 0  # фікс $30 >> виторг $4.99 → збиток


def test_net_margin_zero_fees_is_revenue_minus_api(monkeypatch):
    for k in ("PAYMENT_FEE_PCT", "FX_FEE_PCT", "FIXED_MONTHLY_USD"):
        monkeypatch.setenv(k, "0")
    _seed()
    nm = margin_report.net_margin_report(30)
    assert nm["payment_fee_usd"] == 0 and nm["fx_fee_usd"] == 0 and nm["fixed_cost_usd"] == 0
    assert nm["net_profit_usd"] == round(nm["revenue_usd"] - nm["api_cost_usd"], 2)


def test_net_margin_no_revenue_is_none(monkeypatch):
    for k in ("PAYMENT_FEE_PCT", "FX_FEE_PCT", "FIXED_MONTHLY_USD"):
        monkeypatch.delenv(k, raising=False)
    payment_service.complete_wallet_sign_in(A)  # без оплат
    nm = margin_report.net_margin_report()
    assert nm["revenue_usd"] == 0 and nm["net_margin_pct"] is None


# ── Беззбитковість ────────────────────────────────────────────────────────────

def test_break_even_summary(monkeypatch):
    monkeypatch.setenv("FIXED_MONTHLY_USD", "25")
    monkeypatch.setenv("PAYMENT_FEE_PCT", "1.0")
    monkeypatch.setenv("FX_FEE_PCT", "2.0")
    _seed()  # 1 оплата цього місяця + кілька списань
    be = margin_report.break_even_summary()
    assert 0 < be["contribution_usd"] < 4.99           # є витрати → внесок < ціни
    import math
    assert be["break_even_count"] == math.ceil(25 / be["contribution_usd"])
    assert be["payments_this_month"] == 1
    assert be["remaining"] == max(0, be["break_even_count"] - 1)
    assert be["covered_pct"] == round(100 * 1 / be["break_even_count"])


def test_break_even_zero_fixed_self_host(monkeypatch):
    monkeypatch.setenv("FIXED_MONTHLY_USD", "0")
    _seed()
    be = margin_report.break_even_summary()
    assert be["break_even_count"] == 0 and be["remaining"] == 0
    assert be["covered_pct"] is None
