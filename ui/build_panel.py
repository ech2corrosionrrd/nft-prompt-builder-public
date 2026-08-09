"""Вкладка 🛠 Constructor (classic): один промпт за налаштуваннями.

Винесено з app.py (декомпозиція хотспоту). `build_user_data` — чиста функція
(тестується без Streamlit). Build-only хелпери (`randomize_settings`,
`single_generate`, `save_to_history`) перенесено сюди; спільні з іншими
вкладками значення/функції приходять у `render()` як параметри.
"""

from __future__ import annotations

import json
import random
import re
from datetime import datetime
from typing import Callable

import streamlit as st
from openai import OpenAI

import storage
from batch import _ANTHROPIC_AVAILABLE, estimate_cost, is_claude_model, supports_temperature
from builder import build_system_instruction, build_tech_params, build_user_data
from options import (
    ASPECT_RATIOS,
    BACKGROUNDS,
    CAMERA_ANGLES,
    LIGHTING,
    MOODS,
    QUALITY_TIERS,
    RANDOM_IDEAS,
    list_index,
)
from preset_labels import preset_label
from styles import NFT_STYLES
from ui import billing_ui, creative_presets, workflow_guide
from ui_strings import api_key_missing, t, ui_lang


def randomize_settings() -> None:
    """Випадкові налаштування конструктора (крім ідеї та трейтів)."""
    st.session_state.style = random.choice(NFT_STYLES)
    st.session_state.camera = random.choice(CAMERA_ANGLES)
    st.session_state.lighting = random.choice(LIGHTING)
    st.session_state.background = random.choice(BACKGROUNDS)
    st.session_state.quality = random.choice(QUALITY_TIERS)
    st.session_state.mood = random.choice(MOODS)
    st.session_state.stylize = random.randrange(100, 1001, 50)
    st.session_state.chaos = random.randrange(0, 101, 5)
    st.session_state.active_template = None
    sync_build_widget_keys()


def sync_build_widget_keys() -> None:
    """Синхронізує build_* / widget-ключі після programmatic зміни canonical полів."""
    ss = st.session_state
    st.session_state["build_style"] = ss.get("style", "")
    st.session_state["build_camera"] = ss.get("camera", "")
    st.session_state["build_lighting"] = ss.get("lighting", "")
    st.session_state["build_background"] = ss.get("background", "")
    st.session_state["build_quality"] = ss.get("quality", "")
    st.session_state["build_mood"] = ss.get("mood", "")
    st.session_state["build_aspect"] = ss.get("aspect_ratio", "")
    st.session_state["build_stylize"] = ss.get("stylize", 250)
    st.session_state["build_chaos"] = ss.get("chaos", 0)
    st.session_state["build_seed"] = ss.get("seed", 0)
    st.session_state["build_idea"] = ss.get("idea", "")


