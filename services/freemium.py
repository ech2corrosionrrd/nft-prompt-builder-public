"""B3 — Денний freemium-ліміт на гаманець (ПЛАН_ЗАПОЗИЧЕНЬ.md).

Опційний другий ремінь для welcome-only гаманців (без Helio/grant). За замовчуванням
**вимкнено** (`FREEMIUM_DAILY_LIMIT=0`): при `WELCOME_CREDITS=5` реальну стелю задає
баланс кредитів + rate 10/хв + content-safety. Увімкни (напр. 15–30) лише якщо
підвищиш вітальний пакет або побачиш фарм без поповнення.

Чисті функції без Streamlit; лічильник — у `users.db` (таблиця `freemium_usage`,
ключ `wallet+UTC-дата`). Гаманці з поповненням (Helio `payments` або
`transactions.kind=grant`) **звільнені**.

Landmines: UTC-дата (не локальна); **fail-open** при помилці БД (не блокувати
легітимного користувача через збій сховища).
"""

from __future__ import annotations

import logging
import os
from contextlib import closing
from datetime import datetime, timezone

from services import db, payment_service

logger = logging.getLogger(__name__)


def daily_limit() -> int:
    """Стеля генерацій на гаманець за UTC-добу. 0/відсутнє/некоректне = вимкнено."""
    try:
        return max(0, int(os.environ.get("FREEMIUM_DAILY_LIMIT") or "0"))
    except (TypeError, ValueError):
        return 0


def _today() -> str:
    """Поточна UTC-дата (YYYY-MM-DD) — ключ доби, незалежний від таймзони хоста."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _freemium_exempt(conn, wallet: str) -> bool:
    """Звільнені від денної стелі: Helio-платники та гаманці з grant/popовненням."""
    if conn.execute(
        "SELECT 1 FROM payments WHERE wallet_address = ? LIMIT 1", (wallet,)
    ).fetchone():
        return True
    row = conn.execute(
        "SELECT 1 FROM transactions WHERE wallet_address = ? AND kind IN ('grant', 'payment')"
        " LIMIT 1",
        (wallet,),
    ).fetchone()
    return row is not None


def is_exempt(wallet: str) -> bool:
    """Чи не застосовується денна freemium-стеля (поповнення є). Fail-open → True."""
    try:
        wallet = payment_service.normalize_wallet(wallet)
    except ValueError:
        return True
    try:
        with closing(payment_service._connect()) as conn:
            return _freemium_exempt(conn, wallet)
    except Exception:  # noqa: BLE001 — fail-open
        logger.warning("freemium.is_exempt: збій БД, пропускаю", exc_info=True)
        return True


def usage_today(wallet: str) -> int:
    """Скільки генерацій гаманець зробив сьогодні (UTC). Fail-open → 0."""
    try:
        wallet = payment_service.normalize_wallet(wallet)
    except ValueError:
        return 0
    try:
        with closing(payment_service._connect()) as conn:
            row = conn.execute(
                "SELECT count FROM freemium_usage WHERE wallet_address = ? AND day = ?",
                (wallet, _today()),
            ).fetchone()
            return int(row[0]) if row else 0
    except Exception:  # noqa: BLE001 — fail-open: збій сховища не блокує користувача
        logger.warning("freemium.usage_today: збій БД, повертаю 0", exc_info=True)
        return 0


def check_available(wallet: str) -> tuple[bool, int | None]:
    """Чи доступна ще генерація сьогодні. Повертає (allowed, remaining|None).

    remaining=None коли ліміт вимкнено або гаманець звільнений (був топ-ап).
    Fail-open: будь-який збій → (True, None).
    """
    limit = daily_limit()
    if limit <= 0:
        return True, None
    try:
        wallet = payment_service.normalize_wallet(wallet)
    except ValueError:
        return True, None  # некоректну адресу відсіє пізніший шар, тут не блокуємо
    try:
        with closing(payment_service._connect()) as conn:
            if _freemium_exempt(conn, wallet):
                return True, None  # поповнені гаманці без денної стелі
            row = conn.execute(
                "SELECT count FROM freemium_usage WHERE wallet_address = ? AND day = ?",
                (wallet, _today()),
            ).fetchone()
            used = int(row[0]) if row else 0
            return used < limit, max(0, limit - used)
    except Exception:  # noqa: BLE001 — fail-open
        logger.warning("freemium.check_available: збій БД, пропускаю", exc_info=True)
        return True, None


def record_generation(wallet: str) -> None:
    """Інкрементує денний лічильник гаманця (UPSERT). No-op при вимкненому ліміті.

    Поповнені гаманці не рахуємо (вони звільнені). Fail-open: збій тихо лог.
    """
    if daily_limit() <= 0:
        return
    try:
        wallet = payment_service.normalize_wallet(wallet)
    except ValueError:
        return
    try:
        with closing(payment_service._connect()) as conn, conn:
            if _freemium_exempt(conn, wallet):
                return
            conn.execute(
                "INSERT INTO freemium_usage (wallet_address, day, count) VALUES (?, ?, 1)"
                " ON CONFLICT(wallet_address, day) DO UPDATE SET count = count + 1",
                (wallet, _today()),
            )
            conn.commit()
    except Exception:  # noqa: BLE001 — fail-open: облік не критичний
        logger.warning("freemium.record_generation: збій БД", exc_info=True)


def release_generation(wallet: str) -> None:
    """Скасовує облік однієї генерації — дзеркало `payment_service.refund_credits`.

    Невдала генерація (з поверненням кредитів) НЕ має спалювати денний слот. Декремент
    із підлогою 0. No-op при вимкненому ліміті / для поповнених. Fail-open.
    """
    if daily_limit() <= 0:
        return
    try:
        wallet = payment_service.normalize_wallet(wallet)
    except ValueError:
        return
    try:
        with closing(payment_service._connect()) as conn, conn:
            if _freemium_exempt(conn, wallet):
                return
            conn.execute(
                # db.greatest(): скалярний MAX у SQLite, GREATEST у Postgres
                # (там MAX — лише агрегат). Підлога 0 при декременті.
                f"UPDATE freemium_usage SET count = {db.greatest()}(0, count - 1)"
                " WHERE wallet_address = ? AND day = ?",
                (wallet, _today()),
            )
            conn.commit()
    except Exception:  # noqa: BLE001 — fail-open
        logger.warning("freemium.release_generation: збій БД", exc_info=True)
