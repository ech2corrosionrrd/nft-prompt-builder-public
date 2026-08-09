"""Етап 1 (Текст): конструктор об'єктних промптів із режимами масштабування."""

import streamlit as st

import storage
from services import ai_service, archetype_generator, billing_guard, content_safety, pipeline_batch, project_service, prompt_lint, prompt_polish, prompt_service, payment_service, style_bible, template_pipeline, trait_rules
from state.pipeline_state import GENERATED_PROMPTS
from templates import COLLECTION_TEMPLATES, template_archetype
from ui.billing_ui import connected_wallet
from options import (
    COLOR_DETAIL_PRESETS,
    CORE_OBJECT_PRESETS,
    ENGINE_TAG_PRESETS,
    MATRIX_STORAGE_KEYS,
    matrix_trait_options,
)
from preset_labels import preset_label
from ui import creative_presets, mini_drop_guides, workflow_guide
from ui_strings import matrix_categories, t
from ui_strings import ui_lang

_BIBLE_KEYS = {
    "style": "pl1_bible_style",
    "lighting": "pl1_bible_lighting",
    "camera": "pl1_bible_camera",
    "background_rule": "pl1_bible_background",
}
_BIBLE_CLEAR_PENDING = "_pending_pl1_bible_clear"
_BIBLE_FILL_PENDING = "_pending_pl1_bible_fill"
_MATRIX_APPLY_PENDING = "_pending_pl1_matrix_apply"

MODE_KEYS = ["single", "group", "matrix", "raw", "i2p"]
# Внутрішні ключі матриці (зберігання в data/matrices/) — не перекладаються
_MATRIX_STORAGE_KEYS = MATRIX_STORAGE_KEYS


def _active_archetype() -> str:
    arch = st.session_state.get("_pl2_archetype")
    if arch:
        return str(arch)
    active = st.session_state.get("active_template")
    if active and active in COLLECTION_TEMPLATES:
        return template_archetype(COLLECTION_TEMPLATES[active])
    return "pfp"


def _matrix_caption_key(archetype: str) -> str:
    if archetype == "abstract_geometric":
        return "pl1.matrix_caption_abstract"
    if archetype == "landscape":
        return "pl1.matrix_caption_landscape"
    return "pl1.matrix_caption"


def _preset_label(value: str) -> str:
    return preset_label(value, ui_lang())


def _preset_or_custom_select(label: str, presets: list[str], key: str, placeholder: str) -> str:
    """Випадаючий список пресетів; за замовчуванням порожньо — своє значення або вибір зі списку."""
    value = st.selectbox(
        label,
        presets,
        key=key,
        index=None,
        placeholder=placeholder,
        accept_new_options=True,
        format_func=_preset_label,
    )
    return (value or "").strip()


def _details_inputs(lighting: list[str], cameras: list[str], key_prefix: str) -> list[str]:
    d1, d2 = st.columns(2)
    dash = t("common.dash")
    with d1:
        light = st.selectbox(
            t("pl1.lighting"), [dash] + lighting, key=f"{key_prefix}_light",
            accept_new_options=True,
            format_func=_preset_label,
        )
        camera = st.selectbox(
            t("pl1.camera"), [dash] + cameras, key=f"{key_prefix}_camera",
            accept_new_options=True,
            format_func=_preset_label,
        )
    with d2:
        colors = _preset_or_custom_select(
            t("pl1.colors"),
            COLOR_DETAIL_PRESETS,
            key=f"{key_prefix}_colors",
            placeholder=t("pl1.colors_ph"),
        )
    details = [d for d in (light, camera) if d != dash]
    if colors:
        details.append(colors)
    return details


def _store(prompts: list[dict]) -> None:
    # B1: рання content-safety перевірка на етапі введення — даємо зрозумілий
    # фідбек ще до Етапу 2 (серверний бар'єр у pipeline_batch лишається теж).
    for p in prompts:
        if not content_safety.check_prompt_safety(p.get("prompt", "")).ok:
            st.error(t("error.blocked_prompt"))
            return
    st.session_state[GENERATED_PROMPTS] = prompts
    project_service.autosave(connected_wallet())
    st.success(t("pl1.stored", n=len(prompts)))
    workflow_guide.render_post_prompt_store_forward()


