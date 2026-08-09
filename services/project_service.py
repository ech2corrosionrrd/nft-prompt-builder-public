"""Проєкт-центричне збереження роботи користувача (autosave на диск).

Кожен проєкт — ізольований контейнер:
  data/workspace/<wallet_slug>/<project_id>/
    manifest.json   — id, name, timestamps, stage
    state.json      — pipeline + classic поля (JSON, без bytes)
    assets/         — PNG/JPG зображення конвеєра

Активний проєкт: data/workspace/<wallet_slug>/active.json → {project_id}.

Legacy `data/projects/<wallet>/*.json` (ручний classic save) не чіпаємо.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from options import MATRIX_STORAGE_KEYS, TRAIT_CATEGORIES, trait_key
from state.app_defaults import DEFAULTS
from state.pipeline_state import APPROVED_CONTENT, GENERATED_PROMPTS, MINT_ASSETS, PIPELINE_IMAGES
from services import workspace_limits
from storage import DATA_DIR, wallet_slug
from ui.workflow_guide import (
    MODE_PIPELINE,
    PIPELINE_STAGE_KEY,
    PIPELINE_TRANSFER_MSG_KEY,
    WORKFLOW_KEY,
)

WORKSPACE_ROOT = DATA_DIR / "workspace"
STATE_VERSION = 1
ACTIVE_FILE = "active.json"
PREFS_FILE = "prefs.json"
MANIFEST_FILE = "manifest.json"
STATE_FILE = "state.json"
ASSETS_SUBDIR = "assets"

SESSION_PROJECT_ID = "active_project_id"
SESSION_PROJECT_NAME = "active_project_name"
SESSION_STYLE_BIBLE = "_project_style_bible"
SESSION_CURATOR_RATINGS = "_project_curator_ratings"
SESSION_LOADED_KEY = "_project_loaded_key"
FORCE_PICK_KEY = "_force_project_pick"
# Підпис останнього збереженого snapshot — відсікає повторний autosave на
# навігаційних reruns (див. autosave_if_changed).
AUTOSAVE_SIG_KEY = "_project_autosave_sig"

# Додаткові ключі сесії, що входять у проєкт
_EXTRA_KEYS = (
    "active_template",
    "batch_results",
    "batch_usage",
    "collection_run",
    "pl3_coll_name",
    "ec_ipfs_result",
    "qc_checklist",
    "last_result",  # Result-панель Конструктора (переживає theme reload)
)

# Stage 1 UI (матриця, режим, archetype-hints, поля single/group) — blob у state.json.
_STAGE1_UI_SCALAR_KEYS = (
    "pl1_mode",
    "pl1_style_matrix",
    "pl1_core_single",
    "pl1_core_group",
    "pl1_style_single",
    "pl1_tags",
    "pl1_raw",
    "pl1_single_light",
    "pl1_single_camera",
    "pl1_single_colors",
    "pl1_group_light",
    "pl1_group_camera",
    "pl1_group_colors",
    "pl1_matrix_rules",
    "pl1_rich_matrix",
    "pl1_matrix_tpl_name",
    "_pl2_archetype",
    "_pl2_archetype_negative",
    "pl2_suffix_preset",
    "_pl2_suffix_auto_sig",
)
_STAGE1_UI_LIST_KEYS = ("pl1_styles_group",)


def _collect_stage1_ui() -> dict[str, Any]:
    matrix: dict[str, list[str]] = {}
    for key in MATRIX_STORAGE_KEYS:
        raw = st.session_state.get(f"pl1_matrix_{key}")
        if raw:
            matrix[key] = list(raw)
    scalars = {
        k: st.session_state[k]
        for k in _STAGE1_UI_SCALAR_KEYS
        if k in st.session_state
    }
    lists = {
        k: list(st.session_state[k])
        for k in _STAGE1_UI_LIST_KEYS
        if k in st.session_state
    }
    if not matrix and not scalars and not lists:
        return {}
    out: dict[str, Any] = {}
    if matrix:
        out["matrix"] = matrix
    out.update(scalars)
    if lists:
        out["lists"] = lists
    return out


def _restore_stage1_ui(blob: dict[str, Any] | None) -> None:
    """Відновити Stage 1 після _clear_stage_widget_state (load/autosave)."""
    if not blob:
        return
    for key, values in (blob.get("matrix") or {}).items():
        if key in MATRIX_STORAGE_KEYS and isinstance(values, list):
            st.session_state[f"pl1_matrix_{key}"] = list(values)
    for k in _STAGE1_UI_SCALAR_KEYS:
        if k in blob:
            st.session_state[k] = blob[k]
    for k in _STAGE1_UI_LIST_KEYS:
        raw = (blob.get("lists") or {}).get(k)
        if isinstance(raw, list):
            st.session_state[k] = list(raw)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _state_sig(state: dict) -> str:
    """Стабільний підпис snapshot (для dirty-check autosave)."""
    blob = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def default_project_name() -> str:
    """Автоназва нового проєкту: локальна дата й час (або ручний ввід у UI)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _resolve_name(name: str | None) -> str:
    cleaned = (name or "").strip()
    return cleaned or default_project_name()


