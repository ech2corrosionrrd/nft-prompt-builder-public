"""Білінг конвеєра: SQLite-облік кредитів гаманців + Helio Pay (Base, USDC).

Кредити — внутрішня валюта для покриття витрат на AI API:
- 1 кредит ≈ одна генерація бюджетним двигуном (Flux.1, Stability AI);
- преміум-двигуни OpenAI списують 4 кредити (собівартість у ~4 рази вища).

Поповнення — пакети через Helio Pay (hosted paylink). Streamlit не приймає
вебхуки напряму, тому підтвердження платежів — періодичним опитуванням
API шлюзу (sync_helio_payments); кожна транзакція зараховується рівно один
раз (таблиця payments, tx_id PRIMARY KEY). Для тестів є simulate_payment.

Ця ж логіка згодом переноситься в SaaS-підписки «Взір» (w3ir.io).
"""

import base64
import hashlib
import hmac
import logging
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone

import httpx

from services import db
from services.ai_service import ENGINE_FLUX, ENGINE_GPT_IMAGE, ENGINE_STABILITY
from services.wallet_auth import short_wallet
from storage import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "users.db"
WELCOME_CREDITS = 5
RATE_LIMIT_PER_MINUTE = 10  # дефолт для welcome-only; див. generation_rate_limit_per_minute()
# Час життя nonce для Sign-In: підпис старший за це не приймається (захист від replay)
NONCE_TTL_SECONDS = 600

# Алфавіт base58 (без 0, O, I, l) — для валідації Solana-адрес
_BASE58_ALPHABET = frozenset("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

# ── Тарифна сітка (фінмодель: маржа 60–80 %) ──────────────────────────────────

PACKAGES: dict[str, dict] = {
    "start": {
        "label": "🟢 Старт",
        "usd": 4.99,
        "credits": 100,
        "note": "Низький поріг входу — спробувати сервіс",
        "recommended": False,
    },
    "creator": {
        "label": "🟡 Креатор",
        "usd": 14.99,
        "credits": 400,
        "note": "350 базових + 50 бонусних за обсяг",
        "recommended": True,
    },
    "pro": {
        "label": "🔵 Профі / Колекція",
        "usd": 29.99,
        "credits": 1000,
        "note": "750 базових + 250 бонусних — для матричних дропів",
        "recommended": False,
    },
}

# Вага запиту в кредитах залежно від собівартості двигуна (Draft-рівень)
CREDIT_COSTS: dict[str, int] = {
    ENGINE_GPT_IMAGE: 4,
    ENGINE_STABILITY: 1,
    ENGINE_FLUX: 1,
}

# Final-рівень (ПЛАН_ЯКОСТІ.md § Q1.3): вища якість ⇒ вища собівартість.
# OpenAI hd/high ≈ 2× draft; Flux flux-dev і Stability — 2 кредити.
CREDIT_COSTS_FINAL: dict[str, int] = {
    ENGINE_GPT_IMAGE: 8,
    ENGINE_STABILITY: 2,
    ENGINE_FLUX: 2,
}


def credit_cost(engine: str, final: bool = False) -> int:
    table = CREDIT_COSTS_FINAL if final else CREDIT_COSTS
    return table.get(engine, 2 if final else 1)


# ── База даних (SQLite) ───────────────────────────────────────────────────────

def _migrate_users_schema(conn: sqlite3.Connection) -> None:
    cols = db.table_columns(conn, "users")
    if "verified_at" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN verified_at TEXT")
        # Існуючі користувачі до міграції вважаються підтвердженими.
        conn.execute("UPDATE users SET verified_at = created_at WHERE verified_at IS NULL")
    fe_cols = db.table_columns(conn, "funnel_events")
    if fe_cols and "payload" not in fe_cols:
        conn.execute("ALTER TABLE funnel_events ADD COLUMN payload TEXT")
    # nft_fulfillments: колонки статусу додано пізніше за саму таблицю (reconcile).
    nf_cols = db.table_columns(conn, "nft_fulfillments")
    if nf_cols and "status" not in nf_cols:
        conn.execute("ALTER TABLE nft_fulfillments ADD COLUMN status TEXT NOT NULL DEFAULT 'reserved'")
        conn.execute("ALTER TABLE nft_fulfillments ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE nft_fulfillments ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")


def _connect() -> sqlite3.Connection:
    # Зʼєднання через шар абстракції (services/db.py): SQLite за замовчуванням
    # (mkdir+WAL+timeout, як раніше), Postgres при DATABASE_URL. Схема нижче —
    # ідемпотентна (CREATE TABLE IF NOT EXISTS) і діалект-портована через db.*.
    conn = db.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        " wallet_address TEXT PRIMARY KEY,"
        " credits_balance INTEGER NOT NULL DEFAULT 0,"
        " created_at TEXT NOT NULL,"
        " verified_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS payments ("
        " tx_id TEXT PRIMARY KEY,"
        " wallet_address TEXT NOT NULL,"
        " credits INTEGER NOT NULL,"
        " amount_usd REAL NOT NULL,"
        " created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS transactions ("
        " id " + db.autoinc_pk() + ","
        " wallet_address TEXT NOT NULL,"
        " kind TEXT NOT NULL,"
        " credits INTEGER NOT NULL,"
        " engine TEXT NOT NULL DEFAULT '',"
        " note TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS wallet_nonces ("
        " wallet_address TEXT PRIMARY KEY,"
        " nonce TEXT NOT NULL,"
        " created_at TEXT NOT NULL)"
    )
    # Ідемпотентність + reconcile фулфілменту NFT (мінт/трансфер із сейфу):
    # tx_id платежу — PRIMARY KEY, тож ретрай того самого webhook не запустить
    # мінт удруге (at-most-once). Резерв (status='reserved') ставиться ПЕРЕД
    # запуском subprocess; після завершення → 'completed'/'failed'. Фоновий
    # reconcile добиває 'reserved'/'failed', що зависли (рестарт/збій subprocess).
    conn.execute(
        "CREATE TABLE IF NOT EXISTS nft_fulfillments ("
        " tx_id TEXT PRIMARY KEY,"
        " wallet_address TEXT NOT NULL,"
        " kind TEXT NOT NULL,"
        " detail TEXT NOT NULL DEFAULT '',"
        " status TEXT NOT NULL DEFAULT 'reserved',"
        " attempts INTEGER NOT NULL DEFAULT 0,"
        " created_at TEXT NOT NULL,"
        " updated_at TEXT NOT NULL DEFAULT '')"
    )
    # Реферальна петля (G3.3): хто кого запросив. invitee — PK (один реферер на
    # запрошеного, перший виграє). rewarded_at NULL доти, доки invitee не оплатить
    # уперше — лише тоді нараховується бонус рефереру (анти-Sybil).
    conn.execute(
        "CREATE TABLE IF NOT EXISTS referrals ("
        " invitee_address TEXT PRIMARY KEY,"
        " referrer_address TEXT NOT NULL,"
        " created_at TEXT NOT NULL,"
        " rewarded_at TEXT,"
        " reward_credits INTEGER NOT NULL DEFAULT 0)"
    )
    # Реферал-коди (G3.3): опаковий код → гаманець. У публічній shareable-сторінці
    # світимо КОД, не повну адресу (privacy/анти-leak); код детермінований (HMAC).
    conn.execute(
        "CREATE TABLE IF NOT EXISTS referral_codes ("
        " code TEXT PRIMARY KEY,"
        " wallet_address TEXT NOT NULL,"
        " created_at TEXT NOT NULL)"
    )
    # Денний freemium-ліміт (B3): лічильник генерацій на гаманець за UTC-добу.
    # Ключ (гаманець, день) — анти-abuse стеля поверх вітальних кредитів.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS freemium_usage ("
        " wallet_address TEXT NOT NULL,"
        " day TEXT NOT NULL,"
        " count INTEGER NOT NULL DEFAULT 0,"
        " PRIMARY KEY (wallet_address, day))"
    )
    # Події воронки білдера (НЕ кредитні транзакції): export-бандл тощо. Потрібні
    # для вимірювання конверсії generate→export — термінальної події продукту,
    # якої транзакції-debit не бачать (див. stats.funnel).
    conn.execute(
        "CREATE TABLE IF NOT EXISTS funnel_events ("
        " wallet_address TEXT NOT NULL,"
        " event TEXT NOT NULL,"
        " created_at TEXT NOT NULL)"
    )
    _migrate_users_schema(conn)
    conn.commit()
    return conn


