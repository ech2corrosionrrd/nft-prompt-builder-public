"""Тести R2 mint-path / concierge (services/mint_path.py)."""

from __future__ import annotations

import pytest

from services import mint_path, payment_service

A = "0x" + "aa" * 20


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")


def test_resolve_path_maps():
    assert mint_path.resolve_path("evm_easy") == ("thirdweb", "evm_visual")
    assert mint_path.resolve_path("evm_opensea") == ("opensea", "evm_visual")
    assert mint_path.resolve_path("solana_dev") == ("sugar", "solana_cli")
    assert mint_path.resolve_path("concierge") == ("thirdweb", "concierge")
    assert mint_path.resolve_path("nope") is None


def test_path_kind_for_platform():
    assert mint_path.path_kind_for_platform("thirdweb") == "evm_visual"
    assert mint_path.path_kind_for_platform("sugar") == "solana_cli"
    assert mint_path.path_kind_for_platform("w3ir") == "w3ir"
    assert mint_path.path_kind_for_platform("???") == "unknown"


def test_record_mint_path_intent():
    assert mint_path.record_mint_path_intent(
        A, platform="thirdweb", path_id="evm_easy", source="path_chooser",
    )
    summary = mint_path.mint_path_intent_summary(days=7)
    assert summary["total"] == 1
    assert summary["by_kind"].get("evm_visual") == 1
    assert summary["by_platform"].get("thirdweb") == 1


def test_validate_concierge_request():
    assert mint_path.validate_concierge_request(email="bad") == "ec.concierge.err_email"
    assert mint_path.validate_concierge_request(email="a@b.c", preferred_chain="tron") == (
        "ec.concierge.err_chain"
    )
    assert mint_path.validate_concierge_request(
        email="a@b.co", preferred_chain="solana", supply=0,
    ) == "ec.concierge.err_supply"
    assert mint_path.validate_concierge_request(email="a@b.co", preferred_chain="base") is None


def test_submit_concierge_request(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(mint_path, "send_telegram", lambda text: sent.append(text) or True)

    ok, err = mint_path.submit_concierge_request(
        A,
        email="creator@example.com",
        collection_name="Demo Drop",
        preferred_chain="solana",
        supply=25,
        notes="need by Friday",
    )
    assert ok and err is None
    assert sent and "Concierge" in sent[0]
    reqs = mint_path.list_concierge_requests(limit=5)
    assert len(reqs) == 1
    assert reqs[0]["email"] == "creator@example.com"
    assert reqs[0]["preferred_chain"] == "solana"
    assert reqs[0]["supply"] == 25
    summary = mint_path.mint_path_intent_summary(days=7)
    assert summary["by_kind"].get("concierge") == 1


def test_submit_concierge_rejects_bad_email():
    ok, err = mint_path.submit_concierge_request(A, email="not-an-email")
    assert not ok
    assert err == "ec.concierge.err_email"
