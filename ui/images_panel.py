"""Вкладка 🖼️ Images (classic): генерація прев'ю-зображень gpt-image-1.

Винесено з app.py (декомпозиція хотспоту). `extract_fenced_prompt` — чиста
функція (тестується без Streamlit). Спільний `billing_error` та runtime-значення
приходять у `render()` параметрами.
"""

from __future__ import annotations

import base64
import html
import os
import re
from datetime import datetime
from typing import Callable

import streamlit as st
from openai import OpenAI

import collection
import storage
from batch import strip_platform_flags
from options import IMAGE_QUALITIES, IMAGE_SIZES, list_index
from preset_labels import preset_label
from services import billing_guard, content_safety, payment_service, quality_metrics
from services.ai_service import ENGINE_GPT_IMAGE
from ui import billing_ui, workflow_guide
from ui_strings import t, ui_lang

MAX_STORED_IMAGES = 20  # синхронізовано з storage.PREVIEW_LIMIT


def _preview_alt_text(img: dict, index: int) -> str:
    """Описовий alt для accessibility (BUG-005)."""
    prompt = (img.get("prompt") or "").strip()
    if prompt:
        return prompt[:120]
    filename = (img.get("filename") or "").strip()
    if filename:
        return filename
    return f"NFT preview {index + 1}"


def _render_preview_image(img: dict, index: int, *, width: int = 300) -> None:
    alt = html.escape(_preview_alt_text(img, index))
    b64 = base64.b64encode(img["bytes"]).decode("ascii")
    st.markdown(
        f'<img src="data:image/png;base64,{b64}" alt="{alt}" width="{width}" '
        f'style="max-width:100%;height:auto;border-radius:8px;" loading="lazy" />',
        unsafe_allow_html=True,
    )


def _is_streamlit_cloud() -> bool:
    return os.path.exists("/home/appuser") or os.environ.get("STREAMLIT_SHARING_MODE") == "1"


def extract_fenced_prompt(content: str) -> str:
    """Витягує перший код-блок ```...``` з тексту й чистить platform-прапорці."""
    if not content:
        return ""
    fence = re.search(r"```(?:\w+)?\s*([\s\S]*?)```", content)
    if not fence:
        return ""
    return strip_platform_flags(fence.group(1).strip())


def extract_prompt_from_last_result() -> str:
    """Промпт з останнього результату конструктора (код-блок у content)."""
    return extract_fenced_prompt((st.session_state.get("last_result") or {}).get("content", ""))


def image_prompt_options() -> dict[str, str]:
    """Мапа «ярлик → промпт» з batch-результатів і активного чекпоінта колекції."""
    options: dict[str, str] = {}
    for r in st.session_state.batch_results or []:
        prompt = r.get("prompt", "")
        if not prompt:
            continue
        pid = r.get("id", "?")
        short = prompt[:55] + ("…" if len(prompt) > 55 else "")
        options[f"#{pid} · batch · {short}"] = prompt
    run = st.session_state.get("collection_run")
    if run:
        cp = collection.load_checkpoint(run)
        if cp:
            for r in cp.get("results", []):
                prompt = r.get("prompt", "")
                if not prompt:
                    continue
                pid = r.get("id", "?")
                short = prompt[:50] + ("…" if len(prompt) > 50 else "")
                options[f"#{pid} · {run} · {short}"] = prompt
    return options


