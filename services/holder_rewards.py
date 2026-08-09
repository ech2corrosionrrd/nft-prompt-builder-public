"""Genesis holder → bonus credits.

Verified holders of the W3IR Genesis Avatar collection (Solana Candy Machine,
deployed via C:\\Sugar) can claim bonus generation credits on ai.w3ir.io.

Ownership is checked against `data/genesis_mints.json` — the authoritative list
of every minted Genesis NFT, produced by C:\\Sugar\\scripts\\snapshot-holders.mjs
(re-run it after new mints to refresh). A wallet "holds Genesis" iff it owns a
token (amount 1, decimals 0) whose mint is in that set — no DAS / metadata
decoding needed.

The user is already authenticated by wallet signature on sign-in (EVM **or**
Solana — see services/wallet_auth.py), so a claim can only be made for a wallet
the user controls. Idempotency is enforced per (wallet, period) in `holder_grants`.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone

import requests

from services import db, payment_service, wallet_auth

# ── Config (env-overridable) ────────────────────────────────────────────────
COLLECTION_MINT = os.environ.get(
    "GENESIS_COLLECTION_MINT", "6YRxC2pwqttw11zy4v2cGgV3DztpPX7zSHrFFcA4nmqC"
)
# `... or "N"` — порожній env (`KEY=`) трактується як відсутній, інакше int("")
# валить ValueError (див. [[env-empty-defeats-default]] / гард test_env_defaults_guard).
BONUS_CREDITS = int(os.environ.get("GENESIS_BONUS_CREDITS") or "50")
BONUS_PER_EXTRA = int(os.environ.get("GENESIS_BONUS_PER_EXTRA") or "25")
BONUS_MAX = int(os.environ.get("GENESIS_BONUS_MAX") or "150")
# 'once' = one grant per wallet ever · 'monthly' = one per wallet per calendar month
BONUS_PERIOD = (os.environ.get("GENESIS_BONUS_PERIOD") or "once").strip().lower()
# Global safety cap on total holder credits ever granted (protects API margin).
BONUS_BUDGET = int(os.environ.get("GENESIS_BONUS_BUDGET") or "5000")
DEFAULT_BONUS_EXCLUDE = (
    "DE1gBEaqA11uYdySmF5LRmN8QsvXvnYJYHDVXeAY15Vh",  # deployer
    "63u6SDZckvzcJhC4V5yJn6bZ15qx1iM8c6iB3Z9xD1tn",  # treasury / team mints
    "1BWutmTvYPwDtmw9abTkS4Ssr8no61spGAvW1X6NDix",   # dogfood-гаманець оператора
)
RPC_ORIGIN = os.environ.get("GENESIS_RPC_ORIGIN", "https://mint.w3ir.io").strip()
# Таймаут на ОДНУ RPC-спробу (каскад пробує наступний вузол при збої/таймауті).
_RPC_TIMEOUT = float(os.environ.get("SOLANA_RPC_TIMEOUT") or "10")

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
DATA_DIR = payment_service.DB_PATH.parent
MINTS_FILE = DATA_DIR / "genesis_mints.json"

_mints_cache: dict | None = None  # {"mtime": float, "set": set[str]}
_exclude_cache: set[str] | None = None


def _bonus_exclude_wallets() -> set[str]:
    """Team/admin wallets excluded from holder bonus (same intent as Sugar snapshot EXCLUDE)."""
    global _exclude_cache
    raw = os.environ.get("GENESIS_BONUS_EXCLUDE_WALLETS", "").strip()
    if raw:
        parts = {w.strip() for w in raw.split(",") if w.strip()}
    else:
        parts = set(DEFAULT_BONUS_EXCLUDE)
    try:
        _exclude_cache = {payment_service.normalize_wallet(w) for w in parts}
    except ValueError:
        _exclude_cache = set(parts)
    return _exclude_cache


def _is_bonus_excluded(wallet: str) -> bool:
    try:
        norm = payment_service.normalize_wallet(wallet)
    except ValueError:
        return False
    return norm in _bonus_exclude_wallets()


def _solana_rpc_url() -> str:
    explicit = os.environ.get("SOLANA_RPC_URL", "").strip()
    if explicit:
        return explicit
    alchemy = (
        os.environ.get("ALCHEMY_API_KEY", "").strip()
        or os.environ.get("VITE_ALCHEMY_API_KEY", "").strip()
    )
    if alchemy:
        return f"https://solana-mainnet.g.alchemy.com/v2/{alchemy}"
    return os.environ.get("SOLANA_RPC_FALLBACK", wallet_auth.SOLANA_RPC_DEFAULT)


def _solana_rpc_urls() -> list[str]:
    """Впорядкований каскад RPC-ендпоінтів (перший робочий виграє).

    Порядок: первинний (`_solana_rpc_url`) → `SOLANA_RPC_FALLBACKS` (кома-список) →
    публічний дефолт як останній рубіж. Дедуп зі збереженням порядку. Мета: збій чи
    rate-limit одного вузла не має лишати легітимного холдера без бонусу — fail-closed
    (повернути 0) лише коли ВСІ вузли впали.
    """
    urls = [_solana_rpc_url()]
    for raw in os.environ.get("SOLANA_RPC_FALLBACKS", "").split(","):
        raw = raw.strip()
        if raw:
            urls.append(raw)
    urls.append(wallet_auth.SOLANA_RPC_DEFAULT)
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _rpc_request_headers(rpc_url: str) -> dict[str, str]:
    if "alchemy.com" in rpc_url and RPC_ORIGIN:
        return {"Origin": RPC_ORIGIN}
    return {}


# ── Genesis mint set (from snapshot export) ─────────────────────────────────
def genesis_mint_set() -> set[str]:
    """Set of all minted Genesis NFT mints. Cached, invalidated on file mtime."""
    global _mints_cache
    try:
        mtime = MINTS_FILE.stat().st_mtime
    except OSError:
        return set()
    if _mints_cache and _mints_cache["mtime"] == mtime:
        return _mints_cache["set"]
    try:
        doc = json.loads(MINTS_FILE.read_text(encoding="utf-8"))
        mints = set(doc.get("mints", []))
    except (OSError, ValueError):
        mints = set()
    _mints_cache = {"mtime": mtime, "set": mints}
    return mints


# ── On-chain ownership ──────────────────────────────────────────────────────
def wallet_genesis_count(wallet: str) -> int:
    """How many Genesis NFTs `wallet` currently holds. Network error → 0 (fail-closed)."""
    wallet = wallet_auth.normalize_wallet(wallet) if hasattr(wallet_auth, "normalize_wallet") else wallet
    if not wallet_auth.is_solana_wallet(wallet):
        return 0
    mints = genesis_mint_set()
    if not mints:
        return 0
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            wallet,
            {"programId": TOKEN_PROGRAM},
            {"encoding": "jsonParsed"},
        ],
    }
    # Каскад RPC: перший вузол, що відповів БЕЗ помилки, — джерело правди. Мережевий
    # збій/таймаут або JSON-RPC error (напр. rate-limit як 200) → наступний вузол.
    for rpc in _solana_rpc_urls():
        try:
            resp = requests.post(rpc, json=body, headers=_rpc_request_headers(rpc), timeout=_RPC_TIMEOUT)
            data = resp.json()
        except (requests.RequestException, ValueError):
            continue
        if data.get("error"):
            continue
        rows = data.get("result", {}).get("value", [])
        owned = 0
        for r in rows:
            try:
                info = r["account"]["data"]["parsed"]["info"]
                amt = info["tokenAmount"]
                if amt["decimals"] == 0 and amt["amount"] == "1" and info["mint"] in mints:
                    owned += 1
            except (KeyError, TypeError):
                continue
        return owned  # успішна відповідь (навіть 0 owned) — не каскадимо далі
    return 0  # усі вузли впали → fail-closed (як раніше)


# ── Bonus sizing & period ───────────────────────────────────────────────────
def current_period() -> str:
    if BONUS_PERIOD == "monthly":
        return datetime.now(timezone.utc).strftime("%Y-%m")
    return "once"


def bonus_amount(count: int) -> int:
    if count < 1:
        return 0
    return min(BONUS_MAX, BONUS_CREDITS + (count - 1) * BONUS_PER_EXTRA)


# ── Dedup ledger (holder_grants) ────────────────────────────────────────────
def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS holder_grants (
            wallet_address TEXT NOT NULL,
            period         TEXT NOT NULL,
            nft_count      INTEGER NOT NULL,
            credits        INTEGER NOT NULL,
            granted_at     TEXT NOT NULL,
            PRIMARY KEY (wallet_address, period)
        )
        """
    )


