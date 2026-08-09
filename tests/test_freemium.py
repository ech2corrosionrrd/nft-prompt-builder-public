"""B3 — тести денного freemium-ліміту (ПЛАН_ЗАПОЗИЧЕНЬ.md).

Ізоляція через тимчасову БД (як test_payments). Перевіряємо: вимкнено за
замовчуванням, стеля/блок, скидання за добу (UTC), звільнення платників,
fail-open при збої БД.
"""

import pytest

from services import freemium, payment_service

EVM = "0x" + "ab12" * 10
EVM2 = "0x" + "cd34" * 10


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Кожен тест — зі своєю чистою базою."""
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")


# ── Вимкнено за замовчуванням ─────────────────────────────────────────────────

def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FREEMIUM_DAILY_LIMIT", raising=False)
    assert freemium.daily_limit() == 0
    allowed, remaining = freemium.check_available(EVM)
    assert allowed and remaining is None
    # record — no-op, лічильник не зростає
    freemium.record_generation(EVM)
    assert freemium.usage_today(EVM) == 0


def test_invalid_limit_treated_as_disabled(monkeypatch):
    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "не-число")
    assert freemium.daily_limit() == 0


# ── Стеля / блокування ────────────────────────────────────────────────────────

def test_counts_and_blocks_at_limit(monkeypatch):
    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "3")
    for i in range(3):
        allowed, remaining = freemium.check_available(EVM)
        assert allowed
        assert remaining == 3 - i
        freemium.record_generation(EVM)
    # 4-та — заблоковано
    allowed, remaining = freemium.check_available(EVM)
    assert not allowed and remaining == 0
    assert freemium.usage_today(EVM) == 3


def test_release_decrements_floor_zero(monkeypatch):
    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "5")
    freemium.record_generation(EVM)
    freemium.record_generation(EVM)
    assert freemium.usage_today(EVM) == 2
    freemium.release_generation(EVM)
    assert freemium.usage_today(EVM) == 1
    # підлога 0 — більше релізів не йде в мінус
    freemium.release_generation(EVM)
    freemium.release_generation(EVM)
    assert freemium.usage_today(EVM) == 0


def test_release_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("FREEMIUM_DAILY_LIMIT", raising=False)
    freemium.release_generation(EVM)  # не падає, нічого не робить
    assert freemium.usage_today(EVM) == 0


def test_limit_is_per_wallet(monkeypatch):
    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "1")
    freemium.record_generation(EVM)
    assert not freemium.check_available(EVM)[0]
    # інший гаманець має власний лічильник
    assert freemium.check_available(EVM2)[0]


# ── Скидання за добу (UTC) ────────────────────────────────────────────────────

def test_resets_next_utc_day(monkeypatch):
    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "1")
    monkeypatch.setattr(freemium, "_today", lambda: "2026-06-18")
    freemium.record_generation(EVM)
    assert not freemium.check_available(EVM)[0]
    # наступна доба — лічильник чистий
    monkeypatch.setattr(freemium, "_today", lambda: "2026-06-19")
    allowed, remaining = freemium.check_available(EVM)
    assert allowed and remaining == 1


# ── Звільнення платників ──────────────────────────────────────────────────────

def test_paying_wallet_exempt(monkeypatch):
    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "1")
    payment_service.record_payment("tx-1", EVM, 100, 4.99)
    # навіть після генерацій понад ліміт — платник не блокується
    freemium.record_generation(EVM)
    freemium.record_generation(EVM)
    allowed, remaining = freemium.check_available(EVM)
    assert allowed and remaining is None
    # поповненим лічильник не ведеться
    assert freemium.usage_today(EVM) == 0


def test_grant_wallet_exempt(monkeypatch):
    """Операторський grant = поповнення → без денної freemium-стелі."""
    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "1")
    payment_service.complete_wallet_sign_in(EVM)
    payment_service.grant_credits(EVM, 100, note="ops")
    assert freemium.is_exempt(EVM)
    freemium.record_generation(EVM)
    freemium.record_generation(EVM)
    allowed, remaining = freemium.check_available(EVM)
    assert allowed and remaining is None
    assert freemium.usage_today(EVM) == 0


def test_welcome_only_wallet_limited(monkeypatch):
    """Лише вітальні кредити — денна стеля діє."""
    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "2")
    monkeypatch.setenv("WELCOME_REQUIRE_BALANCE", "0")
    payment_service.complete_wallet_sign_in(EVM)
    assert not freemium.is_exempt(EVM)
    freemium.record_generation(EVM)
    freemium.record_generation(EVM)
    allowed, remaining = freemium.check_available(EVM)
    assert not allowed and remaining == 0


# ── Fail-open при збої БД ─────────────────────────────────────────────────────

def test_fail_open_on_db_error(monkeypatch):
    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "1")

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(payment_service, "_connect", boom)
    allowed, remaining = freemium.check_available(EVM)
    assert allowed and remaining is None  # не блокуємо легітимного користувача
    freemium.record_generation(EVM)  # не падає


def test_invalid_wallet_not_blocked(monkeypatch):
    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "1")
    allowed, remaining = freemium.check_available("not-a-wallet")
    assert allowed and remaining is None


# ── Інтеграція з billing_guard.try_reserve ────────────────────────────────────

def test_billing_guard_blocks_on_freemium(monkeypatch):
    from services import billing_guard

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("WELCOME_REQUIRE_BALANCE", "0")
    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "2")
    payment_service.complete_wallet_sign_in(EVM)
    payment_service.add_credits(EVM, 100)
    # перші дві резервації проходять і ведуть лічильник
    assert billing_guard.try_reserve(EVM, 1, engine="LLM", note="t")[0]
    assert billing_guard.try_reserve(EVM, 1, engine="LLM", note="t")[0]
    # третя — впирається в денну стелю (код freemium), кредити НЕ списано
    bal = payment_service.get_balance(EVM)
    ok, err = billing_guard.try_reserve(EVM, 1, engine="LLM", note="t")
    assert not ok and err == "freemium"
    assert payment_service.get_balance(EVM) == bal


def test_billing_guard_refund_releases_freemium_slot(monkeypatch):
    """Невдала LLM-генерація: refund повертає кредити І звільняє денний слот."""
    from services import billing_guard

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("WELCOME_REQUIRE_BALANCE", "0")
    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "1")
    payment_service.complete_wallet_sign_in(EVM)
    payment_service.add_credits(EVM, 100)
    bal = payment_service.get_balance(EVM)
    assert billing_guard.try_reserve(EVM, 2, engine="LLM", note="t")[0]
    assert freemium.usage_today(EVM) == 1
    # генерація впала → відкат
    billing_guard.refund(EVM, 2, engine="LLM", note="failed")
    assert payment_service.get_balance(EVM) == bal      # кредити повернено
    assert freemium.usage_today(EVM) == 0               # і слот звільнено
    # тож наступна спроба знову доступна (ліміт=1 не вичерпано невдачею)
    assert billing_guard.try_reserve(EVM, 2, engine="LLM", note="t2")[0]
