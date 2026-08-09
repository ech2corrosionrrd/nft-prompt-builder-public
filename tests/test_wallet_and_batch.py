"""Тести wallet auth, pipeline batch, rate limit."""

import pytest

from services import payment_service, pipeline_batch, wallet_auth

EVM = "0x" + "ab12" * 10
SOLANA = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")


def test_build_sign_message_contains_wallet_and_nonce():
    msg = wallet_auth.build_sign_message(EVM, "abc123")
    assert EVM in msg and "abc123" in msg


def test_short_wallet_truncates_long_addresses():
    assert wallet_auth.short_wallet(EVM) == f"{EVM[:6]}…{EVM[-4:]}"
    assert wallet_auth.short_wallet(SOLANA) == f"{SOLANA[:6]}…{SOLANA[-4:]}"
    assert wallet_auth.short_wallet("0xabc") == "0xabc"
    assert wallet_auth.short_wallet("") == ""


@pytest.mark.skipif(not wallet_auth._WEB3_AVAILABLE, reason="web3 не встановлено")
def test_verify_evm_signature_rejects_empty_and_malformed():
    # Порожній / закороткий / не-hex підпис → False без винятку (раніше IndexError)
    for bad in ("", "0x", "0x1234", "not-hex", "0x" + "zz" * 65, "0x" + "ab" * 64):
        assert wallet_auth.verify_evm_signature(EVM, "msg", bad) is False


# ── Sybil-захист вітальних кредитів (баланс-поріг, симетрично EVM/Solana) ──────

def test_welcome_solana_sufficient_balance(monkeypatch):
    monkeypatch.delenv("WELCOME_REQUIRE_BALANCE", raising=False)
    monkeypatch.setattr(
        wallet_auth, "sol_balance_lamports",
        lambda w: wallet_auth.MIN_WELCOME_BALANCE_LAMPORTS,
    )
    ok, msg = wallet_auth.welcome_balance_ok(SOLANA)
    assert ok and msg == ""


def test_welcome_solana_insufficient_balance_blocked(monkeypatch):
    monkeypatch.delenv("WELCOME_REQUIRE_BALANCE", raising=False)
    monkeypatch.setattr(wallet_auth, "sol_balance_lamports", lambda w: 0)
    ok, msg = wallet_auth.welcome_balance_ok(SOLANA)
    assert not ok and "SOL" in msg


def test_welcome_disabled_skips_network(monkeypatch):
    """WELCOME_REQUIRE_BALANCE=0 → видаємо без перевірки балансу (і без мережі)."""
    monkeypatch.setenv("WELCOME_REQUIRE_BALANCE", "0")

    def _boom(*a, **k):  # будь-який мережевий виклик = помилка тесту
        raise AssertionError("мережа не має чіпатися при вимкненому гарді")

    monkeypatch.setattr(wallet_auth, "sol_balance_lamports", _boom)
    monkeypatch.setattr(wallet_auth, "eth_balance_wei", _boom)
    assert wallet_auth.welcome_balance_ok(SOLANA) == (True, "")
    assert wallet_auth.welcome_balance_ok(EVM) == (True, "")


def test_sol_balance_parses_value(monkeypatch):
    class _Resp:
        def json(self):
            return {"jsonrpc": "2.0", "result": {"context": {}, "value": 4_200_000}}

    monkeypatch.setattr(wallet_auth.httpx, "post", lambda *a, **k: _Resp())
    assert wallet_auth.sol_balance_lamports(SOLANA) == 4_200_000


