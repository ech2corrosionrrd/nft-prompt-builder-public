"""Вкладка 📦 Batch (classic-режим): пакетна генерація промптів і експорт.

Винесено з app.py (декомпозиція хотспоту). Чисті функції (`estimate_batch_cost`,
`build_markdown_export`) тестуються без Streamlit. `render()` приймає спільні з
іншими вкладками хелпери app.py як параметри (dependency injection), решту
залежностей імпортує напряму.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Callable

import streamlit as st

from batch import (
    MODEL_PRICES,
    clean_metadata,
    count_combinations,
    estimate_cost,
    is_claude_model,
    metadata_zip,
    to_csv,
    trait_distribution,
)
from i18n import trait_type_en
from ui import billing_ui, workflow_guide
from ui_strings import api_key_missing, t

# Евристика оцінки: ~120 вхідних + ~350 вихідних токенів на один промпт.
_EST_INPUT_TOKENS = 120
_EST_OUTPUT_TOKENS = 350


def estimate_batch_cost(model: str, count: int) -> float:
    """Орієнтовна вартість пакета у $ за прайсом моделі (до фактичного usage)."""
    in_price, out_price = MODEL_PRICES.get(model, (0.50, 1.50))
    return (
        count * _EST_INPUT_TOKENS * in_price
        + count * _EST_OUTPUT_TOKENS * out_price
    ) / 1_000_000


def build_markdown_export(results: list[dict], generated_at: str) -> str:
    """Збирає Markdown-експорт пакета (заголовок + блоки промптів)."""
    lines = [f"# Batch NFT Prompts\n\nGenerated: {generated_at}\n"]
    for r in results:
        lines.append(f"## #{r.get('id')}\n```\n{r.get('prompt', '')}\n```\n")
    return "\n".join(lines)


def render(
    *,
    model: str,
    platform: str,
    temperature: float,
    llm_key: str | None,
    get_traits_weighted: Callable[[], dict],
    run_batch_generation: Callable,
    render_metadata_form: Callable,
    reserve_llm: Callable[[str | None, int, str], bool],
    refund_llm: Callable[[str | None, int, str], None],
    render_pipeline_context: Callable[[], None],
) -> None:
    """Рендерить вкладку пакетної генерації."""
    workflow_guide.render_classic_header("batch", get_traits_weighted)
    st.subheader(t("batch.title"))
    st.caption(t("batch.caption"))
    render_pipeline_context()

    b1, b2, b3 = st.columns(3)
    with b1:
        batch_count = st.number_input(t("batch.count"), 1, 200, 10, 1)  # min 1 — малі дропи/1-of-1
    with b2:
        traits_weighted = get_traits_weighted()
        max_combo = count_combinations(traits_weighted) if traits_weighted else 0
        st.metric(t("batch.combos_avail"), f"{max_combo:,}")
    with b3:
        est_cost = estimate_batch_cost(model, batch_count)
        st.metric(billing_ui.est_llm_metric_label(), billing_ui.est_llm_metric_value(batch_count, est_cost))

    if not traits_weighted:
        st.warning(t("batch.need_traits"))
    elif not st.session_state.idea:
        st.warning(t("batch.need_idea"))
    else:
        if st.button(t("batch.run", n=batch_count), type="primary", width='stretch'):
            if not llm_key:
                st.error(api_key_missing(is_claude_model(model)))
            else:
                wallet = billing_ui.connected_wallet()
                units = int(batch_count)
                if not reserve_llm(wallet, units, "classic batch"):
                    pass
                else:
                    try:
                        results, usage, errors = run_batch_generation(llm_key, model, platform, units, temperature)
                        st.session_state.batch_results = results
                        st.session_state.batch_usage = usage
                        cost = estimate_cost(model, usage["prompt_tokens"], usage["completion_tokens"])
                        charged_units = len(results)
                        if errors:
                            refund_llm(wallet, units - charged_units, "classic batch partial")
                            st.warning(t("batch.partial", ok=charged_units, err=len(errors), first=errors[0]))
                        billing_ui.show_batch_success(wallet, charged_units, cost)
                    except Exception as e:
                        refund_llm(wallet, units, "classic batch failed")
                        st.error(t("batch.error", err=e))

    if st.session_state.batch_results:
        st.divider()
        results = st.session_state.batch_results
        usage = st.session_state.batch_usage
        header = t("batch.results", n=len(results))
        if usage:
            if billing_ui.credits_billing_active():
                header += billing_ui.batch_results_credit_suffix(len(results))
            else:
                real_cost = estimate_cost(model, usage["prompt_tokens"], usage["completion_tokens"])
                header += t(
                    "batch.actual_cost",
                    cost=real_cost,
                    tokens=usage["prompt_tokens"] + usage["completion_tokens"],
                )
        st.markdown(header)

        preview = [
            {
                "#": r.get("id"),
                "Rarity": r.get("rarity_score", ""),
                t("batch.col_prompt"): (r.get("prompt", "")[:110] + "…") if len(r.get("prompt", "")) > 110 else r.get("prompt", ""),
            }
            for r in results
        ]
        st.dataframe(preview, width='stretch', hide_index=True)

        for r in results[:5]:
            with st.expander(t("batch.expander", id=r.get("id"), score=r.get("rarity_score", "—"))):
                st.code(r.get("prompt", ""), language=None)
                if r.get("negative"):
                    st.caption(t("batch.negative"))
                    st.code(r["negative"], language=None)
                if r.get("traits"):
                    display_traits = {
                        trait_type_en(str(k)): v for k, v in r["traits"].items()
                    }
                    st.json(display_traits)

        if len(results) > 5:
            st.caption(t("batch.more_export", n=len(results) - 5))

        csv_data = to_csv(results)
        json_data = json.dumps(results, ensure_ascii=False, indent=2)
        d1, d2, d3 = st.columns(3)
        with d1:
            st.download_button("📥 CSV", csv_data, f"batch_{len(results)}.csv", "text/csv", width='stretch')
        with d2:
            st.download_button("📥 JSON", json_data, f"batch_{len(results)}.json", "application/json", width='stretch')
        with d3:
            md_data = build_markdown_export(results, datetime.now().strftime("%Y-%m-%d %H:%M"))
            st.download_button("📥 Markdown", md_data, f"batch_{len(results)}.md", "text/markdown", width='stretch')

        with st.expander(t("batch.meta_expand")):
            st.caption(t("batch.meta_caption"))
            metadata = render_metadata_form(results, "batch", default_idea=st.session_state.idea)
            md1, md2 = st.columns(2)
            with md1:
                st.download_button(
                    "📥 collection.json",
                    json.dumps(clean_metadata(metadata), ensure_ascii=False, indent=2),
                    "collection.json", "application/json", width='stretch',
                )
            with md2:
                st.download_button(
                    "📥 metadata.zip (JSON на токен)",
                    metadata_zip(metadata),
                    "metadata.zip", "application/zip", width='stretch',
                )

        if traits_weighted:
            with st.expander(t("batch.dist_expand")):
                st.dataframe(
                    trait_distribution(results, traits_weighted),
                    width='stretch', hide_index=True,
                )

        workflow_guide.render_batch_to_pipeline_bridge(results)
    workflow_guide.render_classic_forward_cta("batch", get_traits_weighted)