def already_claimed(wallet: str, period: str | None = None) -> bool:
    wallet = payment_service.normalize_wallet(wallet)
    period = period or current_period()
    with closing(db.connect(payment_service.DB_PATH)) as conn:
        _ensure_table(conn)
        row = conn.execute(
            "SELECT 1 FROM holder_grants WHERE wallet_address = ? AND period = ?",
            (wallet, period),
        ).fetchone()
        return row is not None


def _granted_total() -> int:
    with closing(db.connect(payment_service.DB_PATH)) as conn:
        _ensure_table(conn)
        row = conn.execute("SELECT COALESCE(SUM(credits), 0) FROM holder_grants").fetchone()
        return int(row[0]) if row else 0


# ── Public API ──────────────────────────────────────────────────────────────
def eligibility(wallet: str) -> dict:
    """Status for UI. {is_solana, holds, count, period, already, claimable_credits}."""
    wallet = payment_service.normalize_wallet(wallet)
    period = current_period()
    if _is_bonus_excluded(wallet):
        return {
            "is_solana": wallet_auth.is_solana_wallet(wallet),
            "holds": False,
            "count": 0,
            "period": period,
            "already": False,
            "claimable_credits": 0,
            "excluded": True,
        }
    if not wallet_auth.is_solana_wallet(wallet):
        return {"is_solana": False, "holds": False, "count": 0, "period": period,
                "already": False, "claimable_credits": 0, "excluded": False}
    count = wallet_genesis_count(wallet)
    already = already_claimed(wallet, period)
    return {
        "is_solana": True,
        "holds": count > 0,
        "count": count,
        "period": period,
        "already": already,
        "claimable_credits": 0 if (already or count < 1) else bonus_amount(count),
        "excluded": False,
    }