def render(styles: list[str], cameras: list[str], lighting: list[str], api_key: str | None = None) -> None:
    st.markdown(t("pl1.title"))
    st.caption(t("pl1.caption"))
    active_tpl = st.session_state.get("active_template")
    if mini_drop_guides.guide_key(active_tpl):
        mini_drop_guides.render_template_guide(active_tpl, key_suffix="stage1")
        if st.button(t("nav.help_all_mini_drops"), key="pl1_help_mini_catalog"):
            workflow_guide.queue_help_section("4")
            st.info(t("nav.help_open_tab"))

    _render_style_bible()

    mode = st.radio(
        t("pl1.mode_scale"), MODE_KEYS,
        format_func=lambda k: t(f"pl1.mode.{k}"),
        horizontal=True, key="pl1_mode",
    )

    if mode == "i2p":
        _render_image_to_prompt(api_key)
        _render_preview(api_key)
        return

    if mode == "raw":
        st.caption(t("pl1.raw_caption"))
        raw = st.text_area(t("pl1.raw_prompts"), height=160, key="pl1_raw",
                           placeholder="cyber samurai with plasma katana, neon city")
        if st.button(t("pl1.use_raw"), type="primary", width='stretch', key="pl1_use_raw"):
            prompts = prompt_service.from_raw_text(raw)
            if prompts:
                _store(prompts)
            else:
                st.error(t("pl1.raw_empty"))
        _render_preview(api_key)
        return

    tags = _preset_or_custom_select(
        t("pl1.engine_tags"),
        ENGINE_TAG_PRESETS,
        key="pl1_tags",
        placeholder=t("pl1.engine_tags_ph"),
    )

    if mode in ("single", "group", "matrix"):
        creative_presets.render_styles_catalog(styles)

    if mode == "single":
        core = _preset_or_custom_select(
            t("pl1.core_object"),
            CORE_OBJECT_PRESETS,
            key="pl1_core_single",
            placeholder=t("pl1.core_object_ph"),
        )
        style = st.selectbox(
            t("pl1.style"), styles, key="pl1_style_single", accept_new_options=True,
            format_func=_preset_label,
        )
        creative_presets.render_style_caption(style)
        details = _details_inputs(lighting, cameras, "pl1_single")
        if st.button(t("pl1.build_one"), type="primary", width='stretch', key="pl1_go_single"):
            if not core:
                st.error(t("pl1.core_required"))
            else:
                _store(prompt_service.build_single(core, style, details, tags))

    elif mode == "group":
        core = _preset_or_custom_select(
            t("pl1.core_group"),
            CORE_OBJECT_PRESETS,
            key="pl1_core_group",
            placeholder=t("pl1.core_object_ph"),
        )
        chosen_styles = st.multiselect(
            t("pl1.styles_multi"), styles, key="pl1_styles_group", accept_new_options=True,
            format_func=_preset_label,
        )
        creative_presets.render_selected_style_notes(chosen_styles)
        details = _details_inputs(lighting, cameras, "pl1_group")
        if st.button(
            t("pl1.build_group", n=len(chosen_styles)), type="primary",
            width='stretch', key="pl1_go_group", disabled=not chosen_styles,
        ):
            if not core:
                st.error(t("pl1.core_required"))
            else:
                _store(prompt_service.build_group(core, chosen_styles, details, tags))

    else:
        arch = _active_archetype()
        st.caption(t(_matrix_caption_key(arch)))
        _render_archetype_generator(api_key, arch)
        _apply_pending_matrix()
        categories: dict[str, list[str]] = {}
        display_cats = matrix_categories(arch)
        trait_presets = matrix_trait_options()
        for storage_key, label in zip(_MATRIX_STORAGE_KEYS, display_cats):
            values = st.multiselect(
                label,
                trait_presets.get(storage_key, []),
                key=f"pl1_matrix_{storage_key}",
                accept_new_options=True,
                placeholder=t("pl1.matrix_traits_placeholder"),
                format_func=_preset_label,
            )
            if values:
                categories[storage_key] = values
        dash = t("common.dash")
        style = st.selectbox(
            t("pl1.shared_style"), [dash] + styles, key="pl1_style_matrix",
            accept_new_options=True,
            format_func=_preset_label,
        )
        if style != dash:
            creative_presets.render_style_caption(style)
        total = prompt_service.matrix_size(categories)
        st.metric(t("pl1.matrix_combos"), f"{total:,}")
        if categories:
            with st.expander(t("pl1.rarity_preview")):
                st.dataframe(
                    pipeline_batch.matrix_trait_distribution(categories),
                    width='stretch', hide_index=True,
                )
        msave1, msave2 = st.columns([2, 1])
        with msave1:
            tpl_name = st.text_input(t("pl1.save_matrix_name"), key="pl1_matrix_tpl_name", placeholder="my-matrix")
        with msave2:
            if st.button(t("pl1.save_matrix"), width='stretch', key="pl1_save_matrix", disabled=not categories):
                saved = storage.save_matrix_template(connected_wallet(), tpl_name or "matrix", {
                    "categories": categories,
                    "style": style if style != dash else "",
                    "tags": tags,
                })
                st.success(t("pl1.matrix_saved", name=saved))
        saved_tpls = storage.list_matrix_templates(connected_wallet())
        if saved_tpls:
            pick = st.selectbox(t("pl1.load_matrix"), [dash] + saved_tpls, key="pl1_load_matrix")
            if pick != dash and st.button(t("pl1.apply_matrix"), key="pl1_apply_matrix"):
                data = storage.load_matrix_template(connected_wallet(), pick)
                if data:
                    st.session_state[_MATRIX_APPLY_PENDING] = {
                        cat: list(data.get("categories", {}).get(cat, []))
                        for cat in _MATRIX_STORAGE_KEYS
                    }
                    st.rerun()
        # Правила несумісності traits (Q2.2): пари значень, що не йдуть разом.
        rules_raw = st.text_area(
            t("pl1.rules_label"), key="pl1_matrix_rules", height=80,
            placeholder="golden crown | viking helmet",
            help=t("pl1.rules_help"),
        )
        rules = trait_rules.parse_rules(rules_raw)
        if total > 500:
            st.warning(t("pl1.matrix_warn"))
        rich_matrix = st.checkbox(
            t("pl1.rich_matrix"), key="pl1_rich_matrix", help=t("pl1.rich_matrix_help"),
        )
        if st.button(
            t("pl1.gen_matrix", n=total), type="primary",
            width='stretch', key="pl1_go_matrix", disabled=total == 0,
        ):
            built = prompt_service.build_matrix(
                categories, style if style != dash else "", [], tags,
            )
            kept = trait_rules.filter_combos(built, rules)
            blocked = len(built) - len(kept)
            if blocked:
                st.info(t("pl1.rules_blocked", n=blocked))
            if rich_matrix:
                with st.spinner(t("pl1.rich_matrix_spin")):
                    polished = _execute_polish(kept, api_key, prompt_polish.MODE_LIGHT)
                _store(polished if polished is not None else kept)
                if polished is None and not api_key:
                    st.info(t("pl1.rich_matrix_no_key"))
            else:
                _store(kept)

    _render_preview(api_key)


