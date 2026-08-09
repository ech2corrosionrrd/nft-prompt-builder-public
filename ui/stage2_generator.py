"""Етап 2 (Зображення): паралельна черга, A/B, галерея куратора з рейтингом."""

from __future__ import annotations

import streamlit as st

from i18n import trait_type_en
from metadata_provenance import add_rarity_ranks
from services import ai_service, curation, image_qa, payment_service, pipeline_batch, project_service, prompt_lint, prompt_service, quality_metrics, style_bible
from services.ai_service import AIService
from services.prompt_enhancer import dynamic_preset
from services.prompt_quality import (
    TIER_DRAFT,
    TIER_FINAL,
    TIER_HYBRID,
    PromptQualityProfile,
)
from state.pipeline_state import APPROVED_CONTENT, GENERATED_PROMPTS, PIPELINE_IMAGES, sync_mint_queue_from_approved
from ui import curator_gallery
from ui.billing_ui import connected_wallet, wallet_is_verified
from ui.workflow_guide import PENDING_PIPELINE_STAGE_KEY, render_post_images_generation_hint
from ui_strings import t

SOURCE_STAGE1 = "stage1"
SOURCE_MANUAL = "manual"
LARGE_BATCH_THRESHOLD = 50
# Streamlit: pl2_engine — key selectbox; змінити після instantiate → pending + rerun.
PENDING_PL2_ENGINE_KEY = "_pending_pl2_engine"
# pl2_approve_{i} — key toggle; масове схвалення лише через pending + rerun.
PENDING_PL2_BULK_APPROVE_KEY = "_pending_pl2_bulk_approve"
PENDING_PL2_BULK_EXPORT_KEY = "_pending_pl2_bulk_export"
BULK_EXPORT_CONFIRM_THRESHOLD = 10

# Пресети суфікса якості (ПЛАН_ЯКОСТІ.md § Q1.1) → ключ i18n-підпису.
_SUFFIX_PRESETS: dict[str, str] = {
    "pfp": "pl2.preset_pfp",
    "full_body": "pl2.preset_full_body",
    "landscape": "pl2.preset_landscape",
    "dynamic": "pl2.preset_dynamic",
    "geometric": "pl2.preset_geometric",
    "brand": "pl2.preset_brand",
    "event_badge": "pl2.preset_event_badge",
    "fine_art": "pl2.preset_fine_art",
}


_TIERS = [TIER_DRAFT, TIER_FINAL, TIER_HYBRID]
_TIER_LABELS = {TIER_DRAFT: "pl2.tier_draft", TIER_FINAL: "pl2.tier_final", TIER_HYBRID: "pl2.tier_hybrid"}


def _quality_controls(n_prompts: int) -> PromptQualityProfile:
    """Рендерить контролі якості (tier + Style lock); завжди повертає профіль.

    Style Bible (Q2.1) застосовується автоматично, якщо збережена на Етапі 1.
    Чекбокс Style lock — лише пресет кадру + negative (Q1.1).
    """
    bible = style_bible.StyleBible.from_dict(project_service.style_bible_dict())
    bible_text, bible_suffix = "", ""
    if not bible.is_empty():
        bible_text, bible_suffix = bible.bible_text(), bible.as_suffix()
        st.caption(t("pl2.bible_active"))

    if not bible.is_empty() and "pl2_style_lock" not in st.session_state:
        st.session_state["pl2_style_lock"] = True

    # B2: авто-пресет кадру з Style Bible (pfp/full body/…) при зміні біблії.
    bible_sig = bible.bible_text()
    if bible_sig and st.session_state.get("_pl2_suffix_auto_sig") != bible_sig:
        st.session_state["pl2_suffix_preset"] = dynamic_preset(bible_sig)
        st.session_state["_pl2_suffix_auto_sig"] = bible_sig

    tier = st.radio(
        t("pl2.tier"), _TIERS, format_func=lambda x: t(_TIER_LABELS[x]),
        horizontal=True, key="pl2_tier", help=t("pl2.tier_help"),
    )
    hybrid_n = 0
    if tier == TIER_HYBRID:
        hybrid_n = int(st.number_input(
            t("pl2.tier_hybrid_n"), min_value=1, max_value=max(n_prompts, 1),
            value=min(10, max(n_prompts, 1)), key="pl2_hybrid_n",
        ))

    suffix_preset, use_negative = "", False
    archetype_neg = (st.session_state.get("_pl2_archetype_negative") or "").strip()
    if st.checkbox(t("pl2.style_lock"), key="pl2_style_lock", help=t("pl2.style_lock_help")):
        c1, c2 = st.columns([2, 1])
        with c1:
            preset_key = "pl2_suffix_preset"
            current = st.session_state.get(preset_key)
            if current not in _SUFFIX_PRESETS:
                fallback = dynamic_preset(bible_sig) if bible_sig else "pfp"
                st.session_state[preset_key] = (
                    fallback if fallback in _SUFFIX_PRESETS else "pfp"
                )
            suffix_preset = st.selectbox(
                t("pl2.suffix_preset"), list(_SUFFIX_PRESETS), key=preset_key,
                format_func=lambda p: t(_SUFFIX_PRESETS[p]),
            )
        with c2:
            use_negative = st.checkbox(t("pl2.use_negative"), value=True, key="pl2_use_negative")

    return PromptQualityProfile(
        suffix_preset=suffix_preset, extra_suffix=bible_suffix, use_negative=use_negative,
        negative_base=archetype_neg if use_negative else "",
        style_bible=bible_text, quality_tier=tier, hybrid_final_n=hybrid_n,
    )


