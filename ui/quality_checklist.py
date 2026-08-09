"""NFT Quality Checklist UI — Export Center (recommendation only)."""

from __future__ import annotations

import json

import streamlit as st

from services import billing_guard, nft_quality_checklist
from secrets_env import get_secret
from ui import billing_ui
from ui import workflow_guide
from ui_strings import t, ui_lang

QC_REPORT_KEY = "qc_report"
QC_AI_TIPS_KEY = "qc_ai_tips"
QC_AI_DEEP_DIVE_KEY = "qc_ai_deep_dive"
QC_CHECKLIST_KEY = "qc_checklist"
QC_CHECKLIST_SIG_KEY = "_qc_checklist_sig"
QC_FOCUS_KEY = "qc_focus_code"
QC_FORCE_EXPAND_KEY = "qc_force_expand"

# preflight warn code → QC item code (CN-4)
PREFLIGHT_QC_FOCUS: dict[str, str] = {
    "empty_description": "description_empty",
    "low_curator_rating": "curation_weak",
    "duplicate_prompt": "prompts_duplicate",
    "name_too_long": "name_too_long",
}


def _widget_key(field: str) -> str:
    return f"qc_cb_{field}"


def sync_checklist_widget_keys() -> None:
    """Синхронізувати widget-ключі після load проєкту."""
    checklist = nft_quality_checklist.normalize_checklist(st.session_state.get(QC_CHECKLIST_KEY))
    st.session_state[QC_CHECKLIST_KEY] = checklist
    for key in nft_quality_checklist.CHECKLIST_KEYS:
        st.session_state[_widget_key(key)] = checklist[key]


def _sync_checklist_from_widgets() -> dict[str, bool]:
    checklist = nft_quality_checklist.normalize_checklist(st.session_state.get(QC_CHECKLIST_KEY))
    for key in nft_quality_checklist.CHECKLIST_KEYS:
        wkey = _widget_key(key)
        if wkey in st.session_state:
            checklist[key] = bool(st.session_state[wkey])
    st.session_state[QC_CHECKLIST_KEY] = checklist
    return checklist


def _init_checklist_widgets() -> None:
    checklist = nft_quality_checklist.normalize_checklist(st.session_state.get(QC_CHECKLIST_KEY))
    st.session_state[QC_CHECKLIST_KEY] = checklist
    for key in nft_quality_checklist.CHECKLIST_KEYS:
        wkey = _widget_key(key)
        if wkey not in st.session_state:
            st.session_state[wkey] = checklist[key]


def _clear_ai_results() -> None:
    st.session_state.pop(QC_AI_TIPS_KEY, None)
    st.session_state.pop(QC_AI_DEEP_DIVE_KEY, None)


def _item_text(item: nft_quality_checklist.CheckItem) -> str:
    return t(f"qc.item.{item.code}", **item.fmt)


def _render_item(item: nft_quality_checklist.CheckItem, *, focus_code: str | None = None) -> None:
    text = _item_text(item)
    if item.code == focus_code:
        st.caption(t("qc.focus_hint"))
    if item.severity == "fail":
        st.error(text)
    elif item.severity == "warn":
        st.warning(text)
    elif item.severity == "pass":
        st.success(text)
    else:
        st.info(text)


def _render_category(category: str, items: list[nft_quality_checklist.CheckItem], *, focus_code: str | None = None) -> None:
    cat_items = [i for i in items if i.category == category]
    if not cat_items:
        return
    st.markdown(t(f"qc.cat.{category}"))
    for item in cat_items:
        _render_item(item, focus_code=focus_code)


def _render_checklist_inputs() -> dict[str, bool]:
    _init_checklist_widgets()
    st.markdown(t("qc.checklist.section"))
    st.caption(t("qc.checklist.hint"))

    col_m, col_l = st.columns(2)
    with col_m:
        st.markdown(t("qc.checklist.marketing"))
        for key in nft_quality_checklist.MARKETING_CHECKLIST_KEYS:
            st.checkbox(t(f"qc.cb.{key}"), key=_widget_key(key))
    with col_l:
        st.markdown(t("qc.checklist.legal"))
        for key in nft_quality_checklist.LEGAL_CHECKLIST_KEYS:
            st.checkbox(t(f"qc.cb.{key}"), key=_widget_key(key))

    return _sync_checklist_from_widgets()


def _render_vision_block(title_key: str, data: dict, *, score_key: str, ok_key: str, warn_key: str) -> None:
    st.markdown(t(title_key))
    if data.get("skipped"):
        st.caption(t("qc.ai.skipped", reason=data.get("reason", "—")))
        return
    score = int(data.get("overall_score") or 0)
    st.caption(t(score_key, score=score))
    readable = data.get("readable_at_small_size")
    consistent = data.get("consistent")
    if readable is True or consistent is True:
        st.success(t(ok_key))
    elif readable is False or consistent is False:
        st.warning(t(warn_key))
    summary = str(data.get("summary") or "").strip()
    if summary:
        st.markdown(summary)
    for issue in data.get("issues") or []:
        st.markdown(f"- {issue}")
    for pair in data.get("pairs") or []:
        note = str(pair.get("note") or "").strip()
        if note:
            st.markdown(f"- #{pair.get('index_a')} vs #{pair.get('index_b')}: {note}")