def claim(wallet: str) -> dict:
    """Verify holding → reserve (idempotent) → grant credits.

    Returns {"granted": bool, "reason"?: str, "credits"?, "count"?, "period", "balance"?}.
    """
    wallet = payment_service.normalize_wallet(wallet)
    period = current_period()

    if _is_bonus_excluded(wallet):
        return {"granted": False, "reason": "team_excluded", "period": period}

    if not wallet_auth.is_solana_wallet(wallet):
        return {"granted": False, "reason": "not_solana", "period": period}

    count = wallet_genesis_count(wallet)
    if count < 1:
        return {"granted": False, "reason": "not_holder", "period": period}

    credits = bonus_amount(count)
    if _granted_total() + credits > BONUS_BUDGET:
        return {"granted": False, "reason": "budget_exhausted", "period": period}

    now = datetime.now(timezone.utc).isoformat()
    # Atomic reservation: PK(wallet, period) blocks double-claims even under races.
    try:
        with closing(db.connect(payment_service.DB_PATH)) as conn, conn:
            _ensure_table(conn)
            conn.execute(
                "INSERT INTO holder_grants (wallet_address, period, nft_count, credits, granted_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (wallet, period, count, credits, now),
            )
    except db.integrity_errors():
        return {"granted": False, "reason": "already", "period": period, "count": count}

    # Grant via the existing credit API; roll back the reservation on failure.
    try:
        balance = payment_service.grant_credits(
            wallet, credits, note=f"Genesis holder bonus {period} ({count} NFT)"
        )
    except Exception:
        with closing(db.connect(payment_service.DB_PATH)) as conn, conn:
            conn.execute(
                "DELETE FROM holder_grants WHERE wallet_address = ? AND period = ?",
                (wallet, period),
            )
        raise

    return {"granted": True, "credits": credits, "count": count,
            "period": period, "balance": balance}


# ── Автоматична фонова синхронізація (інкрементальне сканування) ──────────────────
logger = logging.getLogger("holder_rewards")

# Адреса Candy Machine для Genesis
CANDY_MACHINE = "BpHBqJAVeSRuEjyeEyuTkjUL9ocarY63rHBzyEVwmGrM"

