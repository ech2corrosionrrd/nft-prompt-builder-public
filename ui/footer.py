"""Футер застосунку: версія, legal, підтримка."""

from __future__ import annotations

import os

import streamlit as st

from ui_strings import LANG_EN, t, ui_lang


def _legal_url() -> str:
    """Публічні ToS/Privacy/Refund. Легал подає FastAPI (`api_server` /legal).

    На ai.w3ir.io тунель роутить на FastAPI лише /auth і /login — /legal туди НЕ
    доходить (потрапляє у Streamlit → порожня сторінка). Тому дефолтна база —
    `w3ir.io` (FastAPI-origin, де /legal реально працює). Перекривається
    `LEGAL_BASE_URL`, якщо оператор додасть /legal-правило в тунель ai.w3ir.io.
    """
    base = (os.environ.get("LEGAL_BASE_URL") or "https://w3ir.io").strip()
    suffix = "/legal/en" if ui_lang() == LANG_EN else "/legal"
    return f"{base.rstrip('/')}{suffix}"


def render() -> None:
    """Футер: підпис, сусідні поверхні екосистеми, легал, пошта.

    Лінки на Gremlins/Genesis тримаємо саме тут: білдер — вхідна точка воронки,
    а зворотного шляху з нього в спільноту й колекцію не було — граф сайтів
    замикався лише через apex w3ir.io.
    """
    legal = _legal_url()
    st.markdown(
        f"{t('footer.caption')}  \n"
        f"[w3ir.io](https://w3ir.io) · "
        f"[Gremlins Passport](https://gremlins.w3ir.io/?utm_source=builder&utm_medium=footer&utm_campaign=ecosystem) · "
        f"[Genesis](https://mint.w3ir.io/?utm_source=builder&utm_medium=footer&utm_campaign=ecosystem) · "
        f"[{t('footer.legal')}]({legal}) · "
        f"[w3ir@pm.me](mailto:w3ir@pm.me)",
        unsafe_allow_html=False,
    )
