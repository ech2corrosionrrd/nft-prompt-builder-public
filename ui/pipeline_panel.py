"""Вкладка 🚀 Pipeline (Web3-конвеєр): диспетчер етапів text→images→mint→billing.

Винесено з app.py (декомпозиція хотспоту). `pipeline_metrics` — чиста функція
(тестується без Streamlit). `render()` лише оркеструє: метрики, лінійний майстер
(блок недоступних етапів) і виклик відповідного stage-модуля.
"""

from __future__ import annotations

import streamlit as st

from options import CAMERA_ANGLES, LIGHTING
from styles import NFT_STYLES
from ui import billing_ui, stage1_constructor, stage2_generator, stage3_minting, workflow_guide
from ui_strings import t


def pipeline_metrics(
    generated_prompts: list,
    pipeline_images: list,
    approved_content: list,
    mint_assets: list,
) -> dict[str, int]:
    """Лічильники етапів конвеєра (промпти/згенеровані/схвалені/у черзі мінту)."""
    return {
        "prompts": len(generated_prompts),
        "generated": len(pipeline_images),
        "approved": len(approved_content),
        "queue": len(mint_assets),
    }


def render(*, api_key: str | None) -> None:
    """Рендерить вкладку конвеєра: метрики + лінійний майстер етапів."""
    metrics = pipeline_metrics(
        st.session_state.generated_prompts,
        st.session_state.pipeline_images,
        st.session_state.approved_content,
        st.session_state.mint_assets,
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t("pipeline.metric_prompts"), metrics["prompts"])
    m2.metric(t("pipeline.metric_generated"), metrics["generated"])
    m3.metric(t("pipeline.metric_approved"), metrics["approved"])
    m4.metric(t("pipeline.metric_queue"), metrics["queue"])

    active_stage = workflow_guide.render_pipeline_stage_selector()
    workflow_guide.render_pipeline_header(active_stage)
    # UX-B1 linear wizard: якщо етап ще недоступний — показуємо блок-пояснення
    # замість тіла етапу (не перескочити Зображення/Експорт без передумов).
    _pl_progress = workflow_guide.pipeline_progress()
    _block = workflow_guide.stage_block_message(active_stage, _pl_progress)
    if _block:
        st.warning(_block)
        workflow_guide.render_contextual_help_link(
            workflow_guide.pipeline_help_section(active_stage),
            key_suffix=f"gate_{active_stage}",
        )
    else:
        workflow_guide.render_pipeline_empty_state(active_stage, _pl_progress)  # UX-B4 орієнтир
        if active_stage == "text":
            stage1_constructor.render(NFT_STYLES, CAMERA_ANGLES, LIGHTING, api_key)
        elif active_stage == "images":
            stage2_generator.render(api_key)
        elif active_stage == "mint":
            stage3_minting.render()
        else:
            billing_ui.render()
    workflow_guide.render_pipeline_forward_cta(active_stage)
    workflow_guide.render_pipeline_nav(active_stage)