def _curated_traits(img: dict) -> dict:
    traits = {trait_type_en(str(k)): str(v) for k, v in (img.get("traits") or {}).items()}
    if img.get("style") and "Style" not in traits:
        traits["Style"] = img["style"]
    return traits


def _pipeline_images() -> list[dict]:
    return list(st.session_state.get(PIPELINE_IMAGES, []))


def _batch_slice(prompts: list[dict], limit: int) -> list[dict]:
    """Наступна хвиля: пропускає вже згенеровані за кількістю (1 промпт → 1 кадр)."""
    start = len(_pipeline_images())
    return prompts[start:start + int(limit)]


def _auto_rate_from_qa(
    indices: list[int],
    images: list[dict],
    qa_by_path: dict[str, image_qa.QAResult],
    *,
    only_unrated: bool = True,
) -> int:
    """Проставляє pl2_rating_* з QA Score. Лише 0★ за замовчуванням — ручні оцінки не чіпає."""
    rated = 0
    for i in indices:
        if only_unrated and int(st.session_state.get(f"pl2_rating_{i}", 0)) > 0:
            continue
        path = str(images[i].get("path", ""))
        if not path:
            continue
        qa = qa_by_path.get(path) or image_qa.analyze_image_path(path)
        st.session_state[f"pl2_rating_{i}"] = image_qa.star_rating_from_qa(qa.score)
        rated += 1
    return rated


def _run_batch_queue(
    service: AIService,
    prompts: list[dict],
    engine: str,
    orientation: str,
    wallet: str,
    profile: PromptQualityProfile | None = None,
) -> None:
    progress = st.progress(0, text=t("pl2.queue_progress"))

    def on_progress(done: int, total: int) -> None:
        progress.progress(done / max(total, 1), text=t("pl2.queue_done", done=done, total=total))

    generated, errors = pipeline_batch.run_parallel_batch(
        service, prompts, engine, orientation, wallet, on_progress=on_progress, profile=profile,
        project_assets_dir=project_service.assets_dir(wallet),
    )
    progress.empty()
    existing = _pipeline_images()
    merged = existing + generated
    if len(merged) > 1:
        add_rarity_ranks(merged)
    st.session_state[PIPELINE_IMAGES] = merged
    st.session_state.pop("_pl2_batch_sig", None)
    st.session_state.pop("_pl2_qa_sig", None)
    if generated:
        new_idx = list(range(len(existing), len(merged)))
        qa = curator_gallery.build_qa_cache(merged)
        auto_n = _auto_rate_from_qa(new_idx, merged, qa)
        if auto_n:
            st.caption(t("pl2.auto_rate_hint", n=auto_n))
            if wallet:
                _persist_curator_ratings(wallet, merged)
    project_service.autosave(wallet)
    if errors:
        if existing:
            st.warning(t(
                "pl2.gen_partial_append",
                ok=len(generated), total=len(merged), err=len(errors), first=errors[0],
            ))
        else:
            st.warning(t("pl2.gen_partial", ok=len(generated), err=len(errors), first=errors[0]))
        if any(ai_service.is_moderation_blocked(Exception(e)) for e in errors):
            st.info(t("pl2.gen_partial_moderation_hint"))
    elif generated:
        cr = payment_service.credit_cost(engine) * len(generated)
        if existing:
            st.success(t("pl2.gen_ok_append", n=len(generated), cr=cr, total=len(merged)))
        else:
            st.success(t("pl2.gen_ok", n=len(generated), cr=cr))
        quality_metrics.record_batch_generate(
            wallet, len(generated), engine,
            source="pipeline", style_bible=bool(profile and profile.style_bible),
        )
        render_post_images_generation_hint()


