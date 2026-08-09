"""Етап 3 конвеєра: пакування метаданих в IPFS і мінтинг через сторонні двигуни.

Двигуни:
- Thirdweb (Base/EVM): прямий виклик mintTo(address, uri) на NFT Collection
  контракті через web3.py (опційна залежність).
- Crossmint (Base або Solana): HTTP POST до Crossmint Minting API.

Метадані трансформуються під стандарт обраного блокчейну: ERC-721 (Base)
відрізняється від Metaplex JSON (Solana) — symbol, seller_fee_basis_points,
properties.files/creators та ліміти довжини полів.
"""

import json

import ipfs
import network_config
from i18n import trait_type_en
from metadata_provenance import provenance_attributes
from trait_i18n import to_product_en

try:
    from web3 import Web3
    _WEB3_AVAILABLE = True
except ImportError:
    _WEB3_AVAILABLE = False

import httpx

CHAINS = {
    "Base (EVM, ERC-721)": "base",
    "Solana (Metaplex)": "solana",
}
ENGINES = ["Thirdweb SDK", "Crossmint API"]

BASE_RPC_DEFAULT = "https://mainnet.base.org"
CROSSMINT_URL = "https://www.crossmint.com/api/2022-06-09"
CROSSMINT_STAGING_URL = "https://staging.crossmint.com/api/2022-06-09"
MINT_TIMEOUT = 120.0

# Metaplex on-chain ліміти
METAPLEX_NAME_LIMIT = 32
METAPLEX_SYMBOL_LIMIT = 10

# Атрибут Prompt-Lock: формула генерації як незмінна частина метаданих NFT
PROMPT_LOCK_TRAIT = "Generation Prompt"

# Мінімальний ABI Thirdweb NFT Collection (ERC-721): мінт із готовим URI
# та multicall — batch mint однією транзакцією
THIRDWEB_MINT_ABI = [
    {
        "name": "mintTo",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_uri", "type": "string"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "multicall",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "data", "type": "bytes[]"}],
        "outputs": [{"name": "results", "type": "bytes[]"}],
    },
]


# ── Трансформація метаданих під стандарт блокчейну ────────────────────────────

def _attributes(traits: dict, prompt: str = "", item: dict | None = None) -> list[dict]:
    """Атрибути NFT; Prompt-Lock і provenance (rarity, engine, hash).

    Продукт EN-only: назви категорій → trait_type_en, значення й Prompt-Lock →
    to_product_en (словник → зняття укр-підказки → транслітерація-фолбек), щоб
    жодна кирилиця не потрапила on-chain навіть для введеного користувачем тексту.
    """
    attrs = [
        {"trait_type": trait_type_en(str(k)), "value": to_product_en(str(v))}
        for k, v in (traits or {}).items()
    ]
    if prompt.strip():
        attrs.append({"trait_type": PROMPT_LOCK_TRAIT, "value": to_product_en(prompt.strip())})
    if item:
        attrs.extend(provenance_attributes(item))
    return attrs


def build_erc721_metadata(
    name: str, description: str, image_uri: str, traits: dict, prompt: str = "",
    item: dict | None = None,
) -> dict:
    """Метадані ERC-721/OpenSea для Base (EVM)."""
    ctx = dict(item or {})
    if prompt and "prompt" not in ctx:
        ctx["prompt"] = prompt
    return {
        "name": to_product_en(name),
        "description": to_product_en(description),
        "image": image_uri,
        "attributes": _attributes(traits, prompt, item=ctx),
    }


def build_metaplex_metadata(
    name: str,
    symbol: str,
    description: str,
    image_uri: str,
    traits: dict,
    royalty_bps: int = 500,
    creator: str = "",
    prompt: str = "",
    item: dict | None = None,
) -> dict:
    """Метадані Metaplex для Solana — інша структура JSON, ніж ERC-721."""
    ctx = dict(item or {})
    if prompt and "prompt" not in ctx:
        ctx["prompt"] = prompt
    meta = {
        "name": to_product_en(name)[:METAPLEX_NAME_LIMIT],
        "symbol": symbol[:METAPLEX_SYMBOL_LIMIT],
        "description": to_product_en(description),
        "seller_fee_basis_points": int(royalty_bps),
        "image": image_uri,
        "attributes": _attributes(traits, prompt, item=ctx),
        "properties": {
            "files": [{"uri": image_uri, "type": "image/png"}],
            "category": "image",
        },
    }
    if creator.strip():
        meta["properties"]["creators"] = [{"address": creator.strip(), "share": 100}]
    return meta


def build_token_metadata(chain: str, item: dict, **metaplex_kwargs) -> dict:
    """Диспетчер: формує метадані під стандарт обраного блокчейну."""
    prompt = item.get("prompt", "")
    if chain == "solana":
        return build_metaplex_metadata(
            item["name"], metaplex_kwargs.get("symbol", ""), item["description"],
            item["image_uri"], item.get("traits", {}),
            royalty_bps=metaplex_kwargs.get("royalty_bps", 500),
            creator=metaplex_kwargs.get("creator", ""),
            prompt=prompt, item=item,
        )
    return build_erc721_metadata(
        item["name"], item["description"], item["image_uri"], item.get("traits", {}),
        prompt=prompt, item=item,
    )


