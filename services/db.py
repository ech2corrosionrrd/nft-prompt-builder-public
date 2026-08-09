"""Абстракція доступу до БД під `DATABASE_URL` (підготовка до multi-host).

**Дефолт — SQLite**: доки `DATABASE_URL` не задано (або схема `sqlite`), поведінка
байт-у-байт як раніше (той самий файл, WAL, timeout=30). При
`DATABASE_URL=postgres[ql]://...` зʼєднання йде в Postgres через `psycopg`.

Навіщо шов зараз: локальний файл SQLite не масштабується горизонтально — кілька
API-нод за балансувальником не можуть ділити один `users.db`. Абстракцію
найдешевше ввести ДО появи другої ноди й найболючіше ретрофітити після. Тут —
єдина точка створення зʼєднань + діалект-хелпери для місць, де SQL різниться.

Модуль централізує:
- вибір бекенду — `backend()` / `is_postgres()`;
- створення зʼєднання — `connect(sqlite_path)` (SQLite: mkdir+WAL+timeout; Postgres:
  psycopg через сумісний шим `_PgConnection`);
- діалект DDL/DML — `autoinc_pk()`, `insert_or_ignore()`, `insert_or_replace()`,
  `table_columns()`, `q()` (переклад `?`→`%s`).

**Плейсхолдери `?` НЕ треба міняти в call-sites**: шим Postgres перекладає їх у
`%s` автоматично на кожному `execute` (`q()`), тож наявні запити працюють у ОБОХ
бекендах без правок. Діалект-хелпери потрібні лише там, де різниться СТРУКТУРА
(автоінкремент, INSERT OR IGNORE/REPLACE, PRAGMA-інтроспекція).

**Межа готовності (для оператора перед перемиканням на проді)** — повний runbook
у `МІГРАЦІЯ_POSTGRES.md`; коротко:
1. `pip install "psycopg[binary,pool]"` (лінива залежність — не тягнеться для SQLite;
   `pool` обовʼязковий — `connect()` бере зʼєднання з `psycopg_pool.ConnectionPool`);
2. підняти Postgres, задати `DATABASE_URL`;
3. живий smoke: зʼєднання + `payment_service._connect()` (створює схему) + один
   тестовий платіж/списання — крос-БД round-trip тут НЕ тестується (без живого
   сервера), лише діалект-логіка й SQLite-шлях;
4. **бекап-скрипти** (`scripts/backup_users_db.py`, `host_backup.py`,
   `verify_backup.py`) працюють із .db-ФАЙЛОМ напряму (SQLite backup API) — для
   Postgres їх треба замінити на `pg_dump`/`pg_restore` (окремий крок, не тут).
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing  # noqa: F401 — реекспорт для зручності call-sites
from pathlib import Path
from typing import Any, Iterable, Sequence

SQLITE_TIMEOUT = 30.0  # busy-timeout: WAL серіалізує паралельних записувачів


# ── Вибір бекенду ─────────────────────────────────────────────────────────────

def _url() -> str:
    return (os.environ.get("DATABASE_URL") or "").strip()


def backend() -> str:
    """'postgres' якщо `DATABASE_URL` має postgres-схему, інакше 'sqlite' (дефолт)."""
    if _url().lower().startswith(("postgres://", "postgresql://")):
        return "postgres"
    return "sqlite"


def is_postgres() -> bool:
    return backend() == "postgres"


# ── Діалект-хелпери ───────────────────────────────────────────────────────────

def q(sql: str) -> str:
    """Переклад параметр-плейсхолдерів `?`→`%s` для Postgres; SQLite — без змін.

    Наші запити не містять літерального `?` у рядках, тож проста заміна безпечна.
    """
    return sql.replace("?", "%s") if is_postgres() else sql


def autoinc_pk() -> str:
    """DDL-клауза автоінкрементного цілочисельного первинного ключа."""
    return "BIGSERIAL PRIMARY KEY" if is_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"


def greatest() -> str:
    """Імʼя СКАЛЯРНОЇ функції максимуму: `MAX` (SQLite) / `GREATEST` (Postgres).

    Пастка: у SQLite `MAX(a, b)` — скалярна (2+ аргументи), а в Postgres `MAX` —
    ЛИШЕ агрегат; скалярний максимум там `GREATEST(a, b)`. Аналогічно `MIN`↔`LEAST`
    (додати за потреби). Використання: f"... {db.greatest()}(0, count - 1) ...".
    """
    return "GREATEST" if is_postgres() else "MAX"


def insert_or_ignore(insert_sql: str) -> str:
    """`INSERT OR IGNORE` (SQLite) ⇄ `INSERT ... ON CONFLICT DO NOTHING` (Postgres).

    `insert_sql` — звичайний `INSERT INTO ...` (VALUES або SELECT). У SQLite верб
    стає `INSERT OR IGNORE`, у Postgres — суфікс `ON CONFLICT DO NOTHING` (ігнорує
    будь-яке порушення унікальності, як і SQLite-варіант).
    """
    if is_postgres():
        return insert_sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return insert_sql.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)


def insert_or_replace(insert_sql: str, conflict: Sequence[str], update: Sequence[str]) -> str:
    """`INSERT OR REPLACE` (SQLite) ⇄ `INSERT ... ON CONFLICT (..) DO UPDATE` (Postgres).

    `conflict` — колонки унікального ключа (для Postgres-таргета); `update` —
    колонки, що перезаписуються з `EXCLUDED`. У SQLite верб просто стає
    `INSERT OR REPLACE` (замінює рядок цілком за PRIMARY KEY / UNIQUE).
    """
    if is_postgres():
        target = ", ".join(conflict)
        setters = ", ".join(f"{c}=EXCLUDED.{c}" for c in update)
        return insert_sql.rstrip().rstrip(";") + f" ON CONFLICT ({target}) DO UPDATE SET {setters}"
    return insert_sql.replace("INSERT INTO", "INSERT OR REPLACE INTO", 1)


def integrity_errors() -> tuple[type[Exception], ...]:
    """Класи винятків порушення обмежень для `except` — діалект-агностично.

    SQLite завжди кидає `sqlite3.IntegrityError`; Postgres — `psycopg.IntegrityError`
    (напр. UniqueViolation). Використання: `except db.integrity_errors(): ...`.
    """
    errs: list[type[Exception]] = [sqlite3.IntegrityError]
    if is_postgres():
        try:
            import psycopg
            errs.append(psycopg.IntegrityError)
        except ImportError:  # pragma: no cover — залежить від оточення
            pass
    return tuple(errs)


def table_columns(conn: Any, table: str) -> set[str]:
    """Набір назв колонок таблиці — для ідемпотентних міграцій `ADD COLUMN`.

    SQLite: `PRAGMA table_info`; Postgres: `information_schema.columns`.
    """
    if is_postgres():
        cur = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            (table,),
        )
        return {row[0] for row in cur.fetchall()}
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


# ── Зʼєднання ─────────────────────────────────────────────────────────────────

def connect(sqlite_path: Path) -> Any:
    """Створює зʼєднання: SQLite за замовчуванням, Postgres при `DATABASE_URL`.

    `sqlite_path` використовується ЛИШЕ для SQLite-бекенду (Postgres бере DSN із
    `DATABASE_URL`). Повертає обʼєкт із підмножиною sqlite3.Connection-API, яку
    використовує код (`execute`, `commit`, `rollback`, `close`, `with conn:`).
    """
    if is_postgres():
        return _connect_postgres()
    return _connect_sqlite(sqlite_path)


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=SQLITE_TIMEOUT)
    conn.execute("PRAGMA journal_mode=WAL")  # серіалізація записувачів під конкурентність
    return conn


# Пул зʼєднань Postgres — ЛІНИВО-глобальний (один на процес). SQLite відкриває
# локальний файл (дешево), а Postgres — окрема служба: connection-per-query дав би
# TCP-хендшейк ~10–50мс на кожну транзакцію й швидко вичерпав би дескриптори при
# пакетній генерації. Пул перевикористовує зʼєднання; `_PgConnection.close()`
# повертає його в пул (`putconn`), а не рве сокет. Розмір — env-кероване.
_pg_pool: Any = None


def _pg_pool_get() -> Any:
    global _pg_pool
    if _pg_pool is None:
        try:
            from psycopg_pool import ConnectionPool  # лінива залежність
        except ImportError as e:  # pragma: no cover — залежить від оточення
            raise RuntimeError(
                "DATABASE_URL вказує на Postgres, але psycopg_pool не встановлено: "
                'pip install "psycopg[binary,pool]"'
            ) from e
        _pg_pool = ConnectionPool(
            _url(),
            min_size=int(os.environ.get("DATABASE_POOL_MIN") or "2"),
            max_size=int(os.environ.get("DATABASE_POOL_MAX") or "10"),
            # Перевірка зʼєднання перед віддачею: після простою сервер/фаєрвол міг
            # закрити idle-сокет — check відкидає «мертві» й видає живі без помилки.
            check=ConnectionPool.check_connection,
            open=True,
        )
    return _pg_pool


def _connect_postgres() -> "_PgConnection":
    pool = _pg_pool_get()
    return _PgConnection(pool.getconn(), pool=pool)


class _PgConnection:
    """Тонкий адаптер psycopg → сумісний із підмножиною sqlite3.Connection-API.

    Ключова відмінність від psycopg: `with conn:` тут = транзакція в стилі sqlite3
    (commit при успіху, rollback при винятку), а НЕ закриття зʼєднання. `execute()`
    відкриває окремий курсор і повертає його (у нього є `fetchone/fetchall/rowcount`),
    дзеркалячи `sqlite3.Connection.execute`. Плейсхолдери `?` перекладаються `q()`.
    """

    def __init__(self, raw: Any, pool: Any = None):
        self._raw = raw
        self._pool = pool  # якщо з пулу — close() повертає зʼєднання, а не рве

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        cur = self._raw.cursor()
        if params:
            cur.execute(q(sql), tuple(params))
        else:
            cur.execute(q(sql))
        return cur

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> Any:
        cur = self._raw.cursor()
        cur.executemany(q(sql), [tuple(p) for p in seq])
        return cur

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        # Із пулу — повертаємо зʼєднання (pool сам скине відкриту транзакцію);
        # без пулу — фізично закриваємо сокет.
        if self._pool is not None:
            self._pool.putconn(self._raw)
        else:
            self._raw.close()

    def __enter__(self) -> "_PgConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self._raw.commit()
        else:
            self._raw.rollback()
        return False