def _run_ab_queue(
    service: AIService,
    item: dict,
    engine_a: str,
    engine_b: str,
    orientation: str,
    wallet: str,
    profile: PromptQualityProfile | None = None,
) -> None:
    with st.spinner(t("pl2.ab_spin")):
        generated, errors = pipeline_batch.run_ab_compare(
            service, item, engine_a, engine_b, orientation, wallet, profile=profile,
            project_assets_dir=project_service.assets_dir(wallet),
        )
    st.session_state[PIPELINE_IMAGES] = generated
    project_service.autosave(wallet)
    if errors:
        st.warning(t("pl2.ab_errors", errs="; ".join(errors)))
    if generated:
        st.success(t("pl2.ab_ok", n=len(generated)))
        quality_metrics.record_batch_generate(
            wallet, len(generated), engine_a,
            source="pipeline", style_bible=bool(profile and profile.style_bible),
        )


def _hydrate_curator_ratings(wallet: str, images: list[dict]) -> None:
    """Підтягує збережені рейтинги для поточного batch (за шляхом файлу)."""
    batch_sig = tuple(str(img.get("path", "")) for img in images)
    if st.session_state.get("_pl2_batch_sig") == batch_sig:
        return
    st.session_state["_pl2_batch_sig"] = batch_sig
    saved = project_service.curator_ratings_dict()
    for i, img in enumerate(images):
        path = str(img.get("path", ""))
        if path and path in saved:
            st.session_state[f"pl2_rating_{i}"] = saved[path]


def _persist_curator_ratings(wallet: str, images: list[dict]) -> None:
    ratings = {
        str(img.get("path", "")): int(st.session_state.get(f"pl2_rating_{i}", 0))
        for i, img in enumerate(images)
        if img.get("path") and int(st.session_state.get(f"pl2_rating_{i}", 0)) > 0
    }
    project_service.merge_curator_ratings(ratings)
    project_service.autosave(wallet)


def _regenerate_curator_image(
    service: AIService,
    images: list[dict],
    index: int,
    engine: str,
    orientation: str,
    wallet: str,
    profile: PromptQualityProfile | None,
    gate_final: bool,
) -> None:
    """Перегенерує один кадр у поточному batch (зберігає traits/prompt source)."""
    if index < 0 or index >= len(images):
        return
    img = images[index]
    source_item = {
        "prompt": img.get("prompt", ""),
        "traits": img.get("traits", {}),
        "style": img.get("style", ""),
        "negative": img.get("negative", ""),
        "seed": img.get("seed"),
        "polish_history": img.get("polish_history", []),
    }
    with st.spinner(t("pl2.regen_spin")):
        rec, err = pipeline_batch.regenerate_one(
            service, source_item, engine, orientation, wallet,
            profile=profile, final=gate_final,
            project_assets_dir=project_service.assets_dir(wallet),
        )
    if rec:
        images[index] = rec
        st.session_state[PIPELINE_IMAGES] = images
        st.session_state.pop(f"pl2_rating_{index}", None)
        st.session_state.pop(f"pl2_approve_{index}", None)
        st.session_state.pop("_pl2_batch_sig", None)
        st.session_state.pop("_pl2_qa_sig", None)
        quality_metrics.record_regenerate(wallet, index, engine, final=gate_final)
        project_service.autosave(wallet)
        st.success(t("pl2.regen_ok", n=index + 1))
    elif err:
        st.error(t("pl2.regen_failed", err=err))


def _approved_item(img: dict, token_num: int, rating: int) -> dict:
    return {
        "name": f"Token #{token_num}",
        "description": img["prompt"],
        "prompt": img["prompt"],
        "traits": _curated_traits(img),
        "engine": img.get("engine", ""),
        "model_version": img.get("engine", ""),
        "generated_at": img.get("generated_at", ""),
        "rarity_score": img.get("rarity_score"),
        "rarity_rank": img.get("rarity_rank"),
        "rarity_tier": img.get("rarity_tier"),
        "rarity_total": img.get("rarity_total"),
        "curator_rating": rating,
        "path": img["path"],
        "filename": img.get("filename", f"{token_num}.png"),
    }