def normalize_wallet(wallet: str) -> str:
    """Базова валідація адреси (EVM 0x… або Solana base58)."""
    w = (wallet or "").strip()
    if w.startswith("0x"):
        if len(w) != 42 or not all(c in "0123456789abcdefABCDEF" for c in w[2:]):
            raise ValueError("Некоректна EVM-адреса (очікується 0x + 40 hex-символів).")
        return w.lower()
    if 32 <= len(w) <= 44 and all(c in _BASE58_ALPHABET for c in w):
        return w  # Solana base58 — регістр значущий
    raise ValueError("Некоректна адреса гаманця.")


def ensure_user(wallet: str, *, grant_welcome: bool = False) -> tuple[bool, int]:
    """Реєструє гаманець без вітальних кредитів (для платежів Helio тощо).

    Вітальні кредити — лише через complete_wallet_sign_in() після підпису.
    Повертає (is_new, balance).
    """
    wallet = normalize_wallet(wallet)
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT credits_balance FROM users WHERE wallet_address = ?", (wallet,)
        ).fetchone()
        if row is not None:
            return False, int(row[0])
        if grant_welcome:
            from services.wallet_auth import welcome_balance_ok

            ok, _msg = welcome_balance_ok(wallet)
            welcome = WELCOME_CREDITS if ok else 0
        else:
            welcome = 0
        conn.execute(
            "INSERT INTO users (wallet_address, credits_balance, created_at) VALUES (?, ?, ?)",
            (wallet, welcome, datetime.now(timezone.utc).isoformat()),
        )
        if welcome:
            log_transaction(wallet, "welcome", welcome, note="Вітальні кредити", conn=conn)
        conn.commit()
        return True, welcome


def is_wallet_verified(wallet: str) -> bool:
    """Чи пройдено Sign-In з підписом (захист від підміни адреси)."""
    wallet = normalize_wallet(wallet)
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT verified_at FROM users WHERE wallet_address = ?", (wallet,)
        ).fetchone()
    return bool(row and row[0])


