"""Ліміти workspace-проєктів на гаманець (ops + freemium).

Env (0 або порожнє = вимкнено):
  WORKSPACE_MAX_PROJECTS_PER_WALLET — макс. проєктів (безкоштовні гаманці без Helio-оплат)
  WORKSPACE_MAX_MB_PER_WALLET — макс. сумарний обʼєм data/workspace/<wallet>/ (усі користувачі)
  WORKSPACE_PROJECT_WARN_COUNT — soft-попередження в UI (дефолт 15)

Платники (є запис у payments) звільнені від ліміту **кількості** проєктів, як freemium.
Обмеження по MB — для всіх (захист диска хоста). Fail-open при збої БД для перевірки платника.
"""

from __future__ import annotations

import logging
import os
from contextlib import closing
from pathlib import Path

from services import payment_service
from storage import DATA_DIR, wallet_slug

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = DATA_DIR / "workspace"
MANIFEST_FILE = "manifest.json"


class ProjectQuotaError(Exception):
    """Перевищено квоту workspace; code — ключ ui_strings project.quota.*."""

    def __init__(self, code: str, **detail: int | str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


def _env_int(name: str, default: int = 0) -> int:
    try:
        return max(0, int(os.environ.get(name) or str(default)))
    except (TypeError, ValueError):
        return default


def max_projects_limit() -> int:
    return _env_int("WORKSPACE_MAX_PROJECTS_PER_WALLET", 0)


def max_mb_limit() -> int:
    return _env_int("WORKSPACE_MAX_MB_PER_WALLET", 0)


def warn_project_count() -> int:
    return max(1, _env_int("WORKSPACE_PROJECT_WARN_COUNT", 15))


def wallet_root(wallet: str) -> Path:
    return WORKSPACE_ROOT / wallet_slug(wallet)


def _dir_bytes(path: Path) -> int:
    return _dir_stats(path)[0]


def _dir_stats(path: Path) -> tuple[int, int]:
    """Сумарні байти та кількість файлів у теці (один обхід)."""
    if not path.exists():
        return 0, 0
    total = 0
    files = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                files += 1
                total += item.stat().st_size
    except OSError:
        logger.warning("workspace_limits._dir_stats: помилка читання %s", path, exc_info=True)
    return total, files


def project_disk_stats(project_dir: Path) -> dict[str, int]:
    """Розмір проєкту для manifest-кешу (autosave, без rglob на кожен rerun UI)."""
    nbytes, nfiles = _dir_stats(project_dir)
    return {"bytes": nbytes, "files": nfiles}


def count_projects(wallet: str) -> int:
    root = wallet_root(wallet)
    if not root.exists():
        return 0
    n = 0
    for child in root.iterdir():
        if child.is_dir() and (child / MANIFEST_FILE).is_file():
            n += 1
    return n


def wallet_bytes(wallet: str) -> int:
    return _dir_bytes(wallet_root(wallet))


def project_bytes(wallet: str, project_id: str) -> int:
    return project_disk_stats(wallet_root(wallet) / project_id)["bytes"]


def _has_purchased(wallet: str) -> bool:
    try:
        wallet = payment_service.normalize_wallet(wallet)
    except ValueError:
        return False
    try:
        with closing(payment_service._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM payments WHERE wallet_address = ? LIMIT 1",
                (wallet,),
            ).fetchone()
            return row is not None
    except Exception:  # noqa: BLE001 — fail-open
        logger.warning("workspace_limits._has_purchased: збій БД", exc_info=True)
        return False


def quota_status(wallet: str) -> dict:
    """Знімок квоти гаманця для UI та assert.

    Важке рахується лише за потреби: `wallet_bytes` обходить усі файли гаманця
    (rglob+stat), а sidebar рендериться на кожен rerun — тож при вимкненому
    MB-ліміті (дефолт) обсяг не рахуємо (його все одно не показуємо й не
    перевіряємо). Аналогічно `_has_purchased` (хіт у БД) — лише коли діє ліміт
    кількості проєктів.
    """
    count = count_projects(wallet)
    proj_limit = max_projects_limit()
    mb_limit = max_mb_limit()
    used_bytes = wallet_bytes(wallet) if mb_limit > 0 else 0
    purchased = _has_purchased(wallet) if proj_limit > 0 else False
    warn_at = warn_project_count()
    return {
        "count": count,
        "used_bytes": used_bytes,
        "used_mb": round(used_bytes / (1024 * 1024), 1),
        "project_limit": proj_limit,
        "mb_limit": mb_limit,
        "purchased": purchased,
        "warn_at": warn_at,
        "show_warn": count >= warn_at,
        "projects_remaining": (
            None if proj_limit <= 0 or purchased
            else max(0, proj_limit - count)
        ),
        "mb_remaining": (
            None if mb_limit <= 0
            else max(0.0, mb_limit - used_bytes / (1024 * 1024))
        ),
    }


def assert_can_add(
    wallet: str,
    *,
    extra_projects: int = 1,
    extra_bytes: int = 0,
) -> None:
    """Перевірка перед create/duplicate. ProjectQuotaError якщо блок."""
    if not wallet:
        return
    status = quota_status(wallet)
    new_count = status["count"] + extra_projects
    new_bytes = status["used_bytes"] + extra_bytes

    if status["project_limit"] > 0 and not status["purchased"]:
        if new_count > status["project_limit"]:
            raise ProjectQuotaError(
                "project_limit",
                limit=status["project_limit"],
                count=status["count"],
            )

    mb_cap = status["mb_limit"]
    if mb_cap > 0:
        cap_bytes = mb_cap * 1024 * 1024
        if new_bytes > cap_bytes:
            raise ProjectQuotaError(
                "disk_limit",
                limit_mb=mb_cap,
                used_mb=round(status["used_bytes"] / (1024 * 1024), 1),
            )


def host_summary(top_n: int = 10) -> dict:
    """Ops: сумарний розмір workspace і топ гаманців за обʼємом."""
    if not WORKSPACE_ROOT.exists():
        return {"total_bytes": 0, "total_mb": 0.0, "wallet_count": 0, "top_wallets": []}

    rows: list[dict] = []
    total_bytes = 0
    for child in WORKSPACE_ROOT.iterdir():
        if not child.is_dir():
            continue
        size = _dir_bytes(child)
        total_bytes += size
        projects = sum(
            1 for p in child.iterdir()
            if p.is_dir() and (p / MANIFEST_FILE).is_file()
        )
        rows.append({
            "slug": child.name,
            "bytes": size,
            "mb": round(size / (1024 * 1024), 1),
            "projects": projects,
        })
    rows.sort(key=lambda r: r["bytes"], reverse=True)
    return {
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 1),
        "wallet_count": len(rows),
        "top_wallets": rows[:top_n],
    }
