"""b2b_service.py — B2B API authentication, key management & generation quotas.

Стан ключів живе в `users.db` (таблиця `b2b_keys`) через `services/db.py`, а не в
окремому JSON-файлі. Причини саме такого вибору:

- **бекап**: `users.db` знімається погодинно (`backups/hourly/`), а решта `data/`
  свідомо не бекапиться — партнерські ключі в JSON зникли б безслідно;
- **Postgres**: `DATABASE_URL` перемикає весь стан разом, файловий стор лишився б
  на диску однієї ноди й розʼїхався б між воркерами;
- **облік без втрачених оновлень**: `used` інкрементується одним атомарним
  `UPDATE`, а не read-modify-write циклом поверх цілого файлу.

Ключі зберігаються у відкритому вигляді (як і раніше) — перехід на зберігання
SHA-256 хеша лишається окремим кроком.
"""

from __future__ import annotations

import os
import secrets
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services import db
from storage import DATA_DIR

DB_PATH = DATA_DIR / "users.db"

# Демо-ключ стенду: сідиться в таблицю при першому підключенні (INSERT OR IGNORE),
# тож джерело правди лишається одне — БД, а не паралельний dict у памʼяті.
# ⚠️ Значення ПУБЛІЧНЕ (лежить у репо), тому в проді воно НЕ сідиться взагалі:
# інакше свіжа БД — чи відновлення з бекапу, знятого до відкликання, — тихо
# повертала б робочий ключ, який бачив кожен, хто читав код.
STAGING_KEY = "b2b_test_key_w3ir_2026"
STAGING_CLIENT = "Staging Partner DAO"
STAGING_QUOTA = 1000


def _is_production() -> bool:
    env = os.environ.get("APP_ENV", os.environ.get("ENVIRONMENT", "")).strip().lower()
    return env in ("production", "prod")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> Any:
    conn = db.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS b2b_keys ("
        " api_key TEXT PRIMARY KEY,"
        " client_name TEXT NOT NULL,"
        " quota INTEGER NOT NULL DEFAULT 0,"
        " used INTEGER NOT NULL DEFAULT 0,"
        " active INTEGER NOT NULL DEFAULT 1,"
        " created_at TEXT NOT NULL)"
    )
    if not _is_production():
        conn.execute(
            db.insert_or_ignore(
                "INSERT INTO b2b_keys (api_key, client_name, quota, used, active, created_at) "
                "VALUES (?, ?, ?, 0, 1, ?)"
            ),
            (STAGING_KEY, STAGING_CLIENT, STAGING_QUOTA, _now()),
        )
    conn.commit()
    return conn


def _row_to_client(row: Any) -> Dict[str, Any]:
    return {
        "client_name": row[0],
        "quota": int(row[1]),
        "used": int(row[2]),
        "active": bool(row[3]),
    }


def verify_b2b_api_key(api_key: Optional[str]) -> Optional[Dict[str, Any]]:
    """Verifies B2B API key and returns client record if valid and quota is available."""
    if not api_key:
        return None

    # Check env override keys
    env_keys = os.environ.get("W3IR_B2B_KEYS", "").split(",")
    if api_key in env_keys and api_key.strip():
        return {
            "client_name": "Partner Client",
            "quota": 999999,
            "used": 0,
            "active": True,
        }

    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT client_name, quota, used, active FROM b2b_keys WHERE api_key = ?",
            (api_key,),
        ).fetchone()

    if not row:
        return None
    client = _row_to_client(row)
    if client["active"] and client["used"] < client["quota"]:
        return client

    return None


def record_b2b_usage(api_key: str, count: int = 1) -> bool:
    """Increments used quota counter for B2B API key.

    Списання атомарне й all-or-nothing: умова `used + count <= quota` перевіряється
    в тому ж `UPDATE`, тож два паралельні запити не можуть ані загубити інкремент,
    ані разом перевищити квоту (`verify` + окремий інкремент дали б TOCTOU-вікно).
    Повертає False, якщо ключа немає, він вимкнений або квоти не вистачає.
    """
    if not api_key or count <= 0:
        return False

    with closing(_connect()) as conn:
        cur = conn.execute(
            "UPDATE b2b_keys SET used = used + ? "
            "WHERE api_key = ? AND active = 1 AND used + ? <= quota",
            (count, api_key, count),
        )
        updated = cur.rowcount
        conn.commit()
    return updated > 0


def generate_b2b_api_key(client_name: str, quota: int = 500) -> str:
    """Generates a new B2B API key for a partner client."""
    new_key = f"w3ir_b2b_{secrets.token_hex(12)}"
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO b2b_keys (api_key, client_name, quota, used, active, created_at) "
            "VALUES (?, ?, ?, 0, 1, ?)",
            (new_key, client_name, int(quota), _now()),
        )
        conn.commit()
    return new_key


def set_b2b_key_active(api_key: str, active: bool) -> bool:
    """Вимкнути/увімкнути ключ. Повертає False, якщо такого ключа немає.

    Відкликання саме прапорцем, а не `DELETE`: рядок лишається з лічильником
    `used`, тож видно, скільки партнер устиг спожити до відкликання, і ключ не
    можна випадково «перевидати» тим самим значенням.
    """
    if not api_key:
        return False
    with closing(_connect()) as conn:
        cur = conn.execute(
            "UPDATE b2b_keys SET active = ? WHERE api_key = ?",
            (1 if active else 0, api_key),
        )
        updated = cur.rowcount
        conn.commit()
    return updated > 0


def set_b2b_key_client_name(api_key: str, client_name: str) -> bool:
    """Змінити ярлик клієнта. Ключ і лічильник `used` лишаються ті самі.

    Це саме перейменування мітки, а не перевидача: партнеру не треба міняти ключ,
    а історія спожитого не обнуляється. Для компрометованого ключа потрібен
    `set_b2b_key_active(..., False)` + новий ключ, а не перейменування.
    """
    name = (client_name or "").strip()
    if not api_key or not name:
        return False
    with closing(_connect()) as conn:
        cur = conn.execute(
            "UPDATE b2b_keys SET client_name = ? WHERE api_key = ?",
            (name, api_key),
        )
        updated = cur.rowcount
        conn.commit()
    return updated > 0


def set_b2b_key_quota(api_key: str, quota: int) -> bool:
    """Змінити стелю квоти наявного ключа (лічильник `used` не чіпаємо)."""
    if not api_key or quota < 0:
        return False
    with closing(_connect()) as conn:
        cur = conn.execute(
            "UPDATE b2b_keys SET quota = ? WHERE api_key = ?",
            (int(quota), api_key),
        )
        updated = cur.rowcount
        conn.commit()
    return updated > 0


def list_b2b_keys() -> List[Dict[str, Any]]:
    """Усі зареєстровані ключі (для операторського CLI), новіші — першими."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT api_key, client_name, quota, used, active, created_at "
            "FROM b2b_keys ORDER BY created_at DESC"
        ).fetchall()
    return [
        {
            "api_key": r[0],
            "client_name": r[1],
            "quota": int(r[2]),
            "used": int(r[3]),
            "active": bool(r[4]),
            "created_at": (r[5] or "")[:19],
        }
        for r in rows
    ]