def complete_wallet_sign_in(wallet: str) -> tuple[bool, int]:
    """Після перевірки підпису: позначити verified, видати welcome новому гаманцю.

    Повертає (is_new, balance).
    """
    from services.wallet_auth import welcome_balance_ok

    wallet = normalize_wallet(wallet)
    now = datetime.now(timezone.utc).isoformat()
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT credits_balance, verified_at FROM users WHERE wallet_address = ?",
            (wallet,),
        ).fetchone()
        if row is not None:
            balance = int(row[0])
            if not row[1]:
                conn.execute(
                    "UPDATE users SET verified_at = ? WHERE wallet_address = ?",
                    (now, wallet),
                )
                conn.commit()
            return False, balance

        ok, _msg = welcome_balance_ok(wallet)
        welcome = WELCOME_CREDITS if ok else 0
        conn.execute(
            "INSERT INTO users (wallet_address, credits_balance, created_at, verified_at)"
            " VALUES (?, ?, ?, ?)",
            (wallet, welcome, now, now),
        )
        if welcome:
            log_transaction(wallet, "welcome", welcome, note="Вітальні кредити", conn=conn)
        conn.commit()
        return True, welcome


def store_wallet_nonce(wallet: str, nonce: str) -> None:
    wallet = normalize_wallet(wallet)
    with closing(_connect()) as conn, conn:
        conn.execute(
            db.insert_or_replace(
                "INSERT INTO wallet_nonces (wallet_address, nonce, created_at) VALUES (?, ?, ?)",
                conflict=("wallet_address",),
                update=("nonce", "created_at"),
            ),
            (wallet, nonce, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_wallet_nonce(wallet: str) -> str | None:
    wallet = normalize_wallet(wallet)
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT nonce FROM wallet_nonces WHERE wallet_address = ?", (wallet,)
        ).fetchone()
        return str(row[0]) if row else None


def consume_wallet_nonce(wallet: str, max_age_seconds: int = NONCE_TTL_SECONDS) -> str | None:
    """Повертає nonce і одразу видаляє його (one-time use) — захист від replay.

    Повертає None, якщо nonce немає або він старший за max_age_seconds.
    """
    wallet = normalize_wallet(wallet)
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT nonce, created_at FROM wallet_nonces WHERE wallet_address = ?", (wallet,)
        ).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM wallet_nonces WHERE wallet_address = ?", (wallet,))
        conn.commit()
    nonce, created_at = str(row[0]), row[1]
    if max_age_seconds is not None:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(created_at)).total_seconds()
        except (ValueError, TypeError):
            return None
        if age > max_age_seconds:
            return None
    return nonce


def log_transaction(
    wallet: str,
    kind: str,
    credits: int,
    engine: str = "",
    note: str = "",
    conn: sqlite3.Connection | None = None,
) -> None:
    wallet = normalize_wallet(wallet)
    sql = (
        "INSERT INTO transactions (wallet_address, kind, credits, engine, note, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)"
    )
    args = (wallet, kind, credits, engine, note, datetime.now(timezone.utc).isoformat())
    if conn is not None:
        conn.execute(sql, args)
    else:
        with closing(_connect()) as c, c:
            c.execute(sql, args)
            c.commit()


def list_transactions(wallet: str, limit: int = 30) -> list[dict]:
    wallet = normalize_wallet(wallet)
    with closing(_connect()) as conn, conn:
        rows = conn.execute(
            "SELECT kind, credits, engine, note, created_at FROM transactions"
            " WHERE wallet_address = ? ORDER BY id DESC LIMIT ?",
            (wallet, limit),
        ).fetchall()
    return [
        {"kind": r[0], "credits": r[1], "engine": r[2], "note": r[3], "created_at": r[4][:19]}
        for r in rows
    ]


def generation_rate_limit_per_minute(wallet: str) -> int | None:
    """Стеля генерацій/хв. None — поповнений гаманець (лише кредити + throttling провайдера)."""
    from services import freemium

    try:
        wallet = normalize_wallet(wallet)
    except ValueError:
        return _configured_generation_rate_limit()
    if freemium.is_exempt(wallet):
        return None
    return _configured_generation_rate_limit()


def _configured_generation_rate_limit() -> int:
    try:
        return max(1, int(os.environ.get("GENERATION_RATE_LIMIT_PER_MINUTE") or str(RATE_LIMIT_PER_MINUTE)))
    except (TypeError, ValueError):
        return RATE_LIMIT_PER_MINUTE


def check_generation_rate(wallet: str, limit: int | None = None) -> bool:
    """True якщо ліміт генерацій за хвилину не перевищено."""
    if limit is None:
        limit = generation_rate_limit_per_minute(wallet)
    if limit is None:
        return True
    wallet = normalize_wallet(wallet)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM transactions"
            " WHERE wallet_address = ? AND kind = 'debit'"
            " AND created_at >= ?",
            (wallet, cutoff),
        ).fetchone()
    return int(row[0]) < limit if row else True


def seconds_until_generation_slot(
    wallet: str, limit: int | None = None,
) -> float:
    """Секунд до появи слоту rate-limit (0 — можна генерувати зараз)."""
    if limit is None:
        limit = generation_rate_limit_per_minute(wallet)
    if limit is None or check_generation_rate(wallet, limit):
        return 0.0
    wallet = normalize_wallet(wallet)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT MIN(created_at) FROM transactions"
            " WHERE wallet_address = ? AND kind = 'debit'"
            " AND created_at >= ?",
            (wallet, cutoff),
        ).fetchone()
    if not row or not row[0]:
        return 0.0
    oldest = datetime.fromisoformat(row[0])
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    unlock_at = oldest + timedelta(minutes=1)
    return max(0.0, (unlock_at - datetime.now(timezone.utc)).total_seconds())


