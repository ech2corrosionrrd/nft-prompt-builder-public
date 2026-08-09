"""Тести SIWE-гейтвея: nonce-стор, EIP-4361 повідомлення, HMAC-сесія."""

import pytest

from services import auth_gateway as ag

SECRET = "test-secret-not-for-prod"
ADDR = "0xAbC0000000000000000000000000000000000001"
SOLANA_ADDR = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"  # регістрозалежний base58


def test_siwe_message_is_eip4361_shaped():
    msg = ag.build_siwe_message(ADDR, "deadbeef", domain="ai.w3ir.io",
                                uri="https://ai.w3ir.io", chain_id=84532,
                                issued_at="2026-06-14T00:00:00Z")
    assert msg.startswith("ai.w3ir.io wants you to sign in with your Ethereum account:")
    assert f"\n{ADDR}\n" in msg
    assert "Nonce: deadbeef" in msg
    assert "Chain ID: 84532" in msg
    assert "Version: 1" in msg
    assert msg.rstrip().endswith("Issued At: 2026-06-14T00:00:00Z")


def test_siwe_message_reads_chain_id_from_env_at_call_time(monkeypatch):
    """Без явного chain_id значення береться з AUTH_CHAIN_ID у момент виклику.

    Регресія: раніше chain_id «застигав» при імпорті (дефолт 84532), якщо модуль
    імпортовано до load_dotenv() — тож .env=8453 ігнорувався.
    """
    monkeypatch.setenv("AUTH_CHAIN_ID", "8453")
    monkeypatch.setenv("AUTH_DOMAIN", "ai.w3ir.io")
    monkeypatch.setenv("AUTH_URI", "https://ai.w3ir.io")
    msg = ag.build_siwe_message(ADDR, "deadbeef")
    assert "Chain ID: 8453" in msg

    monkeypatch.setenv("AUTH_CHAIN_ID", "84532")
    assert "Chain ID: 84532" in ag.build_siwe_message(ADDR, "deadbeef")


def test_siwe_message_chain_id_falls_back_without_env(monkeypatch):
    monkeypatch.delenv("AUTH_CHAIN_ID", raising=False)
    assert f"Chain ID: {ag._FALLBACK_CHAIN_ID}" in ag.build_siwe_message(ADDR, "deadbeef")


def test_nonce_single_use_and_returns_payload():
    store = ag.NonceStore()
    store.issue("nonce-1", ADDR, "msg-body", now=1000.0)
    assert store.consume("nonce-1", now=1001.0) == (ADDR.lower(), "msg-body")
    # другий раз — вже спожито
    assert store.consume("nonce-1", now=1002.0) is None


def test_nonce_expires_after_ttl():
    store = ag.NonceStore(ttl=60)
    store.issue("nonce-2", ADDR, "m", now=1000.0)
    assert store.consume("nonce-2", now=1000.0 + 61) is None


def test_unknown_nonce_is_none():
    assert ag.NonceStore().consume("nope", now=1.0) is None


def test_session_token_roundtrip():
    tok = ag.issue_session_token(ADDR, secret=SECRET, ttl=3600, now=1000)
    assert ag.verify_session_token(tok, secret=SECRET, now=1500) == ADDR.lower()


def test_session_token_expired():
    tok = ag.issue_session_token(ADDR, secret=SECRET, ttl=10, now=1000)
    assert ag.verify_session_token(tok, secret=SECRET, now=2000) is None


def test_session_token_tampered_signature():
    tok = ag.issue_session_token(ADDR, secret=SECRET, ttl=3600, now=1000)
    body, _sig = tok.split(".", 1)
    forged = body + ".AAAA"
    assert ag.verify_session_token(forged, secret=SECRET, now=1500) is None


def test_session_token_wrong_secret():
    tok = ag.issue_session_token(ADDR, secret=SECRET, ttl=3600, now=1000)
    assert ag.verify_session_token(tok, secret="other", now=1500) is None


def test_session_token_malformed():
    for bad in ("", "noseparator", "a.b.c"):
        assert ag.verify_session_token(bad, secret=SECRET, now=1) is None


def test_session_secret_required(monkeypatch):
    monkeypatch.delenv("AUTH_SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        ag.issue_session_token(ADDR)


# ── Solana: нормалізація та сесія мають зберігати регістр base58 ──────────────────

def test_normalize_addr_evm_lowercased():
    assert ag.normalize_addr(ADDR) == ADDR.lower()


def test_normalize_addr_solana_case_preserved():
    # lower() зіпсував би pubkey — base58 регістрозалежний
    assert ag.normalize_addr(SOLANA_ADDR) == SOLANA_ADDR


def test_session_token_roundtrip_solana_preserves_case():
    tok = ag.issue_session_token(SOLANA_ADDR, secret=SECRET, ttl=3600, now=1000)
    assert ag.verify_session_token(tok, secret=SECRET, now=1500) == SOLANA_ADDR


def test_nonce_store_preserves_solana_case():
    store = ag.NonceStore()
    store.issue("n-sol", SOLANA_ADDR, "m", now=1000.0)
    assert store.consume("n-sol", now=1001.0) == (SOLANA_ADDR, "m")


def test_env_domain_uri_empty_falls_back(monkeypatch):
    """Пастка `AUTH_DOMAIN=`/`AUTH_URI=` (присутні-порожні): дефолт, не "" —
    інакше SIWE-повідомлення мало б порожній domain/uri і верифікація б падала."""
    monkeypatch.setenv("AUTH_DOMAIN", "")
    monkeypatch.setenv("AUTH_URI", "")
    assert ag._env_domain() == "ai.w3ir.io"
    assert ag._env_uri() == "https://ai.w3ir.io"


def test_env_domain_uri_explicit_overrides(monkeypatch):
    monkeypatch.setenv("AUTH_DOMAIN", "staging.w3ir.io")
    monkeypatch.setenv("AUTH_URI", "https://staging.w3ir.io")
    assert ag._env_domain() == "staging.w3ir.io"
    assert ag._env_uri() == "https://staging.w3ir.io"
