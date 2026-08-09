"""Тести імпорту витрат провайдерів (services.provider_spend)."""

import pytest

from services import margin_report, payment_service, provider_spend

A = "0x" + "ab" * 20

GENERIC_CSV = """provider,period_start,period_end,amount_usd,note
openai,2026-06-01,2026-06-01,1.50,day1
openai,2026-06-02,2026-06-02,2.25,day2
replicate,2026-06-01,2026-06-30,3.00,june
"""

OPENAI_DAILY_CSV = """date,cost
2026-06-10,0.40
2026-06-10,0.10
2026-06-11,1.00
"""

STABILITY_CSV = """date,credits_used
2026-06-05,100
2026-06-06,50
"""


@pytest.fixture(autouse=True)
def tmp_dbs(tmp_path, monkeypatch):
    monkeypatch.setattr(provider_spend, "DB_PATH", tmp_path / "provider_spend.db")
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("STABILITY_USD_PER_CREDIT", "0.01")


def test_parse_generic_csv():
    rows = provider_spend.parse_csv(GENERIC_CSV)
    assert len(rows) == 3
    assert sum(r.amount_usd for r in rows) == pytest.approx(6.75)


def test_import_and_total():
    saved, _ = provider_spend.import_csv_text(GENERIC_CSV)
    assert saved == 3
    assert provider_spend.total_usd() == pytest.approx(6.75)
    by = {r["provider"]: r["amount_usd"] for r in provider_spend.by_provider()}
    assert by["openai"] == pytest.approx(3.75)
    assert by["replicate"] == pytest.approx(3.0)


def test_openai_daily_aggregate():
    saved, rows = provider_spend.import_csv_text(OPENAI_DAILY_CSV, "openai")
    assert saved == 2
    assert {r.period_start for r in rows} == {"2026-06-10", "2026-06-11"}
    june10 = next(r for r in rows if r.period_start == "2026-06-10")
    assert june10.amount_usd == pytest.approx(0.50)


def test_stability_credits_to_usd():
    saved, rows = provider_spend.import_csv_text(STABILITY_CSV, "stability")
    assert saved == 2
    assert provider_spend.total_usd() == pytest.approx(1.50)  # 150 credits × 0.01


def test_manual_add():
    provider_spend.add_manual("anthropic", "2026-05-01", "2026-05-31", 9.99, "травень")
    assert provider_spend.total_usd() == pytest.approx(9.99)
    imports = provider_spend.list_imports()
    assert imports[0]["source"] == "manual"


def test_upsert_replaces_same_key():
    provider_spend.add_manual("openai", "2026-06-01", "2026-06-01", 1.0)
    provider_spend.add_manual("openai", "2026-06-01", "2026-06-01", 2.0)
    assert provider_spend.total_usd() == pytest.approx(2.0)


def test_margin_report_with_actual_imports():
    payment_service.complete_wallet_sign_in(A)
    payment_service.record_payment("tx1", A, 100, 4.99)
    payment_service.deduct_credits(A, 10, engine="LLM", note="t")
    provider_spend.add_manual("openai", "2026-06-01", "2099-12-31", 0.50, "test")
    r = margin_report.gross_margin_report()
    assert r["has_actual_imports"] is True
    assert r["actual_api_usd"] == pytest.approx(0.50)
    assert r["actual_gross_margin_pct"] is not None


def test_fetch_openai_costs_mock(monkeypatch):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {
                        "start_time": 1717200000,
                        "results": [{"amount": {"value": 1.23, "currency": "usd"}}],
                    }
                ],
                "has_more": False,
            }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers=None, params=None):
            return FakeResp()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(provider_spend.httpx, "Client", FakeClient)
    saved, rows, err = provider_spend.fetch_openai_costs(7)
    assert err is None
    assert saved == 1
    assert rows[0].amount_usd == pytest.approx(1.23)
    assert rows[0].source == "openai_api"