# ── IPFS-пакування (Pinata) ───────────────────────────────────────────────────

def pin_asset(jwt: str, image_bytes: bytes, filename: str, pin_name: str) -> str:
    """Завантажує зображення в IPFS; повертає image URI (ipfs://CID)."""
    cid = ipfs.upload_file(jwt, filename, image_bytes, pin_name)
    return f"ipfs://{cid}"


def pin_metadata(jwt: str, metadata: dict, pin_name: str) -> str:
    """Завантажує JSON метаданих в IPFS; повертає token URI (ipfs://CID)."""
    content = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")
    cid = ipfs.upload_file(jwt, "metadata.json", content, pin_name)
    return f"ipfs://{cid}"


# ── Crossmint (Base або Solana) ───────────────────────────────────────────────

def build_crossmint_payload(recipient: str, chain: str, metadata: dict) -> dict:
    """Тіло запиту до Crossmint Minting API.

    recipient: адреса гаманця (буде префіксовано "<chain>:") або вже готовий
    ідентифікатор Crossmint ("email:user@x.com:base", "solana:<pubkey>").
    """
    rec = recipient.strip()
    if ":" not in rec:
        rec = f"{chain}:{rec}"
    return {"recipient": rec, "metadata": metadata}


def mint_crossmint(
    api_key: str,
    collection_id: str,
    payload: dict,
    staging: bool = False,
) -> dict:
    """POST /collections/{id}/nfts. Повертає JSON відповіді Crossmint."""
    base = CROSSMINT_STAGING_URL if staging else CROSSMINT_URL
    response = httpx.post(
        f"{base}/collections/{collection_id}/nfts",
        headers=network_config.web3_headers(
            {"X-API-KEY": api_key, "Content-Type": "application/json"},
        ),
        json=payload,
        timeout=MINT_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


# ── Thirdweb (Base / EVM) ─────────────────────────────────────────────────────

def _thirdweb_contract(private_key: str, contract_address: str, rpc_url: str):
    """Спільна підготовка: w3, акаунт мінтера, контракт."""
    if not _WEB3_AVAILABLE:
        raise ImportError("Встановіть пакет web3: pip install web3")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise ConnectionError(f"Немає з'єднання з RPC: {rpc_url}")
    account = w3.eth.account.from_key(private_key)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address), abi=THIRDWEB_MINT_ABI,
    )
    return w3, account, contract


def _send_tx(w3, account, fn_call) -> dict:
    """Підписує та надсилає виклик контракту; чекає на receipt."""
    tx = fn_call.build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
    })
    signed = account.sign_transaction(tx)
    # web3 v7 → raw_transaction, v6 → rawTransaction
    raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
    tx_hash = w3.eth.send_raw_transaction(raw)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    return {
        "tx_hash": tx_hash.hex(),
        "status": "success" if receipt.status == 1 else "reverted",
        "block": receipt.blockNumber,
    }


def encode_mint_calls(contract, recipient: str, token_uris: list[str]) -> list[bytes]:
    """Кодує виклики mintTo для multicall (batch mint однією транзакцією)."""
    to = Web3.to_checksum_address(recipient)
    # web3 v7 → encode_abi(abi_element_identifier=…), v6 → encodeABI(fn_name=…)
    encode = getattr(contract, "encode_abi", None) or getattr(contract, "encodeABI")
    calls = []
    for uri in token_uris:
        try:
            data = encode("mintTo", args=[to, uri])
        except TypeError:
            data = encode(fn_name="mintTo", args=[to, uri])
        calls.append(bytes.fromhex(data[2:]) if isinstance(data, str) else data)
    return calls


def mint_thirdweb(
    private_key: str,
    contract_address: str,
    recipient: str,
    token_uri: str,
    rpc_url: str = BASE_RPC_DEFAULT,
) -> dict:
    """Викликає mintTo на Thirdweb NFT Collection контракті. Повертає tx hash і статус."""
    w3, account, contract = _thirdweb_contract(private_key, contract_address, rpc_url)
    fn_call = contract.functions.mintTo(Web3.to_checksum_address(recipient), token_uri)
    return _send_tx(w3, account, fn_call)


def mint_thirdweb_batch(
    private_key: str,
    contract_address: str,
    recipient: str,
    token_uris: list[str],
    rpc_url: str = BASE_RPC_DEFAULT,
) -> dict:
    """Batch mint: усі mintTo пакуються в один multicall — одна транзакція."""
    if not token_uris:
        raise ValueError("Немає token URI для мінтингу")
    w3, account, contract = _thirdweb_contract(private_key, contract_address, rpc_url)
    calls = encode_mint_calls(contract, recipient, token_uris)
    return _send_tx(w3, account, contract.functions.multicall(calls))