def _commit_approved_indices(
    images: list[dict],
    approved_idx: list[int],
    wallet: str,
    *,
    go_export: bool = True,
) -> None:
    """Записати обрані індекси в APPROVED_CONTENT; опц. синхронізувати чергу мінту."""
    append_mode = st.session_state.get("pl2_append_approved", True)
    saved_batch: list[dict] = []
    if append_mode:
        queue = list(st.session_state.get(APPROVED_CONTENT, []))
        seen_paths = {item.get("path") for item in queue}
        added = 0
        for i in approved_idx:
            img = images[i]
            path = img.get("path")
            if path in seen_paths:
                continue
            rating = int(st.session_state.get(f"pl2_rating_{i}", 0))
            item = _approved_item(img, len(queue) + 1, rating)
            queue.append(item)
            saved_batch.append(item)
            seen_paths.add(path)
            added += 1
        st.session_state[APPROVED_CONTENT] = queue
        st.success(t("pl2.approved_append", n=added, total=len(queue)))
    else:
        new_items = []
        for n, i in enumerate(approved_idx):
            img = images[i]
            rating = int(st.session_state.get(f"pl2_rating_{i}", 0))
            item = _approved_item(img, n + 1, rating)
            new_items.append(item)
            saved_batch.append(item)
        st.session_state[APPROVED_CONTENT] = new_items
        st.success(t("pl2.approved", n=len(approved_idx)))
    quality_metrics.record_curator_save(wallet, saved_batch)
    if wallet:
        _persist_curator_ratings(wallet, images)
    project_service.autosave(wallet)
    if go_export:
        sync_mint_queue_from_approved()
        st.session_state[PENDING_PIPELINE_STAGE_KEY] = "mint"


def _apply_pending_pl2_bulk_approve() -> None:
    """Застосувати відкладене масове схвалення ДО рендеру toggle pl2_approve_{i}."""
    pending = st.session_state.pop(PENDING_PL2_BULK_APPROVE_KEY, None)
    if not pending:
        return
    for i in pending:
        st.session_state[f"pl2_approve_{i}"] = True


def _queue_pl2_bulk_approve(indices: list[int]) -> None:
    """Відкласти масове схвалення — Streamlit не дозволяє міняти key toggle у тому ж run."""
    st.session_state[PENDING_PL2_BULK_APPROVE_KEY] = list(indices)
    st.rerun()


def _render_curator_regen_cost_hint(service: AIService, engine: str, gate_final: bool) -> None:
    """Підказка вартості перегенерації кадра (як у калькуляторі дропу, але для 1 зобр.)."""
    status = service.engine_status()
    per = payment_service.credit_cost(engine, gate_final)
    cheaper = min(
        (e for e in ai_service.ENGINES if not status.get(e)),
        key=lambda e: payment_service.credit_cost(e, gate_final),
        default=None,
    )
    if cheaper and payment_service.credit_cost(cheaper, gate_final) < per:
        st.caption(t(
            "pl2.regen_cost_hint",
            engine=engine, per=per,
            alt=cheaper, alt_per=payment_service.credit_cost(cheaper, gate_final),
        ))
    else:
        st.caption(t("pl2.regen_cost_info", engine=engine, per=per))


def _render_curator_bulk_bar(
    images: list[dict],
    indices: list[int],
    wallet: str,
    qa_by_path: dict[str, image_qa.QAResult],
) -> None:
    """Панель групового схвалення — над сіткою галереї."""
    pending_export = st.session_state.get(PENDING_PL2_BULK_EXPORT_KEY)
    if pending_export:
        st.warning(t(
            "pl2.bulk_export_confirm_warn",
            n=pending_export["count"],
            star=pending_export["star"],
        ))
        yes_col, no_col = st.columns(2)
        with yes_col:
            if st.button(
                t("pl2.bulk_export_confirm_yes"),
                type="primary",
                width='stretch',
                key="pl2_bulk_export_confirm_yes",
            ):
                _commit_approved_indices(
                    images, pending_export["indices"], wallet, go_export=True,
                )
                st.session_state.pop(PENDING_PL2_BULK_EXPORT_KEY, None)
                st.rerun()
        with no_col:
            if st.button(
                t("pl2.bulk_export_confirm_no"),
                width='stretch',
                key="pl2_bulk_export_confirm_no",
            ):
                st.session_state.pop(PENDING_PL2_BULK_EXPORT_KEY, None)
                st.rerun()
        return

    st.markdown(t("pl2.bulk_bar_title"))
    st.caption(t("pl2.bulk_bar_caption"))
    ratings_visible = {i: int(st.session_state.get(f"pl2_rating_{i}", 0)) for i in indices}
    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 2])
    with c1:
        min_star = int(st.number_input(
            t("pl2.bulk_min_star"), 1, 5, 4, key="pl2_bulk_star",
            help=t("pl2.bulk_min_star_help"),
        ))
    with c2:
        if st.button(
            t("pl2.auto_rate_qa"),
            width='stretch',
            key="pl2_auto_rate_btn",
            help=t("pl2.auto_rate_qa_help"),
        ):
            n = _auto_rate_from_qa(indices, images, qa_by_path)
            if n:
                st.toast(t("pl2.auto_rate_hint", n=n))
                st.rerun()
            else:
                st.info(t("pl2.auto_rate_none"))
    with c3:
        if st.button(
            t("pl2.approve_all_visible", n=len(indices)),
            width='stretch',
            key="pl2_bulk_visible_btn",
            help=t("pl2.approve_all_visible_help"),
        ):
            _queue_pl2_bulk_approve(indices)
    with c4:
        if st.button(
            t("pl2.bulk_approve", star=min_star),
            width='stretch',
            key="pl2_bulk_btn",
            help=t("pl2.bulk_approve_help"),
        ):
            bulk_idx = curation.bulk_approve_indices(ratings_visible, min_star)
            if not bulk_idx:
                st.warning(t("pl2.bulk_none_at_star", star=min_star))
            else:
                _queue_pl2_bulk_approve(bulk_idx)
    with c5:
        if st.button(
            t("pl2.bulk_save_export", star=min_star),
            type="primary",
            width='stretch',
            key="pl2_bulk_save_export_btn",
            help=t("pl2.bulk_save_export_help"),
        ):
            bulk_idx = curation.bulk_approve_indices(ratings_visible, min_star)
            if not bulk_idx:
                st.warning(t("pl2.bulk_none_at_star", star=min_star))
            elif len(bulk_idx) >= BULK_EXPORT_CONFIRM_THRESHOLD:
                st.session_state[PENDING_PL2_BULK_EXPORT_KEY] = {
                    "indices": bulk_idx,
                    "star": min_star,
                    "count": len(bulk_idx),
                }
                st.rerun()
            else:
                _commit_approved_indices(images, bulk_idx, wallet, go_export=True)
                st.rerun()