def wait_for_generation_rate(
    wallet: str,
    limit: int | None = None,
    max_wait: float = 7200.0,
) -> bool:
    """Чекає слот rate-limit між хвилями пакетної генерації."""
    if limit is None:
        limit = generation_rate_limit_per_minute(wallet)
    if limit is None:
        return True
    deadline = time.monotonic() + max_wait
    while not check_generation_rate(wallet, limit):
        if time.monotonic() >= deadline:
            return False
        delay = min(
            seconds_until_generation_slot(wallet, limit), 5.0,
            max(0.0, deadline - time.monotonic()),
        )
        if delay > 0:
            time.sleep(delay)
    return True


def get_balance(wallet: str) -> int:
    wallet = normalize_wallet(wallet)
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT credits_balance FROM users WHERE wallet_address = ?", (wallet,)
        ).fetchone()
        return int(row[0]) if row else 0


def add_credits(wallet: str, amount: int) -> int:
    """Нараховує кредити (після успішної оплати). Повертає новий баланс."""
    if amount <= 0:
        raise ValueError("Сума кредитів має бути додатною.")
    wallet = normalize_wallet(wallet)
    ensure_user(wallet)
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE users SET credits_balance = credits_balance + ? WHERE wallet_address = ?",
            (amount, wallet),
        )
        row = conn.execute(
            "SELECT credits_balance FROM users WHERE wallet_address = ?", (wallet,)
        ).fetchone()
        return int(row[0])


def grant_credits(wallet: str, amount: int, *, note: str = "Ручний грант") -> int:
    """Ручне нарахування кредитів гаманцю (адмін-дія). Логує транзакцію 'grant'.

    На відміну від record_payment — НЕ ідемпотентне: кожен виклик додає суму
    (це навмисна разова операція оператора, не звіряння платежу). verified не
    ставить — витрата кредитів усе одно потребує входу підписом. Працює і для
    EVM, і для Solana. Атомарно (UPDATE + лог в одній транзакції). Повертає баланс.
    """
    if amount <= 0:
        raise ValueError("Сума гранту має бути додатною.")
    wallet = normalize_wallet(wallet)
    ensure_user(wallet)
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE users SET credits_balance = credits_balance + ? WHERE wallet_address = ?",
            (amount, wallet),
        )
        log_transaction(wallet, "grant", amount, note=note, conn=conn)
        row = conn.execute(
            "SELECT credits_balance FROM users WHERE wallet_address = ?", (wallet,)
        ).fetchone()
        conn.commit()
    return int(row[0]) if row else 0


def deduct_credits(wallet: str, amount: int = 1, *, engine: str = "", note: str = "") -> bool:
    """Атомарно списує кредити після успішної генерації.

    Повертає False, якщо гаманець не підтверджений підписом або балансу не вистачає.
    """
    if amount <= 0:
        raise ValueError("Сума списання має бути додатною.")
    wallet = normalize_wallet(wallet)
    if not is_wallet_verified(wallet):
        return False
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "UPDATE users SET credits_balance = credits_balance - ?"
            " WHERE wallet_address = ? AND credits_balance >= ?",
            (amount, wallet, amount),
        )
        if cur.rowcount == 1:
            log_transaction(wallet, "debit", -amount, engine=engine, note=note, conn=conn)
            conn.commit()
            return True
        return False


def refund_credits(wallet: str, amount: int = 1, *, engine: str = "", note: str = "") -> int:
    """Повертає зарезервовані кредити, якщо генерація не вдалася. Повертає новий баланс."""
    if amount <= 0:
        raise ValueError("Сума повернення має бути додатною.")
    wallet = normalize_wallet(wallet)
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE users SET credits_balance = credits_balance + ? WHERE wallet_address = ?",
            (amount, wallet),
        )
        log_transaction(wallet, "refund", amount, engine=engine, note=note, conn=conn)
        row = conn.execute(
            "SELECT credits_balance FROM users WHERE wallet_address = ?", (wallet,)
        ).fetchone()
        conn.commit()
        return int(row[0]) if row else 0


def record_payment(tx_id: str, wallet: str, credits: int, amount_usd: float) -> bool:
    """Зараховує платіж рівно один раз. False — транзакція вже оброблена."""
    wallet = normalize_wallet(wallet)
    ensure_user(wallet)
    with closing(_connect()) as conn, conn:
        try:
            conn.execute(
                "INSERT INTO payments (tx_id, wallet_address, credits, amount_usd, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (tx_id, wallet, credits, amount_usd, datetime.now(timezone.utc).isoformat()),
            )
        except sqlite3.IntegrityError:
            return False
        conn.execute(
            "UPDATE users SET credits_balance = credits_balance + ? WHERE wallet_address = ?",
            (credits, wallet),
        )
        log_transaction(wallet, "payment", credits, note=f"${amount_usd}", conn=conn)
        conn.commit()
    # Сповіщення в Telegram — ПІСЛЯ коміту (не блокує транзакцію; помилки тихі).
    _notify_payment_credited(wallet, credits, amount_usd, get_balance(wallet))
    # Реферальний бонус — після успішного платежу (анти-Sybil: лише за оплату).
    reward_referral(wallet)
    return True


