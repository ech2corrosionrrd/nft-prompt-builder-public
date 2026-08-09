"""Реєстр сейфу Дропу #2: каталог індекс → mint + гарди перед трансфером.

Навіщо окремий модуль. 2026-08-03 у бойовому `data/vault_catalog.json` (і в
дзеркалі `C:\\Sugar\\data`) лежала фікстура з тесту: п'ять СЛУЖБОВИХ адрес —
collection mint, candy machine, candy guard, treasury і гаманець деплоєра.
Оплата слоту 0 змусила б сервер віддати покупцеві **Collection NFT** колекції.
Каталог заповнює людина або скрипт, тож валідація має бути в коді, а не в
домовленості.

Правила (fail-closed):
  1. Каталог мусить бути списком {index:int>=0, mint:base58}; дублі індексів і
     мінтів — помилка.
  2. Жоден mint не може бути протокольною адресою (collection/CM/guard/гаманці).
  3. Перед трансфером токен мусить ЗАРАЗ лежати в сейфі. Немає в сейфі —
     трансферу немає, навіть якщо він є в каталозі.

Адреси протоколу беруться з env (див. `PROTOCOL_ADDRESS_ENV`), тож модуль
однаково працює у сторонньому розгортанні з іншою колекцією.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

import httpx

__all__ = [
    "VaultError",
    "load_catalog",
    "protocol_addresses",
    "resolve_mint",
    "vault_token_mints",
]

# base58 без 0OIl; довжина Solana pubkey у base58 — 32..44 символи.
_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

# Адреси, які НІКОЛИ не є товаром. Порожні/незадані env просто ігноруються.
PROTOCOL_ADDRESS_ENV = (
    "VAULT_WALLET_ADDRESS",
    "GENESIS_COLLECTION_MINT",
    "GENESIS_CANDY_MACHINE",
    "GENESIS_CANDY_GUARD",
    "GENESIS_TREASURY_WALLET",
    "GENESIS_DEPLOYER_WALLET",
    "SOLANA_TREASURY_ADDRESS",
)

# Знані адреси w3ir Genesis. Тримаємо навіть без env: саме вони потрапили в
# бойовий каталог із тестової фікстури й саме їх не можна продати ніколи.
_BUILTIN_PROTOCOL = frozenset({
    "6YRxC2pwqttw11zy4v2cGgV3DztpPX7zSHrFFcA4nmqC",  # collection NFT
    "BpHBqJAVeSRuEjyeEyuTkjUL9ocarY63rHBzyEVwmGrM",  # candy machine
    "ZnP8QYCD3yD7n3sCNLu1FrjG7operQ1tTK8z6pGKUNj",  # candy guard
    "63u6SDZckvzcJhC4V5yJn6bZ15qx1iM8c6iB3Z9xD1tn",  # treasury
    "DE1gBEaqA11uYdySmF5LRmN8QsvXvnYJYHDVXeAY15Vh",  # deployer
})


class VaultError(ValueError):
    """Каталог або запит до нього невалідні — фулфілмент виконувати не можна."""


def protocol_addresses() -> frozenset[str]:
    """Адреси, які не можуть бути товаром: env + знані + VAULT_MINT_DENYLIST."""
    found = set(_BUILTIN_PROTOCOL)
    for name in PROTOCOL_ADDRESS_ENV:
        value = (os.environ.get(name) or "").strip()
        if value:
            found.add(value)
    extra = os.environ.get("VAULT_MINT_DENYLIST") or ""
    found.update(a.strip() for a in extra.split(",") if a.strip())
    return frozenset(found)


def load_catalog(path: Path) -> list[dict[str, Any]]:
    """Прочитати й перевірити каталог сейфу. Будь-яка вада → VaultError."""
    if not path.is_file():
        raise VaultError(f"vault catalog not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — будь-яка помилка читання = fail-closed
        raise VaultError(f"vault catalog unreadable: {exc}") from exc

    if not isinstance(raw, list):
        raise VaultError("vault catalog must be a JSON array")

    denied = protocol_addresses()
    seen_index: set[int] = set()
    seen_mint: set[str] = set()
    catalog: list[dict[str, Any]] = []

    for pos, item in enumerate(raw):
        if not isinstance(item, dict):
            raise VaultError(f"catalog entry #{pos} is not an object")
        index = item.get("index")
        mint = item.get("mint")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise VaultError(f"catalog entry #{pos}: index must be a non-negative int")
        if not isinstance(mint, str) or not _BASE58_RE.match(mint):
            raise VaultError(f"catalog entry #{pos}: mint is not a base58 Solana address")
        if index in seen_index:
            raise VaultError(f"catalog has duplicate index {index}")
        if mint in seen_mint:
            raise VaultError(f"catalog has duplicate mint {mint}")
        if mint in denied:
            # Саме цей випадок стався 2026-08-03 (фікстура в бойових даних).
            raise VaultError(
                f"catalog entry #{index} points at a protocol address ({mint}) — refusing to treat it as an item"
            )
        seen_index.add(index)
        seen_mint.add(mint)
        catalog.append({"index": index, "mint": mint})

    return catalog


def resolve_mint(catalog: Iterable[dict[str, Any]], index: int) -> str:
    """Знайти mint за індексом. Немає такого індексу → VaultError."""
    for item in catalog:
        if item.get("index") == index:
            return str(item["mint"])
    raise VaultError(f"index {index} is not in the vault catalog")


async def vault_token_mints(rpc_url: str, vault_address: str, timeout: float = 10.0) -> set[str]:
    """Мінти, що ЗАРАЗ лежать у сейфі (баланс >= 1). Помилка RPC → VaultError.

    Свідомо не кешуємо: це остання перевірка перед віддачею активу, і застарілий
    кеш тут означав би подвійний продаж.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            vault_address,
            {"programId": _TOKEN_PROGRAM_ID},
            {"encoding": "jsonParsed"},
        ],
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(rpc_url, json=payload, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — мережева помилка = fail-closed
        raise VaultError(f"vault RPC request failed: {exc}") from exc

    if response.status_code != 200:
        raise VaultError(f"vault RPC returned HTTP {response.status_code}")

    data = response.json()
    result = data.get("result")
    if not isinstance(result, list):
        raise VaultError("vault RPC returned an unexpected payload")

    mints: set[str] = set()
    for acc in result:
        try:
            info = acc["account"]["data"]["parsed"]["info"]
            if int(info["tokenAmount"]["amount"]) >= 1:
                mints.add(info["mint"])
        except Exception:  # noqa: BLE001 — сторонні акаунти пропускаємо
            continue
    return mints


def rpc_url_from_env() -> str:
    """RPC для перевірок сейфу: Alchemy за ключем, інакше публічна нода."""
    api_key = (os.environ.get("ALCHEMY_API_KEY") or "").strip()
    if api_key:
        return f"https://solana-mainnet.g.alchemy.com/v2/{api_key}"
    return "https://solana-rpc.publicnode.com"