def _render_curator_lite(
    images: list[dict],
    indices: list[int],
    wallet: str,
) -> None:
    """Спрощений куратор для 1/1 — без bulk-фільтрів і сітки."""
    i = indices[0]
    img = images[i]
    st.divider()
    st.markdown(t("pl2.curator_lite_title"))
    st.caption(t("pl2.curator_lite_caption"))
    st.image(img["path"], caption=img.get("prompt", "")[:120], width='stretch')
    if f"pl2_rating_{i}" not in st.session_state:
        st.session_state[f"pl2_rating_{i}"] = 4
    st.slider(t("curator.rate", n=i + 1), 1, 5, key=f"pl2_rating_{i}")
    if st.button(
        t("pl2.save_and_export"),
        type="primary",
        width='stretch',
        key="pl2_approve_btn",
        help=t("pl2.save_and_export_help"),
    ):
        rating = int(st.session_state.get(f"pl2_rating_{i}", 4))
        item = _approved_item(img, 1, rating)
        st.session_state[APPROVED_CONTENT] = [item]
        quality_metrics.record_curator_save(wallet, [item])
        project_service.autosave(wallet)
        sync_mint_queue_from_approved()
        st.session_state[PENDING_PIPELINE_STAGE_KEY] = "mint"
        st.success(t("pl2.approved", n=1))
        if wallet:
            _persist_curator_ratings(wallet, images)
        st.rerun()  # застосувати перехід на «mint» одразу (як у bulk save & export)
    if wallet:
        _persist_curator_ratings(wallet, images)


