"""Тести /api/vault/status та Helio transfer з selectedIndex.

data/ під .gitignore — на CI немає vault_catalog.json. Тести пишуть фікстуру
і задають VAULT_CATALOG_PATH.

⚠️ Фікстура НЕ має містити службових адрес (collection mint, candy machine,
guard, treasury, deployer): саме така фікстура 2026-08-03 опинилась у бойовому
data/vault_catalog.json і зробила Collection NFT «товаром зі слоту 0». Тепер
такий каталог відхиляє `services/vault_registry`, і тест на це є нижче.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from api_server import app

VAULT_ADDRESS = "7VaU1tZ3rKPMxg3PPPy6uEnRw7v3bKZmQ8G1FteJ2XoM"

# Правдоподібні мінти предметів сейфу (жоден не є адресою протоколу w3ir).
ITEM_0 = "8sVaCkYVLbLu9WrbNqfBk4c8pnEUL2spjkGDrYFvVQjS"
ITEM_1 = "5nUyLmnLmXQvETNCwWEbEVoNbG1RY4rQzdWnfyeDo4Rk"
ITEM_2 = "9pKq2vXcM4dRt7BwYzHn6JLfAe3sUg5TmVbNc8QrWxZk"

_FIXTURE_CATALOG = [
    {"index": 0, "mint": ITEM_0},
    {"index": 1, "mint": ITEM_1},
    {"index": 2, "mint": ITEM_2},
]


def _install_catalog(tmp_path: Path, monkeypatch, catalog=None) -> Path:
    catalog_path = tmp_path / "vault_catalog.json"
    catalog_path.write_text(json.dumps(catalog or _FIXTURE_CATALOG), encoding="utf-8")
    monkeypatch.setenv("VAULT_CATALOG_PATH", str(catalog_path))
    return catalog_path


def _mock_vault_rpc(monkeypatch, mints_in_vault):
    """Підміняє RPC: у сейфі лежать саме ці мінти (баланс 1)."""

    class MockResponse:
        status_code = 200

        def json(self):
            return {
                "jsonrpc": "2.0",
                "result": [
                    {"account": {"data": {"parsed": {"info": {
                        "mint": m, "tokenAmount": {"amount": "1"}}}}}}
                    for m in mints_in_vault
                ],
            }

    import httpx

    async def mock_post(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)


def test_vault_status_endpoint(monkeypatch, tmp_path):
    _install_catalog(tmp_path, monkeypatch)
    monkeypatch.setenv("VAULT_WALLET_ADDRESS", VAULT_ADDRESS)
    _mock_vault_rpc(monkeypatch, [ITEM_2])

    client = TestClient(app)
    r = client.get("/api/vault/status")
    assert r.status_code == 200
    res = r.json()
    assert res["success"] is True
    assert res["vault_address"] == VAULT_ADDRESS
    assert 2 in res["available_indexes"]
    assert 0 not in res["available_indexes"]


def test_vault_status_is_rate_limited(monkeypatch, tmp_path):
    """Публічний роут б'є в Solana-RPC на кожен запит — без ліміту це підсилювач.

    Вичерпаний ліміт RPC-провайдера кладе заразом holder-бонус, який ходить туди ж.
    """
    import api_server

    _install_catalog(tmp_path, monkeypatch)
    monkeypatch.setenv("VAULT_WALLET_ADDRESS", VAULT_ADDRESS)
    _mock_vault_rpc(monkeypatch, [ITEM_2])

    calls: list[str] = []

    def fake_allow(bucket, **kwargs):
        calls.append(bucket)
        return len(calls) <= 1  # перший запит пускаємо, далі — стоп

    monkeypatch.setattr(api_server, "allow_request", fake_allow)

    client = TestClient(app)
    assert client.get("/api/vault/status").status_code == 200
    assert client.get("/api/vault/status").status_code == 429
    assert calls and calls[0].startswith("vault_status:")


def test_vault_status_endpoint_fail_closed(monkeypatch, tmp_path):
    _install_catalog(tmp_path, monkeypatch)
    monkeypatch.setenv("VAULT_WALLET_ADDRESS", VAULT_ADDRESS)

    class MockErrorResponse:
        status_code = 500

        def json(self):
            return {}

    import httpx

    async def mock_post(*args, **kwargs):
        return MockErrorResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = TestClient(app)
    r = client.get("/api/vault/status")
    assert r.status_code == 502


def test_vault_status_rejects_protocol_address_in_catalog(monkeypatch, tmp_path):
    """Каталог зі службовою адресою = зламаний каталог, а не «один дивний слот»."""
    _install_catalog(
        tmp_path, monkeypatch,
        catalog=[{"index": 0, "mint": "6YRxC2pwqttw11zy4v2cGgV3DztpPX7zSHrFFcA4nmqC"}],
    )
    monkeypatch.setenv("VAULT_WALLET_ADDRESS", VAULT_ADDRESS)

    client = TestClient(app)
    r = client.get("/api/vault/status")
    assert r.status_code == 500
    assert "catalog" in r.json()["detail"].lower()


def _post_transfer(client: TestClient, index, wallet: str = VAULT_ADDRESS, tx_id="helio-transfer-sig"):
    body_data = {
        "id": tx_id,
        "paylinkId": "plink-mint-test",
        "meta": {"customerWallet": wallet, "selectedIndex": index},
        "status": "SUCCESS",
    }
    body = json.dumps(body_data).encode()
    sig = hmac.new(b"whsec-test", body, hashlib.sha256).hexdigest()
    return client.post(
        "/webhooks/helio",
        content=body,
        headers={"x-helio-signature": sig, "content-type": "application/json"},
    )


def _transfer_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HELIO_WEBHOOK_SECRET", "whsec-test")
    monkeypatch.setenv("HELIO_MINT_PAYLINK_ID", "plink-mint-test")
    monkeypatch.setenv("VAULT_WALLET_ADDRESS", VAULT_ADDRESS)
    monkeypatch.setattr("services.payment_service.DB_PATH", tmp_path / "users.db")


def _spy_subprocess(monkeypatch):
    calls = []

    async def mock_create_subprocess_exec(*args, **kwargs):
        calls.append(args)

        class MockProc:
            returncode = 0

            async def communicate(self):
                return b"Transfer successful mock stdout", b""

        return MockProc()

    import asyncio

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)
    return calls


def test_helio_webhook_with_selected_index(monkeypatch, tmp_path):
    _install_catalog(tmp_path, monkeypatch)
    _transfer_env(monkeypatch, tmp_path)
    _mock_vault_rpc(monkeypatch, [ITEM_0, ITEM_1, ITEM_2])
    calls = _spy_subprocess(monkeypatch)

    r = _post_transfer(TestClient(app), 2)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    time.sleep(0.3)

    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == "node"
    assert "transfer-nft.mjs" in cmd[1]
    assert cmd[2] == VAULT_ADDRESS
    assert cmd[3] == ITEM_2


def test_transfer_refused_when_mint_not_in_vault(monkeypatch, tmp_path):
    """Токен уже пішов із сейфу (або ніколи там не був) → жодного subprocess."""
    _install_catalog(tmp_path, monkeypatch)
    _transfer_env(monkeypatch, tmp_path)
    _mock_vault_rpc(monkeypatch, [ITEM_0])  # index 2 у сейфі немає
    calls = _spy_subprocess(monkeypatch)

    r = _post_transfer(TestClient(app), 2, tx_id="helio-not-in-vault")
    assert r.json()["ok"] is False
    assert r.json()["error"] == "vault item unavailable"

    time.sleep(0.2)
    assert calls == []


def test_transfer_refused_without_vault_address(monkeypatch, tmp_path):
    """VAULT_WALLET_ADDRESS не налаштовано → трансферу немає (fail-closed)."""
    _install_catalog(tmp_path, monkeypatch)
    _transfer_env(monkeypatch, tmp_path)
    monkeypatch.delenv("VAULT_WALLET_ADDRESS", raising=False)
    calls = _spy_subprocess(monkeypatch)

    r = _post_transfer(TestClient(app), 2, tx_id="helio-no-vault-env")
    assert r.json()["ok"] is False
    assert r.json()["error"] == "vault item unavailable"
    assert calls == []


def test_transfer_refused_for_unknown_index(monkeypatch, tmp_path):
    _install_catalog(tmp_path, monkeypatch)
    _transfer_env(monkeypatch, tmp_path)
    _mock_vault_rpc(monkeypatch, [ITEM_0, ITEM_1, ITEM_2])
    calls = _spy_subprocess(monkeypatch)

    r = _post_transfer(TestClient(app), 99, tx_id="helio-unknown-index")
    assert r.json()["ok"] is False
    assert r.json()["error"] == "vault item unavailable"
    assert calls == []