def claim_nft_fulfillment(tx_id: str, wallet: str, kind: str, detail: str = "") -> bool:
    """Резервує обробку мінту/трансферу NFT рівно один раз (at-most-once).

    True — цю транзакцію (`tx_id`) ще не обробляли, викликач МАЄ запустити
    мінт/трансфер. False — транзакція вже зарезервована (ретрай webhook або
    порожній `tx_id`), запускати мінт НЕ можна. Резерв ставиться ДО запуску
    subprocess, тож паралельна повторна доставка webhook блокується одразу.
    """
    tx = (tx_id or "").strip()
    if not tx:
        # Без ідентифікатора гарантувати at-most-once неможливо — безпечніше
        # відмовити (fail-closed), ніж ризикнути другим безкоштовним мінтом.
        return False
    now = datetime.now(timezone.utc).isoformat()
    with closing(_connect()) as conn, conn:
        try:
            conn.execute(
                "INSERT INTO nft_fulfillments"
                " (tx_id, wallet_address, kind, detail, status, attempts, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'reserved', 0, ?, ?)",
                (tx, wallet, kind, detail, now, now),
            )
        except sqlite3.IntegrityError:
            return False
    return True


def mark_fulfillment_done(tx_id: str) -> None:
    """Позначає фулфілмент як завершений (subprocess повернув успіх)."""
    tx = (tx_id or "").strip()
    if not tx:
        return
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE nft_fulfillments SET status='completed', updated_at=? WHERE tx_id=?",
            (datetime.now(timezone.utc).isoformat(), tx),
        )


def mark_fulfillment_failed(tx_id: str) -> None:
    """Позначає спробу фулфілменту як невдалу (+1 attempt) — reconcile повторить."""
    tx = (tx_id or "").strip()
    if not tx:
        return
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE nft_fulfillments SET status='failed', attempts=attempts+1, updated_at=?"
            " WHERE tx_id=?",
            (datetime.now(timezone.utc).isoformat(), tx),
        )


def pending_fulfillments(stale_seconds: int = 300, max_attempts: int = 5) -> list[dict]:
    """Фулфілменти, що зависли: status reserved/failed, не старіші за max_attempts,
    останнє оновлення давніше за stale_seconds. Джерело для reconcile-циклу.

    `reserved`, що старший за stale_seconds — субпроцес не встиг позначити
    завершення (рестарт/крах між ACK і mark). `failed` — subprocess повернув
    помилку. Обидва варті повтору, доки attempts < max_attempts.
    """
    cutoff = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - max(0, stale_seconds), tz=timezone.utc
    ).isoformat()
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT tx_id, wallet_address, kind, detail, status, attempts FROM nft_fulfillments"
            " WHERE status IN ('reserved','failed') AND attempts < ? AND updated_at < ?"
            " ORDER BY updated_at ASC",
            (max_attempts, cutoff),
        ).fetchall()
    return [
        {"tx_id": r[0], "wallet": r[1], "kind": r[2], "detail": r[3],
         "status": r[4], "attempts": r[5]}
        for r in rows
    ]


def known_fulfillment_tx_ids() -> set[str]:
    """Усі tx_id у ledger фулфілменту (будь-який статус) — для звірки з Helio.

    Case A (webhook взагалі не дійшов) = оплата є в Helio, але tx_id немає ТУТ.
    """
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT tx_id FROM nft_fulfillments").fetchall()
    return {r[0] for r in rows}