def _render_ai_results() -> None:
    deep = st.session_state.get(QC_AI_DEEP_DIVE_KEY)
    tips = []
    if deep:
        _render_vision_block(
            "qc.ai.thumbnail_title",
            deep.thumbnail,
            score_key="qc.ai.thumbnail_score",
            ok_key="qc.ai.thumbnail_ok",
            warn_key="qc.ai.thumbnail_warn",
        )
        st.divider()
        _render_vision_block(
            "qc.ai.style_title",
            deep.style,
            score_key="qc.ai.style_score",
            ok_key="qc.ai.style_ok",
            warn_key="qc.ai.style_warn",
        )
        tips = deep.tips
    else:
        tips = st.session_state.get(QC_AI_TIPS_KEY) or []

    if not tips:
        return
    st.divider()
    st.markdown(t("qc.ai_section"))
    for tip in tips:
        cat = tip.get("category", "marketing")
        if cat in nft_quality_checklist.CATEGORIES:
            label = t(f"qc.cat.{cat}")
        else:
            label = cat
        st.markdown(f"**{label}** — {tip.get('text', '')}")


def _analyze(
    assets: list[dict],
    collection_name: str,
    *,
    platform: str,
    royalty_bps: int,
    symbol: str,
    mint_price_sol: float | None,
    ipfs_pinned: bool,
    ipfs_result: dict | None,
    planned_count: int,
    upscale_enabled: bool,
    upscale_available: bool,
    preflight_errors: list[tuple[str, int | None]] | None,
    preflight_warnings: list[tuple[str, int | None]] | None,
    checklist: dict[str, bool],
) -> nft_quality_checklist.QualityReport:
    return nft_quality_checklist.analyze_collection(
        assets,
        collection_name=collection_name,
        platform=platform,
        royalty_bps=royalty_bps,
        symbol=symbol,
        mint_price_sol=mint_price_sol,
        ipfs_pinned=ipfs_pinned,
        ipfs_result=ipfs_result,
        planned_count=planned_count,
        upscale_enabled=upscale_enabled,
        upscale_available=upscale_available,
        preflight_errors=preflight_errors,
        preflight_warnings=preflight_warnings,
        checklist=checklist,
    )


