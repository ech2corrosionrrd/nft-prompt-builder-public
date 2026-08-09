"""Гарди Helio-webhook після відкату серверного Genesis-мінту (Дроп #1).

Серверний випадковий мінт гарячим ключем прибрано свідомо (custody-ризик,
див. ПЛАН_КАСТОДІЯ.md). Лишився ЛИШЕ трансфер конкретного токена з сейфу
(Дроп #2, `selectedIndex`), success-шлях якого покриває test_vault_api.py.

Ці тести фіксують ІНВАРІАНТ: webhook НЕ запускає жодного subprocess, доки не
надано валідний `selectedIndex` — тобто випадок «оплата без selectedIndex»
(колишній тригер мінту) тепер відхиляється, а не мінтить. Регресія, що поверне
серверний мінт, зловиться тут.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

import api_server
from api_server import app


def _sign(body: bytes, secret: str = "whsec-test") -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _mint_env(monkeypatch, tmp_path):
    """Спільне налаштування: секрет підпису, paylink трансферу, ізольований ledger."""
    monkeypatch.setenv("HELIO_WEBHOOK_SECRET", "whsec-test")
    monkeypatch.setenv("HELIO_MINT_PAYLINK_ID", "plink-mint-test")
    # Ізолюємо ledger ідемпотентності, щоб прогони тестів не впливали один на одного.
    monkeypatch.setattr("services.payment_service.DB_PATH", tmp_path / "users.db")


def _guard_subprocess(monkeypatch):
    """Підміняє asyncio.create_subprocess_exec фейком; повертає список викликів.

    Жоден із тестів-відхилень НЕ має його викликати (subprocess = гарячий ключ).
    """
    cmd_called: list[tuple] = []

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"unexpected", b""

    async def fake_exec(*args, **kwargs):
        cmd_called.append(args)
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return cmd_called


def _post(client: TestClient, payload: dict) -> object:
    body = json.dumps(payload).encode()
    return client.post(
        "/webhooks/helio",
        content=body,
        headers={"x-helio-signature": _sign(body), "content-type": "application/json"},
    )


def test_payment_without_selected_index_is_rejected_not_minted(monkeypatch, tmp_path):
    """Колишній тригер Дропу #1 (немає selectedIndex) тепер відхиляється БЕЗ мінту."""
    _mint_env(monkeypatch, tmp_path)
    cmd_called = _guard_subprocess(monkeypatch)

    r = _post(client=TestClient(app), payload={
        "id": "helio-no-index",
        "paylinkId": "plink-mint-test",
        "status": "SUCCESS",
        "meta": {"customerWallet": "DE1gBEaqA11uYdySmF5LRmN8QsvXvnYJYHDVXeAY15Vh"},
    })

    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["error"] == "missing selectedIndex"
    assert cmd_called == []  # жоден subprocess (гарячий ключ) не запущено


def test_invalid_wallet_rejected_before_subprocess(monkeypatch, tmp_path):
    """Некоректна Solana-адреса customerWallet відхиляється до запуску subprocess."""
    _mint_env(monkeypatch, tmp_path)
    cmd_called = _guard_subprocess(monkeypatch)

    r = _post(client=TestClient(app), payload={
        "id": "helio-badwallet",
        "paylinkId": "plink-mint-test",
        "status": "SUCCESS",
        "meta": {"customerWallet": "not-a-valid-solana-address", "selectedIndex": 2},
    })

    assert r.json()["ok"] is False
    assert r.json()["error"] == "invalid customerWallet"
    assert cmd_called == []


def test_missing_tx_id_rejected(monkeypatch, tmp_path):
    """Без ідентифікатора транзакції фулфілмент відхиляється (fail-closed)."""
    _mint_env(monkeypatch, tmp_path)
    cmd_called = _guard_subprocess(monkeypatch)

    r = _post(client=TestClient(app), payload={
        "paylinkId": "plink-mint-test",
        "status": "SUCCESS",
        "meta": {"customerWallet": "DE1gBEaqA11uYdySmF5LRmN8QsvXvnYJYHDVXeAY15Vh", "selectedIndex": 2},
    })

    assert r.json()["ok"] is False
    assert r.json()["error"] == "missing transaction id"
    assert cmd_called == []


@pytest.mark.anyio
async def test_run_fulfillment_rejects_non_transfer_kind(monkeypatch):
    """`_run_fulfillment` — no-op для kind != 'transfer' (жодного subprocess/мінту)."""
    cmd_called: list[tuple] = []

    async def fake_exec(*args, **kwargs):
        cmd_called.append(args)
        raise AssertionError("subprocess не має запускатися для non-transfer")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    # Колишній Genesis-мінт: kind='mint' тепер лог + return, без node.
    await api_server._run_fulfillment("tx-mint", "walletA", "mint", "")
    assert cmd_called == []


@pytest.mark.anyio
async def test_fulfillment_semaphore_caps_concurrency(monkeypatch):
    """Семафор обмежує кількість одночасних node-субпроцесів трансферу (сплеск-захист)."""
    monkeypatch.setattr(api_server, "FULFILLMENT_MAX_CONCURRENCY", 2)
    api_server._fulfillment_semaphores.clear()  # щоб getter створив із новим лімітом

    active = 0
    peak = 0

    class SlowProcess:
        returncode = 0

        async def communicate(self):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.05)
            active -= 1
            return b"ok", b""

    async def fake_exec(*args, **kwargs):
        return SlowProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    # ledger-маркери звертаються до БД — no-op, тест ізольований від сховища.
    monkeypatch.setattr(api_server, "mark_fulfillment_done", lambda tx: None)
    monkeypatch.setattr(api_server, "mark_fulfillment_failed", lambda tx: None)

    tasks = [
        asyncio.create_task(
            api_server._run_fulfillment(f"tx{i}", "walletA", "transfer", "mintX")
        )
        for i in range(6)
    ]
    await asyncio.gather(*tasks)

    assert peak <= 2, f"перевищено стелю одночасності: peak={peak}"
    api_server._fulfillment_semaphores.clear()  # не лишаємо loop у словнику після тесту
