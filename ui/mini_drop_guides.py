"""Гайди міні-дропів (~25): мапінг шаблон → i18n-ключ, рендер у sidebar / Stage 1."""

from __future__ import annotations

import streamlit as st

from templates import COLLECTION_TEMPLATES, template_supply_badge_args
from ui_strings import t

# Ключі ui_strings з покроковими гайдами (uk + en).
TEMPLATE_GUIDE_KEYS: dict[str, str] = {
    "1/1 Fine Art": "welcome.one_guide",
    "Abstract Geometry Series": "welcome.batch_guide",
    "Atmospheric Worlds": "welcome.landscape_guide",
    "Event Badge Series": "welcome.event_guide",
    "Brand Icon System": "welcome.brand_guide",
    "Glitch Geometry": "welcome.glitch_guide",
    "Sumi-e Ink Studies": "welcome.sumie_guide",
    "Chibi Champs": "welcome.chibi_guide",
    "Vinyl Toy Squad": "welcome.vinyl_guide",
    "Retro Poster Series": "welcome.retro_guide",
    "Chrome Fashion Icons": "welcome.chrome_guide",
    "Art Deco Medallions": "welcome.artdeco_guide",
    "Line Art Monograms": "welcome.lineart_guide",
    "W3IR Showcase Demo": "welcome.showcase_guide",
}

SHOW_GUIDE_EXPAND_KEY = "_expand_mini_template_guide"


def is_mini_drop(template_name: str | None) -> bool:
    """Чи шаблон — міні-дроп (supply ≤ SUPPLY_MINI_MAX, badge ~N)."""
    if not template_name or template_name not in COLLECTION_TEMPLATES:
        return False
    size = int(COLLECTION_TEMPLATES[template_name].get("collection_size", 0))
    args = template_supply_badge_args(size)
    return args is not None and args.get("kind") == "mini"


def guide_key(template_name: str | None) -> str | None:
    """i18n-ключ гайда для шаблону або None."""
    if not template_name:
        return None
    return TEMPLATE_GUIDE_KEYS.get(template_name)


def queue_guide_expanded() -> None:
    """Після apply_template — розгорнути гайд у sidebar на наступному run."""
    st.session_state[SHOW_GUIDE_EXPAND_KEY] = True


def render_template_guide(
    template_name: str | None,
    *,
    key_suffix: str = "default",
    expanded: bool | None = None,
) -> None:
    """Розгортач із гайдом; нічого не рендерить, якщо немає мапінгу."""
    gkey = guide_key(template_name)
    if not gkey:
        return
    if expanded is None:
        expanded = bool(
            key_suffix == "active"
            and st.session_state.pop(SHOW_GUIDE_EXPAND_KEY, False)
        )
    with st.expander(
        t("sidebar.template_guide_label"),
        expanded=expanded,
        key=f"mini_drop_guide_{key_suffix}",
    ):
        st.markdown(t(gkey))
        st.caption(t("sidebar.template_guide_help_hint"))