def test_sol_balance_network_error_fails_closed(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("rpc down")

    monkeypatch.setattr(wallet_auth.httpx, "post", _boom)
    # Збій RPC → 0 (недостатній баланс), а не виняток.
    assert wallet_auth.sol_balance_lamports(SOLANA) == 0


@pytest.mark.skipif(not wallet_auth._WEB3_AVAILABLE, reason="web3 не встановлено")
def test_eth_balance_network_error_fails_closed(monkeypatch):
    """Збій Base RPC після is_connected() → 0, а не виняток у потоці входу.
    Симетрично з sol_balance_lamports: інакше get_balance підіймав би помилку аж
    у gateway_guard/app.py при першому вході EVM-гаманця під час збою RPC."""

    class _Eth:
        def get_balance(self, *a, **k):
            raise RuntimeError("rpc 503")

    class _FakeW3:
        eth = _Eth()

        def __init__(self, *a, **k):
            pass

        def is_connected(self):
            return True

        @staticmethod
        def HTTPProvider(*a, **k):
            return None

        @staticmethod
        def to_checksum_address(addr):
            return addr

    monkeypatch.setattr(wallet_auth, "Web3", _FakeW3)
    assert wallet_auth.eth_balance_wei(EVM) == 0


@pytest.mark.skipif(not wallet_auth._WEB3_AVAILABLE, reason="web3 не встановлено")
def test_welcome_evm_insufficient_balance_blocked(monkeypatch):
    """EVM-гаманець без мінімального балансу не отримує welcome (симетрія з Solana)."""
    monkeypatch.delenv("WELCOME_REQUIRE_BALANCE", raising=False)
    monkeypatch.setattr(wallet_auth, "eth_balance_wei", lambda w: 0)
    ok, msg = wallet_auth.welcome_balance_ok(EVM)
    assert not ok and "ETH" in msg


def test_matrix_trait_distribution():
    cats = {"Head": ["a", "b"], "Bg": ["x", "y", "z"]}
    rows = pipeline_batch.matrix_trait_distribution(cats)
    assert len(rows) == 5
    assert rows[0]["Очікувано %"] == 50.0


def test_log_transaction_and_list():
    payment_service.complete_wallet_sign_in(EVM)
    payment_service.log_transaction(EVM, "debit", -1, engine="Flux", note="test")
    rows = payment_service.list_transactions(EVM)
    assert rows[0]["kind"] == "debit"
    assert rows[0]["credits"] == -1


def test_rate_limit_blocks_after_threshold():
    payment_service.complete_wallet_sign_in(EVM)
    payment_service.add_credits(EVM, 100)
    limit = payment_service._configured_generation_rate_limit()
    for _ in range(limit):
        payment_service.deduct_credits(EVM, 1, engine="Flux", note="gen")
    assert not payment_service.check_generation_rate(EVM)
    assert payment_service.seconds_until_generation_slot(EVM) > 0


def test_grant_wallet_exempt_from_rate_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")
    payment_service.complete_wallet_sign_in(EVM)
    payment_service.grant_credits(EVM, 100, note="ops")
    assert payment_service.generation_rate_limit_per_minute(EVM) is None
    for _ in range(15):
        payment_service.deduct_credits(EVM, 1, engine="Flux", note="gen")
    assert payment_service.check_generation_rate(EVM)


def test_store_and_get_nonce():
    payment_service.store_wallet_nonce(EVM, "nonce-1")
    assert payment_service.get_wallet_nonce(EVM) == "nonce-1"


def test_consume_nonce_is_one_time_use():
    payment_service.store_wallet_nonce(EVM, "nonce-x")
    assert payment_service.consume_wallet_nonce(EVM) == "nonce-x"
    # вдруге — вже видалено (захист від replay)
    assert payment_service.consume_wallet_nonce(EVM) is None


def test_consume_nonce_rejects_expired():
    from datetime import datetime, timedelta, timezone

    payment_service.store_wallet_nonce(EVM, "nonce-old")
    old = (
        datetime.now(timezone.utc) - timedelta(seconds=payment_service.NONCE_TTL_SECONDS + 60)
    ).isoformat()
    with payment_service._connect() as conn:
        conn.execute(
            "UPDATE wallet_nonces SET created_at = ? WHERE wallet_address = ?", (old, EVM)
        )
        conn.commit()
    assert payment_service.consume_wallet_nonce(EVM) is None


def test_refund_credits_restores_balance_and_logs():
    payment_service.complete_wallet_sign_in(EVM)
    payment_service.add_credits(EVM, 10)
    assert payment_service.deduct_credits(EVM, 4, engine="DALL-E 3")
    new_balance = payment_service.refund_credits(EVM, 4, engine="DALL-E 3", note="refund: test")
    assert new_balance == payment_service.get_balance(EVM)
    rows = payment_service.list_transactions(EVM)
    assert rows[0]["kind"] == "refund" and rows[0]["credits"] == 4