def _render_curator_panel(
    service: AIService,
    engine: str,
    orientation: str,
    wallet: str,
    profile: PromptQualityProfile | None,
    gate_final: bool,
) -> None:
    images = st.session_state.get(PIPELINE_IMAGES, [])
    if not images:
        return
    if wallet:
        _hydrate_curator_ratings(wallet, images)
    if len(images) > 1 and any(img.get("traits") for img in images):
        add_rarity_ranks(images)

    st.divider()
    st.markdown(t("pl2.curator_title", n=len(images)))
    _render_curator_regen_cost_hint(service, engine, gate_final)
    qa_by_path = curator_gallery.build_qa_cache(images)
    min_rating, min_rarity, trait_q, tier_f, sort_by, min_qa = curator_gallery.render_gallery_filters()
    indices = curator_gallery.filter_images(
        images, min_rating, min_rarity, trait_q, tier_f,
        min_qa_score=min_qa, qa_by_path=qa_by_path,
    )
    indices = curator_gallery.sort_indices(indices, images, sort_by, qa_by_path=qa_by_path)
    st.caption(t("pl2.curator_shown", shown=len(indices), total=len(images)))

    _apply_pending_pl2_bulk_approve()

    if not indices:
        st.info(t("pl2.curator_empty"))
        return

    if len(images) == 1 and len(indices) == 1:
        _render_curator_lite(images, indices, wallet)
        return

    _render_curator_bulk_bar(images, indices, wallet, qa_by_path)
    curator_gallery.render_curator_grid(images, indices, qa_by_path=qa_by_path)

    regen_i = st.session_state.pop("_pl2_regen_index", None)
    if regen_i is not None and wallet:
        _regenerate_curator_image(
            service, images, int(regen_i), engine, orientation, wallet, profile, gate_final,
        )

    # Середній рейтинг прогону (Q2.4): орієнтир якості перед великою чергою.
    ratings_map = {i: int(st.session_state.get(f"pl2_rating_{i}", 0)) for i in indices}
    avg = curation.average_rating(list(ratings_map.values()))
    if avg is not None:
        m1, m2 = st.columns(2)
        m1.metric(t("pl2.avg_rating"), f"{avg:.2f} / 5")
        # Engine winner (Q2.3): двигун із найкращим середнім рейтингом у прогоні.
        winner = curation.engine_winner([(images[i].get("engine", ""), ratings_map[i]) for i in indices])
        if winner:
            m2.metric(t("pl2.engine_winner"), winner)
            if st.button(t("pl2.apply_engine_winner"), key="pl2_apply_engine_winner", width='stretch'):
                st.session_state[PENDING_PL2_ENGINE_KEY] = winner
                st.rerun()
        if curation.is_low_quality(avg):
            st.warning(t("pl2.pilot_low_warn", avg=avg))

    all_ratings = {i: int(st.session_state.get(f"pl2_rating_{i}", 0)) for i in range(len(images))}
    borderline = curation.borderline_indices(all_ratings, 3)
    if borderline and wallet:
        if st.button(
            t("pl2.final_pass_borderline", n=len(borderline)),
            key="pl2_final_pass",
            width='stretch',
        ):
            with st.spinner(t("pl2.final_pass_spin")):
                ok = 0
                for idx in borderline:
                    img = images[idx]
                    source_item = {
                        "prompt": img.get("prompt", ""),
                        "traits": img.get("traits", {}),
                        "style": img.get("style", ""),
                        "negative": img.get("negative", ""),
                        "seed": img.get("seed"),
                        "polish_history": img.get("polish_history", []),
                    }
                    rec, err = pipeline_batch.regenerate_one(
                        service, source_item, engine, orientation, wallet,
                        profile=profile, final=True,
                        project_assets_dir=project_service.assets_dir(wallet),
                    )
                    if rec:
                        images[idx] = rec
                        st.session_state.pop(f"pl2_rating_{idx}", None)
                        st.session_state.pop(f"pl2_approve_{idx}", None)
                        quality_metrics.record_regenerate(wallet, idx, engine, final=True)
                        ok += 1
                st.session_state[PIPELINE_IMAGES] = images
                st.session_state.pop("_pl2_batch_sig", None)
                st.session_state.pop("_pl2_qa_sig", None)
                project_service.autosave(wallet)
            st.success(t("pl2.final_pass_done", ok=ok, n=len(borderline)))
            st.rerun()

    approved_idx = [i for i in indices if st.session_state.get(f"pl2_approve_{i}")]

    st.caption(t("pl2.save_section_caption"))
    st.checkbox(
        t("pl2.append_approved"),
        value=True,
        key="pl2_append_approved",
        help=t("pl2.append_approved_help"),
    )

    if st.button(
        t("pl2.save_and_export") + f" ({len(approved_idx)})",
        type="primary", width='stretch', disabled=not approved_idx, key="pl2_approve_btn",
        help=t("pl2.save_and_export_help"),
    ):
        _commit_approved_indices(images, approved_idx, wallet, go_export=True)
        # Негайний rerun — щоб init_workflow_state застосував PENDING-етап («mint»)
        # у ЦЬОМУ циклі. Без нього перехід відкладається до наступного кліку, і той
        # клік оброблявся б уже на іншому етапі (зниклий віджет → помилка + «стрибок»).
        st.rerun()

    # UX-3: постійний лічильник збереженого в черзі мінту — видно й після Save, і
    # між хвилями генерації (Curator показує лише поточний batch, тож без цього
    # рядка користувач не бачить, скільки вже відкладено до Етапу 3).
    saved_total = len(st.session_state.get(APPROVED_CONTENT, []))
    if saved_total:
        st.caption(t("pl2.approved_running", n=saved_total))

    if wallet:
        _persist_curator_ratings(wallet, images)


def _apply_pending_pl2_engine() -> None:
    """Застосувати відкладений вибір двигуна (engine winner) до наступного run."""
    pending = st.session_state.pop(PENDING_PL2_ENGINE_KEY, None)
    if pending and pending in ai_service.ENGINES:
        st.session_state["pl2_engine"] = pending
        st.session_state["pl2_preferred_engine"] = pending