def _wallet_bible() -> style_bible.StyleBible:
    return style_bible.StyleBible.from_dict(project_service.style_bible_dict())


def _apply_pending_bible() -> None:
    """Скинути / підставити поля Style Bible на початку run (pending-key)."""
    if st.session_state.pop(_BIBLE_CLEAR_PENDING, False):
        for key in _BIBLE_KEYS.values():
            st.session_state[key] = ""
    fill = st.session_state.pop(_BIBLE_FILL_PENDING, None)
    if isinstance(fill, dict):
        for attr, key in _BIBLE_KEYS.items():
            st.session_state[key] = str(fill.get(attr, ""))


def _apply_pending_matrix() -> None:
    """Підставити завантажену матрицю ДО text_input (pending-key)."""
    pending = st.session_state.pop(_MATRIX_APPLY_PENDING, None)
    if not isinstance(pending, dict):
        return
    for cat, raw in pending.items():
        key = f"pl1_matrix_{cat}"
        if isinstance(raw, list):
            st.session_state[key] = raw
        else:
            # зворотна сумісність ізі старими шаблонами (рядок через кому)
            st.session_state[key] = prompt_service.parse_comma_list(str(raw))


_ARCHETYPE_GEN_PENDING = "_pending_pl1_archetype_gen"


def _render_archetype_generator(api_key: str | None, archetype: str) -> None:
    """P3.5 — LLM-список для першої осі матриці."""
    pending = st.session_state.pop(_ARCHETYPE_GEN_PENDING, None)
    if isinstance(pending, list) and pending:
        st.session_state[f"pl1_matrix_{MATRIX_STORAGE_KEYS[0]}"] = pending

    with st.expander(
        t("pl1.archetype_gen_title_abstract" if archetype == "abstract_geometric" else "pl1.archetype_gen_title")
    ):
        st.caption(t("pl1.archetype_gen_help"))
        theme_default = (st.session_state.get("idea") or "").strip()
        c1, c2 = st.columns([2, 1])
        with c1:
            theme = st.text_input(
                t("pl1.archetype_gen_theme"),
                value=theme_default,
                key="pl1_archetype_theme",
            )
        with c2:
            n = st.number_input(
                t("pl1.archetype_gen_n"),
                min_value=1,
                max_value=200,
                value=50,
                step=1,
                key="pl1_archetype_n",
            )
        cost = archetype_generator.credit_cost(int(n))
        if st.button(
            t("pl1.archetype_gen_go", n=int(n), cr=cost),
            key="pl1_archetype_gen_go",
            width='stretch',
        ):
            if not api_key:
                st.info(t("pl1.archetype_gen_no_key"))
                return
            safety = content_safety.check_prompt_safety(theme)
            if not safety.ok:
                st.error(t("pl1.archetype_gen_blocked", code=safety.code or safety.category))
                return
            wallet = connected_wallet()
            ok, err = billing_guard.try_reserve(
                wallet, cost, engine="llm-archetypes", note=f"generate {n} archetypes",
            )
            if not ok:
                _show_billing_error(err)
                return
            try:
                with st.spinner(t("pl1.archetype_gen_go", n=int(n), cr=cost)):
                    names, gen_errors = archetype_generator.generate_archetypes(
                        int(n),
                        theme,
                        archetype=archetype,
                        style_bible=_wallet_bible().bible_text(),
                        call=archetype_generator.openai_call(api_key),
                    )
            except Exception as exc:
                billing_guard.refund(wallet, cost, engine="llm-archetypes", note="archetype gen failed")
                st.error(t("pl1.i2p_error", err=exc))
                return
            if not names:
                billing_guard.refund(wallet, cost, engine="llm-archetypes", note="archetype gen empty")
                st.error(t("pl1.i2p_error", err=gen_errors[0] if gen_errors else "empty"))
                return
            if len(names) < int(n) and gen_errors:
                billing_guard.refund(
                    wallet,
                    archetype_generator.credit_cost(int(n) - len(names)),
                    engine="llm-archetypes",
                    note="archetype gen partial refund",
                )
                st.warning(
                    t(
                        "pl1.archetype_gen_partial",
                        n=len(names),
                        want=int(n),
                        detail="; ".join(gen_errors[:2]),
                    )
                )
            st.session_state[_ARCHETYPE_GEN_PENDING] = names
            st.success(
                t(
                    "pl1.archetype_gen_ok",
                    n=len(names),
                    axis=matrix_categories(archetype)[0],
                )
            )
            st.rerun()