def sync_genesis_mints(rpc_url: str | None = None) -> dict:
    """Інкрементально сканує транзакції Candy Machine та оновлює список мінтів.
    
    Зчитує поточний стан з genesis_mints.json, запитує нові транзакції після 
    останнього обробленого підпису (lastSignature), парсить нові адреси мінту NFT
    та зберігає оновлені дані локально та у дзеркальну папку C:\\Sugar\\data.
    
    Повертає словник із результатами синхронізації.
    """
    logger.info("Початок фонової синхронізації холдерів Genesis NFT...")
    
    # Визначаємо URL для RPC
    rpc = rpc_url or _solana_rpc_url()
    headers = _rpc_request_headers(rpc)
    
    # 1. Зчитуємо поточний стан
    current_doc = {}
    mints = set()
    last_sig = None
    
    if MINTS_FILE.is_file():
        try:
            current_doc = json.loads(MINTS_FILE.read_text(encoding="utf-8"))
            mints = set(current_doc.get("mints", []))
            last_sig = current_doc.get("lastSignature")
        except Exception as e:
            logger.warning(f"Не вдалося зчитати поточний файл мінтів: {e}. Буде створено новий.")
            
    # 2. Запитуємо сигнатури транзакцій після останньої відомої
    params = [CANDY_MACHINE, {"limit": 100}]
    if last_sig:
        params[1]["until"] = last_sig
        
    try:
        resp = requests.post(
            rpc,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": params
            },
            headers=headers,
            timeout=15
        )
        resp.raise_for_status()
        sigs_data = resp.json().get("result", [])
    except Exception as e:
        logger.error(f"Помилка при отриманні сигнатур транзакцій: {e}")
        return {"success": False, "error": f"getSignaturesForAddress: {e}"}
        
    if not sigs_data:
        logger.info("Нових транзакцій не знайдено. Синхронізація завершена.")
        return {"success": True, "new_mints_count": 0}
        
    # Нові транзакції приходять від новіших до старіших.
    # Для інкрементального оновлення `"lastSignature"` має вказувати на НАЙНОВІШУ успішну транзакцію (першу у списку).
    newest_sig = None
    for item in sigs_data:
        if not item.get("err"):
            newest_sig = item.get("signature")
            break
            
    # 3. Обробляємо транзакції від старіших до новіших
    new_mints = set()
    scanned_count = 0
    
    for item in reversed(sigs_data):
        if item.get("err"):
            continue
            
        sig = item.get("signature")
        scanned_count += 1
        time.sleep(0.1) # Дбайливе ставлення до лімітів RPC
        
        try:
            tx_resp = requests.post(
                rpc,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [
                        sig,
                        {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}
                    ]
                },
                headers=headers,
                timeout=15
            )
            tx_resp.raise_for_status()
            tx_data = tx_resp.json().get("result")
            if not tx_data:
                continue
                
            post_balances = tx_data.get("meta", {}).get("postTokenBalances", [])
            for b in post_balances:
                amt = b.get("uiTokenAmount", {})
                mint_addr = b.get("mint")
                if (
                    amt.get("decimals") == 0 
                    and amt.get("amount") == "1" 
                    and mint_addr != COLLECTION_MINT
                ):
                    if mint_addr not in mints and mint_addr not in new_mints:
                        new_mints.add(mint_addr)
                        logger.info(f"Знайдено новий мінт NFT: {mint_addr}")
        except Exception as e:
            logger.error(f"Помилка при зчитуванні транзакції {sig}: {e}")
            # Пропускаємо поодиноку помилку, щоб не блокувати весь процес, спробуємо наступного разу.
            continue

    # 4. Оновлюємо та зберігаємо дані
    if new_mints:
        mints.update(new_mints)
        
    updated_doc = {
        "collection": COLLECTION_MINT,
        "candyMachine": CANDY_MACHINE,
        "generatedAt": datetime.now(timezone.utc).isoformat() + "Z",
        "count": len(mints),
        "mints": sorted(list(mints))
    }
    
    if newest_sig:
        updated_doc["lastSignature"] = newest_sig
    elif last_sig:
        updated_doc["lastSignature"] = last_sig
        
    # Зберігаємо локально у C:\Промт\data
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        MINTS_FILE.write_text(json.dumps(updated_doc, indent=2), encoding="utf-8")
        logger.info(f"Оновлено файл {MINTS_FILE}. Загальна кількість мінтів: {len(mints)}")
    except Exception as e:
        logger.error(f"Не вдалося записати локальний файл мінтів: {e}")
        return {"success": False, "error": f"write file: {e}"}
        
    # Свідомо НЕ дзеркалимо у <SUGAR_PROJECT_PATH>/data. Раніше дзеркалили — а
    # Sugar `snapshot-holders.mjs` писав назад сюди, тож той самий файл мав двох
    # письменників із двох репо. Один раз це вже коштувало бойових даних:
    # `test_holder_sync` через env-дзеркало залив фейкові мінти у C:\\Sugar\\data
    # (фікс 340ef27 — ізоляція в conftest). Обидва проєкти будують цей список із
    # ланцюга самостійно, тож синхронізація не потрібна — лише небезпечна.
    # SUGAR_PROJECT_PATH лишається: ним користується api_server для transfer-nft.mjs.

    # Не забуваємо скинути кеш
    global _mints_cache
    _mints_cache = None
    
    return {
        "success": True,
        "scanned_transactions": scanned_count,
        "new_mints_count": len(new_mints),
        "total_mints_count": len(mints)
    }