def _sync_sidebar_pick(project_id: str) -> None:
    """Синхронізує selectbox sidebar після програмної зміни активного проєкту."""
    if project_id:
        st.session_state[FORCE_PICK_KEY] = project_id


def _wallet_root(wallet: str) -> Path:
    return WORKSPACE_ROOT / wallet_slug(wallet)


def project_dir(wallet: str, project_id: str) -> Path:
    return _wallet_root(wallet) / project_id


def assets_dir(wallet: str, project_id: str | None = None) -> Path | None:
    """Тека assets активного (або заданого) проєкту; None якщо проєкт не обрано."""
    pid = project_id or st.session_state.get(SESSION_PROJECT_ID)
    if not wallet or not pid:
        return None
    d = project_dir(wallet, pid) / ASSETS_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_asset(assets_root: Path, content: bytes, suffix: str = ".png") -> Path:
    """Записує байти в assets/; повертає абсолютний Path."""
    assets_root.mkdir(parents=True, exist_ok=True)
    name = f"img-{uuid.uuid4().hex[:10]}{suffix}"
    path = assets_root / name
    path.write_bytes(content)
    return path


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


_REPLACE_RETRIES = 6
_REPLACE_BACKOFF_SEC = 0.05


def _atomic_replace(tmp_name: str, path: Path, *, payload: str) -> None:
    """temp → path; на PermissionError (типово Windows) — короткі ретраї."""
    last_err: OSError | None = None
    for attempt in range(_REPLACE_RETRIES):
        try:
            os.replace(tmp_name, path)
            return
        except PermissionError as e:
            last_err = e
            if attempt < _REPLACE_RETRIES - 1:
                time.sleep(_REPLACE_BACKOFF_SEC * (attempt + 1))
    # Останній шанс: прямий overwrite (ризик torn read нижчий за втрату autosave).
    path.write_text(payload, encoding="utf-8")
    try:
        os.unlink(tmp_name)
    except OSError:
        pass
    if last_err is not None:
        import logging
        logging.getLogger(__name__).warning(
            "os.replace(%s) після %d спроб → fallback write: %s",
            path.name, _REPLACE_RETRIES, last_err,
        )