def _sync_bible_widgets_to_session(wallet: str) -> None:
    """Тихий sync полів Bible у session (без кнопки Save) — щоб rerun/load не губили правки."""
    bible = style_bible.StyleBible(
        **{attr: str(st.session_state.get(key, "") or "") for attr, key in _BIBLE_KEYS.items()}
    )
    if bible.to_dict() != project_service.style_bible_dict():
        project_service.set_style_bible(bible.to_dict())


def _render_style_bible() -> None:
    """Редактор Style Bible колекції (ПЛАН_ЯКОСТІ.md § Q2.1), збереження per-wallet."""
    wallet = connected_wallet()
    _apply_pending_bible()
    # Пересів значень зі сховища лише при зміні гаманця (інакше затирали б правки
    # сесії) — ДО створення віджетів, щоб не порушити заборону Streamlit на зміну
    # key після інстанціювання (landmine pending-key).
    marker = f"{wallet}:{st.session_state.get(project_service.SESSION_PROJECT_ID, '')}"
    if st.session_state.get("_pl1_bible_marker") != marker:
        saved = _wallet_bible()
        for attr, key in _BIBLE_KEYS.items():
            st.session_state[key] = getattr(saved, attr)
        st.session_state["_pl1_bible_marker"] = marker

    with st.expander(t("pl1.bible_title"), expanded=not _wallet_bible().is_empty()):
        st.caption(t("pl1.bible_help"))
        if not wallet:
            st.warning(t("pl1.bible_no_wallet"))
        dash = t("common.dash")
        tc1, tc2 = st.columns([3, 1])
        with tc1:
            tpl = st.selectbox(
                t("pl1.bible_template_pick"), [dash] + list(COLLECTION_TEMPLATES),
                key="pl1_bible_tpl",
            )
        with tc2:
            if st.button(t("pl1.bible_fill"), key="pl1_bible_fill", disabled=tpl == dash, width='stretch'):
                tpl_dict = COLLECTION_TEMPLATES[tpl]
                filled = style_bible.from_template(tpl_dict)
                st.session_state[_BIBLE_FILL_PENDING] = {
                    attr: getattr(filled, attr) for attr in _BIBLE_KEYS
                }
                st.session_state[_MATRIX_APPLY_PENDING] = template_pipeline.matrix_categories_from_template(tpl_dict)
                style = str(tpl_dict.get("style", "")).strip()
                if style:
                    st.session_state["pl1_style_matrix"] = style
                st.rerun()

        st.text_input(t("pl1.bible_style"), key=_BIBLE_KEYS["style"])
        st.text_input(t("pl1.bible_lighting"), key=_BIBLE_KEYS["lighting"])
        st.text_input(t("pl1.bible_camera"), key=_BIBLE_KEYS["camera"])
        st.text_input(t("pl1.bible_background"), key=_BIBLE_KEYS["background_rule"])

        sc1, sc2 = st.columns([2, 1])
        with sc1:
            if st.button(t("pl1.bible_save"), type="primary", width='stretch', key="pl1_bible_save"):
                if not wallet:
                    st.error(t("pl1.bible_no_wallet"))
                else:
                    bible = style_bible.StyleBible(
                        **{attr: st.session_state.get(key, "") for attr, key in _BIBLE_KEYS.items()}
                    )
                    project_service.set_style_bible(bible.to_dict())
                    project_service.autosave(wallet)
                    st.success(t("pl1.bible_saved"))
        with sc2:
            if st.button(t("pl1.bible_clear"), width='stretch', key="pl1_bible_clear"):
                if wallet:
                    project_service.set_style_bible({})
                    project_service.autosave(wallet)
                st.session_state[_BIBLE_CLEAR_PENDING] = True
                st.rerun()

    if wallet:
        _sync_bible_widgets_to_session(wallet)


