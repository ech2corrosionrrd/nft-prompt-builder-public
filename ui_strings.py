"""UI-локалізація Streamlit (EN / UA; розширення — нові LANG_* у SUPPORTED_UI_LANGS).

Дефолт для публічного сайту — **English** (`UI_DEFAULT_LANG` або LANG_DEFAULT).
Продукт для мінту (промпти, on-chain metadata) — завжди EN — див. i18n.py.
Коментарі в коді — українською (CLAUDE.md).
"""

from __future__ import annotations

import os

import streamlit as st
from strings import admin, collection, commerce, pipeline, quality, shell

LANG_KEY = "ui_lang"
LANG_UA = "uk"
LANG_EN = "en"
LANG_DEFAULT = LANG_EN
SUPPORTED_UI_LANGS = (LANG_EN, LANG_UA)

# Доменні словники i18n. Історично — один літерал на 3200+ рядків; розбито по
# доменах 2026-06-27 (strings/*.py). Порядок модулів зберігає історичний порядок
# ключів; guard ловить випадковий дубль ключа між доменами при майбутніх правках.
_STRING_MODULES = (shell, collection, pipeline, commerce, quality, admin)


def _merge_strings() -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for _mod in _STRING_MODULES:
        for _key, _block in _mod.STRINGS.items():
            if _key in merged:
                raise ValueError(f"дубльований ключ перекладу {_key!r} (модуль {_mod.__name__})")
            merged[_key] = _block
    return merged


_STRINGS: dict[str, dict[str, str]] = _merge_strings()


def api_key_missing(is_claude: bool) -> str:
    return t("build.api_anthropic_missing" if is_claude else "build.api_openai_missing")


def package_label(package_id: str) -> str:
    """Перекладена назва пакета кредитів (fallback — uk-дефолт з PACKAGES.label)."""
    key = f"pkg.{package_id}.label"
    label = t(key)
    return label if label != key else package_id


def package_note(package_id: str) -> str:
    """Перекладений опис пакета кредитів (порожньо, якщо ключа немає)."""
    key = f"pkg.{package_id}.note"
    note = t(key)
    return "" if note == key else note


_LANG_QUERY = "lang"  # ?lang=uk у URL — persist вибору мови між reload (BUG-4)


def _query_lang() -> str | None:
    """Мова з ?lang= URL (валідована) або None. Fail-soft поза Streamlit-runtime.

    URL переживає browser reload, а session_state — ні; тож query-параметр
    зберігає вибір мови для Welcome-гейту, що рендериться до sidebar-перемикача.
    """
    try:
        raw = (st.query_params.get(_LANG_QUERY) or "").strip().lower()
    except Exception:
        return None
    return raw if raw in SUPPORTED_UI_LANGS else None


def default_ui_lang() -> str:
    """Мова UI за замовчуванням: ?lang= URL → env UI_DEFAULT_LANG → EN."""
    from_query = _query_lang()
    if from_query:
        return from_query
    raw = (os.environ.get("UI_DEFAULT_LANG") or LANG_DEFAULT).strip().lower()
    return raw if raw in SUPPORTED_UI_LANGS else LANG_DEFAULT


def ui_lang() -> str:
    return st.session_state.get(LANG_KEY, default_ui_lang())


def _persist_lang_to_query(lang: str) -> None:
    """Записати вибір мови в ?lang= (переживає reload). Fail-soft."""
    try:
        if st.query_params.get(_LANG_QUERY) != lang:
            st.query_params[_LANG_QUERY] = lang
    except Exception:
        pass


def set_ui_lang(lang: str) -> None:
    if lang in SUPPORTED_UI_LANGS:
        st.session_state[LANG_KEY] = lang
        _persist_lang_to_query(lang)


def translate(key: str, lang: str, **fmt) -> str:
    """Рядок UI для заданої мови (без Streamlit-сесії). Fallback: lang → EN → UA → key."""
    block = _STRINGS.get(key, {})
    text = block.get(lang) or block.get(LANG_EN) or block.get(LANG_UA) or key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, ValueError):
            return text
    return text


def t(key: str, lang: str | None = None, **fmt) -> str:
    """Повертає рядок UI для поточної мови. Fallback: обрана → EN → UA → key."""
    return translate(key, lang or ui_lang(), **fmt)


def pipeline_modes() -> list[str]:
    """Режими Етапу 1 з урахуванням мови."""
    return [
        t("pl1.mode.single"),
        t("pl1.mode.group"),
        t("pl1.mode.matrix"),
        t("pl1.mode.raw"),
        t("pl1.mode.i2p"),
    ]


_MATRIX_CAT_BY_ARCHETYPE: dict[str, tuple[str, str, str]] = {
    "pfp": ("pl1.cat.character", "pl1.cat.background", "pl1.cat.accessory"),
    "abstract_geometric": ("pl1.cat.form", "pl1.cat.background", "pl1.cat.pattern"),
    "landscape": ("pl1.cat.scene", "pl1.cat.mood", "pl1.cat.background"),
    "brand_icon": ("pl1.cat.layout", "pl1.cat.background", "pl1.cat.accessory"),
    "event_badge": ("pl1.cat.tier", "pl1.cat.style", "pl1.cat.background"),
    "fine_art": ("pl1.cat.subject", "pl1.cat.background", "pl1.cat.detail"),
}


def matrix_categories(archetype: str = "pfp") -> list[str]:
    """Підписи осей матриці Етапу 1 за архетипом колекції."""
    keys = _MATRIX_CAT_BY_ARCHETYPE.get(archetype, _MATRIX_CAT_BY_ARCHETYPE["pfp"])
    return [t(k) for k in keys]


def _on_lang_change() -> None:
    """Синхронізувати вибір selectbox у ?lang= (persist між reload)."""
    _persist_lang_to_query(st.session_state.get(LANG_KEY, default_ui_lang()))


def render_lang_selector() -> None:
    """Перемикач мови в sidebar (EN першим — дефолт для публічного сайту)."""
    opts = [LANG_EN, LANG_UA]
    labels = {"uk": "🇺🇦 Українська", "en": "🇬🇧 English"}
    if LANG_KEY not in st.session_state:
        st.session_state[LANG_KEY] = default_ui_lang()
    st.selectbox(
        t("lang.label"),
        opts,
        format_func=lambda x: labels[x],
        key=LANG_KEY,
        on_change=_on_lang_change,
    )
