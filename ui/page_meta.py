"""OG/meta-теги та <title> для Streamlit-застосунку (BUG-006, BUG-010).

Streamlit не має нативного OG API; теги інжектяться на початку body.
Telegram/Discord часто їх підхоплюють при fetch HTML.
"""

from __future__ import annotations

import html

import streamlit as st

from ui_strings import t

_OG_IMAGE = "https://w3ir.io/og-card.png"
_OG_URL = "https://ai.w3ir.io/"


def inject_page_meta() -> None:
    """Інжектить og:* та узгоджений title (викликати одразу після set_page_config)."""
    title = t("app.page_title")
    desc = t("app.og_description")
    st.markdown(
        f"""
        <meta property="og:type" content="website" />
        <meta property="og:title" content="{html.escape(title)}" />
        <meta property="og:description" content="{html.escape(desc)}" />
        <meta property="og:url" content="{_OG_URL}" />
        <meta property="og:image" content="{_OG_IMAGE}" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content="{html.escape(title)}" />
        <meta name="twitter:description" content="{html.escape(desc)}" />
        <meta name="twitter:image" content="{_OG_IMAGE}" />
        """,
        unsafe_allow_html=True,
    )
