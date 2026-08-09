"""Тести reconcile-фолбеку NFT-фулфілменту (мінт/трансфер із сейфу).

Покриває ledger статусу в payment_service (reserved→completed/failed, pending-вибірку)
та executor/політику авто-повтору в api_server.
"""

from __future__ import annotations

import asyncio

import pytest

from services import payment_service as ps


def _iso_offset(seconds: int) -> str:
    """ISO-час зі зсувом (для підробки updated_at без Date.now у тесті)."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() + seconds, tz=timezone.utc
    ).isoformat()


def _set_updated_at(tx_id: str, iso: str) -> None:
    from contextlib import closing
    with closing(ps._connect()) as conn, conn:
        conn.execute("UPDATE nft_fulfillments SET updated_at=? WHERE tx_id=?", (iso, tx_id))


def test_claim_sets_reserved(monkeypatch, tmp_path):
    monkeypatch.setattr("services.payment_service.DB_PATH", tmp_path / "users.db")
    assert ps.claim_nft_fulfillment("tx1", "walletA", "mint") is True
    # Другий раз — вже зарезервовано.
    assert ps.claim_nft_fulfillment("tx1", "walletA", "mint") is False
    # Свіжий 'reserved' НЕ потрапляє у pending (subprocess ще міг бігти).
    assert ps.pending_fulfillments(stale_seconds=300) == []


def test_done_excludes_from_pending(monkeypatch, tmp_path):
    monkeypatch.setattr("services.payment_service.DB_PATH", tmp_path / "users.db")
    ps.claim_nft_fulfillment("tx2", "walletA", "transfer", "MintAddr")
    ps.mark_fulfillment_done("tx2")
    # Навіть як стале — completed не повертається.
    assert ps.pending_fulfillments(stale_seconds=0) == []


def test_failed_appears_in_pending_with_attempts(monkeypatch, tmp_path):
    monkeypatch.setattr("services.payment_service.DB_PATH", tmp_path / "users.db")
    ps.claim_nft_fulfillment("tx3", "walletA", "mint")
    ps.mark_fulfillment_failed("tx3")
    pend = ps.pending_fulfillments(stale_seconds=0)
    assert len(pend) == 1
    assert pend[0]["tx_id"] == "tx3"
    assert pend[0]["status"] == "failed"
    assert pend[0]["attempts"] == 1
    assert pend[0]["kind"] == "mint"


def test_stale_reserved_appears_but_fresh_does_not(monkeypatch, tmp_path):
    monkeypatch.setattr("services.payment_service.DB_PATH", tmp_path / "users.db")
    ps.claim_nft_fulfillment("tx4", "walletA", "transfer", "MintAddr")
    # Свіже — не стале.
    assert ps.pending_fulfillments(stale_seconds=600) == []
    # Підробляємо updated_at на 10 хв назад → стале.
    _set_updated_at("tx4", _iso_offset(-600))
    pend = ps.pending_fulfillments(stale_seconds=300)
    assert [r["tx_id"] for r in pend] == ["tx4"]


def test_max_attempts_stops_retry(monkeypatch, tmp_path):
    monkeypatch.setattr("services.payment_service.DB_PATH", tmp_path / "users.db")
    ps.claim_nft_fulfillment("tx5", "walletA", "mint")
    for _ in range(5):
        ps.mark_fulfillment_failed("tx5")
    # attempts == 5, поріг max_attempts=5 → більше не повертається.
    assert ps.pending_fulfillments(stale_seconds=0, max_attempts=5) == []
    # Але з вищим порогом — знову у черзі.
    assert len(ps.pending_fulfillments(stale_seconds=0, max_attempts=6)) == 1


def test_known_ids_and_counts(monkeypatch, tmp_path):
    monkeypatch.setattr("services.payment_service.DB_PATH", tmp_path / "users.db")
    ps.claim_nft_fulfillment("k1", "walletA", "mint")
    ps.claim_nft_fulfillment("k2", "walletB", "transfer", "MintAddr")
    ps.mark_fulfillment_done("k2")
    ps.claim_nft_fulfillment("k3", "walletC", "mint")
    ps.mark_fulfillment_failed("k3")

    assert ps.known_fulfillment_tx_ids() == {"k1", "k2", "k3"}
    counts = ps.nft_fulfillment_counts()
    assert counts == {"reserved": 1, "completed": 1, "failed": 1}
    # Case A: оплата, якої немає в ledger, — не в known.
    assert "paid-but-missing" not in ps.known_fulfillment_tx_ids()


def test_autoretry_policy():
    import api_server
    # Трансфер — завжди безпечний (on-chain ідемпотентний).
    assert api_server._fulfillment_should_autoretry({"kind": "transfer", "status": "reserved"}) is True
    # 'failed' будь-якого типу — безпечний (subprocess дав помилку).
    assert api_server._fulfillment_should_autoretry({"kind": "mint", "status": "failed"}) is True
    # Стале 'reserved' Genesis-мінту — НЕ авто (ризик подвійного мінту), поки opt-in off.
    assert api_server._fulfillment_should_autoretry({"kind": "mint", "status": "reserved"}) is False


@pytest.mark.anyio
async def test_run_fulfillment_marks_done_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr("services.payment_service.DB_PATH", tmp_path / "users.db")
    import api_server

    class FakeProc:
        returncode = 0
        async def communicate(self):
            return b"ok", b""

    async def fake_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    ps.claim_nft_fulfillment("tx6", "walletA", "transfer", "MintAddr")
    await api_server._run_fulfillment("tx6", "walletA", "transfer", "MintAddr")
    # completed → не в pending навіть як стале.
    assert ps.pending_fulfillments(stale_seconds=0) == []


@pytest.mark.anyio
async def test_run_fulfillment_marks_failed_on_nonzero(monkeypatch, tmp_path):
    monkeypatch.setattr("services.payment_service.DB_PATH", tmp_path / "users.db")
    import api_server

    class FakeProc:
        returncode = 1
        async def communicate(self):
            return b"", b"boom"

    async def fake_exec(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    ps.claim_nft_fulfillment("tx7", "walletA", "transfer", "MintAddr")
    await api_server._run_fulfillment("tx7", "walletA", "transfer", "MintAddr")
    pend = ps.pending_fulfillments(stale_seconds=0)
    assert len(pend) == 1
    assert pend[0]["status"] == "failed"
    assert pend[0]["attempts"] == 1
