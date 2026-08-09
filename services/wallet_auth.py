"""Перевірка володіння гаманцем (Sign-In, EVM + Solana) та Sybil-захист кредитів."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

import httpx

try:
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from web3 import Web3
    _WEB3_AVAILABLE = True
except ImportError:
    Account = None  # type: ignore[assignment,misc]
    _WEB3_AVAILABLE = False

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    _ED25519_AVAILABLE = True
except ImportError:
    _ED25519_AVAILABLE = False

BASE_RPC_DEFAULT = "https://mainnet.base.org"
# ≈ $0.50 ETH на Base (грубо 0.0002 ETH)
MIN_WELCOME_BALANCE_WEI = int(0.0002 * 10**18)

SOLANA_RPC_DEFAULT = "https://api.mainnet-beta.solana.com"
# ≈ $0.50 SOL (грубо 0.003 SOL = 3_000_000 лампортів) — симетрично з EVM-порогом
MIN_WELCOME_BALANCE_LAMPORTS = int(0.003 * 10**9)

# Алфавіт base58 (без 0, O, I, l) — для декодування Solana pubkey/підпису
_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {ch: i for i, ch in enumerate(_B58_ALPHABET)}


def is_evm_wallet(wallet: str) -> bool:
    return (wallet or "").startswith("0x") and len(wallet) == 42


def short_wallet(wallet: str) -> str:
    """Скорочена адреса для UI (sidebar, Credits, адмінка) — не для ідентифікації."""
    w = (wallet or "").strip()
    return f"{w[:6]}…{w[-4:]}" if len(w) > 12 else w


def _b58decode(s: str) -> bytes:
    """Декодує base58-рядок у байти (Bitcoin-алфавіт). Кидає ValueError на неприпустимих символах."""
    num = 0
    for ch in s:
        idx = _B58_INDEX.get(ch)
        if idx is None:
            raise ValueError(f"Недопустимий base58-символ: {ch!r}")
        num = num * 58 + idx
    body = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    pad = len(s) - len(s.lstrip("1"))  # провідні «1» → провідні нульові байти
    return b"\x00" * pad + body


def is_solana_wallet(wallet: str) -> bool:
    """Чи адреса схожа на Solana pubkey (base58 → рівно 32 байти)."""
    w = (wallet or "").strip()
    if not w or is_evm_wallet(w):
        return False
    try:
        return len(_b58decode(w)) == 32
    except ValueError:
        return False


def _decode_signature(signature: str) -> bytes | None:
    """Підпис ed25519 (64 байти): приймає hex (з фронтенду) або base58."""
    sig = (signature or "").strip()
    if not sig:
        return None
    if sig.startswith("0x"):
        sig = sig[2:]
    try:  # спершу hex (фронтенд Phantom віддає hex)
        if len(sig) == 128 and all(c in "0123456789abcdefABCDEF" for c in sig):
            return bytes.fromhex(sig)
        return _b58decode(sig)
    except ValueError:
        return None


def verify_solana_signature(wallet: str, message: str, signature: str) -> bool:
    """Перевіряє ed25519-підпис повідомлення Phantom для Solana-гаманця."""
    if not _ED25519_AVAILABLE:
        raise RuntimeError("Потрібен пакет cryptography для перевірки Solana-підпису.")
    try:
        pubkey = _b58decode((wallet or "").strip())
    except ValueError:
        return False
    if len(pubkey) != 32:
        return False
    sig_bytes = _decode_signature(signature)
    if sig_bytes is None or len(sig_bytes) != 64:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(pubkey).verify(sig_bytes, message.encode("utf-8"))
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def build_sign_message(wallet: str, nonce: str) -> str:
    return (
        "NFT Prompt Builder — Sign-In\n"
        f"Wallet: {wallet}\n"
        f"Nonce: {nonce}\n"
        f"Issued: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )


def new_nonce() -> str:
    return secrets.token_hex(16)


def verify_evm_signature(wallet: str, message: str, signature: str) -> bool:
    """Перевіряє personal_sign (EIP-191) для EVM-гаманця."""
    if not _WEB3_AVAILABLE or Account is None:
        raise RuntimeError("Потрібен пакет web3 та eth_account: pip install web3")
    wallet = wallet.lower()
    sig = (signature or "").strip()
    if not sig.startswith("0x"):
        sig = "0x" + sig
    # personal_sign = 65 байт = 0x + 130 hex-символів. Порожній/некоректний підпис
    # не передаємо в recover_message (інакше IndexError на порожніх байтах) — це не збіг.
    if len(sig) != 132 or any(c not in "0123456789abcdefABCDEF" for c in sig[2:]):
        return False
    try:
        recovered = Account.recover_message(encode_defunct(text=message), signature=sig)
    except Exception:
        return False
    return recovered.lower() == wallet


def eth_balance_wei(wallet: str, rpc_url: str | None = None) -> int:
    """Нативний баланс гаманця на Base (для Sybil-захисту).

    Будь-яка помилка мережі/RPC → 0 (fail-closed, симетрично з
    sol_balance_lamports): краще не видати вітальні кредити, ніж кинути виняток
    у потік входу. get_balance робить мережевий I/O і може впасти навіть після
    успішного is_connected() (таймаут, rate-limit, 5xx) — тож ловимо тут, а не
    лишаємо підійматися аж у gateway_guard/app.py, де його ніхто не чекає.
    """
    if not _WEB3_AVAILABLE:
        return 0
    rpc = rpc_url or os.environ.get("BASE_RPC_URL") or BASE_RPC_DEFAULT
    try:
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 15}))
        if not w3.is_connected():
            return 0
        return int(w3.eth.get_balance(Web3.to_checksum_address(wallet)))
    except Exception:
        return 0


def sol_balance_lamports(wallet: str, rpc_url: str | None = None) -> int:
    """Нативний баланс Solana-гаманця в лампортах (для Sybil-захисту).

    Опитує JSON-RPC `getBalance`. Будь-яка помилка мережі/RPC → 0, що
    трактується як недостатній баланс (fail-closed: краще не видати вітальні
    кредити, ніж роздавати їх безкоштовно при збої RPC).
    """
    rpc = rpc_url or os.environ.get("SOLANA_RPC_URL") or SOLANA_RPC_DEFAULT
    try:
        resp = httpx.post(
            rpc,
            json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [wallet]},
            timeout=15.0,
        )
        return int(resp.json()["result"]["value"])
    except Exception:
        return 0


def welcome_balance_ok(wallet: str) -> tuple[bool, str]:
    """Чи достатній нативний баланс для вітальних кредитів (Sybil-захист).

    Симетрично для обох мереж: EVM — мін. ETH на Base, Solana — мін. SOL. Так
    безкоштовні кредити дістаються лише гаманцям із реальним балансом, що
    ускладнює масове фармлення нових адрес. Вимкнення — WELCOME_REQUIRE_BALANCE=0.
    """
    if os.environ.get("WELCOME_REQUIRE_BALANCE", "1") == "0":
        return True, ""
    if is_evm_wallet(wallet):
        if not _WEB3_AVAILABLE:
            return True, ""
        balance = eth_balance_wei(wallet)
        if balance >= MIN_WELCOME_BALANCE_WEI:
            return True, ""
        eth = balance / 10**18
        return False, (
            f"Для вітальних кредитів потрібен мінімальний баланс ETH на Base "
            f"(≈0.0002 ETH). Поточний: {eth:.6f} ETH."
        )
    if is_solana_wallet(wallet):
        balance = sol_balance_lamports(wallet)
        if balance >= MIN_WELCOME_BALANCE_LAMPORTS:
            return True, ""
        sol = balance / 10**9
        return False, (
            f"Для вітальних кредитів потрібен мінімальний баланс SOL "
            f"(≈0.003 SOL). Поточний: {sol:.6f} SOL."
        )
    # Невідомий формат адреси — не блокуємо (на практиці auth пропускає лише EVM/Solana).
    return True, ""