def nft_fulfillment_counts() -> dict[str, int]:
    """Розподіл фулфілментів за статусом (reserved/completed/failed) — для звіту."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) FROM nft_fulfillments GROUP BY status"
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def record_funnel_event(wallet: str, event: str, payload: dict | None = None) -> bool:
    """Реєструє подію воронки білдера (напр. 'export') для метрики конверсії.

    Не кредитна транзакція — окрема легка таблиця. **Fail-open**: збій обліку не
    має ламати UX (експорт-бандл уже зібрано). Гаманець нормалізуємо так само, як
    білінг (`normalize_wallet`), щоб збігалося з first_debit-гаманцями у воронці.

    payload — опційний JSON (напр. avg_rating для curator_save).
    """
    import json

    ev = (event or "").strip()
    if not (wallet or "").strip() or not ev:
        return False
    try:
        w = normalize_wallet(wallet)  # у try: некоректна адреса → fail-open (False)
        payload_json = json.dumps(payload) if payload else None
        with closing(_connect()) as conn, conn:
            conn.execute(
                "INSERT INTO funnel_events (wallet_address, event, created_at, payload) "
                "VALUES (?, ?, ?, ?)",
                (w, ev, datetime.now(timezone.utc).isoformat(), payload_json),
            )
        return True
    except Exception:
        return False


def _notify_payment_credited(wallet: str, credits: int, amount_usd: float, balance: int) -> None:
    """Шле в Telegram повідомлення про зарахований платіж (якщо бот налаштовано)."""
    from services.notify import send_telegram

    send_telegram(
        f"💰 Оплата зарахована\n"
        f"+{credits} кредитів (${amount_usd})\n"
        f"Гаманець: {short_wallet(wallet)}\n"
        f"Баланс: {balance}"
    )


# ── Реферальна петля (G3.3) ───────────────────────────────────────────────────

def referral_bonus_credits() -> int:
    """Бонус рефереру за ПЕРШУ оплату запрошеного (ліниво з env, дефолт 50).

    Вимикається значенням REFERRAL_BONUS_CREDITS=0. Читається у момент виклику
    (після load_dotenv), не як module-level константа.
    """
    try:
        return max(0, int(os.getenv("REFERRAL_BONUS_CREDITS") or "50"))
    except ValueError:
        return 50


def _referral_secret() -> str:
    return (os.getenv("AUTH_SESSION_SECRET") or "").strip()


def referral_code_for(wallet: str) -> str:
    """Детермінований опаковий реферал-код для гаманця (HMAC).

    Один гаманець → стабільний код; з коду гаманець НЕ вивести (HMAC), тож
    публічна shareable-сторінка несе код, не адресу (privacy/анти-leak).
    Зворотну мапу зберігаємо у `referral_codes` для resolve_referral_code.
    Fail-closed: без AUTH_SESSION_SECRET кодів не видаємо (повертає '').
    """
    secret = _referral_secret()
    if not secret:
        return ""
    try:
        w = normalize_wallet(wallet)
    except ValueError:
        return ""
    digest = hmac.new(secret.encode(), b"referral:" + w.encode(), hashlib.sha256).digest()
    code = base64.b32encode(digest).decode().rstrip("=").lower()[:10]
    with closing(_connect()) as conn, conn:
        conn.execute(
            db.insert_or_ignore(
                "INSERT INTO referral_codes (code, wallet_address, created_at)"
                " VALUES (?, ?, ?)"
            ),
            (code, w, datetime.now(timezone.utc).isoformat()),
        )
    return code


def resolve_referral_code(code: str) -> str | None:
    """Реферал-код → гаманець (None, якщо невідомий)."""
    code = (code or "").strip().lower()
    if not code:
        return None
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT wallet_address FROM referral_codes WHERE code = ?", (code,)
        ).fetchone()
    return row[0] if row else None


def resolve_referrer(ref: str) -> str:
    """?ref=<code|wallet> → гаманець реферера ('' якщо нерозпізнано).

    Спершу пробуємо як наш реферал-код; фолбек — прямий ?ref=<wallet>
    (зворотна сумісність зі старими посиланнями).
    """
    ref = (ref or "").strip()
    if not ref:
        return ""
    wallet = resolve_referral_code(ref)
    if wallet:
        return wallet
    try:
        return normalize_wallet(ref)
    except ValueError:
        return ""


def record_referral(invitee: str, referrer: str) -> bool:
    """Прив'язує реферера (з ?ref=<referrer>) до запрошеного `invitee`.

    Бонус тут НЕ нараховується — лише після першої оплати invitee (анти-Sybil:
    інакше фарм вітальних кредитів реєстраціями). Повертає True, якщо зв'язок
    створено. Не діє, якщо: адреса некоректна, самореферал, invitee вже має
    реферера, або invitee вже платив (не можна заднім числом привласнити клієнта).
    """
    try:
        invitee = normalize_wallet(invitee)
        referrer = normalize_wallet(referrer)
    except ValueError:
        return False
    if invitee == referrer:
        return False
    with closing(_connect()) as conn, conn:
        paid = conn.execute(
            "SELECT 1 FROM payments WHERE wallet_address = ? LIMIT 1", (invitee,)
        ).fetchone()
        if paid:
            return False
        cur = conn.execute(
            db.insert_or_ignore(
                "INSERT INTO referrals"
                " (invitee_address, referrer_address, created_at) VALUES (?, ?, ?)"
            ),
            (invitee, referrer, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.rowcount == 1


def reward_referral(invitee: str) -> bool:
    """Нараховує реферальний бонус рефереру після першої оплати invitee.

    Ідемпотентно: «займає» слот (UPDATE rewarded_at WHERE rewarded_at IS NULL)
    перед нарахуванням, тож повторні/паралельні платежі дають рівно один бонус.
    Грант — окремою транзакцією (grant_credits), поза транзакцією платежу.
    Повертає True, якщо бонус нараховано цим викликом.
    """
    bonus = referral_bonus_credits()
    if bonus <= 0:
        return False
    try:
        invitee = normalize_wallet(invitee)
    except ValueError:
        return False
    now = datetime.now(timezone.utc).isoformat()
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT referrer_address FROM referrals"
            " WHERE invitee_address = ? AND rewarded_at IS NULL", (invitee,)
        ).fetchone()
        if not row:
            return False
        referrer = str(row[0])
        cur = conn.execute(
            "UPDATE referrals SET rewarded_at = ?, reward_credits = ?"
            " WHERE invitee_address = ? AND rewarded_at IS NULL",
            (now, bonus, invitee),
        )
        if cur.rowcount != 1:
            return False  # уже нагороджено паралельно
        conn.commit()
    grant_credits(referrer, bonus, note=f"Реферальний бонус за {short_wallet(invitee)}")
    _notify_referral_reward(referrer, invitee, bonus)
    return True


def _notify_referral_reward(referrer: str, invitee: str, bonus: int) -> None:
    """Шле в Telegram оператору сповіщення про нарахований реферальний бонус."""
    from services.notify import send_telegram

    send_telegram(
        f"🎁 Реферальний бонус\n"
        f"+{bonus} кредитів рефереру {short_wallet(referrer)}\n"
        f"за першу оплату {short_wallet(invitee)}"
    )


# ── Helio Pay ─────────────────────────────────────────────────────────────────

# Зараховуємо лише з явним успішним статусом (без статусу — пропускаємо).
_SUCCESS_STATUSES = frozenset({"SUCCESS", "PAID", "COMPLETED", "CONFIRMED", "SETTLED"})

HELIO_PAY_BASE = "https://app.hel.io/pay/"
HELIO_TX_URL = "https://api.hel.io/v1/export/payments"
HELIO_TIMEOUT = 60.0

_PAYLINK_ENV = {
    "start": "HELIO_PAYLINK_START",
    "creator": "HELIO_PAYLINK_CREATOR",
    "pro": "HELIO_PAYLINK_PRO",
}
_PAYLINK_HEX_RE = re.compile(r"^[0-9a-f]+$")


def sanitize_paylink_id(raw: str) -> str:
    """Нормалізує Helio paylinkId: trim, lower-case hex, типова опечатка T→0.

    Helio paylink — hex-рядок; невалідні символи (напр. «T» замість «0») ламають
    hosted URL і webhook-мапу. Консервативна авто-правка лише для T між hex-цифрами.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    if _PAYLINK_HEX_RE.fullmatch(s):
        return s.lower()
    # Поширена опечатка в .env: «T0» замість «0» (напр. …01T0b… → …010b…).
    corrected = re.sub(r"(?i)T0", "0", s)
    if _PAYLINK_HEX_RE.fullmatch(corrected):
        fixed = corrected.lower()
        if fixed != s.lower():
            logger.warning("Helio paylink auto-corrected T0→0: %r → %r", s, fixed)
        return fixed
    corrected = re.sub(r"(?<=[0-9a-fA-F])T(?=[0-9a-fA-F])", "0", s)
    if _PAYLINK_HEX_RE.fullmatch(corrected):
        fixed = corrected.lower()
        if fixed != s.lower():
            logger.warning("Helio paylink auto-corrected T→0: %r → %r", s, fixed)
        return fixed
    return s


