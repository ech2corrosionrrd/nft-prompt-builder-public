"""Перевірка «пульсу» бекапів: чи не зупинився погодинний cron.

Мотив із проду 2026-08-07: копії лежали лише в `backups/hourly/` на тому ж диску,
що й БД, а сам розклад ніхто не моніторив — зламався б cron, і про це стало б
відомо аж у момент відновлення.
"""
from datetime import datetime, timedelta, timezone

from services.backup_health import DEFAULT_MAX_AGE_HOURS, check_backups, max_age_hours, summary_text

NOW = datetime(2026, 8, 7, 18, 0, tzinfo=timezone.utc)


def _make_backup(tmp_path, name="users_20260807_170001.db", *, age_hours=0.5, size=4096):
    d = tmp_path / "hourly"
    d.mkdir(exist_ok=True)
    f = d / name
    f.write_bytes(b"x" * size)
    mtime = (NOW - timedelta(hours=age_hours)).timestamp()
    import os

    os.utime(f, (mtime, mtime))
    return d


def test_fresh_backup_ok(tmp_path):
    d = _make_backup(tmp_path, age_hours=0.5)
    st = check_backups(d, now=NOW)
    assert st.ok is True
    assert st.problem is None
    assert st.count == 1
    assert st.age_hours < 1
    assert "✅" in summary_text(st)


def test_stale_backup_flagged(tmp_path):
    """Головний сценарій: cron помер, файли лишились — тека виглядає «повною»."""
    d = _make_backup(tmp_path, age_hours=30)
    st = check_backups(d, now=NOW)
    assert st.ok is False
    assert "розклад бекапів зупинився" in st.problem
    assert st.newest_name is not None  # файл є, але протух
    assert "❌" in summary_text(st)


def test_empty_backup_file_flagged(tmp_path):
    """Обірваний бекап: файл створено, дані не дописані."""
    d = _make_backup(tmp_path, age_hours=0.1, size=0)
    st = check_backups(d, now=NOW)
    assert st.ok is False
    assert "порожній" in st.problem


def test_missing_dir_and_empty_dir(tmp_path):
    missing = check_backups(tmp_path / "nope", now=NOW)
    assert missing.ok is False
    assert "не існує" in missing.problem

    empty = tmp_path / "hourly"
    empty.mkdir()
    st = check_backups(empty, now=NOW)
    assert st.ok is False
    assert "немає жодного бекапу" in st.problem


def test_newest_file_wins(tmp_path):
    d = _make_backup(tmp_path, name="old.db", age_hours=48)
    _make_backup(tmp_path, name="new.db", age_hours=0.2)
    st = check_backups(d, now=NOW)
    assert st.ok is True
    assert st.newest_name == "new.db"
    assert st.count == 2


def test_max_age_from_env(monkeypatch):
    assert max_age_hours() == DEFAULT_MAX_AGE_HOURS
    monkeypatch.setenv("BACKUP_MAX_AGE_HOURS", "6")
    assert max_age_hours() == 6.0
    # Сміття й нуль не мають вимикати перевірку — падаємо на дефолт.
    monkeypatch.setenv("BACKUP_MAX_AGE_HOURS", "не число")
    assert max_age_hours() == DEFAULT_MAX_AGE_HOURS
    monkeypatch.setenv("BACKUP_MAX_AGE_HOURS", "0")
    assert max_age_hours() == DEFAULT_MAX_AGE_HOURS
