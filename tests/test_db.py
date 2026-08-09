"""Тести абстракції доступу до БД (services/db.py, підготовка під DATABASE_URL).

Покриваємо детерміновано (без живого Postgres): вибір бекенду, переклад
плейсхолдерів `?`→`%s`, діалект-хелпери DDL/DML для обох діалектів, SQLite-
зʼєднання (WAL), інтроспекцію колонок і шим `_PgConnection` через фейковий драйвер.
Живий крос-БД round-trip — межа готовності оператора (див. docstring db.py).
"""

from __future__ import annotations

import sqlite3
import sys
import types

import pytest

from services import db


# ── Вибір бекенду ─────────────────────────────────────────────────────────────

def test_backend_default_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.backend() == "sqlite"
    assert db.is_postgres() is False


def test_backend_empty_url_is_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")  # присутній-порожній ≠ postgres
    assert db.backend() == "sqlite"


@pytest.mark.parametrize("url", [
    "postgres://u:p@host/db",
    "postgresql://u:p@host:5432/db",
    "POSTGRESQL://Host/DB",  # регістронезалежно
])
def test_backend_postgres_detected(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    assert db.backend() == "postgres"
    assert db.is_postgres() is True


# ── Переклад плейсхолдерів ────────────────────────────────────────────────────

def test_q_sqlite_unchanged(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.q("SELECT * FROM t WHERE a = ? AND b = ?") == "SELECT * FROM t WHERE a = ? AND b = ?"


def test_q_postgres_translates(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    assert db.q("SELECT * FROM t WHERE a = ? AND b = ?") == "SELECT * FROM t WHERE a = %s AND b = %s"


# ── Діалект DDL/DML ───────────────────────────────────────────────────────────

def test_autoinc_pk_dialect(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.autoinc_pk() == "INTEGER PRIMARY KEY AUTOINCREMENT"
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    assert db.autoinc_pk() == "BIGSERIAL PRIMARY KEY"


def test_insert_or_ignore_dialect(monkeypatch):
    sql = "INSERT INTO t (a, b) VALUES (?, ?)"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.insert_or_ignore(sql) == "INSERT OR IGNORE INTO t (a, b) VALUES (?, ?)"
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    assert db.insert_or_ignore(sql) == "INSERT INTO t (a, b) VALUES (?, ?) ON CONFLICT DO NOTHING"


def test_insert_or_replace_dialect(monkeypatch):
    sql = "INSERT INTO t (k, v, ts) VALUES (?, ?, ?)"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.insert_or_replace(sql, ("k",), ("v", "ts")) == "INSERT OR REPLACE INTO t (k, v, ts) VALUES (?, ?, ?)"
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    assert db.insert_or_replace(sql, ("k",), ("v", "ts")) == (
        "INSERT INTO t (k, v, ts) VALUES (?, ?, ?) "
        "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, ts=EXCLUDED.ts"
    )


def test_integrity_errors_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.integrity_errors() == (sqlite3.IntegrityError,)


# ── SQLite-зʼєднання (реальне) ────────────────────────────────────────────────

def test_connect_sqlite_wal_and_roundtrip(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = tmp_path / "sub" / "t.db"  # має створити батьківську теку
    conn = db.connect(path)
    try:
        assert path.exists()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
        assert mode == "wal"
        conn.execute("CREATE TABLE t (id " + db.autoinc_pk() + ", name TEXT)")
        conn.execute("INSERT INTO t (name) VALUES (?)", ("alice",))
        conn.commit()
        assert conn.execute("SELECT name FROM t WHERE id = ?", (1,)).fetchone()[0] == "alice"
        assert db.table_columns(conn, "t") == {"id", "name"}
    finally:
        conn.close()


# ── Postgres-шим через фейковий драйвер ──────────────────────────────────────

class _FakeCursor:
    def __init__(self, log):
        self._log = log
        self.rowcount = 1

    def execute(self, sql, params=None):
        self._log.append((sql, params))

    def executemany(self, sql, seq):
        self._log.append((sql, list(seq)))

    def fetchone(self):
        return (1,)

    def fetchall(self):
        return [(1,)]


class _FakeRaw:
    def __init__(self):
        self.log = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return _FakeCursor(self.log)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def test_pg_shim_translates_placeholders(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    raw = _FakeRaw()
    conn = db._PgConnection(raw)
    conn.execute("SELECT * FROM t WHERE a = ?", (5,))
    assert raw.log[0] == ("SELECT * FROM t WHERE a = %s", (5,))


def test_pg_shim_transaction_commits_on_success(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    raw = _FakeRaw()
    conn = db._PgConnection(raw)
    with conn:
        conn.execute("INSERT INTO t (a) VALUES (?)", (1,))
    assert raw.commits == 1 and raw.rollbacks == 0


def test_pg_shim_transaction_rolls_back_on_error(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    raw = _FakeRaw()
    conn = db._PgConnection(raw)
    with pytest.raises(ValueError):
        with conn:
            conn.execute("UPDATE t SET a = ?", (1,))
            raise ValueError("boom")
    assert raw.rollbacks == 1 and raw.commits == 0


def test_greatest_dialect(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.greatest() == "MAX"        # SQLite: MAX(a, b) скалярний
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    assert db.greatest() == "GREATEST"   # Postgres: MAX лише агрегат


class _FakePool:
    """Фейковий psycopg_pool.ConnectionPool: віддає/приймає одне зʼєднання."""

    check_connection = staticmethod(lambda conn: None)  # референс для check=

    def __init__(self, dsn, min_size=2, max_size=10, check=None, open=True):
        self.dsn = dsn
        self.check = check
        self._raw = _FakeRaw()
        self.borrowed = 0
        self.returned = 0

    def getconn(self):
        self.borrowed += 1
        return self._raw

    def putconn(self, raw):
        self.returned += 1


def test_connect_routes_to_postgres_pool(monkeypatch, tmp_path):
    """connect() при postgres-URL бере зʼєднання з пулу, а close() повертає його."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setattr(db, "_pg_pool", None)  # лінивий глобальний пул — скидаємо
    monkeypatch.setitem(sys.modules, "psycopg_pool", types.SimpleNamespace(ConnectionPool=_FakePool))

    conn = db.connect(tmp_path / "unused.db")  # шлях ігнорується для PG
    assert isinstance(conn, db._PgConnection)
    pool = db._pg_pool
    assert pool.borrowed == 1 and pool.returned == 0
    assert pool.check is _FakePool.check_connection  # check-alive проти idle-killed
    conn.close()
    assert pool.returned == 1  # close() → putconn (не рве сокет)
    monkeypatch.setattr(db, "_pg_pool", None)  # не лишаємо фейк-пул між тестами


def test_integrity_errors_includes_psycopg(monkeypatch):
    """integrity_errors() на postgres-бекенді додає psycopg.IntegrityError."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    fake_psycopg = types.SimpleNamespace(IntegrityError=type("IntegrityError", (Exception,), {}))
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    errs = db.integrity_errors()
    assert sqlite3.IntegrityError in errs and fake_psycopg.IntegrityError in errs