def render(
    *,
    api_key: str | None,
    get_traits_weighted: Callable[[], dict],
    render_pipeline_context: Callable[[], None],
    billing_error: Callable[[str | None], None],
) -> None:
    """Рендерить вкладку генерації прев'ю-зображень."""
    workflow_guide.render_classic_header("images", get_traits_weighted)
    st.info(t("img.pipeline_banner"))
    st.subheader(t("img.title"))
    st.caption(t("img.caption"))
    cr_per = payment_service.credit_cost(ENGINE_GPT_IMAGE)
    st.info(t("img.requirements", per=cr_per))

    with st.expander(t("img.expand_title"), expanded=False):
        st.markdown(t("img.expand_body"))
    if _is_streamlit_cloud():
        st.info(t("img.cloud_hint"))

    st.markdown(
        '<style>[data-testid="stImage"] img { pointer-events: none; cursor: default; }</style>',
        unsafe_allow_html=True,
    )
    render_pipeline_context()

    if not st.session_state.idea:
        st.warning(t("img.no_idea"))

    prompt_options = image_prompt_options()
    if prompt_options:
        labels = list(prompt_options.keys())
        if st.session_state.get("img_prompt_pick") not in prompt_options:
            st.session_state.img_prompt_pick = labels[0]
        st.selectbox(
            t("img.prompt_pick"),
            labels,
            key="img_prompt_pick",
            help=t("img.prompt_pick_help"),
        )
        selected_label = st.session_state.img_prompt_pick
        if st.session_state.get("_last_img_prompt_pick") != selected_label:
            st.session_state._last_img_prompt_pick = selected_label
            st.session_state.image_prompt_edit = strip_platform_flags(prompt_options[selected_label])
    else:
        constructor_prompt = extract_prompt_from_last_result()
        if constructor_prompt and not st.session_state.image_prompt_edit.strip():
            st.session_state.image_prompt_edit = constructor_prompt
        if constructor_prompt:
            st.info(t("img.from_constructor"))
        else:
            st.info(t("img.prompt_hint"))

    default_img_size = collection.image_size_for_aspect(st.session_state.aspect_ratio)
    image_prompt = st.text_area(
        t("img.prompt_label"),
        key="image_prompt_edit",
        height=100,
        help=t("img.prompt_help"),
    )

    i1, i2, i3 = st.columns(3)
    with i1:
        image_size = st.selectbox(
            t("coll.size"),
            IMAGE_SIZES,
            index=list_index(IMAGE_SIZES, default_img_size),
            help=t("coll.size_help", ar=st.session_state.aspect_ratio.split(" (")[0]),
            key="img_tab_size",
        )
    with i2:
        image_quality = st.selectbox(
            t("coll.quality"), IMAGE_QUALITIES, index=1, key="img_tab_quality",
            format_func=lambda value: preset_label(value, ui_lang()),
        )
    with i3:
        image_n = st.slider(t("img.variants"), 1, 4, 1, key="img_tab_variants")

    per_img = collection.image_cost(image_quality, image_size)
    st.caption(t("img.cost_hint", per=per_img, n=image_n, total=per_img * image_n))
    st.caption(t("img.credits_hint", per=cr_per, n=image_n, total=cr_per * image_n))

    workflow_guide.render_images_to_pipeline_bridge(
        image_prompt=image_prompt,
        prompt_options=prompt_options,
        batch_results=st.session_state.get("batch_results") or None,
    )

    btn_label = t("img.gen_one") if image_n == 1 else t("img.gen_many", n=image_n)
    if st.button(btn_label, type="primary", width='stretch', key="img_tab_gen_btn"):
        if not api_key:
            st.error(t("coll.no_openai"))
        elif not image_prompt.strip():
            st.error(t("img.prompt_required"))
        # B1: content-safety і на класичному шляху — конвеєр перевіряє в
        # pipeline_batch._generate_one, але ця вкладка кликала images.generate
        # напряму й оминала фільтр (CSAM/насильство) до платного виклику.
        elif not (_safety := content_safety.check_prompt_safety(image_prompt.strip())).ok:
            content_safety.log_safety(_safety)
            st.error(t("error.blocked_prompt"))
        else:
            wallet = billing_ui.connected_wallet()
            img_cost = payment_service.credit_cost(ENGINE_GPT_IMAGE) * image_n
            ok, err = billing_guard.try_reserve(
                wallet, img_cost, engine=ENGINE_GPT_IMAGE, note="classic preview images",
            )
            if not ok:
                billing_error(err)
            else:
                try:
                    spin = t("img.gen_spin_many", n=image_n) if image_n > 1 else t("img.gen_spin_one")
                    with st.spinner(spin):
                        client = OpenAI(api_key=api_key)
                        response = client.images.generate(
                            model="gpt-image-1",
                            prompt=image_prompt.strip(),
                            size=image_size,
                            quality=image_quality,
                            n=image_n,
                        )
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        saved_paths: list[str] = []
                        for k, item in enumerate(response.data):
                            variant = f"{k + 1}/{image_n}" if image_n > 1 else ""
                            image_bytes = base64.b64decode(item.b64_json)
                            saved_path = storage.save_preview(wallet, image_bytes, ts, variant)
                            saved_paths.append(str(saved_path))
                            entry = {
                                "prompt": image_prompt.strip(),
                                "bytes": image_bytes,
                                "timestamp": ts,
                                "path": str(saved_path),
                                "filename": saved_path.name,
                            }
                            if variant:
                                entry["variant"] = variant
                            st.session_state.generated_images.insert(0, entry)
                        st.session_state.generated_images = st.session_state.generated_images[:MAX_STORED_IMAGES]
                    count = len(response.data)
                    # §2.8: classic-генерація мітиться source="classic" — інакше
                    # Classic-частку (поріг E7 >15%) не виміряти у funnel.
                    quality_metrics.record_batch_generate(
                        wallet, count, ENGINE_GPT_IMAGE, source="classic",
                    )
                    if not billing_ui.credits_billing_active():
                        st.session_state.session_cost += per_img * count
                    if count == 1:
                        billing_ui.show_image_success(
                            wallet, img_cost, "img.gen_ok_one", path=saved_paths[0],
                        )
                    else:
                        billing_ui.show_image_success(
                            wallet, img_cost, "img.gen_ok_many",
                            n=count, path=saved_paths[0], extra=count - 1,
                        )
                except Exception as e:
                    billing_guard.refund(
                        wallet, img_cost, engine=ENGINE_GPT_IMAGE, note="classic preview failed",
                    )
                    st.error(t("img.gen_error", err=e))

    preview_files = storage.list_previews(billing_ui.connected_wallet())
    if st.session_state.generated_images or preview_files:
        st.divider()
        head_col, clear_col = st.columns([4, 1])
        with head_col:
            shown = max(len(st.session_state.generated_images), len(preview_files))
            st.markdown(t("img.recent", n=shown))
        with clear_col:
            if preview_files and st.button(t("img.clear"), width='stretch', help=t("img.clear_help")):
                storage.clear_previews(billing_ui.connected_wallet())
                st.session_state.generated_images = []
                st.rerun()

        display_items: list[dict] = []
        seen_paths: set[str] = set()
        for img in st.session_state.generated_images:
            path = img.get("path", "")
            if path and path in seen_paths:
                continue
            if path:
                seen_paths.add(path)
            display_items.append(img)
        for path in preview_files:
            path_str = str(path)
            if path_str in seen_paths:
                continue
            seen_paths.add(path_str)
            display_items.append({
                "bytes": path.read_bytes(),
                "path": path_str,
                "filename": path.name,
                "timestamp": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "prompt": "",
            })

        img_cols = st.columns(2)
        for i, img in enumerate(display_items[:MAX_STORED_IMAGES]):
            with img_cols[i % 2]:
                caption = img["timestamp"]
                if img.get("variant"):
                    caption = t("img.variant_cap", v=img["variant"]) + caption
                if img.get("prompt"):
                    caption += f" · {img['prompt'][:60]}"
                if img.get("filename"):
                    caption += f"\n\n`{img['filename']}`"
                file_name = img.get("filename") or f"nft_preview_{i + 1}.png"
                st.download_button(
                    t("img.download_png"),
                    img["bytes"],
                    file_name,
                    "image/png",
                    key=f"img_dl_{file_name}_{i}",
                    width='stretch',
                    type="secondary",
                    help=t("img.download_help"),
                )
                _render_preview_image(img, i, width=300)
                st.caption(caption)
    workflow_guide.render_classic_forward_cta("images", get_traits_weighted)
