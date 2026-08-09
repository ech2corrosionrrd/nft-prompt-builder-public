"""Життєвий цикл сховища хоста: метрика диска + GC ефемерних тек.

Проблема: `data/` росте без межі на одному хості. `workspace/` має власний
MB-ліміт (services/workspace_limits), але регенеровані артефакти —
`data/exports/` (ZIP-бандли колекцій) і `data/previews/<гаманець>/` (прев'ю
PNG) — накопичуються без прибирання й рано чи пізно впираються в диск.

Дві незалежні відповідальності:
  1. **Метрика диска** — завжди read-only, безпечна: обсяг тому під `data/`,
     використаний %, розбивка по підтеках. Іде в денний дайджест
     (alerts.digest_text → digest_line) і в Telegram-алерт при перевищенні порога.
  2. **GC** — видалення старих файлів РІВНО з ефемерних тек (`_GC_SUBDIRS`,
     хардкод — оператор не може випадково націлити на `public/`, `workspace/`,
     `images/`). Вимкнено за замовчуванням (STORAGE_GC_ENABLED != "1"),
     дзеркалячи обережний патерн проєкту (freemium/cascade/workspace теж off).

Чиста логіка (без Streamlit, без мережі): функції приймають `data_dir`/`now`
для тестів; надсилання алертів — у scripts/storage_gc.py через services.notify.

Env:
  STORAGE_GC_ENABLED    — "1" вмикає реальне видалення (дефолт off; звіт завжди).
  STORAGE_GC_TTL_DAYS   — вік файлу в ефемерній теці для GC (дефолт 14).
  STORAGE_DISK_WARN_PCT — поріг використання тому для алерту (дефолт 80).
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from storage import DATA_DIR

logger = logging.getLogger(__name__)

# Теки з регенерованими/ефемерними артефактами — ЄДИНЕ, що GC чіпає.
# НЕ вносити сюди `public`/`public_archive` (live /c/*), `workspace` (проєкти
# користувачів, свій ліміт), `images` (може бути assets проєкту), `checkpoints`
# (resume-стан), `history`, `curator_ratings`. Хардкод, а не env — щоб конфіг
# не міг перетворити прибирання на втрату користувацького контенту.
_GC_SUBDIRS = ("previews", "exports")

DEFAULT_GC_TTL_DAYS = 14
DEFAULT_DISK_WARN_PCT = 80


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name) or str(default)))
    except (TypeError, ValueError):
        return default


def gc_enabled() -> bool:
    """Реальне видалення вмикається рівно "1" (решта — лише звіт/метрика)."""
    return os.environ.get("STORAGE_GC_ENABLED", "0").strip() == "1"


def gc_ttl_days() -> int:
    """Вік файлу (дні) в ефемерній теці, після якого він — кандидат на GC."""
    return _env_int("STORAGE_GC_TTL_DAYS", DEFAULT_GC_TTL_DAYS)


def disk_warn_pct() -> int:
    """Поріг використання тому (%), при якому дайджест/скрипт алертить."""
    return min(100, _env_int("STORAGE_DISK_WARN_PCT", DEFAULT_DISK_WARN_PCT))


def _human(nbytes: int) -> str:
    """Людиночитний розмір: B/KB/MB/GB (двійкові одиниці)."""
    size = float(nbytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            precision = 0 if unit in ("B", "KB") else 1
            return f"{size:.{precision}f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _dir_stats(path: Path) -> tuple[int, int]:
    """Сумарні байти та кількість файлів у теці (один обхід); 0/0 якщо нема."""
    if not path.exists():
        return 0, 0
    total = 0
    files = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                files += 1
                try:
                    total += item.stat().st_size
                except OSError:
                    continue
    except OSError:
        logger.warning("storage_gc._dir_stats: збій читання %s", path, exc_info=True)
    return total, files


def disk_status(data_dir: Path | None = None) -> dict:
    """Знімок тому під data/ + розбивка по підтеках (read-only, без побічних дій).

    Ключі: total_bytes/used_bytes/free_bytes/used_pct тому; data_bytes/data_files
    сумарно по data/; subdirs — [{name, bytes, files, human}] за спаданням обсягу.
    """
    root = data_dir or DATA_DIR
    try:
        usage = shutil.disk_usage(root if root.exists() else root.parent)
        total, used, free = usage.total, usage.used, usage.free
    except OSError:
        logger.warning("storage_gc.disk_status: диск недоступний для %s", root, exc_info=True)
        total = used = free = 0

    subdirs: list[dict] = []
    data_bytes = 0
    data_files = 0
    if root.exists():
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            nbytes, nfiles = _dir_stats(child)
            data_bytes += nbytes
            data_files += nfiles
            subdirs.append(
                {"name": child.name, "bytes": nbytes, "files": nfiles, "human": _human(nbytes)}
            )
    subdirs.sort(key=lambda r: r["bytes"], reverse=True)

    return {
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "used_pct": round(used / total * 100, 1) if total else 0.0,
        "total_human": _human(total),
        "used_human": _human(used),
        "free_human": _human(free),
        "data_bytes": data_bytes,
        "data_files": data_files,
        "data_human": _human(data_bytes),
        "subdirs": subdirs,
    }


def should_alert(status: dict, *, warn_pct: int | None = None) -> bool:
    """True, якщо використання тому досягло порога (для Telegram-алерту)."""
    threshold = disk_warn_pct() if warn_pct is None else warn_pct
    return float(status.get("used_pct") or 0.0) >= threshold


def gc_candidates(
    data_dir: Path | None = None,
    *,
    now: datetime | None = None,
    ttl_days: int | None = None,
) -> list[dict]:
    """Файли в ефемерних теках, старші за TTL (кандидати на видалення).

    Read-only: нічого не видаляє. Кожен запис — {path, subdir, age_days, bytes}.
    """
    root = data_dir or DATA_DIR
    now = now or datetime.now()
    ttl = gc_ttl_days() if ttl_days is None else ttl_days
    cutoff = now.timestamp() - ttl * 86400

    out: list[dict] = []
    for name in _GC_SUBDIRS:
        base = root / name
        if not base.exists():
            continue
        try:
            for item in base.rglob("*"):
                if not item.is_file():
                    continue
                try:
                    st = item.stat()
                except OSError:
                    continue
                if st.st_mtime >= cutoff:
                    continue
                out.append(
                    {
                        "path": item,
                        "subdir": name,
                        "age_days": int((now.timestamp() - st.st_mtime) // 86400),
                        "bytes": st.st_size,
                    }
                )
        except OSError:
            logger.warning("storage_gc.gc_candidates: збій обходу %s", base, exc_info=True)
    return out


def _prune_empty_dirs(root: Path) -> None:
    """Прибирає порожні підтеки в ефемерних теках (напр. previews/<гаманець>/)."""
    for name in _GC_SUBDIRS:
        base = root / name
        if not base.exists():
            continue
        for child in sorted(base.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if child.is_dir():
                try:
                    next(child.iterdir())
                except StopIteration:
                    try:
                        child.rmdir()
                    except OSError:
                        pass
                except OSError:
                    pass


def run_gc(
    data_dir: Path | None = None,
    *,
    now: datetime | None = None,
    ttl_days: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Видаляє старі файли з ефемерних тек. dry_run=True — лише звіт.

    Повертає {dry_run, ttl_days, deleted_files, freed_bytes, freed_human,
    by_subdir:{name:{files,bytes}}, errors}. Стійкий до збоїв окремого файлу
    (лічить в errors, не валить прогін) — cron не має падати через один локнутий PNG.
    """
    root = data_dir or DATA_DIR
    ttl = gc_ttl_days() if ttl_days is None else ttl_days
    candidates = gc_candidates(root, now=now, ttl_days=ttl)

    by_subdir: dict[str, dict[str, int]] = {}
    deleted = 0
    freed = 0
    errors = 0
    for cand in candidates:
        bucket = by_subdir.setdefault(cand["subdir"], {"files": 0, "bytes": 0})
        if dry_run:
            bucket["files"] += 1
            bucket["bytes"] += cand["bytes"]
            deleted += 1
            freed += cand["bytes"]
            continue
        try:
            cand["path"].unlink()
        except OSError:
            errors += 1
            logger.warning("storage_gc.run_gc: не видалено %s", cand["path"], exc_info=True)
            continue
        bucket["files"] += 1
        bucket["bytes"] += cand["bytes"]
        deleted += 1
        freed += cand["bytes"]

    if not dry_run and deleted:
        _prune_empty_dirs(root)

    return {
        "dry_run": dry_run,
        "ttl_days": ttl,
        "deleted_files": deleted,
        "freed_bytes": freed,
        "freed_human": _human(freed),
        "by_subdir": by_subdir,
        "errors": errors,
    }


def digest_line(data_dir: Path | None = None) -> str:
    """Рядок для денного дайджесту (alerts.digest_text): диск + обсяг data/.

    Emoji-маркер сигналить перевищення порога, щоб оператор бачив у дайджесті,
    що час увімкнути STORAGE_GC_ENABLED або розширити диск.
    """
    status = disk_status(data_dir)
    marker = "🔴" if should_alert(status) else "💾"
    return (
        f"{marker} Диск: {status['used_pct']:.0f}% "
        f"({status['used_human']} / {status['total_human']}) "
        f"· data {status['data_human']}"
    )
