from services import billing_guard, payment_service

EVM = "0x1234567890123456789012345678901234567890"


def test_enforcement_off_by_default(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("BILLING_ENFORCE_LLM", "0")
    ok, err = billing_guard.try_reserve(None, 1, engine="LLM", note="t")
    assert ok and err is None


def test_enforcement_production_requires_wallet(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    ok, err = billing_guard.try_reserve(None, 1, engine="LLM", note="t")
    assert not ok and err == "wallet"


EVM = "0x1234567890123456789012345678901234567890"
EVM_BILL = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"


def test_reserve_and_refund(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("WELCOME_REQUIRE_BALANCE", "0")
    payment_service.complete_wallet_sign_in(EVM_BILL)
    payment_service.add_credits(EVM_BILL, 5)
    before = payment_service.get_balance(EVM_BILL)
    ok, err = billing_guard.try_reserve(EVM_BILL, 2, engine="LLM", note="test")
    assert ok and err is None
    assert payment_service.get_balance(EVM_BILL) == before - 2
    billing_guard.refund(EVM_BILL, 2, engine="LLM", note="refund")
    assert payment_service.get_balance(EVM_BILL) == before
