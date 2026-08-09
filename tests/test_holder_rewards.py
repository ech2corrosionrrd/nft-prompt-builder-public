"""Tests for Genesis holder bonus integration."""

from __future__ import annotations

import json


from services import holder_rewards


def test_bonus_exclude_defaults(monkeypatch):
    monkeypatch.delenv("GENESIS_BONUS_EXCLUDE_WALLETS", raising=False)
    holder_rewards._exclude_cache = None
    excluded = holder_rewards._bonus_exclude_wallets()
    assert "63u6SDZckvzcJhC4V5yJn6bZ15qx1iM8c6iB3Z9xD1tn" in excluded


def test_bonus_exclude_env_override(monkeypatch):
    monkeypatch.setenv("GENESIS_BONUS_EXCLUDE_WALLETS", "3LhuUXBbUUWmUi6UjFCRKkNcsD44iFxjYm2PD6GvLzfD")
    holder_rewards._exclude_cache = None
    excluded = holder_rewards._bonus_exclude_wallets()
    assert len(excluded) == 1


def test_eligibility_team_excluded(monkeypatch):
    treasury = "63u6SDZckvzcJhC4V5yJn6bZ15qx1iM8c6iB3Z9xD1tn"
    monkeypatch.setattr(holder_rewards, "wallet_genesis_count", lambda w: 4)
    elig = holder_rewards.eligibility(treasury)
    assert elig["excluded"] is True
    assert elig["claimable_credits"] == 0


def test_claim_team_excluded(monkeypatch):
    treasury = "63u6SDZckvzcJhC4V5yJn6bZ15qx1iM8c6iB3Z9xD1tn"
    res = holder_rewards.claim(treasury)
    assert res["granted"] is False
    assert res["reason"] == "team_excluded"


def test_solana_rpc_prefers_explicit_url(monkeypatch):
    monkeypatch.setenv("SOLANA_RPC_URL", "https://example-rpc.test")
    monkeypatch.delenv("ALCHEMY_API_KEY", raising=False)
    assert holder_rewards._solana_rpc_url() == "https://example-rpc.test"


def test_solana_rpc_builds_alchemy(monkeypatch):
    monkeypatch.delenv("SOLANA_RPC_URL", raising=False)
    monkeypatch.setenv("ALCHEMY_API_KEY", "test-key")
    assert holder_rewards._solana_rpc_url().endswith("/test-key")


def test_rpc_headers_add_origin_for_alchemy():
    headers = holder_rewards._rpc_request_headers("https://solana-mainnet.g.alchemy.com/v2/x")
    assert headers.get("Origin") == "https://mint.w3ir.io"


def test_wallet_genesis_count_uses_mint_set(tmp_path, monkeypatch):
    real_mint = "2Hz2JTgZS8Zg9sFzE94rC1zj9un6Jst1Wyw7qmZU9cTc"
    holder = "3LhuUXBbUUWmUi6UjFCRKkNcsD44iFxjYm2PD6GvLzfD"
    mints_file = tmp_path / "genesis_mints.json"
    mints_file.write_text(json.dumps({"mints": [real_mint]}), encoding="utf-8")
    monkeypatch.setattr(holder_rewards, "MINTS_FILE", mints_file)
    holder_rewards._mints_cache = None

    captured: dict = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        class Resp:
            def json(self):
                return {
                    "result": {
                        "value": [{
                            "account": {
                                "data": {
                                    "parsed": {
                                        "info": {
                                            "mint": real_mint,
                                            "tokenAmount": {"decimals": 0, "amount": "1"},
                                        }
                                    }
                                }
                            }
                        }]
                    }
                }
        return Resp()

    monkeypatch.setattr(holder_rewards.requests, "post", fake_post)
    monkeypatch.setenv("ALCHEMY_API_KEY", "abc")
    count = holder_rewards.wallet_genesis_count(holder)
    assert count == 1
    assert "alchemy.com" in captured["url"]
    assert captured["headers"].get("Origin")


def test_rpc_cascade_falls_over_to_next_node(tmp_path, monkeypatch):
    """Перший RPC падає (мережа + JSON-RPC error) → каскад бере наступний вузол."""
    real_mint = "2Hz2JTgZS8Zg9sFzE94rC1zj9un6Jst1Wyw7qmZU9cTc"
    holder = "3LhuUXBbUUWmUi6UjFCRKkNcsD44iFxjYm2PD6GvLzfD"
    mints_file = tmp_path / "genesis_mints.json"
    mints_file.write_text(json.dumps({"mints": [real_mint]}), encoding="utf-8")
    monkeypatch.setattr(holder_rewards, "MINTS_FILE", mints_file)
    holder_rewards._mints_cache = None

    # Каскад: первинний (explicit) + один фолбек + публічний дефолт
    monkeypatch.setenv("SOLANA_RPC_URL", "https://primary.test")
    monkeypatch.setenv("SOLANA_RPC_FALLBACKS", "https://backup.test")
    monkeypatch.delenv("ALCHEMY_API_KEY", raising=False)

    calls: list[str] = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if url == "https://primary.test":
            raise holder_rewards.requests.ConnectionError("node down")  # мережевий збій

        class Resp:
            def json(self):
                if url == "https://backup.test":
                    return {"error": {"code": 429, "message": "rate limited"}}  # 200 з RPC-error
                # публічний дефолт — робоча відповідь
                return {"result": {"value": [{
                    "account": {"data": {"parsed": {"info": {
                        "mint": real_mint,
                        "tokenAmount": {"decimals": 0, "amount": "1"},
                    }}}}
                }]}}
        return Resp()

    monkeypatch.setattr(holder_rewards.requests, "post", fake_post)
    count = holder_rewards.wallet_genesis_count(holder)
    assert count == 1
    # Пройшлися каскадом: primary(збій) → backup(RPC-error) → дефолт(успіх)
    assert calls == ["https://primary.test", "https://backup.test", holder_rewards.wallet_auth.SOLANA_RPC_DEFAULT]
