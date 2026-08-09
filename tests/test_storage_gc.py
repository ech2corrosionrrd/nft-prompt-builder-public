"""Тести storage_gc: метрика диска (read-only) + GC ефемерних тек.

Ключова інваріанта безпеки: GC чіпає РІВНО previews/ і exports/, а не
public/workspace/images — щоб конфіг чи регресія не з'їли користувацький контент.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

import pytest

from services import storage_gc


def _touch(path, *, age_days: float = 0.0, size: int = 16):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
    return path


def _seed(root):
    """Типова data/: свіжі й старі файли в ефемерних та захищених теках."""
    _touch(root / "previews" / "0xabc" / "fresh.png", age_days=1)
    _touch(root / "previews" / "0xabc" / "stale.png", age_days=30)
    _touch(root / "exports" / "recent.zip", age_days=2)
    _touch(root / "exports" / "old.zip", age_days=40, size=1024)
    # Захищені — GC не має їх бачити навіть старими.
    _touch(root / "public" / "showcase.png", age_days=99)
    _touch(root / "workspace" / "0xdef" / "asset.png", age_days=99)
    _touch(root / "images" / "gen.png", age_days=99)


# ── метрика диска ──────────────────────────────────────────────────────────

def test_disk_status_keys_and_subdirs(tmp_path):
    _seed(tmp_path)
    status = storage_gc.disk_status(tmp_path)
    for key in ("total_bytes", "used_bytes", "free_bytes", "used_pct", "data_bytes", "subdirs"):
        assert key in status
    assert status["total_bytes"] > 0
    assert status["data_files"] == 7
    names = {r["name"] for r in status["subdirs"]}
    assert {"previews", "exports", "public", "workspace", "images"} <= names
    # subdirs відсортовані за спаданням обсягу.
    sizes = [r["bytes"] for r in status["subdirs"]]
    assert sizes == sorted(sizes, reverse=True)


def test_disk_status_empty_dir(tmp_path):
    status = storage_gc.disk_status(tmp_path)
    assert status["data_bytes"] == 0
    assert status["subdirs"] == []
    assert status["total_bytes"] > 0  # том усе одно існує


def test_should_alert_threshold():
    assert storage_gc.should_alert({"used_pct": 95.0}, warn_pct=80) is True
    assert storage_gc.should_alert({"used_pct": 50.0}, warn_pct=80) is False
    assert storage_gc.should_alert({"used_pct": 80.0}, warn_pct=80) is True  # межа включно


def test_digest_line_marker(tmp_path, monkeypatch):
    _seed(tmp_path)
    line = storage_gc.digest_line(tmp_path)
    assert "Диск:" in line and "data" in line
    # На реальному томі використання зазвичай < 80%, тож маркер спокійний.
    assert line.startswith("💾") or line.startswith("🔴")


# ── GC-кандидати ───────────────────────────────────────────────────────────

def test_gc_candidates_only_stale_in_ephemeral(tmp_path):
    _seed(tmp_path)
    cands = storage_gc.gc_candidates(tmp_path, now=datetime.now(), ttl_days=14)
    paths = {c["path"].name for c in cands}
    assert paths == {"stale.png", "old.zip"}  # свіжі й захищені — відсутні
    subdirs = {c["subdir"] for c in cands}
    assert subdirs <= {"previews", "exports"}


def test_gc_candidates_respects_ttl(tmp_path):
    _seed(tmp_path)
    # TTL 50д — жоден із засіяних (макс 40д) не старий.
    assert storage_gc.gc_candidates(tmp_path, ttl_days=50) == []


# ── GC-виконання ───────────────────────────────────────────────────────────

def test_run_gc_dry_run_deletes_nothing(tmp_path):
    _seed(tmp_path)
    report = storage_gc.run_gc(tmp_path, ttl_days=14, dry_run=True)
    assert report["dry_run"] is True
    assert report["deleted_files"] == 2
    assert report["freed_bytes"] > 0
    # Нічого не видалено фізично.
    assert (tmp_path / "exports" / "old.zip").exists()
    assert (tmp_path / "previews" / "0xabc" / "stale.png").exists()


def test_run_gc_deletes_only_stale_ephemeral(tmp_path):
    _seed(tmp_path)
    report = storage_gc.run_gc(tmp_path, ttl_days=14, dry_run=False)
    assert report["deleted_files"] == 2
    assert report["errors"] == 0
    # Старі ефемерні — видалено.
    assert not (tmp_path / "exports" / "old.zip").exists()
    assert not (tmp_path / "previews" / "0xabc" / "stale.png").exists()
    # Свіжі ефемерні — лишились.
    assert (tmp_path / "exports" / "recent.zip").exists()
    assert (tmp_path / "previews" / "0xabc" / "fresh.png").exists()
    # Захищені теки — недоторкані навіть при віці 99д.
    assert (tmp_path / "public" / "showcase.png").exists()
    assert (tmp_path / "workspace" / "0xdef" / "asset.png").exists()
    assert (tmp_path / "images" / "gen.png").exists()


def test_run_gc_prunes_empty_wallet_dirs(tmp_path):
    # Лише старі файли в теці гаманця → після GC порожня тека прибирається.
    _touch(tmp_path / "previews" / "0xghost" / "a.png", age_days=30)
    _touch(tmp_path / "previews" / "0xghost" / "b.png", age_days=30)
    storage_gc.run_gc(tmp_path, ttl_days=14, dry_run=False)
    assert not (tmp_path / "previews" / "0xghost").exists()


# ── env-хелпери ────────────────────────────────────────────────────────────

def test_env_helpers_defaults():
    assert storage_gc.gc_enabled() is False
    assert storage_gc.gc_ttl_days() == storage_gc.DEFAULT_GC_TTL_DAYS
    assert storage_gc.disk_warn_pct() == storage_gc.DEFAULT_DISK_WARN_PCT


def test_gc_enabled_exact_one(monkeypatch):
    monkeypatch.setenv("STORAGE_GC_ENABLED", "true")
    assert storage_gc.gc_enabled() is False  # лише "1" вмикає
    monkeypatch.setenv("STORAGE_GC_ENABLED", "1")
    assert storage_gc.gc_enabled() is True


@pytest.mark.parametrize("raw,expected", [("7", 7), ("", 14), ("abc", 14), ("-3", 0)])
def test_gc_ttl_env(monkeypatch, raw, expected):
    monkeypatch.setenv("STORAGE_GC_TTL_DAYS", raw)
    assert storage_gc.gc_ttl_days() == expected