def paylink_id_valid(paylink_id: str) -> bool:
    """Чи paylinkId — валідний hex (після sanitize)."""
    return bool(paylink_id) and bool(_PAYLINK_HEX_RE.fullmatch(paylink_id))


def _env_paylink(package_id: str) -> str:
    env_name = _PAYLINK_ENV.get(package_id, "")
    return sanitize_paylink_id(os.environ.get(env_name, "")) if env_name else ""


def helio_paylink_url(package_id: str) -> str | None:
    """Hosted-сторінка оплати пакета (кнопка/iframe у UI)."""
    paylink_id = _env_paylink(package_id)
    if not paylink_id:
        return None
    if not paylink_id_valid(paylink_id):
        logger.error("Invalid HELIO paylink for %s: %r", package_id, paylink_id)
        return None
    return f"{HELIO_PAY_BASE}{paylink_id}"


def helio_keys() -> tuple[str, str] | None:
    api_key = os.environ.get("HELIO_API_KEY", "")
    secret = os.environ.get("HELIO_API_SECRET", "")
    return (api_key, secret) if api_key and secret else None


def paylink_to_package_map() -> dict[str, str]:
    """paylinkId → package_id (start / creator / pro).

    Ключі — сире значення з .env і санітизований варіант (якщо відрізняється),
    щоб webhook і sync працювали і з Helio-id, і з тестовими plink-*.
    """
    out: dict[str, str] = {}
    for package_id in _PAYLINK_ENV:
        env_name = _PAYLINK_ENV[package_id]
        raw = (os.environ.get(env_name, "") or "").strip()
        if not raw:
            continue
        out[raw] = package_id
        cleaned = sanitize_paylink_id(raw)
        if cleaned and cleaned != raw:
            out[cleaned] = package_id
    return out


def package_for_paylink(paylink_id: str) -> str | None:
    pid = str(paylink_id or "").strip()
    if not pid:
        return None
    m = paylink_to_package_map()
    if pid in m:
        return m[pid]
    return m.get(sanitize_paylink_id(pid))


def process_helio_webhook_payload(payload: dict) -> tuple[bool, str]:
    """Обробляє одну подію Helio webhook. Повертає (зараховано, повідомлення)."""
    if not isinstance(payload, dict):
        return False, "Invalid payload"

    paylink_id = str(
        payload.get("paylinkId") or payload.get("paylink")
        or (payload.get("meta") or {}).get("paylinkId") or ""
    )
    package_id = package_for_paylink(paylink_id)
    if not package_id:
        return False, f"Unknown paylink: {paylink_id or '(empty)'}"

    package = PACKAGES[package_id]
    credited_any = False
    for payment in extract_payments([payload]):
        try:
            wallet = normalize_wallet(payment["wallet"])
        except ValueError:
            continue
        if record_payment(payment["tx_id"], wallet, package["credits"], package["usd"]):
            credited_any = True
    if credited_any:
        return True, f"Credited {package['credits']} credits ({package_id})"
    return False, "Already processed or no wallet in payload"


