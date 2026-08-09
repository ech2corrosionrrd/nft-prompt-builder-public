"""Sidebar Tier 1–3 (UX-A2): мова, шаблон, AI, проєкти."""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

import storage
import theme
from batch import MODEL_PRICES, _ANTHROPIC_AVAILABLE, is_claude_model
from builder import PLATFORMS
from services import admin_access, project_service
from templates import COLLECTION_TEMPLATES, template_archetype, template_description, template_supply_badge_args, visible_templates
from state.sidebar_constants import SIDEBAR_NO_TEMPLATE
from ui import billing_ui, project_bar, workflow_guide, mini_drop_guides
from ui.workflow_guide import MODE_CLASSIC, workflow_mode
from ui_strings import render_lang_selector, t, ui_lang

_TEMPLATE_PICK_KEY = "sidebar_template_pick"
_TEMPLATE_PICK_PENDING = "_sidebar_template_pick_pending"


_ARCHETYPE_EMOJI: dict[str, str] = {
    "abstract_geometric": "🔷",
    "brand_icon": "🏷️",
    "landscape": "🌄",
    "event_badge": "🎫",
    "fine_art": "🎨",
}


def _archetype_badge(tpl: dict) -> str:
    emoji = _ARCHETYPE_EMOJI.get(template_archetype(tpl))
    return f" {emoji}" if emoji else ""


def _template_label(name: str) -> str:
    return COLLECTION_TEMPLATES[name]["label"] if name in COLLECTION_TEMPLATES else name


def _template_supply_badge_text(tpl: dict) -> str:
    """Короткий підпис supply для selectbox і картки шаблону."""
    args = template_supply_badge_args(tpl.get("collection_size", 0))
    if not args:
        return ""
    return t(f"sidebar.template_badge_{args['kind']}", short=args["short"])


def _template_option_label(name: str) -> str:
    if name not in COLLECTION_TEMPLATES:
        return name
    base = _template_label(name)
    badge = _template_supply_badge_text(COLLECTION_TEMPLATES[name])
    arch = _archetype_badge(COLLECTION_TEMPLATES[name])
    return f"{base}{arch} · {badge}" if badge else f"{base}{arch}"


def _template_card_html(tpl: dict) -> str:
    badge = _template_supply_badge_text(tpl)
    badge_html = ""
    args = template_supply_badge_args(tpl.get("collection_size", 0))
    if badge and args:
        badge_html = (
            f'<span class="template-supply-badge template-supply-badge--{args["kind"]}">'
            f"{badge}</span>"
        )
    desc = template_description(tpl, ui_lang())
    return (
        f'<div class="template-card"><h4>{tpl["label"]}{badge_html}</h4>'
        f'<p>{desc}</p></div>'
    )


def queue_template_pick_reset() -> None:
    """Скинути selectbox шаблону на наступному run (pending-key, не чіпати widget key)."""
    st.session_state[_TEMPLATE_PICK_PENDING] = SIDEBAR_NO_TEMPLATE


def _apply_pending_sidebar_template_pick() -> None:
    """Підставити відкладене значення selectbox ДО його створення (pending + rerun)."""
    pending = st.session_state.pop(_TEMPLATE_PICK_PENDING, None)
    if pending is not None:
        st.session_state[_TEMPLATE_PICK_KEY] = pending


def _render_classic_config_export(
    wallet: str,
    *,
    collect_config: Callable[[], dict],
    apply_config: Callable[[dict], None],
) -> None:
    """Ручний export/import JSON конфігу конструктора — лише classic-режим."""
    with st.expander(t("sidebar.classic_config_export"), expanded=False):
        st.caption(t("sidebar.classic_config_hint"))
        snapshot_name = st.text_input(
            t("sidebar.config_snapshot_name"),
            placeholder="my-config",
            key="sidebar_classic_snapshot_name",
        )
        if st.button(t("sidebar.save_config_snapshot"), width='stretch'):
            if snapshot_name.strip():
                saved = storage.save_project(wallet, snapshot_name.strip(), collect_config())
                st.success(t("sidebar.config_snapshot_saved", path=saved))
            else:
                st.error(t("sidebar.config_snapshot_name_required"))

        snapshots = storage.list_projects(wallet)
        if snapshots:
            selected = st.selectbox(
                t("sidebar.saved_config_snapshots"),
                snapshots,
                key="sidebar_classic_snapshot_pick",
            )
            sc1, sc2 = st.columns(2)
            with sc1:
                if st.button(t("sidebar.load_config_snapshot"), width='stretch'):
                    config = storage.load_project(wallet, selected)
                    if config:
                        apply_config(config)
                        st.rerun()
            with sc2:
                if st.button(t("sidebar.delete_config_snapshot"), width='stretch'):
                    storage.delete_project(wallet, selected)
                    st.rerun()


