"""Селектор активного проєкту в sidebar (Tier 1)."""

from __future__ import annotations

import streamlit as st

from services import project_service, workspace_limits
from ui import billing_ui
from ui_strings import t


def _project_id_to_name(projects: list[dict], pid: str, fallback: str) -> dict[str, str]:
    id_to_name = {p["id"]: p["name"] for p in projects}
    if pid and pid not in id_to_name:
        id_to_name[pid] = fallback
    return id_to_name


def _show_quota_error(exc: workspace_limits.ProjectQuotaError) -> None:
    st.error(t(f"project.quota.{exc.code}", **exc.detail))


def render_sidebar_project() -> None:
    wallet = billing_ui.connected_wallet()
    if not wallet:
        return
    project_service.on_wallet_ready(wallet)
    projects = project_service.list_projects(wallet)
    pid = st.session_state.get(project_service.SESSION_PROJECT_ID, "")
    name = st.session_state.get(
        project_service.SESSION_PROJECT_NAME, project_service.default_project_name(),
    )
    st.divider()  # межа зони «Проєкт» (рендериться лише з гаманцем — без сирітських hr)
    st.markdown(f"#### {t('project.title')}")
    st.caption(t("project.autosave_hint"))
    st.caption(t("project.active_caption", name=name))
    disk = project_service.active_project_disk_hint(wallet)
    if disk is not None:
        st.caption(t("project.active_disk", size_mb=disk["size_mb"], files=disk["files"]))
    quota = workspace_limits.quota_status(wallet)
    if quota["show_warn"]:
        st.warning(t("project.warn_many", count=quota["count"]))
    if quota["project_limit"] > 0 or quota["mb_limit"] > 0:
        limit_part = ""
        if quota["project_limit"] > 0 and not quota["purchased"]:
            limit_part = f" / {quota['project_limit']}"
        mb_part = ""
        if quota["mb_limit"] > 0:
            mb_part = f" / {quota['mb_limit']} MB"
        st.caption(t(
            "project.quota_usage",
            count=quota["count"],
            limit_part=limit_part,
            used_mb=quota["used_mb"],
            mb_part=mb_part,
        ))
    id_to_name = _project_id_to_name(projects, pid, name)
    if projects:
        options = [p["id"] for p in projects]
        if pid not in options and pid:
            options = [pid] + options
        forced = st.session_state.pop(project_service.FORCE_PICK_KEY, None)
        if forced:
            st.session_state["sidebar_project_pick"] = forced
        picked = st.selectbox(
            t("project.pick"),
            options,
            index=options.index(pid) if pid in options else 0,
            format_func=lambda i: id_to_name.get(i, i),
            key="sidebar_project_pick",
        )
        if picked and picked != pid:
            try:
                project_service.load_project(wallet, picked)
                st.rerun()
            except OSError:
                st.error(t("project.load_disk_error"))
        elif pid and st.session_state.get("sidebar_project_pick") != pid:
            st.session_state["sidebar_project_pick"] = pid
    new_col, dup_col, dl_col, ren_col, del_col = st.columns(5)
    with new_col:
        if st.button(t("project.new"), width='stretch', key="project_new_btn"):
            st.session_state["_project_new_panel"] = True
    with dup_col:
        if st.button(
            t("project.duplicate"),
            width='stretch',
            key="project_dup_btn",
            help=t("project.duplicate_help"),
        ):
            try:
                project_service.duplicate_project(wallet)
                st.rerun()
            except workspace_limits.ProjectQuotaError as e:
                _show_quota_error(e)
            except ValueError as e:
                st.error(str(e))
    with dl_col:
        if st.button(
            t("project.download"),
            width='stretch',
            key="project_dl_btn",
            help=t("project.download_help"),
            disabled=not pid,
        ):
            try:
                project_service.persist(wallet)  # свіжий snapshot перед пакуванням
                st.session_state["_project_dl"] = project_service.build_project_zip(wallet, pid)
            except ValueError as e:
                st.error(str(e))
    with ren_col:
        if st.button(
            t("project.rename"),
            width='stretch',
            key="project_rename_btn",
            help=t("project.rename_help"),
            disabled=not projects and not pid,
        ):
            st.session_state["_project_rename_panel"] = True
    with del_col:
        if st.button(
            t("project.delete"),
            width='stretch',
            key="project_delete_btn",
            help=t("project.delete_help"),
            disabled=not projects,
        ):
            st.session_state["_project_delete_panel"] = True

    if st.session_state.get("_project_dl"):
        dl_name, dl_bytes = st.session_state["_project_dl"]
        st.caption(t("project.download_ready", size_mb=round(len(dl_bytes) / (1024 * 1024), 1)))
        dl_save_col, dl_cancel_col = st.columns(2)
        with dl_save_col:
            # on_click чистить session — багатомегабайтний ZIP не живе між reruns.
            st.download_button(
                t("project.download_save"),
                data=dl_bytes,
                file_name=dl_name,
                mime="application/zip",
                key="project_dl_save",
                width='stretch',
                on_click=lambda: st.session_state.pop("_project_dl", None),
            )
        with dl_cancel_col:
            if st.button(t("project.cancel"), key="project_dl_cancel", width='stretch'):
                st.session_state.pop("_project_dl", None)
                st.rerun()

    if st.session_state.get("_project_new_panel"):
        default_name = project_service.default_project_name()
        new_name = st.text_input(
            t("project.new_ph"),
            value=default_name,
            key="project_new_input",
            help=t("project.new_help"),
        )
        save_col, cancel_col = st.columns(2)
        with save_col:
            if st.button(t("project.new_save"), key="project_new_save", width='stretch'):
                try:
                    project_service.create_project(wallet, new_name)
                    st.session_state.pop("_project_new_panel", None)
                    st.rerun()
                except workspace_limits.ProjectQuotaError as e:
                    _show_quota_error(e)
        with cancel_col:
            if st.button(t("project.cancel"), key="project_new_cancel", width='stretch'):
                st.session_state.pop("_project_new_panel", None)
                st.rerun()

    if st.session_state.get("_project_rename_panel"):
        rename_options = list(id_to_name.keys())
        if not rename_options:
            st.warning(t("project.rename_none"))
            st.session_state.pop("_project_rename_panel", None)
        else:
            default_idx = rename_options.index(pid) if pid in rename_options else 0
            target_id = st.selectbox(
                t("project.rename_pick"),
                rename_options,
                index=default_idx,
                format_func=lambda i: id_to_name.get(i, i),
                key="project_rename_target_id",
            )
            sync_key = "_project_rename_sync_target"
            name_key = "project_rename_name_input"
            if st.session_state.get(sync_key) != target_id:
                st.session_state[sync_key] = target_id
                st.session_state[name_key] = id_to_name.get(target_id, "")
            new_name = st.text_input(t("project.rename_ph"), key=name_key)
            save_col, cancel_col = st.columns(2)
            with save_col:
                if st.button(t("project.rename_save"), key="project_rename_save", width='stretch'):
                    if project_service.rename_project(wallet, target_id, new_name):
                        st.session_state.pop("_project_rename_panel", None)
                        st.session_state.pop(sync_key, None)
                        st.rerun()
                    else:
                        st.error(t("project.rename_failed"))
            with cancel_col:
                if st.button(t("project.cancel"), key="project_rename_cancel", width='stretch'):
                    st.session_state.pop("_project_rename_panel", None)
                    st.session_state.pop(sync_key, None)
                    st.rerun()

    if st.session_state.get("_project_delete_panel"):
        delete_options = list(id_to_name.keys())
        if not delete_options:
            st.warning(t("project.delete_none"))
            st.session_state.pop("_project_delete_panel", None)
        else:
            default_idx = delete_options.index(pid) if pid in delete_options else 0
            target_id = st.selectbox(
                t("project.delete_pick"),
                delete_options,
                index=default_idx,
                format_func=lambda i: id_to_name.get(i, i),
                key="project_delete_target_id",
            )
            target_name = id_to_name.get(target_id, target_id)
            st.warning(t("project.delete_confirm", name=target_name))
            confirm_col, cancel_col = st.columns(2)
            with confirm_col:
                if st.button(
                    t("project.delete_confirm_btn"),
                    key="project_delete_confirm",
                    width='stretch',
                    type="primary",
                ):
                    if project_service.delete_project(wallet, target_id):
                        st.session_state.pop("_project_delete_panel", None)
                        st.session_state.pop("sidebar_project_pick", None)
                        st.rerun()
                    else:
                        st.error(t("project.delete_failed"))
            with cancel_col:
                if st.button(t("project.cancel"), key="project_delete_cancel", width='stretch'):
                    st.session_state.pop("_project_delete_panel", None)
                    st.rerun()

    stage = st.session_state.get("pipeline_active_stage", "")
    from ui.workflow_guide import MODE_PIPELINE, workflow_mode

    if workflow_mode() == MODE_PIPELINE and stage:
        st.caption(t("project.stage_hint", stage=stage))
    elif workflow_mode() != MODE_PIPELINE:
        # Classic: не показувати «Етап: billing» — це етап конвеєра, не колекції.
        idea = (st.session_state.get("idea") or "").strip()
        if idea:
            short = idea if len(idea) <= 40 else idea[:37] + "…"
            st.caption(t("project.classic_hint", idea=short))
        else:
            st.caption(t("project.classic_hint_empty"))