def _render_image_to_prompt(api_key: str | None) -> None:
    st.caption(t("pl1.i2p_caption"))
    upload = st.file_uploader(t("pl1.i2p_upload"), type=["png", "jpg", "jpeg"], key="pl1_i2p_upload")
    if upload:
        st.image(upload.getvalue(), width=300)
    detailed = st.checkbox(t("pl1.i2p_detailed"), key="pl1_i2p_detailed", help=t("pl1.i2p_detailed_help"))
    if st.button(t("pl1.i2p_go"), type="primary", width='stretch',
                 key="pl1_i2p_go", disabled=not upload):
        if not api_key:
            st.error(t("pl1.i2p_no_key"))
            return
        wallet = connected_wallet()
        vision_cost = billing_guard.CREDIT_COST_VISION
        ok, err = billing_guard.try_reserve(wallet, vision_cost, engine="vision", note="image-to-prompt")
        if not ok:
            if err == "wallet":
                st.error(t("pl2.connect_wallet"))
            elif err == "unverified":
                st.error(t("pl2.unverified_wallet"))
            elif err == "credits":
                st.error(t("pl2.low_credits"))
            elif err == "rate":
                st.error(t("pl2.rate_limit", rate=payment_service.RATE_LIMIT_PER_MINUTE))
            elif err == "freemium":
                st.error(t("pl2.freemium_limit"))
            return
        mime = "image/jpeg" if upload.name.lower().endswith((".jpg", ".jpeg")) else "image/png"
        try:
            with st.spinner(t("pl1.i2p_analyzing")):
                formula = ai_service.image_to_prompt(api_key, upload.getvalue(), mime, detailed=detailed)
        except Exception as e:
            billing_guard.refund(wallet, vision_cost, engine="vision", note="i2p failed")
            st.error(t("pl1.i2p_error", err=e))
            return
        f1, f2 = st.columns(2)
        with f1:
            st.markdown(f"**Core Object:** {formula['core']}")
            st.markdown(f"**Style:** {formula['style'] or '—'}")
        with f2:
            st.markdown(f"**Detailing:** {', '.join(formula['details']) or '—'}")
            st.markdown(f"**Engine Tags:** {formula['tags'] or '—'}")
        st.code(formula["prompt"], language=None)
        _store([formula])