def render_quality_checklist(
    assets: list[dict],
    collection_name: str,
    *,
    platform: str,
    royalty_bps: int = 500,
    symbol: str = "",
    mint_price_sol: float | None = None,
    ipfs_pinned: bool = False,
    ipfs_result: dict | None = None,
    planned_count: int = 0,
    upscale_enabled: bool = False,
    upscale_available: bool = False,
    preflight_errors: list[tuple[str, int | None]] | None = None,
    preflight_warnings: list[tuple[str, int | None]] | None = None,
    force_expanded: bool = False,
) -> int | None:
    """Expander з чек-листом якості (не блокує експорт). Повертає score після run."""
    focus_code = st.session_state.get(QC_FOCUS_KEY)
    expanded = force_expanded or bool(st.session_state.pop(QC_FORCE_EXPAND_KEY, False))
    with st.expander(t("qc.title"), expanded=expanded):
        st.caption(t("qc.subtitle"))
        st.caption(t("qc.workflow_guide"))
        st.caption(t("qc.disclaimer"))
        workflow_guide.render_contextual_help_link("4", key_suffix="qc_export")

        checklist = _render_checklist_inputs()
        checklist_sig = json.dumps(checklist, sort_keys=True)
        prev_sig = st.session_state.get(QC_CHECKLIST_SIG_KEY)
        checklist_changed = prev_sig is not None and prev_sig != checklist_sig
        st.session_state[QC_CHECKLIST_SIG_KEY] = checklist_sig

        run = st.button(t("qc.run"), key="qc_run_btn", width='stretch')

        st.markdown(t("qc.ai_section_title"))
        st.caption(t("qc.deep_dive_hint"))
        api_key = get_secret("OPENAI_API_KEY") or st.session_state.get("api_key_input")
        col_ai, col_deep = st.columns(2)
        with col_ai:
            ai_btn = st.button(
                t("qc.ai_run", credits=nft_quality_checklist.CREDITS_AI_TIPS),
                key="qc_ai_btn",
                width='stretch',
                disabled=not api_key or QC_REPORT_KEY not in st.session_state,
            )
        with col_deep:
            deep_btn = st.button(
                t("qc.deep_dive_run", credits=nft_quality_checklist.CREDITS_DEEP_DIVE),
                key="qc_deep_dive_btn",
                width='stretch',
                disabled=not api_key or QC_REPORT_KEY not in st.session_state,
            )

        analyze_kw = dict(
            platform=platform,
            royalty_bps=royalty_bps,
            symbol=symbol,
            mint_price_sol=mint_price_sol,
            ipfs_pinned=ipfs_pinned,
            ipfs_result=ipfs_result,
            planned_count=planned_count,
            upscale_enabled=upscale_enabled,
            upscale_available=upscale_available,
            preflight_errors=preflight_errors,
            preflight_warnings=preflight_warnings,
            checklist=checklist,
        )

        if run or (checklist_changed and QC_REPORT_KEY in st.session_state):
            report = _analyze(assets, collection_name, **analyze_kw)
            st.session_state[QC_REPORT_KEY] = report
            _clear_ai_results()

        if ai_btn:
            report = st.session_state.get(QC_REPORT_KEY)
            if not report:
                st.warning(t("qc.run"))
            elif not api_key:
                st.warning(t("qc.ai_need_key"))
            else:
                wallet = billing_ui.connected_wallet()
                cost = nft_quality_checklist.CREDITS_AI_TIPS
                ok, err = billing_guard.try_reserve(
                    wallet, cost, engine="llm-quality", note="nft quality tips",
                )
                if not ok:
                    st.warning(err or t("qc.ai_no_credits"))
                else:
                    try:
                        tips = nft_quality_checklist.generate_ai_tips(
                            report,
                            collection_name=collection_name,
                            call=nft_quality_checklist.openai_call(api_key),
                            lang=ui_lang(),
                        )
                        st.session_state[QC_AI_TIPS_KEY] = tips
                        st.session_state.pop(QC_AI_DEEP_DIVE_KEY, None)
                    except Exception as e:
                        billing_guard.refund(wallet, cost, engine="llm-quality", note="nft quality fail")
                        st.error(str(e))

        if deep_btn:
            report = st.session_state.get(QC_REPORT_KEY)
            if not report:
                st.warning(t("qc.run"))
            elif not api_key:
                st.warning(t("qc.ai_need_key"))
            else:
                wallet = billing_ui.connected_wallet()
                cost = nft_quality_checklist.CREDITS_DEEP_DIVE
                ok, err = billing_guard.try_reserve(
                    wallet, cost, engine="llm-quality-vision", note="nft quality deep dive",
                )
                if not ok:
                    st.warning(err or t("qc.ai_no_credits"))
                else:
                    try:
                        result = nft_quality_checklist.run_ai_deep_dive(
                            report,
                            assets,
                            collection_name=collection_name,
                            vision_call=nft_quality_checklist.openai_vision_json_call(api_key),
                            tips_call=nft_quality_checklist.openai_call(api_key),
                            lang=ui_lang(),
                        )
                        st.session_state[QC_AI_DEEP_DIVE_KEY] = result
                        st.session_state.pop(QC_AI_TIPS_KEY, None)
                    except Exception as e:
                        billing_guard.refund(
                            wallet, cost, engine="llm-quality-vision", note="nft deep dive fail",
                        )
                        st.error(str(e))

        report: nft_quality_checklist.QualityReport | None = st.session_state.get(QC_REPORT_KEY)
        if not report:
            return None

        st.metric(t("qc.score"), f"{report.score}/100")
        st.markdown(t(f"qc.band.{report.band}"))

        for cat in nft_quality_checklist.CATEGORIES:
            _render_category(cat, report.items, focus_code=focus_code)

        _render_ai_results()

        col_json, col_md = st.columns(2)
        report_payload = nft_quality_checklist.report_to_dict(report)
        deep = st.session_state.get(QC_AI_DEEP_DIVE_KEY)
        if deep:
            report_payload["ai_deep_dive"] = {
                "thumbnail": deep.thumbnail,
                "style": deep.style,
                "tips": deep.tips,
            }
        elif st.session_state.get(QC_AI_TIPS_KEY):
            report_payload["ai_tips"] = st.session_state[QC_AI_TIPS_KEY]
        report_json = json.dumps(report_payload, ensure_ascii=False, indent=2)
        report_md = nft_quality_checklist.format_markdown(
            report, collection_name, item_label=_item_text,
        )
        with col_json:
            st.download_button(
                t("qc.download_json"),
                report_json,
                file_name="quality-report.json",
                mime="application/json",
                width='stretch',
                key="qc_download_json",
            )
        with col_md:
            st.download_button(
                t("qc.download_md"),
                report_md,
                file_name="quality-report.md",
                mime="text/markdown",
                width='stretch',
                key="qc_download_md",
            )
    report = st.session_state.get(QC_REPORT_KEY)
    if report:
        return int(report.score)
    return None