def render(api_key: str | None) -> None:
    st.markdown(t("pl2.title"))
    st.caption(t("pl2.caption"))
    _apply_pending_pl2_engine()

    # Гаманець визначаємо одразу — використовується і в ранніх хендлерах
    # (напр. «Очистити батч» → autosave), і нижче в гейті балансу.
    wallet = connected_wallet()

    stage1_prompts = st.session_state.get(GENERATED_PROMPTS, [])
    source = st.radio(
        t("pl2.source"),
        [SOURCE_STAGE1, SOURCE_MANUAL],
        format_func=lambda s: (
            f"{t('pl2.from_stage1')} ({len(stage1_prompts)})" if s == SOURCE_STAGE1 else t("pl2.manual")
        ),
        horizontal=True, key="pl2_source",
    )

    if source == SOURCE_MANUAL:
        raw = st.text_area(
            t("pl2.prompts_area"), height=140, key="pl2_raw",
            placeholder="cyber samurai with plasma katana, neon city",
        )
        prompts = prompt_service.from_raw_text(raw)
        st.caption(t("pl2.prompts_found", n=len(prompts)))
    else:
        prompts = stage1_prompts
        if not prompts:
            st.warning(t("pl2.no_stage1"))
        else:
            lint_counts = prompt_lint.summary(prompts)
            if lint_counts:
                parts = ", ".join(t(f"lint.{code}") + f": {n}" for code, n in lint_counts.items())
                st.warning(t("pl2.polish_recommended", parts=parts))

    service = AIService(openai_key=api_key)
    status = service.engine_status()
    ab_mode = st.checkbox(t("pl2.ab_mode"), key="pl2_ab")

    # Міграція застарілого вибору двигуна (DALL-E 3 вилучено з OpenAI API) → дефолт.
    for _ek in ("pl2_engine", "pl2_engine_b"):
        if st.session_state.get(_ek) not in ai_service.ENGINES:
            st.session_state.pop(_ek, None)

    g1, g2, g3 = st.columns(3)
    with g1:
        engine = st.selectbox(
            t("pl2.engine_a") if ab_mode else t("pl2.engine"),
            ai_service.ENGINES, key="pl2_engine",
            format_func=lambda e: e if not status[e] else f"{e} ⚠️",
        )
    with g2:
        orientation = st.radio(t("pl2.size"), list(ai_service.SIZE_PRESETS), horizontal=True, key="pl2_orientation")
    with g3:
        existing_n = len(_pipeline_images()) if prompts and not ab_mode else 0
        remaining = max(0, len(prompts) - existing_n) if prompts else 0
        limit = st.number_input(
            t("pl2.limit"), 1, max(remaining or len(prompts) or 1, 1),
            min(remaining or len(prompts) or 1, 100),
            key="pl2_limit", disabled=not prompts or ab_mode,
        )

    if existing_n > 0 and not ab_mode:
        c_resume, c_clear = st.columns([3, 1])
        with c_resume:
            if remaining > 0:
                st.info(t("pl2.batch_resume", done=existing_n, total=len(prompts), remaining=remaining))
            else:
                st.success(t("pl2.batch_complete", n=existing_n))
        with c_clear:
            if st.button(t("pl2.clear_batch"), key="pl2_clear_batch", width='stretch'):
                st.session_state[PIPELINE_IMAGES] = []
                st.session_state.pop("_pl2_batch_sig", None)
                st.session_state.pop("_pl2_qa_sig", None)
                project_service.autosave(wallet) if wallet else None
                st.rerun()

    engine_b = None
    if ab_mode:
        engine_b = st.selectbox(
            t("pl2.engine_b"), [e for e in ai_service.ENGINES if e != engine], key="pl2_engine_b",
            format_func=lambda e: e if not status[e] else f"{e} ⚠️",
        )

    if status[engine]:
        st.warning(f"{engine}: {status[engine]}.")

    # B6: ненав'язлива підказка двигуна за текстом ідеї — лише якщо рекомендований
    # відрізняється від обраного і реально доступний (не радимо те, чого нема ключа).
    if prompts and not ab_mode:
        idea_text = " ".join(p.get("prompt", "") for p in prompts[:3])
        suggested = prompt_service.suggest_engine(idea_text)
        if suggested != engine and not status.get(suggested):
            st.caption(t("pl2.engine_hint", engine=suggested))

    profile = _quality_controls(len(prompts))

    # Reproducibility (Q3.0): фіксований base seed → відтворювана колекція.
    reproducible = st.checkbox(t("pl2.reproducible"), key="pl2_reproducible", help=t("pl2.reproducible_help"))
    base_seed = 0
    if reproducible:
        base_seed = int(st.number_input(
            t("pl2.base_seed"), min_value=0, max_value=2_000_000_000, value=42, key="pl2_base_seed",
        ))

    verified = wallet_is_verified()
    # Гейт балансу рахуємо за дорожчим рівнем, якщо в прогоні є Final-зображення.
    gate_final = profile.quality_tier != TIER_DRAFT
    per_image_credits = payment_service.credit_cost(engine, gate_final)
    balance = payment_service.get_balance(wallet) if wallet and verified else 0
    # Витрата кредитів лише з підтвердженого (підписом) гаманця — інакше
    # будь-хто, ввівши чужу адресу, спалив би її баланс.
    paywall_blocked = (
        not wallet or not verified
        or balance < per_image_credits
    )

    if not wallet:
        st.warning(t("pl2.connect_wallet"))
    elif not verified:
        st.warning(t("pl2.unverified_wallet"))
    elif balance < per_image_credits:
        st.warning(t("pl2.low_credits"))
    else:
        st.info(t(
            "pl2.debit_info",
            per=per_image_credits,
            bal=balance,
            rate=payment_service.RATE_LIMIT_PER_MINUTE,
        ))

    # #1: мовчазний стрибок вартості при дорожчому двигуні (Flux 1 кр → gpt-image 4 кр).
    # Радимо найдешевший ДОСТУПНИЙ двигун (без ключа двигун не радимо) і рахуємо
    # сумарну різницю за поточний обсяг (limit), щоб 4× стрибок не пройшов непоміченим.
    if prompts and not ab_mode:
        cheaper = min(
            (e for e in ai_service.ENGINES if not status.get(e)),
            key=lambda e: payment_service.credit_cost(e, gate_final),
            default=None,
        )
        if cheaper and payment_service.credit_cost(cheaper, gate_final) < per_image_credits:
            n_run = int(limit)
            alt_per = payment_service.credit_cost(cheaper, gate_final)
            st.warning(t(
                "pl2.engine_cost_warn",
                engine=engine, per=per_image_credits, total=per_image_credits * n_run, n=n_run,
                alt=cheaper, alt_per=alt_per, alt_total=alt_per * n_run,
            ))

    run_disabled = (
        not prompts
        or bool(status[engine])
        or paywall_blocked
        or bool(ab_mode and engine_b and status.get(engine_b))
    )

    if not ab_mode and int(limit) > LARGE_BATCH_THRESHOLD:
        st.warning(t("pl2.large_batch_warn", n=int(limit), cr=per_image_credits * int(limit)))
        if not st.checkbox(t("pl2.large_batch_confirm"), key="pl2_large_confirm"):
            run_disabled = True

    run_prompts = prompt_service.assign_seeds(prompts, base_seed) if reproducible else prompts

    # UX-1: rate-limit лише для welcome-only; поповнені — без штучних хвиль.
    rate = payment_service.generation_rate_limit_per_minute(wallet) if wallet else payment_service.RATE_LIMIT_PER_MINUTE
    if not ab_mode and rate is not None and int(limit) > rate:
        waves = (int(limit) + rate - 1) // rate
        st.warning(t("pl2.rate_wave_warn", rate=rate, n=int(limit), waves=waves, mins=waves))

    # #4 + Pilot (Q2.4): невелика партія перед великою чергою — оцінити якість, не
    # палячи кредити. Коли Pilot доступний, він — ПЕРВИННИЙ CTA (primary), а повний
    # запуск стає вторинним: новачок має спершу перевірити стиль на 10, а не одразу
    # витратити кредити на весь дроп.
    pilot_n = curation.pilot_count(remaining or len(prompts)) if not ab_mode else curation.pilot_count(len(prompts))
    pilot_available = bool(pilot_n) and not ab_mode

    if pilot_available:
        st.caption(t("pl2.pilot_recommend"))
        if st.button(
            t("pl2.pilot", n=pilot_n), type="primary", width='stretch', key="pl2_pilot",
            disabled=run_disabled, help=t("pl2.pilot_help"),
        ):
            with st.spinner(t("pl2.parallel_spin")):
                pilot_prompts = curation.pilot_subset(
                    run_prompts[existing_n:] if existing_n else run_prompts, pilot_n,
                )
                _run_batch_queue(
                    service, pilot_prompts,
                    engine, orientation, wallet, profile=profile,
                )

    run_label = (
        t("pl2.run_ab") if ab_mode
        else t("pl2.run_batch_continue", n=int(limit), from_=existing_n + 1) if existing_n and remaining
        else t("pl2.run_batch", n=int(limit))
    )
    if st.button(
        run_label,
        type="secondary" if pilot_available else "primary",
        width='stretch', key="pl2_run", disabled=run_disabled or (not ab_mode and remaining == 0),
    ):
        if ab_mode and engine_b:
            _run_ab_queue(service, run_prompts[0], engine, engine_b, orientation, wallet, profile=profile)
        else:
            st.session_state[GENERATED_PROMPTS] = run_prompts
            batch = _batch_slice(run_prompts, int(limit))
            if not batch:
                st.warning(t("pl2.batch_complete", n=existing_n))
            else:
                with st.spinner(t("pl2.parallel_spin")):
                    _run_batch_queue(service, batch, engine, orientation, wallet, profile=profile)

    _render_curator_panel(service, engine, orientation, wallet, profile, gate_final)