def _render_preview(api_key: str | None = None) -> None:
    prompts = st.session_state.get(GENERATED_PROMPTS, [])
    if not prompts:
        return
    st.divider()
    st.markdown(t("pl1.preview_title", n=len(prompts)))
    issues = prompt_lint.lint_prompts(prompts)
    st.dataframe(
        [
            {
                "#": i + 1,
                t("pl1.col_prompt"): (p["prompt"][:110] + "…") if len(p["prompt"]) > 110 else p["prompt"],
                t("pl1.col_traits"): ", ".join(f"{k}: {v}" for k, v in p.get("traits", {}).items()),
                t("pl1.lint_col"): ", ".join(t(f"lint.{code}") for code in issues.get(i, [])),
            }
            for i, p in enumerate(prompts)
        ],
        width='stretch', hide_index=True,
    )
    counts = prompt_lint.summary(prompts)
    if counts:
        parts = ", ".join(f"{t(f'lint.{code}')}: {n}" for code, n in counts.items())
        st.warning(t("pl1.lint_summary", parts=parts))
    _render_polish(prompts, api_key)


def _execute_polish(
    prompts: list[dict], api_key: str | None, mode: str,
) -> list[dict] | None:
    """LLM-полірування списку промптів. None — ключ/білінг/збій."""
    if not prompts:
        return []
    if not api_key:
        return None
    n_chunks = prompt_polish.chunk_count(len(prompts))
    wallet = connected_wallet()
    ok, err = billing_guard.try_reserve(wallet, n_chunks, engine="llm-polish", note="prompt polish")
    if not ok:
        _show_billing_error(err)
        return None
    try:
        results, errors = prompt_polish.polish_prompts(
            prompts, call=prompt_polish.openai_call(api_key), mode=mode,
            style_bible=_wallet_bible().bible_text(),
            archetype=_active_archetype(),
        )
    except Exception as e:
        billing_guard.refund(wallet, n_chunks, engine="llm-polish", note="polish failed")
        st.error(t("pl1.i2p_error", err=e))
        return None
    if errors:
        billing_guard.refund(wallet, len(errors), engine="llm-polish", note="polish partial refund")
        st.warning(t("pl1.polish_partial", err=len(errors)))
    return results


