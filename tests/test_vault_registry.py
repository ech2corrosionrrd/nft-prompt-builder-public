"""Гарди реєстру сейфу (services/vault_registry).

Регресія, яку вони фіксують: 2026-08-03 у бойовому data/vault_catalog.json
опинилась тестова фікстура з п'ятьма СЛУЖБОВИМИ адресами (collection mint,
candy machine, guard, treasury, deployer). Оплата слоту 0 віддала б покупцеві
Collection NFT колекції. Тому каталог тепер валідується цілком, а перед
трансфером токен мусить лежати в сейфі.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services import vault_registry

# Правдоподібні адреси предметів (не належать протоколу w3ir).
ITEM_A = "8sVaCkYVLbLu9WrbNqfBk4c8pnEUL2spjkGDrYFvVQjS"
ITEM_B = "5nUyLmnLmXQvETNCwWEbEVoNbG1RY4rQzdWnfyeDo4Rk"

COLLECTION_MINT = "6YRxC2pwqttw11zy4v2cGgV3DztpPX7zSHrFFcA4nmqC"


def _write(tmp_path: Path, data) -> Path:
    path = tmp_path / "vault_catalog.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_valid_catalog_loads(tmp_path):
    path = _write(tmp_path, [{"index": 0, "mint": ITEM_A}, {"index": 1, "mint": ITEM_B}])
    catalog = vault_registry.load_catalog(path)
    assert catalog == [{"index": 0, "mint": ITEM_A}, {"index": 1, "mint": ITEM_B}]
    assert vault_registry.resolve_mint(catalog, 1) == ITEM_B


def test_missing_catalog_is_fail_closed(tmp_path):
    with pytest.raises(vault_registry.VaultError):
        vault_registry.load_catalog(tmp_path / "nope.json")


def test_protocol_address_in_catalog_is_rejected(tmp_path):
    """Головна регресія: Collection NFT не може бути товаром — навіть з env."""
    path = _write(tmp_path, [{"index": 0, "mint": COLLECTION_MINT}])
    with pytest.raises(vault_registry.VaultError, match="protocol address"):
        vault_registry.load_catalog(path)


def test_env_protocol_address_is_rejected(tmp_path, monkeypatch):
    """Стороннє розгортання: свої службові адреси задаються через env."""
    monkeypatch.setenv("GENESIS_COLLECTION_MINT", ITEM_A)
    path = _write(tmp_path, [{"index": 0, "mint": ITEM_A}])
    with pytest.raises(vault_registry.VaultError, match="protocol address"):
        vault_registry.load_catalog(path)


def test_denylist_env_is_respected(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_MINT_DENYLIST", f"foo, {ITEM_B} ")
    path = _write(tmp_path, [{"index": 0, "mint": ITEM_B}])
    with pytest.raises(vault_registry.VaultError):
        vault_registry.load_catalog(path)


@pytest.mark.parametrize(
    "bad",
    [
        {"index": -1, "mint": ITEM_A},
        {"index": "0", "mint": ITEM_A},
        {"index": 0, "mint": "not-base58-0OIl"},
        {"index": 0},
        {"mint": ITEM_A},
    ],
)
def test_malformed_entries_are_rejected(tmp_path, bad):
    path = _write(tmp_path, [bad])
    with pytest.raises(vault_registry.VaultError):
        vault_registry.load_catalog(path)


def test_duplicate_index_and_mint_are_rejected(tmp_path):
    dup_index = _write(tmp_path, [{"index": 0, "mint": ITEM_A}, {"index": 0, "mint": ITEM_B}])
    with pytest.raises(vault_registry.VaultError, match="duplicate index"):
        vault_registry.load_catalog(dup_index)

    dup_mint = _write(tmp_path, [{"index": 0, "mint": ITEM_A}, {"index": 1, "mint": ITEM_A}])
    with pytest.raises(vault_registry.VaultError, match="duplicate mint"):
        vault_registry.load_catalog(dup_mint)


def test_catalog_must_be_a_list(tmp_path):
    path = _write(tmp_path, {"index": 0, "mint": ITEM_A})
    with pytest.raises(vault_registry.VaultError, match="JSON array"):
        vault_registry.load_catalog(path)


def test_resolve_mint_unknown_index(tmp_path):
    catalog = [{"index": 0, "mint": ITEM_A}]
    with pytest.raises(vault_registry.VaultError, match="not in the vault catalog"):
        vault_registry.resolve_mint(catalog, 7)


@pytest.mark.anyio
async def test_vault_token_mints_parses_balances(monkeypatch):
    class MockResponse:
        status_code = 200

        def json(self):
            return {
                "result": [
                    {"account": {"data": {"parsed": {"info": {
                        "mint": ITEM_A, "tokenAmount": {"amount": "1"}}}}}},
                    # Нульовий баланс = токен уже пішов із сейфу.
                    {"account": {"data": {"parsed": {"info": {
                        "mint": ITEM_B, "tokenAmount": {"amount": "0"}}}}}},
                    {"account": {"data": {"parsed": {}}}},  # сміття — пропустити
                ]
            }

    import httpx

    async def mock_post(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    mints = await vault_registry.vault_token_mints("https://rpc.example", "VaultAddr")
    assert mints == {ITEM_A}


@pytest.mark.anyio
async def test_vault_token_mints_rpc_error_is_fail_closed(monkeypatch):
    class MockResponse:
        status_code = 500

        def json(self):
            return {}

    import httpx

    async def mock_post(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    with pytest.raises(vault_registry.VaultError):
        await vault_registry.vault_token_mints("https://rpc.example", "VaultAddr")
