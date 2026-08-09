"""SIWE-гейтвей: EIP-4361 повідомлення, nonce-стор і HMAC-сесійний токен.

Окремий від `services.wallet_auth` шар, що перетворює перевірений підпис на
коротко­живу підписану сесію для входу в застосунок (заміна Cloudflare-екрану).
Криптоперевірку підпису делегуємо у `wallet_auth.verify_evm_signature`
(EIP-191 recover) — SIWE-повідомлення підписується тим самим personal_sign,
тож recover працює як є.

Сесійний токен — stdlib, без зовнішніх залежностей (PyJWT не потрібен):
    base64url(payload_json) + "." + base64url(HMAC-SHA256(secret, payload))
payload = {"addr": <lower hex>, "iat": <unix>, "exp": <unix>}.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone

# Фолбеки-дефолти. Самі змінні читаються з середовища ЛІНИВО (у момент виклику
# build_siwe_message), а не при імпорті — інакше значення «застигне» з дефолтом,
# якщо модуль імпортовано до load_dotenv() (див. порядок у api_server.py).
_FALLBACK_DOMAIN = "ai.w3ir.io"
_FALLBACK_URI = "https://ai.w3ir.io"
_FALLBACK_CHAIN_ID = 8453  # Base mainnet (наживо AUTH_CHAIN_ID=8453; фолбек вирівняно з продом)


def _env_domain() -> str:
    return os.environ.get("AUTH_DOMAIN") or _FALLBACK_DOMAIN


def _env_uri() -> str:
    return os.environ.get("AUTH_URI") or _FALLBACK_URI


def _env_chain_id() -> int:
    return int(os.environ.get("AUTH_CHAIN_ID") or _FALLBACK_CHAIN_ID)


def normalize_addr(address: str) -> str:
    """Нормалізує адресу для порівняння/зберігання.

    EVM (0x…) — у нижній регістр (регістр неважливий, ще й checksum-варіація).
    Solana base58 — як є: lower зіпсував би pubkey (алфавіт регістрозалежний).
    """
    a = (address or "").strip()
    return a.lower() if a.startswith("0x") else a


SIWE_STATEMENT = "Sign in to NFT Prompt Builder. This request will not trigger an on-chain transaction or cost gas."

NONCE_TTL_SECONDS = 5 * 60          # вікно на підпис
SESSION_TTL_SECONDS = 4 * 60 * 60  # тривалість входу (скорочено з 12h — безпека)


def _session_secret() -> str:
    """Секрет для HMAC-підпису сесії. Обов'язковий — інакше токени підробні."""
    secret = (os.environ.get("AUTH_SESSION_SECRET") or "").strip()
    if not secret:
        raise RuntimeError(
            "AUTH_SESSION_SECRET не налаштовано — гейтвей вимкнено (інакше "
            "сесійні токени можна підробити)."
        )
    return secret


# ── SIWE (EIP-4361) ────────────────────────────────────────────────────────────

def new_nonce() -> str:
    return secrets.token_hex(16)


def build_siwe_message(
    address: str,
    nonce: str,
    *,
    domain: str | None = None,
    uri: str | None = None,
    chain_id: int | None = None,
    issued_at: str | None = None,
) -> str:
    """Канонічне EIP-4361 повідомлення. Сервер будує його й верифікує дзеркально.

    domain/uri/chain_id, якщо не передані явно, читаються з середовища у момент
    виклику (AUTH_DOMAIN/AUTH_URI/AUTH_CHAIN_ID) — не «застигають» при імпорті.
    """
    domain = domain if domain is not None else _env_domain()
    uri = uri if uri is not None else _env_uri()
    chain_id = chain_id if chain_id is not None else _env_chain_id()
    issued = issued_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"{domain} wants you to sign in with your Ethereum account:\n"
        f"{address}\n\n"
        f"{SIWE_STATEMENT}\n\n"
        f"URI: {uri}\n"
        f"Version: 1\n"
        f"Chain ID: {chain_id}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued}"
    )


# ── Nonce-стор (in-memory, потокобезпечний) ─────────────────────────────────────
# Прив'язує nonce → (address, message, expiry). Один процес FastAPI; для кількох
# воркерів винести у Redis (TTL-логіка та сама).

