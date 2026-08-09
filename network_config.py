"""Мережева конфігурація та керування тимчасовими активами.

1. Web3-Origin: запити до сторонніх Web3-платформ (Crossmint, Pinata) йдуть
   із заголовками Origin/Referer бренду (https://w3ir.io за замовчуванням,
   перевизначається через W3IR_ORIGIN у .env або st.secrets), щоб платформи
   не блокували транзакції через перевірку походження.

2. temp_assets/: згенеровані зображення зберігаються на диск під UUID-іменами
   замість тримання байтів у st.session_state — захищає Streamlit від падіння
   через брак пам'яті під час пакетної генерації. Після успішного мінтингу
   файли автоматично прибираються.

3. static/: публічні посилання на локальні зображення через вбудований
   статичний сервер Streamlit (enableStaticServing → /app/static/...).
   Зовнішні Web3-сервіси (Crossmint, IPFS-гейтвеї) скачують файл напряму
   через тунель замість довгої передачі в одному HTTP-запиті — це обходить
   ліміт Cloudflare у 100 секунд на запит.
"""

import os
import shutil
import uuid
from pathlib import Path

DEFAULT_ORIGIN = "https://w3ir.io"
DEFAULT_APP_URL = "https://ai.w3ir.io"
_ROOT = Path(__file__).resolve().parent
TEMP_ASSETS_DIR = _ROOT / "temp_assets"
STATIC_DIR = _ROOT / "static"


def _read_setting(name: str) -> str | None:
    """Значення зі змінних середовища або st.secrets (без хардкоду ключів)."""
    if value := os.environ.get(name):
        return value
    try:
        import streamlit as st
        if name in st.secrets and st.secrets[name]:
            return str(st.secrets[name])
    except Exception:
        pass
    return None


def get_origin() -> str:
    """Базовий Origin застосунку для зовнішніх Web3-запитів."""
    return (_read_setting("W3IR_ORIGIN") or DEFAULT_ORIGIN).rstrip("/")


def get_app_url() -> str:
    """Зовнішня адреса застосунку (тунель). Перевизначається через W3IR_APP_URL."""
    return (_read_setting("W3IR_APP_URL") or DEFAULT_APP_URL).rstrip("/")


def web3_headers(extra: dict | None = None) -> dict:
    """Заголовки походження для запитів до Web3-платформ (Crossmint, Pinata)."""
    origin = get_origin()
    headers = {"Origin": origin, "Referer": f"{origin}/"}
    if extra:
        headers.update(extra)
    return headers


# ── Публічні посилання на локальні активи (через статичний сервер) ────────────

def publish_static_asset(path: str | Path) -> str:
    """Копіює локальний файл у static/ і повертає публічний URL через тунель.

    Streamlit (enableStaticServing = true) роздає static/ на /app/static/<файл>,
    тому зовнішній сервіс скачує зображення окремим швидким GET-запитом —
    без передачі великих тіл усередині одного довгого запиту до застосунку.
    """
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"Актив не знайдено: {src}")
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    dest = STATIC_DIR / src.name
    if not dest.exists():
        shutil.copy2(src, dest)
    return f"{get_app_url()}/app/static/{src.name}"


def cleanup_static_assets() -> int:
    """Прибирає опубліковані копії зі static/. Повертає кількість видалених."""
    if not STATIC_DIR.exists():
        return 0
    removed = 0
    for path in STATIC_DIR.iterdir():
        if path.is_file():
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


# ── Тимчасові активи (оптимізація пам'яті) ────────────────────────────────────

def init() -> Path:
    """Гарантує існування temp_assets/. Викликається при старті app.py."""
    TEMP_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_ASSETS_DIR


def save_temp_asset(content: bytes, suffix: str = ".png") -> Path:
    """Зберігає контент у temp_assets/<uuid4><suffix>; повертає шлях."""
    init()
    path = TEMP_ASSETS_DIR / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(content)
    return path


# Корені, з яких дозволено читати активи: temp_assets/ (in-memory оптимізація) і
# data/ (workspace проєктів — pipeline пише PNG у data/workspace/<wallet>/<id>/assets/).
_DATA_DIR = _ROOT / "data"


def read_asset(path: str | Path) -> bytes:
    """Читає байти активу з диска (для IPFS-upload чи показу).

    Дозволено лише файли в межах керованих застосунком тек (temp_assets/ або data/).
    Інакше — ValueError (захист від читання довільних шляхів). Корені читаються з
    глобалів на кожен виклик — щоб monkeypatch у тестах працював.
    """
    resolved = Path(path).resolve()
    roots = (TEMP_ASSETS_DIR, _DATA_DIR)
    if not any(resolved.is_relative_to(root.resolve()) for root in roots):
        raise ValueError(f"Дозволено лише файли з {TEMP_ASSETS_DIR} або {_DATA_DIR}")
    return resolved.read_bytes()


def cleanup_files(paths: list[str | Path]) -> int:
    """Видаляє конкретні файли (після успішного мінтингу). Повертає кількість."""
    removed = 0
    for raw in paths:
        path = Path(raw)
        # прибираємо лише вміст temp_assets/ — чужі шляхи не чіпаємо
        if path.parent != TEMP_ASSETS_DIR:
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            pass
    return removed


def cleanup_temp_assets() -> int:
    """Повне очищення temp_assets/. Повертає кількість видалених файлів."""
    if not TEMP_ASSETS_DIR.exists():
        return 0
    removed = 0
    for path in TEMP_ASSETS_DIR.iterdir():
        if path.is_file():
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed
