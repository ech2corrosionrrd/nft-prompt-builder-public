"""Вкладка 🧬 Traits (classic): категорії трейтів і налаштування рідкості.

Винесено з app.py (декомпозиція хотспоту). `weights_to_lines` — чиста функція
(тестується без Streamlit). Спільний `get_traits_weighted` і `render_pipeline_context`
приходять у `render()` параметрами.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

from batch import count_combinations
from i18n import trait_category_label
from options import TRAIT_CATEGORIES, trait_key
from services.traits_from_result import parse_traits_from_content
from ui import rarity_sliders, workflow_guide
from ui_strings import t, ui_lang

# Запис ваг зі слайдерів рідкості назад у текстові поля категорій. Streamlit
# забороняє міняти key віджета в тому ж run, тож кнопка лише ставить pending,
# а застосування — на початку наступного run, ДО створення text_area.
_TRAIT_WEIGHT_PENDING = "_trait_weight_pending"
_TRAIT_IMPORT_PENDING = "_trait_import_pending"


def weights_to_lines(weights: dict[str, int]) -> str:
    """{назва: %} → текст «назва | %» для trait_key(cat)."""
    return "\n".join(f"{name} | {pct}" for name, pct in weights.items())


def apply_pending_trait_weights() -> None:
    """Застосовує відкладені ваги слайдерів у text_area (до їх створення)."""
    pending = st.session_state.pop(_TRAIT_WEIGHT_PENDING, None)
    if not pending:
        return
    for cat, text in pending.items():
        st.session_state[trait_key(cat)] = text


def apply_pending_trait_import() -> None:
    """Імпорт traits з last_result Конструктора (pending-key + rerun)."""
    pending = st.session_state.pop(_TRAIT_IMPORT_PENDING, None)
    if not pending:
        return
    for cat, text in pending.items():
        if cat in TRAIT_CATEGORIES and text:
            st.session_state[trait_key(cat)] = text


def render(
    *,
    collection_size: int,
    get_traits_weighted: Callable[[], dict],
    render_pipeline_context: Callable[[], None],
) -> None:
    """Рендерить вкладку трейтів зі слайдерами рідкості."""
    apply_pending_trait_import()
    apply_pending_trait_weights()  # застосувати ваги слайдерів ДО text_area
    workflow_guide.render_classic_header("traits", get_traits_weighted)
    st.subheader(t("traits.title"))
    render_pipeline_context()
    st.caption(t("traits.caption"))

    last = st.session_state.get("last_result") or {}
    parsed = parse_traits_from_content(str(last.get("content") or ""))
    if parsed:
        st.info(t("traits.import_hint", n=len(parsed)))
        if st.button(t("traits.import_btn"), key="traits_import_from_build", width='stretch'):
            st.session_state[_TRAIT_IMPORT_PENDING] = parsed
            st.rerun()

    trait_cols = st.columns(2)
    lang = ui_lang()
    for i, cat in enumerate(TRAIT_CATEGORIES):
        label = trait_category_label(cat, lang)
        with trait_cols[i % 2]:
            st.text_area(label, height=120, key=trait_key(cat))

    traits_weighted = get_traits_weighted()
    if not traits_weighted:
        st.info(t("traits.empty"))
        workflow_guide.render_classic_forward_cta("traits", get_traits_weighted)
        return

    total = count_combinations(traits_weighted)
    st.metric(t("traits.combos"), f"{total:,}")
    if total < collection_size:
        st.warning(t("traits.combos_low", total=total, target=collection_size))

    # Інтерактивний розподіл рідкості замість сухих warning'ів: на кожну
    # непорожню категорію — слайдери, нормалізовані до 100%. Кнопка пише
    # ваги назад у trait_key(cat) як «назва | %» (двигун читає їх через
    # get_traits_weighted → parse_trait_lines).
    st.divider()
    st.markdown("##### 🎲 Налаштування рідкості traits")
    new_weights: dict[str, dict[str, int]] = {}
    for cat in TRAIT_CATEGORIES:
        items = traits_weighted.get(cat)
        if not items:
            continue
        initial = rarity_sliders.normalize_pct(items)
        new_weights[cat] = rarity_sliders.render_rarity_sliders(
            initial,
            prefix=f"trait{TRAIT_CATEGORIES.index(cat)}",
            title=trait_category_label(cat, lang),
        )
    if new_weights and st.button(
        t("traits.apply_weights"),
        width='stretch', key="traits_rarity_apply",
    ):
        st.session_state[_TRAIT_WEIGHT_PENDING] = {
            cat: weights_to_lines(w) for cat, w in new_weights.items()
        }
        st.rerun()
    workflow_guide.render_classic_forward_cta("traits", get_traits_weighted)
