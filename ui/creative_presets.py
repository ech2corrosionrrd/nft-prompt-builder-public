"""Підказки під творчими пресетами (стилі) у Streamlit — без зміни prompt-значень."""

from __future__ import annotations

import streamlit as st

from preset_labels import preset_label, style_description
from ui_strings import t, ui_lang


def render_style_caption(value: str) -> None:
    """Підпис під selectbox стилю — що це за вигляд і для яких колекцій."""
    if not value:
        return
    desc = style_description(value, ui_lang())
    if desc:
        st.caption(desc)


def render_styles_catalog(styles: list[str], *, expanded: bool = False) -> None:
    """Згорнутий каталог усіх стилів — коли користувач лише бачить коротку назву в списку."""
    with st.expander(t("creative.styles_catalog"), expanded=expanded):
        lang = ui_lang()
        for value in styles:
            label = preset_label(value, lang)
            desc = style_description(value, lang)
            if desc:
                st.markdown(f"**{label}** — {desc}")
            else:
                st.markdown(f"**{label}**")


def render_selected_style_notes(values: list[str]) -> None:
    """Примітки для multiselect (режим «Група») — по одному рядку на обраний стиль."""
    if not values:
        return
    with st.expander(t("creative.style_notes"), expanded=len(values) <= 3):
        lang = ui_lang()
        for value in values:
            label = preset_label(value, lang)
            desc = style_description(value, lang)
            if desc:
                st.caption(f"**{label}** — {desc}")
