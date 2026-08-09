"""Вкладка 🏭 Collection (classic): чекпоінт-конвеєр промптів+зображень+експорт.

Винесено з app.py (декомпозиція хотспоту). Блок орієнтований на оркестрацію
(чекпоінти, async-генерація, IPFS, ZIP), тож «чистого» ядра тут мало — оцінку
вартості промптів переиспользуємо з batch_panel. Спільні з іншими вкладками
хелпери app.py приходять у `render()` параметрами (dependency injection).
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

import collection
import ipfs
import storage
from batch import estimate_cost, is_claude_model, sample_trait_combinations, to_csv
from services import quality_metrics
from services.ai_service import ENGINE_GPT_IMAGE
from builder import build_tech_params
from options import IMAGE_QUALITIES, IMAGE_SIZES, list_index
from preset_labels import preset_label
from ui import billing_ui, workflow_guide
from ui.batch_panel import estimate_batch_cost
from ui_strings import api_key_missing, t, ui_lang


def render(
    *,
    model: str,
    platform: str,
    temperature: float,
    llm_key: str | None,
    api_key: str | None,
    collection_size: int,
    get_traits_weighted: Callable[[], dict],
    get_base_config: Callable[[], dict],
    get_llm_api_key: Callable[[str], str | None],
    reserve_llm: Callable[[str | None, int, str], bool],
    refund_llm: Callable[[str | None, int, str], None],
    render_metadata_form: Callable,
    render_pipeline_context: Callable[[], None],
    run_async: Callable,
) -> None:
    """Рендерить вкладку колекції (чекпоінт-ран, зображення, IPFS, ZIP)."""
    workflow_guide.render_classic_header("collection", get_traits_weighted)
    st.info(t("coll.pipeline_banner"))
    st.subheader(t("coll.title"))
    st.caption(t("coll.caption"))
    render_pipeline_context()

    if st.session_state.get("coll_flash"):
        kind, text = st.session_state.pop("coll_flash")
        (st.success if kind == "ok" else st.warning)(text)

    traits_weighted = get_traits_weighted()
    runs = collection.list_checkpoints()

    cstart, ccontinue = st.columns(2, gap="large")

    with cstart:
        st.markdown(t("coll.new_run"))
        default_run_name = storage.safe_name(st.session_state.idea[:40]) if st.session_state.idea else "collection"
        run_name = st.text_input(t("coll.run_name"), value=default_run_name)
        # min 1 — дозволяє 1/1 і малі колекції; дефолт читає collection_size (не клампимо до 50)
        target = st.number_input(t("coll.token_count"), 1, 10000, min(max(int(collection_size), 1), 10000), 1)
        est_prompts_cost = estimate_batch_cost(model, target)
        st.caption(billing_ui.prompt_cost_caption(model, int(target), est_prompts_cost))

        if st.button(t("coll.start"), type="primary", width='stretch'):
            if not llm_key:
                st.error(api_key_missing(is_claude_model(model)))
            elif not traits_weighted:
                st.error(t("coll.need_traits"))
            elif not st.session_state.idea:
                st.error(t("batch.need_idea"))
            elif collection.load_checkpoint(run_name):
                st.error(t("coll.run_exists", name=run_name))
            else:
                wallet = billing_ui.connected_wallet()
                units = int(target)
                if not reserve_llm(wallet, units, f"collection {run_name}"):
                    pass
                else:
                    combos = sample_trait_combinations(traits_weighted, units)
                    tech = build_tech_params(
                        platform, st.session_state.aspect_ratio,
                        st.session_state.stylize, st.session_state.chaos, st.session_state.seed,
                    )
                    cp = collection.create_checkpoint(
                        run_name, units, model, platform, get_base_config(), tech, combos,
                    )
                    st.session_state.collection_run = cp["name"]
                    progress = st.progress(0, text=t("coll.prompt_progress"))
                    try:
                        cp = run_async(collection.run_collection_async(
                            llm_key, cp, temperature,
                            on_progress=lambda done, total: progress.progress(
                                min(done / total, 1.0), text=t("coll.prompts_of", done=done, total=total)
                            ),
                        ))
                        progress.empty()
                        cost = estimate_cost(cp["model"], cp["usage"]["prompt_tokens"], cp["usage"]["completion_tokens"])
                        done_n = len(cp["results"])
                        billing_ui.record_llm_usd_or_credits(wallet, done_n, cost)
                        refund_llm(wallet, units - done_n, "collection partial")
                        st.session_state.coll_flash = (
                            "ok",
                            billing_ui.prompts_run_done_text(wallet, done_n, cp["target"]),
                        )
                    except Exception as e:
                        progress.empty()
                        refund_llm(wallet, units, "collection failed")
                        st.session_state.coll_flash = ("warn", t("coll.interrupted", err=e))
                    st.rerun()

    with ccontinue:
        st.markdown(t("coll.saved_runs"))
        if not runs:
            st.info(t("coll.no_runs"))
        else:
            selected_run = st.selectbox(
                t("coll.run_select"), runs,
                index=runs.index(st.session_state.collection_run) if st.session_state.collection_run in runs else 0,
                key="collection_run_select",
            )
            st.session_state.collection_run = selected_run
            cp = collection.load_checkpoint(selected_run)
            if cp:
                done_prompts = len(cp["results"])
                done_images = len(collection.existing_image_ids(selected_run))
                real_cost = estimate_cost(cp["model"], cp["usage"]["prompt_tokens"], cp["usage"]["completion_tokens"])
                s1, s2, s3 = st.columns(3)
                s1.metric(t("coll.metric_prompts"), f"{done_prompts}/{cp['target']}")
                s2.metric(t("coll.metric_images"), f"{done_images}")
                if billing_ui.credits_billing_active():
                    s3.metric(t("coll.metric_credits_spent"), f"{done_prompts} cr")
                else:
                    s3.metric(t("coll.metric_spent"), f"${real_cost:.2f}")

                rc1, rc2 = st.columns(2)
                with rc1:
                    if done_prompts < cp["target"]:
                        if st.button(t("coll.resume"), width='stretch'):
                            run_llm_key = get_llm_api_key(cp["model"])
                            if not run_llm_key:
                                st.error(api_key_missing(is_claude_model(cp["model"])))
                            else:
                                remaining = cp["target"] - done_prompts
                                wallet = billing_ui.connected_wallet()
                                if not reserve_llm(wallet, remaining, f"collection resume {selected_run}"):
                                    pass
                                else:
                                    st.session_state.collection_run = selected_run
                                    progress = st.progress(done_prompts / cp["target"], text=t("coll.resuming"))
                                    try:
                                        cp = run_async(collection.run_collection_async(
                                            run_llm_key, cp, temperature,
                                            on_progress=lambda done, total: progress.progress(
                                                min(done / total, 1.0), text=t("coll.prompts_of", done=done, total=total)
                                            ),
                                        ))
                                        progress.empty()
                                        cost = estimate_cost(cp["model"], cp["usage"]["prompt_tokens"], cp["usage"]["completion_tokens"])
                                        total_done = len(cp["results"])
                                        new_units = total_done - done_prompts
                                        billing_ui.record_llm_usd_or_credits(wallet, new_units, cost)
                                        refund_llm(wallet, remaining - new_units, "collection resume partial")
                                        st.session_state.coll_flash = (
                                            "ok",
                                            billing_ui.prompts_run_done_text(wallet, total_done, cp["target"]),
                                        )
                                    except Exception as e:
                                        progress.empty()
                                        refund_llm(wallet, remaining, "collection resume failed")
                                        st.session_state.coll_flash = ("warn", t("coll.interrupted", err=e))
                                    st.rerun()
                    else:
                        if st.button(t("coll.to_batch"), width='stretch', help=t("coll.to_batch_help")):
                            st.session_state.batch_results = cp["results"]
                            st.session_state.batch_usage = cp["usage"]
                            st.session_state.collection_run = selected_run
                            st.success(t("coll.loaded_batch"))
                with rc2:
                    if st.button(t("coll.delete_run"), width='stretch'):
                        collection.delete_checkpoint(selected_run)
                        if st.session_state.collection_run == selected_run:
                            st.session_state.collection_run = None
                        st.rerun()

    # ── Batch-зображення та збірний експорт ──
    active_run = st.session_state.collection_run
    active_cp = collection.load_checkpoint(active_run) if active_run else None

    if active_cp and active_cp["results"]:
        st.divider()
        st.markdown(t("coll.images_for", run=active_run))
        done_images = len(collection.existing_image_ids(active_run))
        remaining = len(active_cp["results"]) - done_images
        st.caption(t("coll.images_progress", done=done_images, total=len(active_cp["results"])))

        workflow_guide.render_pipeline_bridge(
            active_cp["results"], f"coll_{active_run}", source=f"Колекція «{active_run}»",
        )

        default_img_size = collection.image_size_for_aspect(st.session_state.aspect_ratio)
        ic1, ic2, ic3 = st.columns(3)
        with ic1:
            img_size = st.selectbox(
                t("coll.size"),
                IMAGE_SIZES,
                index=list_index(IMAGE_SIZES, default_img_size),
                help=t("coll.size_help", ar=st.session_state.aspect_ratio.split(" (")[0]),
                key="coll_img_size",
            )
        with ic2:
            img_quality = st.selectbox(
                t("coll.quality"), IMAGE_QUALITIES, index=0, key="coll_img_quality",
                format_func=lambda value: preset_label(value, ui_lang()),
            )
        with ic3:
            budget = st.number_input(t("coll.budget"), 0.0, 1000.0, 5.0, 1.0)

        per_image = collection.image_cost(img_quality, img_size)
        affordable = int(budget / per_image) if budget > 0 else remaining
        will_generate = min(remaining, affordable)
        st.caption(t("coll.image_cost_hint", per=per_image, n=will_generate, total=will_generate * per_image))

        if st.button(t("coll.gen_images", n=will_generate), type="primary", width='stretch', disabled=will_generate <= 0):
            if not api_key:
                st.error(t("coll.no_openai"))
            else:
                progress = st.progress(0, text=t("coll.img_progress"))
                try:
                    summary = run_async(collection.generate_images_async(
                        api_key, active_run, active_cp["results"],
                        size=img_size, quality=img_quality, budget_usd=budget,
                        on_progress=lambda done, total: progress.progress(
                            min(done / max(total, 1), 1.0), text=t("coll.images_of", done=done, total=total)
                        ),
                    ))
                    progress.empty()
                    # §2.8: classic Collection-генерація → source="classic" у funnel.
                    quality_metrics.record_batch_generate(
                        billing_ui.connected_wallet(), int(summary.get("generated") or 0),
                        ENGINE_GPT_IMAGE, source="classic",
                    )
                    if not billing_ui.credits_billing_active():
                        st.session_state.session_cost += summary["spent"]
                    msg = t("coll.images_done", n=summary["generated"], spent=summary["spent"])
                    if summary["failed"]:
                        msg += t("coll.images_failed", n=summary["failed"])
                        if summary["errors"]:
                            msg += f" · {summary['errors'][0]}"
                        st.session_state.coll_flash = ("warn", msg)
                    else:
                        st.session_state.coll_flash = ("ok", msg)
                except Exception as e:
                    progress.empty()
                    st.session_state.coll_flash = ("warn", t("coll.images_interrupted", err=e))
                st.rerun()

        st.divider()
        st.markdown(t("coll.export_title"))
        st.caption(t("coll.export_caption"))

        images_cid = active_cp.get("ipfs_images_cid", "")
        metadata = render_metadata_form(
            active_cp["results"], "coll",
            default_idea=active_cp["base"].get("idea", active_run),
            default_base_uri=f"ipfs://{images_cid}" if images_cid else "",
        )

        pinata_jwt = ipfs.get_pinata_jwt()
        st.markdown(t("coll.ipfs_title"))
        if not pinata_jwt:
            st.info(t("coll.pinata_hint"))
        else:
            metadata_cid = active_cp.get("ipfs_metadata_cid", "")
            if images_cid:
                st.caption(t("coll.ipfs_images", cid=images_cid))
            if metadata_cid:
                st.caption(t("coll.ipfs_meta", cid=metadata_cid))

            if1, if2 = st.columns(2)
            with if1:
                if st.button(t("coll.upload_images"), width='stretch', disabled=done_images == 0):
                    try:
                        with st.spinner(t("coll.uploading_images", n=done_images)):
                            files = ipfs.collect_directory_files(collection.images_dir(active_run), active_cp["name"])
                            cid = ipfs.upload_directory(pinata_jwt, files, f"{active_run}-images")
                        active_cp["ipfs_images_cid"] = cid
                        collection.save_checkpoint(active_cp)
                        st.session_state.coll_flash = ("ok", t("coll.ipfs_images_ok", cid=cid))
                        st.rerun()
                    except Exception as e:
                        st.error(t("coll.ipfs_error", err=e))
            with if2:
                if st.button(t("coll.upload_meta"), width='stretch', help=t("coll.upload_meta_help")):
                    try:
                        with st.spinner(t("coll.uploading_meta")):
                            files = ipfs.metadata_files(metadata, active_cp["name"])
                            cid = ipfs.upload_directory(pinata_jwt, files, f"{active_run}-metadata")
                        active_cp["ipfs_metadata_cid"] = cid
                        collection.save_checkpoint(active_cp)
                        st.session_state.coll_flash = ("ok", t("coll.ipfs_meta_ok", cid=cid))
                        st.rerun()
                    except Exception as e:
                        st.error(t("coll.ipfs_error", err=e))

        if st.button(t("coll.build_zip"), width='stretch'):
            zip_path = collection.build_collection_zip(
                active_run, active_cp["results"], metadata, to_csv(active_cp["results"]),
            )
            size_mb = zip_path.stat().st_size / 1_048_576
            st.success(t("coll.zip_ok", path=zip_path, mb=size_mb))
            if size_mb <= 200:
                st.download_button(
                    t("coll.download_zip"), zip_path.read_bytes(),
                    f"{active_run}.zip", "application/zip", width='stretch',
                )
            else:
                st.info(t("coll.zip_too_large"))
    elif runs:
        st.divider()
        st.info(t("coll.pick_run_hint"))
    workflow_guide.render_classic_forward_cta("collection", get_traits_weighted)