def single_generate(
    model: str,
    api_key: str,
    system_msg: str,
    user_msg: str,
    temperature: float,
) -> tuple[str, float]:
    """Повертає (content, cost). Підтримує OpenAI і Claude."""
    if is_claude_model(model):
        if not _ANTHROPIC_AVAILABLE:
            raise ImportError("Встановіть пакет anthropic: pip install anthropic")
        from anthropic import Anthropic
        claude = Anthropic(api_key=api_key)
        resp = claude.messages.create(
            model=model,
            max_tokens=2048,
            system=system_msg,
            messages=[{"role": "user", "content": user_msg}],
        )
        content = resp.content[0].text
        cost = estimate_cost(model, resp.usage.input_tokens, resp.usage.output_tokens)
        return content, cost
    else:
        client = OpenAI(api_key=api_key)
        sampling = {"temperature": temperature} if supports_temperature(model) else {}
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            **sampling,
        )
        content = resp.choices[0].message.content or ""
        cost = estimate_cost(model, resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return content, cost


def save_to_history(entry: dict) -> None:
    """Додає запис на початок історії (з лімітом) і зберігає для гаманця."""
    st.session_state.history.insert(0, entry)
    st.session_state.history = st.session_state.history[:storage.HISTORY_LIMIT]
    storage.save_history(billing_ui.connected_wallet(), st.session_state.history)


def _preset_label(value: str) -> str:
    return preset_label(value, ui_lang())


def _render_result_content(content: str) -> None:
    """Показує відповідь Builder: промпт у st.code (перенос рядків), решта — markdown."""
    from ui.images_panel import extract_fenced_prompt

    prompt = extract_fenced_prompt(content)
    if prompt:
        st.markdown(f"**{t('build.prompt_label')}**")
        st.code(prompt, language=None)
        # Решта відповіді без першого fence (щоб не дублювати промпт)
        rest = re.sub(
            r"```(?:\w+)?\s*[\s\S]*?```",
            "",
            content,
            count=1,
        ).strip()
        if rest:
            st.markdown(rest)
    else:
        st.markdown(content)


def render(
    *,
    model: str,
    platform: str,
    temperature: float,
    llm_key: str | None,
    include_traits: bool,
    include_negative: bool,
    collection_size: int,
    get_traits_weighted: Callable[[], dict],
    reserve_llm: Callable[[str | None, int, str], bool],
    refund_llm: Callable[[str | None, int, str], None],
) -> None:
    """Рендерить вкладку конструктора одиночного промпта."""
    workflow_guide.render_classic_header("build", get_traits_weighted)
    st.caption(t("build.caption"))
    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.subheader(t("build.settings"))
        creative_presets.render_styles_catalog(NFT_STYLES)

        r1, r2, r3 = st.columns(3)
        with r1:
            if st.button(t("build.random_params"), width='stretch', help=t("build.random_params_help")):
                randomize_settings()
                st.session_state.constructor_flash = "traits_unchanged"
                st.rerun()
        with r2:
            if st.button(t("build.random_idea"), width='stretch', help=t("build.random_idea_help")):
                st.session_state.idea = random.choice(RANDOM_IDEAS)
                st.session_state["build_idea"] = st.session_state.idea
                st.rerun()
        with r3:
            if st.button(t("build.random_all"), width='stretch', help=t("build.random_all_help")):
                randomize_settings()
                st.session_state.idea = random.choice(RANDOM_IDEAS)
                st.session_state["build_idea"] = st.session_state.idea
                st.session_state.constructor_flash = "traits_unchanged"
                st.rerun()

        if st.session_state.pop("constructor_flash", None) == "traits_unchanged":
            st.warning(t("build.traits_unchanged"))

        st.session_state.idea = st.text_input(
            t("build.idea"), value=st.session_state.idea, key="build_idea",
        )

        ca, cb = st.columns(2)
        with ca:
            st.session_state.style = st.selectbox(
                t("build.style"), NFT_STYLES,
                index=list_index(NFT_STYLES, st.session_state.style),
                format_func=_preset_label,
                key="build_style",
            )
            creative_presets.render_style_caption(st.session_state.style)
            st.session_state.camera = st.selectbox(
                t("build.camera"), CAMERA_ANGLES,
                index=list_index(CAMERA_ANGLES, st.session_state.camera),
                format_func=_preset_label,
                key="build_camera",
            )
            st.session_state.lighting = st.selectbox(
                t("build.lighting"), LIGHTING,
                index=list_index(LIGHTING, st.session_state.lighting),
                format_func=_preset_label,
                key="build_lighting",
            )
        with cb:
            st.session_state.background = st.selectbox(
                t("build.background"), BACKGROUNDS,
                index=list_index(BACKGROUNDS, st.session_state.background),
                format_func=_preset_label,
                key="build_background",
            )
            st.session_state.quality = st.selectbox(
                t("build.quality"), QUALITY_TIERS,
                index=list_index(QUALITY_TIERS, st.session_state.quality),
                format_func=_preset_label,
                key="build_quality",
            )
            st.session_state.mood = st.selectbox(
                t("build.mood"), MOODS,
                index=list_index(MOODS, st.session_state.mood),
                format_func=_preset_label,
                key="build_mood",
            )

        with st.expander(t("build.tech_expand"), expanded=True):
            st.session_state.aspect_ratio = st.radio(
                t("build.aspect"), ASPECT_RATIOS,
                index=list_index(ASPECT_RATIOS, st.session_state.aspect_ratio),
                horizontal=True,
                format_func=_preset_label,
                key="build_aspect",
            )
            c1, c2, c3 = st.columns(3)
            with c1:
                st.session_state.stylize = st.slider(
                    t("build.stylize"), 50, 1000, st.session_state.stylize, 50, key="build_stylize",
                )
            with c2:
                st.session_state.chaos = st.slider(
                    t("build.chaos"), 0, 100, st.session_state.chaos, 5, key="build_chaos",
                )
            with c3:
                st.session_state.seed = st.number_input(
                    t("build.seed"), 0, value=st.session_state.seed, key="build_seed",
                )

        st.session_state.extra_notes = st.text_area(
            t("build.extra"), value=st.session_state.extra_notes, height=80, key="build_extra",
        )
        submit_button = st.button(t("build.submit"), type="primary", width='stretch')

    with col2:
        st.subheader(t("build.result"))
        if submit_button:
            if not st.session_state.idea:
                st.error(t("build.idea_required"))
            elif not llm_key:
                st.error(api_key_missing(is_claude_model(model)))
            else:
                lang = ui_lang()
                tech = build_tech_params(platform, st.session_state.aspect_ratio, st.session_state.stylize, st.session_state.chaos, st.session_state.seed)
                user_data = build_user_data(
                    idea=st.session_state.idea,
                    style=st.session_state.style,
                    camera=st.session_state.camera,
                    lighting=st.session_state.lighting,
                    background=st.session_state.background,
                    quality=st.session_state.quality,
                    mood=st.session_state.mood,
                    platform=platform,
                    tech=tech,
                    collection_size=collection_size,
                    extra_notes=st.session_state.extra_notes,
                    lang=lang,
                )
                try:
                    wallet = billing_ui.connected_wallet()
                    if not reserve_llm(wallet, 1, "classic build"):
                        pass
                    else:
                        with st.spinner(t("build.generating")):
                            content, cost = single_generate(
                                model, llm_key,
                                build_system_instruction(
                                    platform, include_traits, include_negative, lang=lang,
                                ),
                                user_data, temperature,
                            )
                            st.session_state.last_result = {
                                "content": content,
                                "idea": st.session_state.idea,
                                "platform": platform,
                                "model": model,
                                "timestamp": datetime.now().isoformat(),
                            }
                            save_to_history(st.session_state.last_result)
                            try:
                                from services import project_service

                                if wallet and st.session_state.get(project_service.SESSION_PROJECT_ID):
                                    project_service.persist(wallet)
                            except OSError:
                                pass
                        billing_ui.show_llm_success(wallet, 1, cost)
                        _render_result_content(content)
                        st.divider()
                        e1, e2 = st.columns(2)
                        with e1:
                            st.download_button("📥 .md", content, f"prompt_{st.session_state.idea[:15]}.md", "text/markdown", width='stretch')
                        with e2:
                            st.download_button("📥 .json", json.dumps(st.session_state.last_result, ensure_ascii=False, indent=2), "prompt.json", "application/json", width='stretch')
                except Exception as e:
                    refund_llm(billing_ui.connected_wallet(), 1, "classic build failed")
                    st.error(t("build.api_error", err=e))
        elif st.session_state.get("last_result"):
            st.info(t("build.last_saved"))
            _render_result_content(st.session_state["last_result"]["content"])
            st.caption(t("build.ai_lang_note"))
        else:
            st.markdown(
                f'<div class="metric-card"><h4>{t("build.quickstart_title")}</h4>'
                f"<p>{t('build.quickstart_body')}</p></div>",
                unsafe_allow_html=True,
            )
    workflow_guide.render_classic_forward_cta("build", get_traits_weighted)
