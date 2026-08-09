"""Персистентне зберігання історії та проєктів у JSON-файлах (папка data/).

Усі дані РОЗМЕЖОВАНІ по гаманцю: кожен гаманець має власну історію, проєкти,
превʼю та шаблони матриць (підтека за адресою). Це ізолює користувачів на
спільному хості — ніхто не бачить і не затирає чужих артефактів. Кредити/баланс
живуть окремо у payment_service (users.db), теж за гаманцем.

Усі функції приймають `wallet` першим аргументом; UI передає поточний гаманець
(billing_ui.connected_wallet()). Порожній гаманець → спільна тека '_local'
(dev / сесії без входу).
"""

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
HISTORY_DIR = DATA_DIR / "history"
PROJECTS_DIR = DATA_DIR / "projects"
PREVIEWS_DIR = DATA_DIR / "previews"
MATRICES_DIR = DATA_DIR / "matrices"
BIBLES_DIR = DATA_DIR / "bibles"
CURATOR_RATINGS_DIR = DATA_DIR / "curator_ratings"
HISTORY_LIMIT = 50
PREVIEW_LIMIT = 20


def wallet_slug(wallet: str) -> str:
    """Безпечна для файлової системи назва теки гаманця.

    EVM (0x…) та Solana base58-адреси майже завжди ФС-безпечні, але про всяк
    випадок лишаємо тільки [A-Za-z0-9_-] й обрізаємо. Порожній/невідомий гаманець
    → '_local' (єдина тека для dev або сесій без входу).
    """
    w = (wallet or "").strip()
    if not w:
        return "_local"
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", w)
    return cleaned[:64] or "_local"


# ── Історія ───────────────────────────────────────────────────────────────────

def _history_file(wallet: str) -> Path:
    return HISTORY_DIR / f"{wallet_slug(wallet)}.json"


def load_history(wallet: str) -> list[dict]:
    path = _history_file(wallet)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_history(wallet: str, history: list[dict]) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    _history_file(wallet).write_text(
        json.dumps(history[:HISTORY_LIMIT], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Проєкти ───────────────────────────────────────────────────────────────────

def safe_name(name: str) -> str:
    """Прибирає з назви символи, заборонені у файлових системах."""
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    return cleaned[:80] or "project"


def _projects_dir(wallet: str) -> Path:
    return PROJECTS_DIR / wallet_slug(wallet)


def list_projects(wallet: str) -> list[str]:
    d = _projects_dir(wallet)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def save_project(wallet: str, name: str, config: dict) -> str:
    d = _projects_dir(wallet)
    d.mkdir(parents=True, exist_ok=True)
    safe = safe_name(name)
    (d / f"{safe}.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return safe


def load_project(wallet: str, name: str) -> dict | None:
    path = _projects_dir(wallet) / f"{safe_name(name)}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def delete_project(wallet: str, name: str) -> None:
    path = _projects_dir(wallet) / f"{safe_name(name)}.json"
    if path.exists():
        path.unlink()


# ── Превʼю-зображення (вкладка «Зображення») ─────────────────────────────────

def _previews_dir(wallet: str) -> Path:
    return PREVIEWS_DIR / wallet_slug(wallet)


def save_preview(wallet: str, image_bytes: bytes, stamp: str, variant: str = "") -> Path:
    """Зберігає PNG у data/previews/<гаманець>/ і повертає шлях до файлу."""
    d = _previews_dir(wallet)
    d.mkdir(parents=True, exist_ok=True)
    safe_stamp = re.sub(r'[\\/:*?"<>|]+', "-", stamp.replace(":", "-").replace(" ", "_"))
    suffix = f"_v{variant.replace('/', '-')}" if variant else ""
    path = d / f"{safe_stamp}{suffix}.png"
    n = 1
    while path.exists():
        path = d / f"{safe_stamp}{suffix}_{n}.png"
        n += 1
    path.write_bytes(image_bytes)
    return path


def list_previews(wallet: str, limit: int = PREVIEW_LIMIT) -> list[Path]:
    d = _previews_dir(wallet)
    if not d.exists():
        return []
    files = sorted(d.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def clear_previews(wallet: str) -> int:
    d = _previews_dir(wallet)
    if not d.exists():
        return 0
    removed = 0
    for path in d.glob("*.png"):
        path.unlink()
        removed += 1
    return removed


# ── Шаблони матриць (Етап 1 конвеєра) ────────────────────────────────────────

def _matrices_dir(wallet: str) -> Path:
    return MATRICES_DIR / wallet_slug(wallet)


def save_matrix_template(wallet: str, name: str, data: dict) -> str:
    d = _matrices_dir(wallet)
    d.mkdir(parents=True, exist_ok=True)
    safe = safe_name(name)
    (d / f"{safe}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return safe


def list_matrix_templates(wallet: str) -> list[str]:
    d = _matrices_dir(wallet)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def load_matrix_template(wallet: str, name: str) -> dict | None:
    path = _matrices_dir(wallet) / f"{safe_name(name)}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def delete_matrix_template(wallet: str, name: str) -> None:
    path = _matrices_dir(wallet) / f"{safe_name(name)}.json"
    if path.exists():
        path.unlink()


# ── Style Bible (ПЛАН_ЯКОСТІ.md § Q2.1) ───────────────────────────────────────
# Одна біблія стилю на гаманець (як історія) — фіксує вигляд усієї колекції.

def _bible_file(wallet: str) -> Path:
    return BIBLES_DIR / f"{wallet_slug(wallet)}.json"


def load_style_bible(wallet: str) -> dict:
    """Повертає збережену біблію стилю гаманця ({} якщо немає/пошкоджено)."""
    path = _bible_file(wallet)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_style_bible(wallet: str, data: dict) -> None:
    BIBLES_DIR.mkdir(parents=True, exist_ok=True)
    _bible_file(wallet).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def clear_style_bible(wallet: str) -> None:
    path = _bible_file(wallet)
    if path.exists():
        path.unlink()


# ── Рейтинги куратора (per-wallet, by image path) ─────────────────────────────

def _curator_ratings_file(wallet: str) -> Path:
    return CURATOR_RATINGS_DIR / f"{wallet_slug(wallet)}.json"


def load_curator_ratings(wallet: str) -> dict[str, int]:
    """Повертає {image_path: rating} для гаманця."""
    path = _curator_ratings_file(wallet)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        by_path = data.get("by_path", data) if isinstance(data, dict) else {}
        return {
            str(k): int(v)
            for k, v in by_path.items()
            if isinstance(v, (int, float)) and int(v) >= 0
        }
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}


def merge_curator_ratings(wallet: str, ratings: dict[str, int]) -> None:
    """Дописує/оновлює рейтинги за шляхом зображення (0 ігноруємо)."""
    if not ratings:
        return
    current = load_curator_ratings(wallet)
    for path, rating in ratings.items():
        if path and int(rating) > 0:
            current[str(path)] = int(rating)
    CURATOR_RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    _curator_ratings_file(wallet).write_text(
        json.dumps({"by_path": current}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