def _write_json(path: Path, data: dict) -> None:
    """Атомарний запис JSON: temp у тій самій теці + os.replace.

    Прямий запис у цільовий файл небезпечний — краш або одночасний autosave з
    двох вкладок лишає обрізаний файл, і `_read_json` мовчки повертає None (робота
    зникає без помилки). `os.replace` атомарний у межах ФС: читач завжди бачить
    або старий, або новий цілий файл. Серіалізацію робимо ДО створення temp —
    несеріалізовні дані падають, не лишаючи ні temp, ні зіпсованого оригіналу.
    На Windows при WinError 5 — `_atomic_replace` ретраїть і fallback-ить.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        _atomic_replace(tmp_name, path, payload=payload)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _active_path(wallet: str) -> Path:
    return _wallet_root(wallet) / ACTIVE_FILE


def _prefs_path(wallet: str) -> Path:
    return _wallet_root(wallet) / PREFS_FILE


def welcome_seen_persisted(wallet: str) -> bool:
    """Чи користувач уже проходив welcome-гейт (per-wallet на диску)."""
    if not wallet:
        return False
    data = _read_json(_prefs_path(wallet))
    return bool(data and data.get("welcome_seen"))


def set_welcome_seen(wallet: str) -> None:
    """Запамʼятати welcome для гаманця (нова сесія Streamlit не показує гейт знову)."""
    if not wallet:
        return
    _wallet_root(wallet).mkdir(parents=True, exist_ok=True)
    prev = _read_json(_prefs_path(wallet)) or {}
    prev["welcome_seen"] = True
    prev["updated_at"] = _now_iso()
    _write_json(_prefs_path(wallet), prev)


def has_saved_projects(wallet: str) -> bool:
    return bool(list_projects(wallet))


def _relativize_path(path_str: str, proj: Path) -> str:
    if not path_str:
        return path_str
    p = Path(path_str)
    assets = (proj / ASSETS_SUBDIR).resolve()
    try:
        rel = p.resolve().relative_to(assets)
        return f"{ASSETS_SUBDIR}/{rel.as_posix()}"
    except (ValueError, OSError):
        return path_str


def _resolve_path(path_str: str, proj: Path) -> str:
    if not path_str:
        return path_str
    if path_str.startswith(f"{ASSETS_SUBDIR}/"):
        return str((proj / path_str).resolve())
    p = Path(path_str)
    if p.is_absolute() and p.exists():
        return str(p)
    candidate = proj / path_str
    if candidate.exists():
        return str(candidate.resolve())
    return path_str


def _normalize_records(records: list[dict], proj: Path, *, to_disk: bool) -> list[dict]:
    out: list[dict] = []
    for rec in records:
        item = dict(rec)
        item.pop("bytes", None)
        item.pop("image_bytes", None)
        path = str(item.get("path", "") or "")
        if path:
            item["path"] = _relativize_path(path, proj) if to_disk else _resolve_path(path, proj)
        out.append(item)
    return out


# Префікси widget-key Streamlit (stage1/2) — очищаємо при новому/перемиканні проєкту,
# інакше матриця/raw/pl2 зберігають попередні значення в session і «повертають» чужі промпти.
_STAGE_WIDGET_PREFIXES = ("pl1_", "pl2_", "_pl1_", "_pl2_", "_pending_pl1_", "_pending_pl2_")


def _clear_stage_widget_state() -> None:
    for key in list(st.session_state.keys()):
        if any(key.startswith(p) for p in _STAGE_WIDGET_PREFIXES):
            st.session_state.pop(key, None)
    for key in ("_pl1_bible_marker", "_pl2_qa_sig", "_pl2_qa"):
        st.session_state.pop(key, None)


def _reset_pipeline_session(*, clear_extras: bool = True) -> None:
    """Скидає pipeline-стан сесії до порожнього дропа."""
    st.session_state[GENERATED_PROMPTS] = []
    st.session_state[PIPELINE_IMAGES] = []
    st.session_state[APPROVED_CONTENT] = []
    st.session_state[MINT_ASSETS] = []
    st.session_state[WORKFLOW_KEY] = MODE_PIPELINE
    st.session_state[PIPELINE_STAGE_KEY] = "billing"
    for k, v in DEFAULTS.items():
        st.session_state[k] = v
    for cat in TRAIT_CATEGORIES:
        st.session_state[trait_key(cat)] = ""
    st.session_state[SESSION_STYLE_BIBLE] = {}
    st.session_state[SESSION_CURATOR_RATINGS] = {}
    st.session_state.pop(PIPELINE_TRANSFER_MSG_KEY, None)
    st.session_state.pop("_pl2_batch_sig", None)
    _clear_stage_widget_state()
    if clear_extras:
        st.session_state["active_template"] = None
        st.session_state["batch_results"] = []
        st.session_state["batch_usage"] = None
        st.session_state["collection_run"] = None
        st.session_state.pop("pl3_coll_name", None)
        st.session_state.pop("ec_ipfs_result", None)
        st.session_state.pop("qc_checklist", None)
        st.session_state.pop("last_result", None)
        st.session_state.pop("qc_report", None)
        for key in (
            "discord", "twitter", "waitlist", "utility", "reveal_plan",
            "rights_attestation", "policy_review",
        ):
            st.session_state.pop(f"qc_cb_{key}", None)


def list_projects(wallet: str) -> list[dict]:
    """Список проєктів гаманця (нова workspace-модель)."""
    root = _wallet_root(wallet)
    if not root.exists():
        return []
    items: list[dict] = []
    for child in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not child.is_dir():
            continue
        manifest = _read_json(child / MANIFEST_FILE)
        if not manifest:
            continue
        items.append({
            "id": manifest.get("id", child.name),
            "name": manifest.get("name", child.name),
            "updated_at": manifest.get("updated_at", ""),
            "stage": manifest.get("stage", ""),
        })
    return items


def active_project_disk_hint(wallet: str) -> dict[str, float | int] | None:
    """Розмір активного проєкту з manifest-кешу (fallback — один обхід диска)."""
    pid = st.session_state.get(SESSION_PROJECT_ID)
    if not wallet or not pid:
        return None
    proj = project_dir(wallet, pid)
    if not proj.exists():
        return None
    manifest = _read_json(proj / MANIFEST_FILE) or {}
    nbytes = manifest.get("size_bytes")
    nfiles = manifest.get("file_count")
    if nbytes is None or nfiles is None:
        disk = workspace_limits.project_disk_stats(proj)
        nbytes = disk["bytes"]
        nfiles = disk["files"]
    return {
        "size_mb": round(nbytes / (1024 * 1024), 1),
        "files": int(nfiles),
    }


def create_project(wallet: str, name: str | None = None, *, reset_session: bool = True) -> str:
    """Новий порожній проєкт; робить його активним."""
    if reset_session and st.session_state.get(SESSION_PROJECT_ID):
        persist(wallet)
    workspace_limits.assert_can_add(wallet, extra_projects=1)
    resolved_name = _resolve_name(name)
    project_id = uuid.uuid4().hex[:12]
    proj = project_dir(wallet, project_id)
    proj.mkdir(parents=True, exist_ok=True)
    (proj / ASSETS_SUBDIR).mkdir(exist_ok=True)
    now = _now_iso()
    _write_json(proj / MANIFEST_FILE, {
        "id": project_id,
        "name": resolved_name,
        "created_at": now,
        "updated_at": now,
        "stage": "billing",
        "version": STATE_VERSION,
    })
    _write_json(proj / STATE_FILE, {"version": STATE_VERSION})
    _set_active(wallet, project_id)
    st.session_state[SESSION_PROJECT_ID] = project_id
    st.session_state[SESSION_PROJECT_NAME] = resolved_name
    if reset_session:
        _reset_pipeline_session(clear_extras=True)
    st.session_state[SESSION_LOADED_KEY] = f"{wallet}:{project_id}"
    _sync_sidebar_pick(project_id)
    persist(wallet)
    return project_id


def _set_active(wallet: str, project_id: str) -> None:
    ap = _active_path(wallet)
    existing = _read_json(ap)
    if existing and str(existing.get("project_id") or "") == project_id:
        return  # зайвий запис active.json — часта причина WinError 5 на Windows
    try:
        _write_json(ap, {"project_id": project_id, "updated_at": _now_iso()})
    except OSError:
        # state.json уже збережено; вказівник active — best-effort (не роняємо UI).
        import logging
        logging.getLogger(__name__).warning(
            "active.json не оновлено для %s (project %s)", wallet_slug(wallet), project_id,
            exc_info=True,
        )


def active_project_id(wallet: str) -> str | None:
    if st.session_state.get(SESSION_PROJECT_ID):
        return st.session_state[SESSION_PROJECT_ID]
    data = _read_json(_active_path(wallet))
    if data:
        return str(data.get("project_id") or "") or None
    return None


def collect_state(wallet: str) -> dict[str, Any]:
    """Знімає snapshot session_state для збереження."""
    pid = st.session_state.get(SESSION_PROJECT_ID)
    if not pid:
        return {}
    proj = project_dir(wallet, pid)
    traits = {cat: st.session_state.get(trait_key(cat), "") for cat in TRAIT_CATEGORIES}
    return {
        "version": STATE_VERSION,
        "workflow_mode": st.session_state.get(WORKFLOW_KEY, MODE_PIPELINE),
        "pipeline_active_stage": st.session_state.get(PIPELINE_STAGE_KEY, "billing"),
        "defaults": {k: st.session_state.get(k, DEFAULTS.get(k)) for k in DEFAULTS},
        "traits": traits,
        "generated_prompts": list(st.session_state.get(GENERATED_PROMPTS, [])),
        "pipeline_images": _normalize_records(
            list(st.session_state.get(PIPELINE_IMAGES, [])), proj, to_disk=True,
        ),
        "approved_content": _normalize_records(
            list(st.session_state.get(APPROVED_CONTENT, [])), proj, to_disk=True,
        ),
        "mint_assets": _normalize_records(
            list(st.session_state.get(MINT_ASSETS, [])), proj, to_disk=True,
        ),
        "style_bible": dict(st.session_state.get(SESSION_STYLE_BIBLE) or {}),
        "curator_ratings": dict(st.session_state.get(SESSION_CURATOR_RATINGS) or {}),
        "stage1_ui": _collect_stage1_ui(),
        **{k: st.session_state.get(k) for k in _EXTRA_KEYS if k in st.session_state},
    }


def apply_state(wallet: str, project_id: str, state: dict) -> None:
    """Відновлює session_state зі збереженого snapshot."""
    proj = project_dir(wallet, project_id)
    st.session_state[WORKFLOW_KEY] = state.get("workflow_mode", MODE_PIPELINE)
    st.session_state[PIPELINE_STAGE_KEY] = state.get("pipeline_active_stage", "billing")
    for k, v in (state.get("defaults") or {}).items():
        if k in DEFAULTS:
            st.session_state[k] = v
    for cat, raw in (state.get("traits") or {}).items():
        if cat in TRAIT_CATEGORIES:
            st.session_state[trait_key(cat)] = raw
    st.session_state[GENERATED_PROMPTS] = list(state.get("generated_prompts") or [])
    st.session_state[PIPELINE_IMAGES] = _normalize_records(
        list(state.get("pipeline_images") or []), proj, to_disk=False,
    )
    st.session_state[APPROVED_CONTENT] = _normalize_records(
        list(state.get("approved_content") or []), proj, to_disk=False,
    )
    st.session_state[MINT_ASSETS] = _normalize_records(
        list(state.get("mint_assets") or []), proj, to_disk=False,
    )
    st.session_state[SESSION_STYLE_BIBLE] = dict(state.get("style_bible") or {})
    st.session_state[SESSION_CURATOR_RATINGS] = dict(state.get("curator_ratings") or {})
    for k in _EXTRA_KEYS:
        if k in state:
            st.session_state[k] = state[k]
    _clear_stage_widget_state()
    _restore_stage1_ui(state.get("stage1_ui"))
    st.session_state.pop("_pl2_batch_sig", None)
    st.session_state[SESSION_LOADED_KEY] = f"{wallet}:{project_id}"
    from ui.build_panel import sync_build_widget_keys
    from ui.quality_checklist import sync_checklist_widget_keys
    sync_build_widget_keys()
    sync_checklist_widget_keys()


def persist(wallet: str, state: dict | None = None) -> None:
    """Autosave активного проєкту на диск.

    `state` можна передати готовим (з autosave_if_changed), щоб не знімати
    snapshot двічі. Після запису фіксуємо підпис — щоб подальші reruns без змін
    не переписували файли (див. autosave_if_changed).
    """
    pid = st.session_state.get(SESSION_PROJECT_ID)
    if not wallet or not pid:
        return
    proj = project_dir(wallet, pid)
    if state is None:
        state = collect_state(wallet)
    _write_json(proj / STATE_FILE, state)
    manifest_path = proj / MANIFEST_FILE
    manifest = _read_json(manifest_path) or {"id": pid}
    manifest["name"] = st.session_state.get(SESSION_PROJECT_NAME) or manifest.get("name") or default_project_name()
    manifest["updated_at"] = _now_iso()
    manifest["stage"] = st.session_state.get(PIPELINE_STAGE_KEY, "billing")
    manifest["version"] = STATE_VERSION
    disk = workspace_limits.project_disk_stats(proj)
    manifest["size_bytes"] = disk["bytes"]
    manifest["file_count"] = disk["files"]
    _write_json(manifest_path, manifest)
    _set_active(wallet, pid)
    st.session_state[AUTOSAVE_SIG_KEY] = _state_sig(state)


def autosave_if_changed(wallet: str) -> None:
    """Autosave лише якщо snapshot змінився з попереднього запису.

    Кінець кожного прогону `app.py` кличе це — покриває classic-вкладки
    (Batch/Collection/Traits/Builder), де немає точкових autosave-викликів.
    Підпис у session відсікає зайві записи на навігаційних reruns.
    """
    if not wallet or not st.session_state.get(SESSION_PROJECT_ID):
        return
    state = collect_state(wallet)
    if _state_sig(state) == st.session_state.get(AUTOSAVE_SIG_KEY):
        return
    persist(wallet, state)


def load_project(wallet: str, project_id: str) -> bool:
    """Перемикає активний проєкт (autosave попереднього)."""
    if not wallet or not project_id:
        return False
    current = st.session_state.get(SESSION_PROJECT_ID)
    if current and current != project_id:
        try:
            persist(wallet)
        except OSError:
            import logging
            logging.getLogger(__name__).warning(
                "autosave попереднього проєкту %s перед перемиканням не вдався",
                current, exc_info=True,
            )
    proj = project_dir(wallet, project_id)
    if not proj.exists():
        return False
    manifest = _read_json(proj / MANIFEST_FILE) or {}
    state = _read_json(proj / STATE_FILE) or {}
    apply_state(wallet, project_id, state)
    st.session_state[SESSION_PROJECT_ID] = project_id
    st.session_state[SESSION_PROJECT_NAME] = manifest.get("name", project_id)
    st.session_state[SESSION_LOADED_KEY] = f"{wallet}:{project_id}"
    _set_active(wallet, project_id)
    _sync_sidebar_pick(project_id)
    return True


def ensure_active(wallet: str) -> str:
    """Гарантує активний проєкт; створює з автоназвою (дата/час), якщо немає."""
    loaded = st.session_state.get(SESSION_LOADED_KEY, "")
    pid = st.session_state.get(SESSION_PROJECT_ID)
    if pid and loaded == f"{wallet}:{pid}":
        return pid
    active = active_project_id(wallet)
    if active and project_dir(wallet, active).exists():
        load_project(wallet, active)
        return active
    has_work = bool(
        st.session_state.get(GENERATED_PROMPTS)
        or st.session_state.get(PIPELINE_IMAGES)
        or st.session_state.get(APPROVED_CONTENT)
    )
    if has_work:
        new_id = create_project(wallet, reset_session=False)
        persist(wallet)
        return new_id
    return create_project(wallet)


def on_wallet_ready(wallet: str) -> None:
    """Після adopt гаманця: завантажити active або створити новий."""
    if not wallet:
        return
    marker = st.session_state.get("_project_wallet_marker")
    pid = st.session_state.get(SESSION_PROJECT_ID)
    loaded = st.session_state.get(SESSION_LOADED_KEY, "")
    if marker == wallet and pid and loaded == f"{wallet}:{pid}":
        return
    st.session_state["_project_wallet_marker"] = wallet
    ensure_active(wallet)


def rename_project(wallet: str, project_id: str, name: str) -> bool:
    """Перейменовує збережений проєкт на диску (активний чи ні)."""
    if not wallet or not project_id:
        return False
    proj = project_dir(wallet, project_id)
    if not proj.exists():
        return False
    new_name = _resolve_name(name)
    manifest_path = proj / MANIFEST_FILE
    manifest = _read_json(manifest_path) or {"id": project_id}
    manifest["name"] = new_name
    manifest["updated_at"] = _now_iso()
    _write_json(manifest_path, manifest)
    if st.session_state.get(SESSION_PROJECT_ID) == project_id:
        st.session_state[SESSION_PROJECT_NAME] = new_name
        _sync_sidebar_pick(project_id)
    else:
        load_project(wallet, project_id)
    return True


def rename_active(wallet: str, name: str) -> None:
    pid = st.session_state.get(SESSION_PROJECT_ID)
    if pid:
        rename_project(wallet, pid, name)


def _duplicate_name(base: str) -> str:
    """Назва копії: «Cyber Drop (copy)» або «Cyber Drop (copy 2)»."""
    base = _resolve_name(base)
    root = re.sub(r" \(copy(?: \d+)?\)$", "", base)
    n = 1
    while True:
        suffix = " (copy)" if n == 1 else f" (copy {n})"
        candidate = f"{root}{suffix}"
        if len(candidate) <= 80:
            return candidate
        root = root[: max(1, 80 - len(suffix))]
        n += 1


def _remap_curator_ratings(ratings: dict, src: Path, dst: Path) -> dict:
    """Переносить рейтинги на нові абсолютні шляхи assets/ (за basename)."""
    out: dict[str, int] = {}
    dst_assets = dst / ASSETS_SUBDIR
    for key, val in (ratings or {}).items():
        try:
            rating = int(val)
        except (TypeError, ValueError):
            continue
        if rating <= 0:
            continue
        fn = Path(str(key)).name
        if not fn:
            continue
        candidate = dst_assets / fn
        if candidate.exists():
            out[str(candidate.resolve())] = rating
    return out


def duplicate_project(
    wallet: str,
    source_id: str | None = None,
    *,
    name: str | None = None,
) -> str:
    """Копія проєкту (state + assets) → новий id; активує копію для іншої лінії розвитку."""
    if not wallet:
        raise ValueError("Гаманець не підключено.")
    persist(wallet)
    source_id = source_id or st.session_state.get(SESSION_PROJECT_ID)
    if not source_id:
        raise ValueError("Немає проєкту для дублювання.")
    src = project_dir(wallet, source_id)
    if not src.exists():
        raise ValueError("Вихідний проєкт не знайдено.")
    extra_bytes = workspace_limits.project_bytes(wallet, source_id)
    workspace_limits.assert_can_add(wallet, extra_projects=1, extra_bytes=extra_bytes)

    manifest = _read_json(src / MANIFEST_FILE) or {}
    new_id = uuid.uuid4().hex[:12]
    dst = project_dir(wallet, new_id)
    dst.mkdir(parents=True, exist_ok=True)

    src_assets = src / ASSETS_SUBDIR
    dst_assets = dst / ASSETS_SUBDIR
    if src_assets.is_dir():
        shutil.copytree(src_assets, dst_assets)

    state = dict(_read_json(src / STATE_FILE) or {"version": STATE_VERSION})
    state["curator_ratings"] = _remap_curator_ratings(
        state.get("curator_ratings") or {}, src, dst,
    )
    # IPFS CID / export — копія для нової гілки; користувач може перезібрати експорт.
    now = _now_iso()
    new_name = _resolve_name(name or _duplicate_name(manifest.get("name") or default_project_name()))
    _write_json(dst / STATE_FILE, state)
    disk = workspace_limits.project_disk_stats(dst)
    _write_json(dst / MANIFEST_FILE, {
        "id": new_id,
        "name": new_name,
        "created_at": now,
        "updated_at": now,
        "stage": manifest.get("stage", "billing"),
        "version": STATE_VERSION,
        "forked_from": source_id,
        "size_bytes": disk["bytes"],
        "file_count": disk["files"],
    })
    apply_state(wallet, new_id, state)
    st.session_state[SESSION_PROJECT_ID] = new_id
    st.session_state[SESSION_PROJECT_NAME] = new_name
    st.session_state[SESSION_LOADED_KEY] = f"{wallet}:{new_id}"
    _set_active(wallet, new_id)
    _sync_sidebar_pick(new_id)
    return new_id


def _portable_ratings(ratings: dict, proj: Path) -> dict[str, int]:
    """Ключі рейтингів → відносні `assets/<файл>` (для перенесення між хостами).

    На диску curator_ratings історично зберігаються з абсолютними шляхами —
    у локальному бекапі вони були б мертвими. Лишаємо тільки рейтинги файлів,
    які реально є в assets/ проєкту.
    """
    out: dict[str, int] = {}
    assets = proj / ASSETS_SUBDIR
    for key, val in (ratings or {}).items():
        try:
            rating = int(val)
        except (TypeError, ValueError):
            continue
        if rating <= 0:
            continue
        fn = Path(str(key)).name
        if fn and (assets / fn).exists():
            out[f"{ASSETS_SUBDIR}/{fn}"] = rating
    return out


def _export_slug(name: str) -> str:
    """ASCII-slug назви проєкту для імені файла (кирилиця в cwd — landmine)."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name or "").strip("-").lower()
    return slug[:40] or "project"


