"""Тести білінгу: SQLite-облік кредитів, тарифи, Helio-парсер (без мережі)."""

import importlib.util
import sys
from pathlib import Path

import pytest

from services import payment_service
from services.payment_service import CREDIT_COSTS, PACKAGES, WELCOME_CREDITS

ROOT = Path(__file__).resolve().parent.parent


def _load_grant_credits():
    """Завантажує scripts/grant_credits.py як модуль (scripts/ — не пакет)."""
    spec = importlib.util.spec_from_file_location(
        "grant_credits", ROOT / "scripts" / "grant_credits.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["grant_credits"] = mod
    spec.loader.exec_module(mod)
    return mod

EVM = "0x" + "ab12" * 10
SOLANA = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Кожен тест — зі своєю чистою базою."""
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")


# ── Гаманці та вітальні кредити ───────────────────────────────────────────────

def test_credit_cost_draft_and_final():
    from services.ai_service import ENGINE_FLUX, ENGINE_GPT_IMAGE

    assert payment_service.credit_cost(ENGINE_FLUX) == 1
    assert payment_service.credit_cost(ENGINE_FLUX, final=True) == 2
    assert payment_service.credit_cost(ENGINE_GPT_IMAGE) == 4
    assert payment_service.credit_cost(ENGINE_GPT_IMAGE, final=True) == 8
    # Невідомий/застарілий двигун (вкл. вилучений DALL-E 3): 1 (draft) / 2 (final).
    assert payment_service.credit_cost("???") == 1
    assert payment_service.credit_cost("???", final=True) == 2
    assert payment_service.credit_cost("OpenAI DALL-E 3") == 1


def test_normalize_wallet():
    assert payment_service.normalize_wallet(f"  {EVM.upper().replace('0X', '0x')} ") == EVM
    assert payment_service.normalize_wallet(SOLANA) == SOLANA  # регістр значущий
    for bad in ("", "0x123", "0x" + "g" * 40, "too-short"):
        with pytest.raises(ValueError):
            payment_service.normalize_wallet(bad)


def test_new_wallet_gets_welcome_credits_after_sign_in():
    is_new, balance = payment_service.complete_wallet_sign_in(EVM)
    assert is_new and balance == WELCOME_CREDITS
    assert payment_service.is_wallet_verified(EVM)
    assert payment_service.get_balance(EVM) == WELCOME_CREDITS
    is_new, balance = payment_service.complete_wallet_sign_in(EVM)
    assert not is_new and balance == WELCOME_CREDITS


def test_ensure_user_without_welcome():
    is_new, balance = payment_service.ensure_user(EVM)
    assert is_new and balance == 0
    assert not payment_service.is_wallet_verified(EVM)


def test_unknown_wallet_balance_zero():
    assert payment_service.get_balance(EVM) == 0


def test_deduct_requires_verified_wallet():
    payment_service.ensure_user(EVM)
    payment_service.add_credits(EVM, 10)
    assert not payment_service.deduct_credits(EVM, 1)
    payment_service.complete_wallet_sign_in(EVM)
    assert payment_service.deduct_credits(EVM, 1)


# ── Нарахування та списання ───────────────────────────────────────────────────

def test_add_and_deduct_credits():
    payment_service.complete_wallet_sign_in(EVM)
    assert payment_service.add_credits(EVM, 100) == WELCOME_CREDITS + 100
    assert payment_service.deduct_credits(EVM, 4)
    assert payment_service.get_balance(EVM) == WELCOME_CREDITS + 96


def test_deduct_insufficient_changes_nothing():
    payment_service.complete_wallet_sign_in(EVM)
    assert not payment_service.deduct_credits(EVM, WELCOME_CREDITS + 1)
    assert payment_service.get_balance(EVM) == WELCOME_CREDITS


def test_amounts_must_be_positive():
    payment_service.complete_wallet_sign_in(EVM)
    with pytest.raises(ValueError):
        payment_service.add_credits(EVM, 0)
    with pytest.raises(ValueError):
        payment_service.deduct_credits(EVM, -1)


# ── Ручний грант кредитів (адмін) ─────────────────────────────────────────────

def test_grant_credits_adds_and_logs():
    assert payment_service.grant_credits(EVM, 100) == 100
    assert payment_service.get_balance(EVM) == 100
    txs = payment_service.list_transactions(EVM)
    grants = [t for t in txs if t["kind"] == "grant"]
    assert len(grants) == 1 and grants[0]["credits"] == 100


def test_grant_credits_not_idempotent_stacks():
    """Кожен грант додає (на відміну від record_payment) — навмисна разова дія."""
    payment_service.grant_credits(EVM, 100)
    payment_service.grant_credits(EVM, 50, note="бонус")
    assert payment_service.get_balance(EVM) == 150


def test_grant_credits_works_for_solana():
    assert payment_service.grant_credits(SOLANA, 30) == 30
    assert payment_service.get_balance(SOLANA) == 30


def test_grant_credits_rejects_nonpositive():
    for bad in (0, -5):
        with pytest.raises(ValueError):
            payment_service.grant_credits(EVM, bad)
    assert payment_service.get_balance(EVM) == 0


def test_grant_credits_rejects_invalid_wallet():
    with pytest.raises(ValueError):
        payment_service.grant_credits("not-a-wallet", 10)


def test_grant_credits_does_not_verify_wallet():
    """Грант не робить гаманець verified — витрата все одно потребує входу підписом."""
    payment_service.grant_credits(EVM, 100)
    assert not payment_service.is_wallet_verified(EVM)
    assert not payment_service.deduct_credits(EVM, 1)  # без входу — не списати


def test_grant_credits_cli(monkeypatch, capsys):
    gc = _load_grant_credits()
    monkeypatch.setattr(sys, "argv", ["grant_credits.py", "--wallet", EVM, "--amount", "100"])
    assert gc.main() == 0
    assert payment_service.get_balance(EVM) == 100
    out = capsys.readouterr().out
    assert "100" in out and "підписом" in out  # баланс + попередження про неверифікований


def test_grant_credits_cli_invalid_wallet(monkeypatch, capsys):
    gc = _load_grant_credits()
    monkeypatch.setattr(sys, "argv", ["grant_credits.py", "--wallet", "bad", "--amount", "10"])
    assert gc.main() == 1
    assert "❌" in capsys.readouterr().out


# ── Платежі: ідемпотентність транзакцій ───────────────────────────────────────

def test_record_payment_once():
    assert payment_service.record_payment("tx-1", EVM, 100, 4.99)
    assert payment_service.get_balance(EVM) == 100
    assert not payment_service.record_payment("tx-1", EVM, 100, 4.99)
    assert payment_service.get_balance(EVM) == 100


def test_record_payment_notifies_once(monkeypatch):
    """Сповіщення в Telegram — рівно раз на платіж (не на дублікаті)."""
    from services import notify

    sent = []
    monkeypatch.setattr(notify, "send_telegram", lambda text: sent.append(text))

    assert payment_service.record_payment("tx-n", EVM, 100, 4.99)
    assert len(sent) == 1
    assert "100" in sent[0] and "4.99" in sent[0]
    # Повтор тієї ж транзакції не зараховується — і не сповіщає.
    assert not payment_service.record_payment("tx-n", EVM, 100, 4.99)
    assert len(sent) == 1


def test_simulate_payment(monkeypatch):
    monkeypatch.setenv("ENABLE_SIM_PAYMENTS", "1")
    monkeypatch.setenv("APP_ENV", "development")
    payment_service.complete_wallet_sign_in(EVM)
    balance = payment_service.simulate_payment(EVM, "creator")
    assert balance == WELCOME_CREDITS + PACKAGES["creator"]["credits"]


def test_simulate_payment_blocked_in_production(monkeypatch):
    monkeypatch.setenv("ENABLE_SIM_PAYMENTS", "1")
    monkeypatch.setenv("APP_ENV", "production")
    payment_service.complete_wallet_sign_in(EVM)
    with pytest.raises(RuntimeError):
        payment_service.simulate_payment(EVM, "creator")


# ── Тарифи та вага двигунів ───────────────────────────────────────────────────

def test_packages_match_financial_model():
    assert PACKAGES["start"]["usd"] == 4.99 and PACKAGES["start"]["credits"] == 100
    assert PACKAGES["creator"]["usd"] == 14.99 and PACKAGES["creator"]["credits"] == 400
    assert PACKAGES["pro"]["usd"] == 29.99 and PACKAGES["pro"]["credits"] == 1000
    assert PACKAGES["creator"]["recommended"]
    per_credit = [p["usd"] / p["credits"] for p in PACKAGES.values()]
    assert per_credit == sorted(per_credit, reverse=True)


def test_credit_cost_by_engine():
    from services import ai_service
    assert payment_service.credit_cost(ai_service.ENGINE_GPT_IMAGE) == 4
    assert payment_service.credit_cost(ai_service.ENGINE_STABILITY) == 1
    assert payment_service.credit_cost(ai_service.ENGINE_FLUX) == 1
    assert payment_service.credit_cost("невідомий") == 1
    assert set(CREDIT_COSTS) == set(ai_service.ENGINES)


# ── Helio: парсер відповіді (без мережі) ──────────────────────────────────────

def test_extract_payments_tolerant_formats():
    raw = [
        {"id": "tx-a", "senderPublicKey": EVM, "status": "SUCCESS"},
        {"transactionId": "tx-b", "meta": {"senderPK": SOLANA}, "status": "PAID"},
        {"id": "tx-c", "status": "SUCCESS"},
        {"senderPublicKey": EVM, "status": "SUCCESS"},
        "not-a-dict",
    ]
    payments = payment_service.extract_payments(raw)
    assert payments == [
        {"tx_id": "tx-a", "wallet": EVM, "paylink": ""},
        {"tx_id": "tx-b", "wallet": SOLANA, "paylink": ""},
    ]


def test_extract_payments_captures_paylink():
    raw = [
        {"id": "tx-a", "from": EVM, "status": "SUCCESS", "paymentRequestId": "plink-pro"},
        {"id": "tx-b", "from": SOLANA, "status": "SUCCESS", "paylinkId": "plink-start"},
    ]
    payments = payment_service.extract_payments(raw)
    assert payments == [
        {"tx_id": "tx-a", "wallet": EVM, "paylink": "plink-pro"},
        {"tx_id": "tx-b", "wallet": SOLANA, "paylink": "plink-start"},
    ]


def test_extract_payments_reads_status_from_meta():
    """Webhook / paylink-transactions часто несуть SUCCESS лише в meta."""
    raw = [
        {
            "id": "tx-webhook",
            "paylinkId": "plink-start",
            "meta": {
                "transactionStatus": "SUCCESS",
                "senderPK": SOLANA,
            },
        },
    ]
    assert payment_service.extract_payments(raw) == [
        {"tx_id": "tx-webhook", "wallet": SOLANA, "paylink": "plink-start"},
    ]


def test_extract_payments_skips_unsuccessful_status():
    raw = [
        {"id": "tx-ok", "senderPublicKey": EVM, "status": "SUCCESS"},
        {"id": "tx-pending", "senderPublicKey": EVM, "status": "PENDING"},
        {"id": "tx-failed", "senderPublicKey": EVM, "transactionStatus": "FAILED"},
        {"id": "tx-nostatus", "senderPublicKey": SOLANA},
    ]
    payments = payment_service.extract_payments(raw)
    assert payments == [{"tx_id": "tx-ok", "wallet": EVM, "paylink": ""}]


def test_helio_paylink_url(monkeypatch):
    monkeypatch.delenv("HELIO_PAYLINK_START", raising=False)
    assert payment_service.helio_paylink_url("start") is None
    monkeypatch.setenv("HELIO_PAYLINK_START", "abc123")
    assert payment_service.helio_paylink_url("start") == "https://app.hel.io/pay/abc123"


def test_sanitize_paylink_typo_t_between_hex(monkeypatch):
    """Поширена опечатка T замість 0 у hex paylink (BUG-001)."""
    raw = "6a2d2ab121ac01T0b1306435"
    assert payment_service.sanitize_paylink_id(raw) == "6a2d2ab121ac010b1306435"
    monkeypatch.setenv("HELIO_PAYLINK_PRO", raw)
    assert payment_service.helio_paylink_url("pro") == "https://app.hel.io/pay/6a2d2ab121ac010b1306435"


def test_helio_paylink_url_rejects_invalid_hex(monkeypatch):
    monkeypatch.setenv("HELIO_PAYLINK_START", "not-hex-xyz!")
    assert payment_service.helio_paylink_url("start") is None


def test_sync_requires_keys(monkeypatch):
    monkeypatch.delenv("HELIO_API_KEY", raising=False)
    monkeypatch.delenv("HELIO_API_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        payment_service.sync_helio_payments()


def test_sync_credits_correct_package_despite_unfiltered_export(monkeypatch):
    """Експорт Helio повертає один платіж під будь-яким paylinkId у запиті.

    Sync має нарахувати пакет за реальним paymentRequestId платежу (тут — pro),
    а не за першим у переліку (start) лише тому, що його запитали першим.
    """
    monkeypatch.setenv("HELIO_API_KEY", "k")
    monkeypatch.setenv("HELIO_API_SECRET", "s")
    monkeypatch.setenv("HELIO_PAYLINK_START", "plink-start")
    monkeypatch.setenv("HELIO_PAYLINK_CREATOR", "plink-creator")
    monkeypatch.setenv("HELIO_PAYLINK_PRO", "plink-pro")

    # Той самий запис повертається для будь-якого запитаного paylink_id.
    record = {"id": "tx-pro", "from": EVM, "status": "SUCCESS", "paymentRequestId": "plink-pro"}
    monkeypatch.setattr(
        payment_service, "fetch_helio_payments",
        lambda paylink_id, api_key, secret: [record],
    )

    new_tx, credited = payment_service.sync_helio_payments()
    assert new_tx == 1
    assert credited == PACKAGES["pro"]["credits"]
    assert payment_service.get_balance(EVM) == PACKAGES["pro"]["credits"]


# ── Звіряння без винятків (фоновий цикл / cron) ───────────────────────────────

def test_reconcile_safe_no_keys_returns_zero(monkeypatch):
    monkeypatch.delenv("HELIO_API_KEY", raising=False)
    monkeypatch.delenv("HELIO_API_SECRET", raising=False)
    # Не кидає попри відсутність ключів (sync_helio_payments кинув би RuntimeError).
    assert payment_service.reconcile_payments_safe() == (0, 0)


def test_reconcile_safe_swallows_sync_errors(monkeypatch):
    monkeypatch.setenv("HELIO_API_KEY", "k")
    monkeypatch.setenv("HELIO_API_SECRET", "s")

    def _boom(target_wallet=None):
        raise RuntimeError("Helio 503")

    monkeypatch.setattr(payment_service, "sync_helio_payments", _boom)
    assert payment_service.reconcile_payments_safe() == (0, 0)


def test_reconcile_safe_passes_through_result(monkeypatch):
    monkeypatch.setenv("HELIO_API_KEY", "k")
    monkeypatch.setenv("HELIO_API_SECRET", "s")
    monkeypatch.setattr(payment_service, "sync_helio_payments", lambda target_wallet=None: (2, 500))
    assert payment_service.reconcile_payments_safe() == (2, 500)


# ── Реферальна петля (G3.3) ───────────────────────────────────────────────────

REFERRER = "0x" + "cd34" * 10


def test_referral_rewards_referrer_on_first_payment(monkeypatch):
    monkeypatch.setenv("REFERRAL_BONUS_CREDITS", "50")
    assert payment_service.record_referral(EVM, REFERRER) is True
    # До оплати реферер бонусу не має (анти-Sybil: лише за оплату).
    assert payment_service.get_balance(REFERRER) == 0
    payment_service.record_payment("tx-1", EVM, 100, 4.99)
    assert payment_service.get_balance(REFERRER) == 50


def test_referral_self_referral_rejected():
    assert payment_service.record_referral(EVM, EVM) is False


def test_referral_not_attached_if_invitee_already_paid(monkeypatch):
    monkeypatch.setenv("REFERRAL_BONUS_CREDITS", "50")
    payment_service.record_payment("tx-prior", EVM, 100, 4.99)
    # Не можна заднім числом привласнити вже-платіжного клієнта.
    assert payment_service.record_referral(EVM, REFERRER) is False
    payment_service.record_payment("tx-2", EVM, 100, 4.99)
    assert payment_service.get_balance(REFERRER) == 0


def test_referral_rewarded_only_once(monkeypatch):
    monkeypatch.setenv("REFERRAL_BONUS_CREDITS", "50")
    payment_service.record_referral(EVM, REFERRER)
    payment_service.record_payment("tx-1", EVM, 100, 4.99)
    payment_service.record_payment("tx-2", EVM, 100, 4.99)  # друга оплата
    assert payment_service.get_balance(REFERRER) == 50  # бонус рівно один


def test_referral_first_referrer_wins():
    assert payment_service.record_referral(EVM, REFERRER) is True
    other = "0x" + "ef56" * 10
    assert payment_service.record_referral(EVM, other) is False


def test_referral_bonus_zero_disables(monkeypatch):
    monkeypatch.setenv("REFERRAL_BONUS_CREDITS", "0")
    payment_service.record_referral(EVM, REFERRER)
    assert payment_service.reward_referral(EVM) is False
    payment_service.record_payment("tx-1", EVM, 100, 4.99)
    assert payment_service.get_balance(REFERRER) == 0


def test_referral_invalid_addresses_rejected():
    assert payment_service.record_referral("not-a-wallet", REFERRER) is False
    assert payment_service.record_referral(EVM, "bad") is False


# ── Реферал-коди (privacy-петля shareable-сторінки) ───────────────────────────

def test_referral_code_roundtrip_and_privacy(monkeypatch):
    monkeypatch.setenv("AUTH_SESSION_SECRET", "secret-x")
    code = payment_service.referral_code_for(REFERRER)
    assert code and payment_service.resolve_referral_code(code) == REFERRER.lower()
    # privacy: з коду гаманець не вивести — адреси в коді немає
    assert REFERRER.lower() not in code and REFERRER[2:].lower() not in code


def test_referral_code_deterministic(monkeypatch):
    monkeypatch.setenv("AUTH_SESSION_SECRET", "secret-x")
    assert payment_service.referral_code_for(REFERRER) == payment_service.referral_code_for(REFERRER)


def test_referral_code_fail_closed_without_secret(monkeypatch):
    monkeypatch.delenv("AUTH_SESSION_SECRET", raising=False)
    assert payment_service.referral_code_for(REFERRER) == ""


def test_resolve_referrer_code_wallet_and_garbage(monkeypatch):
    monkeypatch.setenv("AUTH_SESSION_SECRET", "secret-x")
    code = payment_service.referral_code_for(REFERRER)
    assert payment_service.resolve_referrer(code) == REFERRER.lower()      # код → гаманець
    assert payment_service.resolve_referrer(REFERRER) == REFERRER.lower()  # пряма адреса (сумісність)
    assert payment_service.resolve_referrer("garbage") == ""               # не код і не адреса


def test_resolve_referrer_into_record_referral(monkeypatch):
    """Повна петля: код зі share-сторінки → resolve → record_referral прив'язує."""
    monkeypatch.setenv("AUTH_SESSION_SECRET", "secret-x")
    code = payment_service.referral_code_for(REFERRER)
    referrer = payment_service.resolve_referrer(code)
    assert payment_service.record_referral(EVM, referrer) is True