class NonceStore:
    def __init__(self, ttl: int = NONCE_TTL_SECONDS) -> None:
        self._ttl = ttl
        self._lock = threading.Lock()
        self._data: dict[str, tuple[str, str, float]] = {}

    def issue(self, nonce: str, address: str, message: str, *, now: float | None = None) -> str:
        """Зберігає (address, exact message) під заданим nonce. Повідомлення має
        будуватися ВЖЕ з цим nonce — клієнт підписує саме цей рядок, а verify
        порівнює дзеркально."""
        now = time.time() if now is None else now
        with self._lock:
            self._prune(now)
            self._data[nonce] = (normalize_addr(address), message, now + self._ttl)
        return nonce

    def consume(self, nonce: str, *, now: float | None = None) -> tuple[str, str] | None:
        """Одноразово повертає (address, message) для nonce; None — якщо немає/протух."""
        now = time.time() if now is None else now
        with self._lock:
            entry = self._data.pop(nonce, None)
        if not entry:
            return None
        address, message, expiry = entry
        if now > expiry:
            return None
        return address, message

    def _prune(self, now: float) -> None:
        expired = [n for n, (_, _, exp) in self._data.items() if now > exp]
        for n in expired:
            self._data.pop(n, None)


# ── Redis-бекенд (для multi-worker: nonce спільний між процесами) ────────────────
# Той самий зовнішній контракт issue/consume, що й NonceStore. TTL — нативний
# Redis (SET ex=ttl), одноразовість — атомарний GETDEL. Параметр now ігнорується
# (Redis сам відлічує час); лишений у сигнатурі для сумісності інтерфейсу.

_REDIS_PREFIX = "siwe:nonce:"


class RedisNonceStore:
    def __init__(self, client, ttl: int = NONCE_TTL_SECONDS) -> None:
        self._r = client
        self._ttl = ttl

    def issue(self, nonce: str, address: str, message: str, *, now: float | None = None) -> str:
        payload = json.dumps({"address": normalize_addr(address), "message": message})
        self._r.set(_REDIS_PREFIX + nonce, payload, ex=self._ttl)
        return nonce

    def consume(self, nonce: str, *, now: float | None = None) -> tuple[str, str] | None:
        # GETDEL — атомарне читання+видалення: гарантує одноразовість навіть під
        # гонкою кількох воркерів. Протерміновані ключі Redis уже прибрав сам.
        raw = self._r.getdel(_REDIS_PREFIX + nonce)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            obj = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            return None
        return obj["address"], obj["message"]


def create_nonce_store(ttl: int = NONCE_TTL_SECONDS):
    """Фабрика nonce-стору за env AUTH_NONCE_BACKEND (memory|redis).

    memory (дефолт) — in-memory NonceStore (один процес, --workers 1).
    redis           — RedisNonceStore за REDIS_URL (дозволяє --workers >1).
    """
    backend = (os.environ.get("AUTH_NONCE_BACKEND") or "memory").strip().lower()
    if backend == "redis":
        try:
            import redis  # опційна залежність
        except ImportError as exc:
            raise RuntimeError(
                "AUTH_NONCE_BACKEND=redis потребує пакет redis: pip install redis"
            ) from exc
        url = os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
        return RedisNonceStore(redis.Redis.from_url(url), ttl=ttl)
    return NonceStore(ttl=ttl)


# ── HMAC-сесійний токен ─────────────────────────────────────────────────────────

def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_session_token(
    address: str,
    *,
    secret: str | None = None,
    ttl: int = SESSION_TTL_SECONDS,
    now: float | None = None,
) -> str:
    now = int(time.time() if now is None else now)
    key = (secret or _session_secret()).encode()
    payload = {"addr": normalize_addr(address), "iat": now, "exp": now + ttl}
    body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(key, body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64url(sig)}"


def verify_session_token(
    token: str,
    *,
    secret: str | None = None,
    now: float | None = None,
) -> str | None:
    """Повертає address, якщо токен валідний і не протух; інакше None."""
    now = int(time.time() if now is None else now)
    if not token or token.count(".") != 1:
        return None
    body, sig = token.split(".", 1)
    key = (secret or _session_secret()).encode()
    expected = _b64url(hmac.new(key, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(_b64url_decode(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or now > int(payload.get("exp", 0)):
        return None
    addr = payload.get("addr")
    # Приймаємо і EVM (0x…), і Solana base58. Від підробки захищає HMAC вище —
    # перевірка формату тут лише санітарна (токен ми ж і видавали верифікованій адресі).
    return addr if isinstance(addr, str) and addr else None
