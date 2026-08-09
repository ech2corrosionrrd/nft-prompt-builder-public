"""Завантаження секретів з .env (пріоритет над порожніми st.secrets / os.environ)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent

_loaded = False

# Helio paylink ID змінюються в кабінеті; .env — джерело правди (не st.secrets).
_HELIO_PAYLINK_KEYS = frozenset({
    "HELIO_PAYLINK_START",
    "HELIO_PAYLINK_CREATOR",
    "HELIO_PAYLINK_PRO",
})


def load_project_env(force: bool = False) -> None:
    """Підставляє значення з .env, якщо в os.environ ключ відсутній або порожній.

    Виняток: HELIO_PAYLINK_* — завжди з .env (Streamlit secrets часто застарілі).
    Файл читається один раз за процес; force=True лише перечитує файл (щоб
    повторно застосувати HELIO_PAYLINK_* після hydrate st.secrets) — він НЕ
    клобає непорожні OS-env значення інших ключів.
    """
    global _loaded
    if _loaded and not force:
        return
    _loaded = True
    path = ROOT / ".env"
    if not path.exists():
        return
    for key, val in dotenv_values(path).items():
        if not val:
            continue
        if key in _HELIO_PAYLINK_KEYS:
            os.environ[key] = val
        elif not str(os.environ.get(key) or "").strip():
            os.environ[key] = val


def _st_secret(name: str) -> str | None:
    """Непорожнє значення з st.secrets, якщо Streamlit доступний."""
    try:
        import streamlit as st

        if name in st.secrets and st.secrets[name]:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    return None


def get_secret(name: str) -> str | None:
    """Ключ з .env / os.environ / st.secrets (непорожні значення)."""
    load_project_env()
    val = os.environ.get(name)
    if val and str(val).strip():
        return str(val).strip()
    return _st_secret(name)


def has_secret(name: str) -> bool:
    return bool(get_secret(name))
