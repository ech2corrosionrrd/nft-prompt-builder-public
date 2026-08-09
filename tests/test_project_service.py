"""Тести project_service: ізоляція проєктів, autosave, шляхи assets."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from services import project_service
from state.pipeline_state import GENERATED_PROMPTS, PIPELINE_IMAGES


@pytest.fixture
def mock_st_session(monkeypatch):
    class _State(dict):
        def get(self, key, default=None):
            return super().get(key, default)

        def pop(self, key, default=None):
            return super().pop(key, default)

    sess = _State()
    monkeypatch.setattr(project_service.st, "session_state", sess)
    return sess


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(project_service, "WORKSPACE_ROOT", tmp_path / "workspace")
    return tmp_path / "workspace"


def test_default_project_name_format():
    name = project_service.default_project_name()
    assert len(name) == 19
    assert name[4] == "-" and name[7] == "-"
    assert name[10] == " "
    assert name[13] == ":" and name[16] == ":"


def test_welcome_seen_persisted_per_wallet(mock_st_session, workspace):
    wallet = "0xabc"
    assert not project_service.welcome_seen_persisted(wallet)
    project_service.set_welcome_seen(wallet)
    assert project_service.welcome_seen_persisted(wallet)
    prefs = project_service._prefs_path(wallet)
    assert prefs.exists()
    assert json.loads(prefs.read_text(encoding="utf-8"))["welcome_seen"] is True


def test_ensure_active_loads_without_new_project(mock_st_session, workspace):
    """Повторний візит: ensure_active відновлює active, не плодить проєкт."""
    wallet = "0xabc"
    pid = project_service.create_project(wallet, "First")
    mock_st_session[GENERATED_PROMPTS] = [{"prompt": "kept"}]
    project_service.persist(wallet)
    mock_st_session.clear()
    mock_st_session["_project_wallet_marker"] = wallet
    loaded = project_service.ensure_active(wallet)
    assert loaded == pid
    assert mock_st_session[GENERATED_PROMPTS][0]["prompt"] == "kept"
    assert len(project_service.list_projects(wallet)) == 1


def test_create_project_default_name(mock_st_session, workspace, monkeypatch):
    monkeypatch.setattr(project_service, "default_project_name", lambda: "2026-06-21 12:00:00")
    project_service.create_project("0xabc")
    assert mock_st_session[project_service.SESSION_PROJECT_NAME] == "2026-06-21 12:00:00"


def test_create_project_empty_name_uses_default(mock_st_session, workspace, monkeypatch):
    monkeypatch.setattr(project_service, "default_project_name", lambda: "2026-06-21 12:00:00")
    project_service.create_project("0xabc", "   ")
    assert mock_st_session[project_service.SESSION_PROJECT_NAME] == "2026-06-21 12:00:00"


def test_rename_project_updates_manifest(mock_st_session, workspace):
    wallet = "0xabc123"
    pid = project_service.create_project(wallet, "Alpha")
    assert project_service.rename_project(wallet, pid, "Beta")
    items = project_service.list_projects(wallet)
    assert items[0]["name"] == "Beta"
    assert mock_st_session[project_service.SESSION_PROJECT_NAME] == "Beta"


def test_rename_inactive_project_becomes_active(mock_st_session, workspace):
    wallet = "0xabc123"
    p1 = project_service.create_project(wallet, "One")
    project_service.persist(wallet)
    p2 = project_service.create_project(wallet, "Two")
    assert mock_st_session[project_service.SESSION_PROJECT_ID] == p2
    assert project_service.rename_project(wallet, p1, "One renamed")
    assert mock_st_session[project_service.SESSION_PROJECT_ID] == p1
    assert mock_st_session[project_service.SESSION_PROJECT_NAME] == "One renamed"


def test_create_project_syncs_sidebar_pick(mock_st_session, workspace):
    pid = project_service.create_project("0xabc", "New drop")
    assert mock_st_session[project_service.FORCE_PICK_KEY] == pid


def test_delete_project_removes_from_disk(mock_st_session, workspace):
    wallet = "0xabc123"
    pid = project_service.create_project(wallet, "Gone")
    assert project_service.delete_project(wallet, pid)
    assert not project_service.project_dir(wallet, pid).exists()
    assert mock_st_session[project_service.SESSION_PROJECT_ID] != pid


def test_delete_active_switches_to_remaining(mock_st_session, workspace):
    wallet = "0xabc123"
    p1 = project_service.create_project(wallet, "Keep")
    project_service.persist(wallet)
    p2 = project_service.create_project(wallet, "Remove")
    assert project_service.delete_project(wallet, p2)
    assert mock_st_session[project_service.SESSION_PROJECT_ID] == p1


def test_delete_last_project_creates_new(mock_st_session, workspace):
    wallet = "0xabc123"
    pid = project_service.create_project(wallet, "Only")
    assert project_service.delete_project(wallet, pid)
    new_pid = mock_st_session[project_service.SESSION_PROJECT_ID]
    assert new_pid and new_pid != pid
    assert len(project_service.list_projects(wallet)) == 1


def test_create_and_list_projects(mock_st_session, workspace):
    wallet = "0xabc123"
    pid = project_service.create_project(wallet, "Cyber Drop")
    assert pid
    assert mock_st_session[project_service.SESSION_PROJECT_ID] == pid
    items = project_service.list_projects(wallet)
    assert len(items) == 1
    assert items[0]["name"] == "Cyber Drop"


def test_persist_and_load_roundtrip(mock_st_session, workspace):
    wallet = "0xabc123"
    pid = project_service.create_project(wallet, "Test")
    mock_st_session[GENERATED_PROMPTS] = [{"prompt": "fox", "traits": {}}]
    assets = project_service.assets_dir(wallet, pid)
    img_path = project_service.write_asset(assets, b"png-bytes")
    mock_st_session[PIPELINE_IMAGES] = [{
        "prompt": "fox",
        "path": str(img_path),
        "filename": img_path.name,
        "traits": {},
    }]
    project_service.persist(wallet)

    mock_st_session[GENERATED_PROMPTS] = []
    mock_st_session[PIPELINE_IMAGES] = []
    proj_dir = project_service.project_dir(wallet, pid)
    assert (proj_dir / "state.json").exists()
    data = __import__("json").loads((proj_dir / "state.json").read_text(encoding="utf-8"))
    assert len(data["generated_prompts"]) == 1

    project_service.load_project(wallet, pid)
    assert len(mock_st_session[GENERATED_PROMPTS]) == 1
    loaded_path = mock_st_session[PIPELINE_IMAGES][0]["path"]
    assert Path(loaded_path).exists()

    manifest = json.loads((proj_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["size_bytes"] > 0
    assert manifest["file_count"] >= 2  # state + manifest + asset


def test_active_project_disk_hint_uses_manifest_cache(mock_st_session, workspace):
    wallet = "0xabc123"
    pid = project_service.create_project(wallet, "Sized")
    project_service.write_asset(project_service.assets_dir(wallet, pid), b"png")
    project_service.persist(wallet)
    hint = project_service.active_project_disk_hint(wallet)
    assert hint is not None
    assert hint["files"] >= 1
    assert hint["size_mb"] >= 0


def test_create_project_clears_prompts_and_persists(mock_st_session, workspace):
    wallet = "0xabc123"
    project_service.create_project(wallet, "First")
    mock_st_session[GENERATED_PROMPTS] = [{"prompt": "stale from old session"}]
    mock_st_session["pl1_raw"] = "stale raw prompts"
    p2 = project_service.create_project(wallet, "Fresh")
    assert mock_st_session[GENERATED_PROMPTS] == []
    assert "pl1_raw" not in mock_st_session
    state = json.loads(
        (project_service.project_dir(wallet, p2) / "state.json").read_text(encoding="utf-8")
    )
    assert state.get("generated_prompts") == []


def test_switch_projects_isolated(mock_st_session, workspace):
    wallet = "0xdef456"
    p1 = project_service.create_project(wallet, "One")
    mock_st_session[GENERATED_PROMPTS] = [{"prompt": "one"}]
    project_service.persist(wallet)
    project_service.create_project(wallet, "Two")
    assert mock_st_session[GENERATED_PROMPTS] == []
    project_service.load_project(wallet, p1)
    assert mock_st_session[GENERATED_PROMPTS][0]["prompt"] == "one"


def test_relativize_asset_paths(mock_st_session, workspace):
    wallet = "0x111"
    pid = project_service.create_project(wallet, "Paths")
    proj = project_service.project_dir(wallet, pid)
    rel = project_service._relativize_path(str(proj / "assets" / "img-1.png"), proj)
    assert rel == "assets/img-1.png"
    resolved = project_service._resolve_path(rel, proj)
    assert resolved.endswith("img-1.png")


def test_curator_ratings_in_state(mock_st_session, workspace):
    wallet = "0x222"
    project_service.create_project(wallet, "Ratings")
    project_service.merge_curator_ratings({"/a.png": 5})
    project_service.persist(wallet)
    mock_st_session[project_service.SESSION_CURATOR_RATINGS] = {}
    pid = mock_st_session[project_service.SESSION_PROJECT_ID]
    project_service.load_project(wallet, pid)
    assert project_service.curator_ratings_dict()["/a.png"] == 5


def test_duplicate_project_copies_state_and_assets(mock_st_session, workspace):
    wallet = "0x333"
    pid = project_service.create_project(wallet, "Original")
    assets = project_service.assets_dir(wallet, pid)
    img = project_service.write_asset(assets, b"png-data")
    mock_st_session[GENERATED_PROMPTS] = [{"prompt": "fox"}]
    mock_st_session[PIPELINE_IMAGES] = [{
        "prompt": "fox", "path": str(img), "filename": img.name, "traits": {},
    }]
    mock_st_session[project_service.SESSION_STYLE_BIBLE] = {"style": "neon"}
    project_service.merge_curator_ratings({str(img): 4})
    project_service.persist(wallet)

    new_id = project_service.duplicate_project(wallet, pid)
    assert new_id != pid
    assert mock_st_session[project_service.SESSION_PROJECT_NAME].endswith("(copy)")
    assert len(mock_st_session[GENERATED_PROMPTS]) == 1
    assert len(mock_st_session[PIPELINE_IMAGES]) == 1
    dup_path = Path(mock_st_session[PIPELINE_IMAGES][0]["path"])
    assert dup_path.exists()
    assert project_service.style_bible_dict().get("style") == "neon"
    assert project_service.curator_ratings_dict()
    assert len(project_service.list_projects(wallet)) == 2


# ── Fix 2: атомарний запис JSON ───────────────────────────────────────────────

def test_write_json_atomic_no_tmp_leftover(workspace, tmp_path):
    target = tmp_path / "sub" / "data.json"
    project_service._write_json(target, {"a": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    # У теці не лишилось жодного .tmp після успішного запису.
    assert [p for p in target.parent.iterdir() if p.suffix == ".tmp"] == []


def test_write_json_failure_preserves_original(tmp_path):
    target = tmp_path / "data.json"
    project_service._write_json(target, {"ok": True})
    # Несеріалізовний об'єкт → json.dumps падає ДО будь-якого файлового запису.
    with pytest.raises(TypeError):
        project_service._write_json(target, {"bad": object()})
    # Оригінал цілий, temp не лишився.
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}
    assert [p for p in target.parent.iterdir() if p.suffix == ".tmp"] == []


def test_atomic_replace_retries_then_succeeds(tmp_path, monkeypatch):
    target = tmp_path / "active.json"
    calls = {"n": 0}
    real_replace = os.replace

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(5, "Access is denied")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky_replace)
    monkeypatch.setattr(project_service.time, "sleep", lambda _: None)
    project_service._write_json(target, {"project_id": "abc"})
    assert json.loads(target.read_text(encoding="utf-8"))["project_id"] == "abc"
    assert calls["n"] == 3


def test_atomic_replace_fallback_after_exhausted_retries(tmp_path, monkeypatch):
    target = tmp_path / "active.json"
    monkeypatch.setattr(os, "replace", lambda *_a, **_k: (_ for _ in ()).throw(
        PermissionError(5, "Access is denied")
    ))
    monkeypatch.setattr(project_service.time, "sleep", lambda _: None)
    project_service._write_json(target, {"project_id": "fallback"})
    assert json.loads(target.read_text(encoding="utf-8"))["project_id"] == "fallback"
    assert [p for p in tmp_path.iterdir() if p.suffix == ".tmp"] == []


def test_set_active_skips_redundant_write(mock_st_session, workspace, monkeypatch):
    wallet = "0xdedupe"
    pid = project_service.create_project(wallet, "One")
    writes: list[Path] = []
    orig = project_service._write_json

    def track_write(path: Path, data: dict) -> None:
        writes.append(path)
        orig(path, data)

    monkeypatch.setattr(project_service, "_write_json", track_write)
    project_service._set_active(wallet, pid)
    project_service._set_active(wallet, pid)
    active_writes = [p for p in writes if p.name == project_service.ACTIVE_FILE]
    assert len(active_writes) == 0
    project_service._set_active(wallet, "other-id")
    active_writes = [p for p in writes if p.name == project_service.ACTIVE_FILE]
    assert len(active_writes) == 1


def test_corrupt_state_falls_back_to_empty(mock_st_session, workspace):
    """Обрізаний state.json → load_project відкриває порожнім, без винятку."""
    wallet = "0xc0ffee"
    pid = project_service.create_project(wallet, "Corrupt")
    mock_st_session[GENERATED_PROMPTS] = [{"prompt": "keep"}]
    project_service.persist(wallet)
    # Імітуємо торнутий запис (як від крашу при неатомарному _write_json).
    (project_service.project_dir(wallet, pid) / "state.json").write_text("{ broken", encoding="utf-8")
    assert project_service.load_project(wallet, pid) is True
    assert mock_st_session[GENERATED_PROMPTS] == []


# ── Fix 3: autosave_if_changed (покриття classic-вкладок) ─────────────────────

def test_autosave_if_changed_persists_classic_work(mock_st_session, workspace):
    wallet = "0xaa11"
    pid = project_service.create_project(wallet, "Batch")
    # Робота в classic Batch (немає точкового autosave у вкладці).
    mock_st_session["batch_results"] = [{"id": 1, "prompt": "neon"}]
    project_service.autosave_if_changed(wallet)
    on_disk = json.loads(
        (project_service.project_dir(wallet, pid) / "state.json").read_text(encoding="utf-8")
    )
    assert on_disk.get("batch_results") == [{"id": 1, "prompt": "neon"}]


def test_autosave_if_changed_skips_when_unchanged(mock_st_session, workspace):
    wallet = "0xbb22"
    pid = project_service.create_project(wallet, "Idle")
    state_path = project_service.project_dir(wallet, pid) / "state.json"
    project_service.autosave_if_changed(wallet)  # підпис уже стоїть від create→persist
    mtime_before = state_path.stat().st_mtime_ns
    project_service.autosave_if_changed(wallet)  # без змін → не переписувати
    assert state_path.stat().st_mtime_ns == mtime_before


def test_autosave_if_changed_rewrites_after_edit(mock_st_session, workspace):
    wallet = "0xcc33"
    pid = project_service.create_project(wallet, "Edit")
    state_path = project_service.project_dir(wallet, pid) / "state.json"
    sig_before = mock_st_session.get(project_service.AUTOSAVE_SIG_KEY)
    mock_st_session[GENERATED_PROMPTS] = [{"prompt": "changed"}]
    project_service.autosave_if_changed(wallet)
    assert mock_st_session.get(project_service.AUTOSAVE_SIG_KEY) != sig_before
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk.get("generated_prompts") == [{"prompt": "changed"}]


def test_autosave_persists_qc_checklist(mock_st_session, workspace):
    wallet = "0xdd44"
    pid = project_service.create_project(wallet, "QC")
    mock_st_session["qc_checklist"] = {
        "discord": True,
        "twitter": False,
        "waitlist": True,
        "utility": False,
        "reveal_plan": False,
        "rights_attestation": True,
        "policy_review": False,
    }
    project_service.autosave_if_changed(wallet)
    on_disk = json.loads(
        (project_service.project_dir(wallet, pid) / "state.json").read_text(encoding="utf-8")
    )
    assert on_disk.get("qc_checklist", {}).get("discord") is True
    assert on_disk.get("qc_checklist", {}).get("rights_attestation") is True

    mock_st_session.clear()
    assert project_service.load_project(wallet, pid) is True
    assert mock_st_session["qc_checklist"]["discord"] is True
    assert mock_st_session["qc_cb_discord"] is True


# ── Download проєкту на ПК (локальний бекап користувача) ─────────────────────

def test_build_project_zip_contains_state_and_assets(mock_st_session, workspace):
    wallet = "0xzip1"
    pid = project_service.create_project(wallet, "Cyber Drop #1")
    assets = project_service.assets_dir(wallet, pid)
    img = project_service.write_asset(assets, b"png-bytes")
    mock_st_session[GENERATED_PROMPTS] = [{"prompt": "fox"}]
    mock_st_session[PIPELINE_IMAGES] = [{
        "prompt": "fox", "path": str(img), "filename": img.name, "traits": {},
    }]
    project_service.persist(wallet)

    filename, blob = project_service.build_project_zip(wallet, pid)
    assert filename == f"w3ir-project-cyber-drop-1-{pid}.zip"

    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "state.json" in names
        assert f"assets/{img.name}" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["id"] == pid
        assert manifest["exported_at"]
        state = json.loads(zf.read("state.json"))
        # Шляхи в архіві портативні (відносні assets/...), не привʼязані до хоста.
        assert state["pipeline_images"][0]["path"] == f"assets/{img.name}"
        assert zf.read(f"assets/{img.name}") == b"png-bytes"


def test_build_project_zip_remaps_ratings_to_relative(mock_st_session, workspace):
    wallet = "0xzip2"
    pid = project_service.create_project(wallet, "Rated")
    assets = project_service.assets_dir(wallet, pid)
    img = project_service.write_asset(assets, b"png")
    # Абсолютний ключ (як пише куратор) + мертвий рейтинг неіснуючого файла.
    project_service.merge_curator_ratings({str(img): 5, "/ghost/nope.png": 3})
    project_service.persist(wallet)

    import io
    import zipfile

    _, blob = project_service.build_project_zip(wallet, pid)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        state = json.loads(zf.read("state.json"))
    assert state["curator_ratings"] == {f"assets/{img.name}": 5}


def test_build_project_zip_missing_project_raises(mock_st_session, workspace):
    with pytest.raises(ValueError):
        project_service.build_project_zip("0xzip3", "no-such-id")
    with pytest.raises(ValueError):
        project_service.build_project_zip("", "abc")


def test_export_slug_ascii_only():
    assert project_service._export_slug("Кібер Дроп №1") == "1"
    assert project_service._export_slug("") == "project"
    assert project_service._export_slug("Neon Foxes!") == "neon-foxes"


def test_stage1_ui_matrix_roundtrip(mock_st_session, workspace):
    """pl1_matrix_* і scalars зберігаються в stage1_ui і відновлюються після load."""
    wallet = "0xstage1"
    pid = project_service.create_project(wallet, "Matrix")
    mock_st_session["pl1_matrix_Варіанти персонажа"] = ["a", "b"]
    mock_st_session["pl1_matrix_Варіанти фону"] = ["bg1", "bg2"]
    mock_st_session["pl1_mode"] = "matrix"
    mock_st_session["pl1_style_matrix"] = "Neon"
    project_service.persist(wallet)

    mock_st_session.clear()
    mock_st_session["_project_wallet_marker"] = wallet
    project_service.load_project(wallet, pid)

    assert mock_st_session["pl1_matrix_Варіанти персонажа"] == ["a", "b"]
    assert mock_st_session["pl1_matrix_Варіанти фону"] == ["bg1", "bg2"]
    assert mock_st_session["pl1_mode"] == "matrix"
    assert mock_st_session["pl1_style_matrix"] == "Neon"


def test_stage1_ui_single_fields_roundtrip(mock_st_session, workspace):
    """Core Object / mode single / кольори — не губляться після load_project."""
    wallet = "0xstage1b"
    pid = project_service.create_project(wallet, "Neon Ocean")
    mock_st_session["pl1_mode"] = "single"
    mock_st_session["pl1_core_single"] = "bioluminescent anglerfish humanoid"
    mock_st_session["pl1_style_single"] = "neon underwater cinematic"
    mock_st_session["pl1_single_colors"] = "neon blue and teal palette"
    project_service.persist(wallet)

    mock_st_session.clear()
    project_service.load_project(wallet, pid)

    assert mock_st_session["pl1_mode"] == "single"
    assert "anglerfish" in mock_st_session["pl1_core_single"]
    assert mock_st_session["pl1_single_colors"] == "neon blue and teal palette"


def test_set_active_swallows_disk_error(mock_st_session, workspace, monkeypatch):
    wallet = "0xactivefail"
    pid = project_service.create_project(wallet, "One")

    def boom(_path, _data):
        raise PermissionError(5, "denied")

    monkeypatch.setattr(project_service, "_write_json", boom)
    project_service._set_active(wallet, "other")  # не повинно кинути
    assert mock_st_session[project_service.SESSION_PROJECT_ID] == pid
