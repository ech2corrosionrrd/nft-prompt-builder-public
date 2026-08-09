"""Тести ендпоінта /gremlin/holder (контракт Gremlin Passport ↔ W3IR).

Доступ — той самий `X-Gremlin-Key`, що й у /gremlin/generate (server-to-server).
RPC не викликається в юніт-тестах: `wallet_genesis_count` мокається.
"""
import pytest
from fastapi.testclient import TestClient

import api_server
from api_server import app

KEY = "test-shared-secret"


@pytest.fixture
def no_rate_limit(monkeypatch):
    monkeypatch.setattr(api_server, "allow_request", lambda *a, **k: True)


@pytest.fixture
def with_key(monkeypatch, no_rate_limit):
    monkeypatch.setattr(api_server, "_GREMLIN_API_KEY", KEY)


def _get(wallet="SoLWallet111", chain="solana", key=KEY, **params):
    headers = {"X-Gremlin-Key": key} if key is not None else {}
    q = {"wallet": wallet, **params}
    if chain is not None:
        q["chain"] = chain
    return TestClient(app).get("/gremlin/holder", params=q, headers=headers)


def test_gremlin_holder_503_when_key_not_configured(monkeypatch, no_rate_limit):
    monkeypatch.setattr(api_server, "_GREMLIN_API_KEY", "")
    r = _get(key="anything")
    assert r.status_code == 503


def test_gremlin_holder_401_without_header(with_key):
    r = _get(key=None)
    assert r.status_code == 401


def test_gremlin_holder_401_with_wrong_key(with_key):
    r = _get(key="wrong")
    assert r.status_code == 401


def test_gremlin_holder_solana_holder(monkeypatch, with_key):
    monkeypatch.setattr(api_server.holder_rewards, "wallet_genesis_count", lambda w: 3)
    r = _get(wallet="SoLWallet111", chain="solana")
    assert r.status_code == 200
    assert r.json() == {
        "wallet": "SoLWallet111",
        "chain": "solana",
        "isGenesisHolder": True,
        "genesisCount": 3,
    }


def test_gremlin_holder_solana_non_holder(monkeypatch, with_key):
    monkeypatch.setattr(api_server.holder_rewards, "wallet_genesis_count", lambda w: 0)
    r = _get(wallet="SoLWallet222", chain=None)
    assert r.status_code == 200
    body = r.json()
    assert body["isGenesisHolder"] is False
    assert body["genesisCount"] == 0
    assert body["chain"] == "solana"  # дефолт


def test_gremlin_holder_evm_never_holder(monkeypatch, with_key):
    # EVM не тримає Genesis (Solana-колекція) → 0 без звернення до RPC.
    def _boom(_w):
        raise AssertionError("wallet_genesis_count не має викликатись для EVM")

    monkeypatch.setattr(api_server.holder_rewards, "wallet_genesis_count", _boom)
    r = _get(wallet="0xABC", chain="evm")
    assert r.status_code == 200
    body = r.json()
    assert body["isGenesisHolder"] is False
    assert body["genesisCount"] == 0


def test_gremlin_holder_requires_wallet(with_key):
    r = _get(wallet="  ")
    assert r.status_code == 400