def _render_polish(prompts: list[dict], api_key: str | None) -> None:
    """LLM-полірування поточних промптів (ПЛАН_ЯКОСТІ.md § Q1.4), 1 кр/чанк."""
    n_chunks = prompt_polish.chunk_count(len(prompts))
    with st.expander(t("pl1.polish_title")):
        st.caption(t("pl1.polish_help", size=prompt_polish.CHUNK_SIZE))
        mode = st.radio(
            t("pl1.polish_mode"), [prompt_polish.MODE_LIGHT, prompt_polish.MODE_FULL],
            format_func=lambda m: t(f"pl1.polish_{m}"), horizontal=True, key="pl1_polish_mode",
        )
        # #3: прев'ю «до/після» на першому промпті (1 кр.) — побачити, що саме
        # зміниться, перш ніж застосовувати до всіх N промптів.
        _render_polish_preview(prompts, api_key, mode)
        if not st.button(
            t("pl1.polish_go", n=len(prompts), cr=n_chunks),
            type="primary", width='stretch', key="pl1_polish_go",
        ):
            return
        with st.spinner(t("pl1.polish_spin")):
            results = _execute_polish(prompts, api_key, mode)
        if results is None:
            return
        st.session_state[GENERATED_PROMPTS] = results
        project_service.autosave(connected_wallet())
        st.success(t("pl1.polish_ok", n=len(results)))
        st.rerun()


def _render_polish_preview(prompts: list[dict], api_key: str | None, mode: str) -> None:
    """#3: прогін полірування на 1-му промпті + показ before/after (коштує 1 кр.).

    Дешевий спосіб побачити, що саме зробить LLM, перш ніж платити за весь дроп.
    Збій/порожня відповідь → рефанд. Результат не застосовується до промптів —
    лише відображається; для застосування є основна кнопка «Полірувати».
    """
    if st.button(t("pl1.polish_preview"), width='stretch', key="pl1_polish_preview"):
        if not api_key:
            st.error(t("pl1.polish_no_key"))
            return
        wallet = connected_wallet()
        ok, err = billing_guard.try_reserve(wallet, 1, engine="llm-polish", note="prompt polish preview")
        if not ok:
            _show_billing_error(err)
            return
        try:
            with st.spinner(t("pl1.polish_spin")):
                results, errors = prompt_polish.polish_prompts(
                    prompts[:1], call=prompt_polish.openai_call(api_key), mode=mode,
                    style_bible=_wallet_bible().bible_text(),
                    archetype=_active_archetype(),
                )
        except Exception as e:
            billing_guard.refund(wallet, 1, engine="llm-polish", note="polish preview failed")
            st.error(t("pl1.i2p_error", err=e))
            return
        if errors or not results:
            billing_guard.refund(wallet, 1, engine="llm-polish", note="polish preview refund")
            st.warning(t("pl1.polish_partial", err=len(errors) or 1))
            return
        st.session_state["pl1_polish_preview_pair"] = {
            "before": prompts[0].get("prompt", ""),
            "after": results[0].get("prompt", ""),
        }

    pair = st.session_state.get("pl1_polish_preview_pair")
    if pair:
        pc1, pc2 = st.columns(2)
        with pc1:
            st.caption(t("pl1.polish_before"))
            st.code(pair["before"], language=None)
        with pc2:
            st.caption(t("pl1.polish_after"))
            st.code(pair["after"], language=None)


def _show_billing_error(err: str | None) -> None:
    if err == "wallet":
        st.error(t("pl2.connect_wallet"))
    elif err == "unverified":
        st.error(t("pl2.unverified_wallet"))
    elif err == "credits":
        st.error(t("pl2.low_credits"))
    elif err == "rate":
        st.error(t("pl2.rate_limit", rate=payment_service.RATE_LIMIT_PER_MINUTE))