def build_project_zip(wallet: str, project_id: str) -> tuple[str, bytes]:
    """ZIP проєкту для локального бекапу користувача: manifest + state + assets/.

    Це «сирий» знімок теки проєкту (портативний: шляхи в state відносні,
    рейтинги переписані на `assets/<файл>`), НЕ mint-ready експорт — той
    збирає export_bundle. PNG на сервері свідомо не бекапляться (рішення
    2026-07-01), тож цей архів — єдина повна копія роботи в руках користувача.
    Імпорту назад у застосунок поки немає (свідомо: окреме рішення).
    """
    import io
    import zipfile

    if not wallet or not project_id:
        raise ValueError("Немає проєкту для завантаження.")
    proj = project_dir(wallet, project_id)
    if not proj.exists():
        raise ValueError("Проєкт не знайдено.")

    manifest = _read_json(proj / MANIFEST_FILE) or {"id": project_id}
    manifest["exported_at"] = _now_iso()
    state = dict(_read_json(proj / STATE_FILE) or {"version": STATE_VERSION})
    state["curator_ratings"] = _portable_ratings(state.get("curator_ratings") or {}, proj)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_FILE, json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr(STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2))
        assets = proj / ASSETS_SUBDIR
        if assets.is_dir():
            for f in sorted(assets.iterdir()):
                if f.is_file():
                    zf.write(f, f"{ASSETS_SUBDIR}/{f.name}")

    filename = f"w3ir-project-{_export_slug(str(manifest.get('name') or ''))}-{project_id}.zip"
    return filename, buf.getvalue()