def render_sidebar(
    *,
    apply_template: Callable[[str], None],
    apply_config: Callable[[dict], None],
    collect_config: Callable[[], dict],
    get_api_key: Callable[[], str | None],
    get_llm_api_key: Callable[[str], str | None],
    has_persistent_api_key: Callable[[], bool],
    has_persistent_anthropic_key: Callable[[], bool],
) -> dict[str, Any]:
    """Рендер бічної панелі. Повертає model/platform/temperature/traits flags для app.py."""
    # Tier 1: set-once преференції компактним рядом — не витісняють баланс/проєкт.
    lang_col, theme_col = st.columns(2)
    with lang_col:
        render_lang_selector()
    with theme_col:
        theme.render_theme_selector()
    workflow_guide.render_nav_to_welcome()
    workflow_guide.render_sidebar_mode_selector()
    billing_ui.render_sidebar_balance()
    project_bar.render_sidebar_project()

    st.divider()
    st.markdown(t("sidebar.templates"))
    st.caption(t("sidebar.templates_supply_hint"))
    template_names = visible_templates(admin_access.is_admin(billing_ui.connected_wallet()))
    active = st.session_state.get("active_template")

    if active and active in COLLECTION_TEMPLATES:
        tpl = COLLECTION_TEMPLATES[active]
        st.markdown(_template_card_html(tpl), unsafe_allow_html=True)
        st.caption(t("sidebar.active_template", label=tpl["label"]))
        mini_drop_guides.render_template_guide(active, key_suffix="active")

    template_options = [SIDEBAR_NO_TEMPLATE] + template_names
    _apply_pending_sidebar_template_pick()
    selected_template = st.selectbox(
        t("sidebar.pick_template"),
        template_options,
        format_func=lambda x: (
            t("sidebar.no_template") if x == SIDEBAR_NO_TEMPLATE else _template_option_label(x)
        ),
        key=_TEMPLATE_PICK_KEY,
    )
    if (
        selected_template != SIDEBAR_NO_TEMPLATE
        and selected_template != active
        and selected_template in COLLECTION_TEMPLATES
    ):
        tpl = COLLECTION_TEMPLATES[selected_template]
        st.markdown(_template_card_html(tpl), unsafe_allow_html=True)
        if st.button(t("sidebar.apply_template"), width='stretch'):
            apply_template(selected_template)
            wallet = billing_ui.connected_wallet()
            if wallet:
                project_service.persist(wallet)
            st.rerun()

    st.divider()  # межа зони «Налаштування» (expanders + версія)
    available_models = [m for m in MODEL_PRICES if not is_claude_model(m) or _ANTHROPIC_AVAILABLE]
    model = available_models[0]
    platform = list(PLATFORMS.keys())[0]
    temperature = 0.7
    include_traits = True
    include_negative = True
    collection_size = int(st.session_state.get("collection_size", 100))

    classic = workflow_mode() == MODE_CLASSIC
    # У Pipeline модель/platform/temperature не використовуються — ховаємо зайве.
    # Expander лишаємо лише в classic або коли dev без серверних ключів.
    show_ai_expander = classic or not has_persistent_api_key()

    if show_ai_expander:
        with st.expander(t("sidebar.ai_settings"), expanded=False):
            api_key = get_api_key()
            if not has_persistent_api_key():
                st.text_input(
                    t("sidebar.openai_key"),
                    type="password",
                    placeholder="sk-...",
                    help=t("sidebar.openai_key_help"),
                    key="api_key_input",
                )
                api_key = st.session_state.get("api_key_input") or api_key

            if classic:
                model = st.selectbox(
                    t("sidebar.llm_model"),
                    available_models,
                    help=t("sidebar.prompt_model_help"),
                    key="sidebar_prompt_model",
                )
                st.caption(t("sidebar.prompt_model_caption"))

                if is_claude_model(model):
                    if not has_persistent_anthropic_key():
                        st.text_input(
                            t("sidebar.anthropic_key"),
                            type="password",
                            placeholder="sk-ant-...",
                            key="anthropic_key_input",
                        )
                    st.caption(t("sidebar.images_openai"))

                platform = st.selectbox(t("sidebar.platform"), list(PLATFORMS.keys()), key="sidebar_platform")
                temperature = st.slider(t("sidebar.creativity"), 0.0, 1.0, 0.7, 0.1, key="sidebar_temperature")

                llm_key = get_llm_api_key(model)
                if is_claude_model(model):
                    st.success(t("sidebar.anthropic_ok")) if llm_key else st.warning(t("sidebar.anthropic_missing"))
                    if not api_key:
                        st.caption(t("sidebar.openai_for_images"))
                else:
                    st.success(t("sidebar.api_ok")) if llm_key else st.warning(t("sidebar.api_missing"))
            else:
                st.caption(t("sidebar.pipeline_llm_fixed"))
                if not api_key:
                    st.warning(t("sidebar.api_missing"))

    with st.expander(t("sidebar.generation_opts"), expanded=False):
        st.caption(t("sidebar.constructor_opts"))
        include_traits = st.checkbox(t("sidebar.gen_traits"), value=True, key="sidebar_gen_traits")
        include_negative = st.checkbox(t("sidebar.negative_prompt"), value=True, key="sidebar_negative_prompt")
        if workflow_mode() == MODE_CLASSIC:
            collection_size = st.number_input(
                t("sidebar.collection_size"), 1, 10000, step=10, key="collection_size",
            )
        else:
            collection_size = int(st.session_state.get("collection_size", 1))
            st.caption(t("sidebar.collection_size_pipeline", n=collection_size))

        if workflow_mode() == MODE_CLASSIC:
            billing_ui.render_session_spend_sidebar(classic_mode=True)

        _wallet = billing_ui.connected_wallet()
        if workflow_mode() == MODE_CLASSIC and _wallet:
            st.divider()
            _render_classic_config_export(
                _wallet,
                collect_config=collect_config,
                apply_config=apply_config,
            )

    st.caption(t("app.version"))
    return {
        "model": model,
        "platform": platform,
        "temperature": temperature,
        "include_traits": include_traits,
        "include_negative": include_negative,
        "collection_size": collection_size,
    }