def fetch_helio_payments(paylink_id: str, api_key: str, secret: str) -> list[dict]:
    """Опитує API Helio щодо платежів конкретного paylink (заміна вебхука)."""
    response = httpx.get(
        HELIO_TX_URL,
        params={"paylinkId": paylink_id, "apiKey": api_key},
        headers={"Authorization": f"Bearer {secret}"},
        timeout=HELIO_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else data.get("payments", [])


def extract_payments(raw: list[dict]) -> list[dict]:
    """Толерантний парсер відповіді Helio → [{tx_id, wallet, paylink}].

    Формат експорту може відрізнятися між версіями API, тому id, гаманець
    відправника та paylink платежу шукаються за кількома відомими ключами.
    `paylink` — реальний paymentRequestId платежу (порожній, якщо API його не
    повертає); потрібен, бо експорт-ендпоінт не фільтрує за paylinkId у запиті.
    """
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        status = str(
            item.get("transactionStatus") or item.get("status")
            or item.get("paymentStatus") or item.get("state")
            or meta.get("transactionStatus") or meta.get("status") or ""
        ).strip().upper()
        if status not in _SUCCESS_STATUSES:
            continue
        tx_id = str(
            item.get("id") or item.get("transactionId") or item.get("transaction")
            or meta.get("id") or ""
        )
        wallet = str(
            item.get("senderPublicKey") or item.get("from") or meta.get("senderPK") or ""
        )
        paylink = str(
            item.get("paymentRequestId") or item.get("paylinkId")
            or item.get("paylink") or meta.get("paylinkId") or ""
        ).strip()
        if tx_id and wallet:
            result.append({"tx_id": tx_id, "wallet": wallet, "paylink": paylink})
    return result


def sync_helio_payments(target_wallet: str | None = None) -> tuple[int, int]:
    """Опитує всі налаштовані paylink-и та зараховує нові платежі.

    Повертає (нових_транзакцій, нараховано_кредитів). Якщо заданий
    target_wallet — зараховуються лише його платежі.
    """
    keys = helio_keys()
    if not keys:
        raise RuntimeError("Не задані HELIO_API_KEY / HELIO_API_SECRET у .env або Secrets.")
    api_key, secret = keys
    target = normalize_wallet(target_wallet) if target_wallet else None
    new_tx, credited = 0, 0
    for package_id, env_name in _PAYLINK_ENV.items():
        paylink_raw = os.environ.get(env_name, "")
        paylink_id = sanitize_paylink_id(paylink_raw)
        if not paylink_id:
            continue
        package = PACKAGES[package_id]
        for payment in extract_payments(fetch_helio_payments(paylink_raw, api_key, secret)):
            # Експорт Helio повертає ВСІ платежі незалежно від paylinkId у
            # запиті, тож звіряємо реальний paymentRequestId платежу з поточним
            # paylink. Без цього платіж за «Креатор»/«Профі» нарахувався б за
            # першим пакетом у переліку (start) — занижені кредити.
            pl = payment.get("paylink") or ""
            if pl and pl != paylink_id and pl != paylink_raw.strip():
                continue
            try:
                wallet = normalize_wallet(payment["wallet"])
            except ValueError:
                continue
            if target and wallet != target:
                continue
            if record_payment(payment["tx_id"], wallet, package["credits"], package["usd"]):
                new_tx += 1
                credited += package["credits"]
    # Маркер часу для адмін-панелі (ADM-C). Лінивий імпорт — щоб не зв'язувати
    # низькорівневий білінг з UI-support-модулем на старті; помилки проковтуються.
    from services.ops_status import write_reconcile_marker
    write_reconcile_marker()
    return new_tx, credited


def reconcile_payments_safe(target_wallet: str | None = None) -> tuple[int, int]:
    """Звіряє платежі з Helio, НЕ кидаючи винятків — для фонового циклу та cron.

    На відміну від sync_helio_payments, проковтує будь-яку помилку (відсутні
    ключі, мережа, 5xx Helio) і пише її в лог, повертаючи (0, 0). Це гарантує,
    що періодичне звіряння ніколи не валить процес-носій (api_server чи Task
    Scheduler). Нарахування лишається ідемпотентним (payments.tx_id PK).
    """
    if not helio_keys():
        logger.warning("Helio reconcile пропущено: не задані HELIO_API_KEY / HELIO_API_SECRET")
        return 0, 0
    try:
        new_tx, credited = sync_helio_payments(target_wallet)
    except Exception as exc:  # noqa: BLE001 — фон не має падати через збій Helio/мережі
        logger.warning("Helio reconcile не вдалося: %s: %s", type(exc).__name__, exc)
        return 0, 0
    if new_tx:
        logger.info("Helio reconcile: %d нових транзакцій, нараховано %d кредитів", new_tx, credited)
    else:
        logger.debug("Helio reconcile: нових платежів немає")
    return new_tx, credited


def sim_payments_allowed() -> bool:
    """Чи дозволена імітація платежів (dev/test; заблоковано в production)."""
    if os.environ.get("ENABLE_SIM_PAYMENTS", "0") != "1":
        return False
    env = os.environ.get("APP_ENV", os.environ.get("ENVIRONMENT", "")).strip().lower()
    return env not in ("production", "prod")


def simulate_payment(wallet: str, package_id: str) -> int:
    """Імітація успішного відгуку шлюзу (для тестів/розробки). Повертає баланс."""
    if not sim_payments_allowed():
        raise RuntimeError("simulate_payment вимкнено (ENABLE_SIM_PAYMENTS або production).")
    package = PACKAGES[package_id]
    record_payment(f"sim-{uuid.uuid4().hex}", wallet, package["credits"], package["usd"])
    return get_balance(wallet)