def delete_project(wallet: str, project_id: str) -> bool:
    """Видаляє проєкт з диска; якщо був активним — перемикає на інший або створює новий."""
    if not wallet or not project_id:
        return False
    proj = project_dir(wallet, project_id)
    if not proj.exists():
        return False

    was_active = st.session_state.get(SESSION_PROJECT_ID) == project_id
    shutil.rmtree(proj, ignore_errors=True)

    active = _read_json(_active_path(wallet))
    if active and active.get("project_id") == project_id:
        ap = _active_path(wallet)
        if ap.exists():
            ap.unlink()

    if was_active:
        st.session_state.pop(SESSION_PROJECT_ID, None)
        st.session_state.pop(SESSION_PROJECT_NAME, None)
        st.session_state.pop(SESSION_LOADED_KEY, None)
        remaining = list_projects(wallet)
        if remaining:
            load_project(wallet, remaining[0]["id"])
        else:
            create_project(wallet)
    return True


def style_bible_dict() -> dict:
    return dict(st.session_state.get(SESSION_STYLE_BIBLE) or {})


def set_style_bible(data: dict) -> None:
    st.session_state[SESSION_STYLE_BIBLE] = dict(data)


def curator_ratings_dict() -> dict[str, int]:
    raw = st.session_state.get(SESSION_CURATOR_RATINGS) or {}
    return {str(k): int(v) for k, v in raw.items() if int(v) > 0}


def merge_curator_ratings(ratings: dict[str, int]) -> None:
    if not ratings:
        return
    current = curator_ratings_dict()
    for path, rating in ratings.items():
        if path and int(rating) > 0:
            current[str(path)] = int(rating)
    st.session_state[SESSION_CURATOR_RATINGS] = current


def autosave(wallet: str) -> None:
    """Зручний alias для UI-після дій."""
    if wallet and st.session_state.get(SESSION_PROJECT_ID):
        persist(wallet)


def project_stage_label(wallet: str) -> str:
    pid = st.session_state.get(SESSION_PROJECT_ID)
    if not wallet or not pid:
        return ""
    manifest = _read_json(project_dir(wallet, pid) / MANIFEST_FILE)
    return str((manifest or {}).get("stage") or "")
