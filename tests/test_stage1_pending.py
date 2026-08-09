"""Pending-key патерн у stage1_constructor (Style Bible clear, matrix apply)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_stage1():
    spec = importlib.util.spec_from_file_location("stage1_constructor", ROOT / "ui" / "stage1_constructor.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(ROOT))
    spec.loader.exec_module(mod)
    return mod


def test_apply_pending_bible_clears_keys(monkeypatch):
    mod = _load_stage1()
    state = {
        mod._BIBLE_CLEAR_PENDING: True,
        mod._BIBLE_KEYS["style"]: "old",
        mod._BIBLE_KEYS["lighting"]: "x",
    }
    monkeypatch.setattr(mod.st, "session_state", state, raising=False)
    mod._apply_pending_bible()
    assert mod._BIBLE_CLEAR_PENDING not in state
    assert state[mod._BIBLE_KEYS["style"]] == ""
    assert state[mod._BIBLE_KEYS["lighting"]] == ""


def test_apply_pending_bible_fill_writes_keys(monkeypatch):
    mod = _load_stage1()
    state = {
        mod._BIBLE_FILL_PENDING: {"style": "pixel", "lighting": "soft", "camera": "close", "background_rule": "solid"},
    }
    monkeypatch.setattr(mod.st, "session_state", state, raising=False)
    mod._apply_pending_bible()
    assert mod._BIBLE_FILL_PENDING not in state
    assert state[mod._BIBLE_KEYS["style"]] == "pixel"
    assert state[mod._BIBLE_KEYS["background_rule"]] == "solid"


def test_apply_pending_matrix_writes_inputs(monkeypatch):
    mod = _load_stage1()
    state = {
        mod._MATRIX_APPLY_PENDING: {"Варіанти персонажа": ["a", "b"]},
    }
    monkeypatch.setattr(mod.st, "session_state", state, raising=False)
    mod._apply_pending_matrix()
    assert mod._MATRIX_APPLY_PENDING not in state
    assert state["pl1_matrix_Варіанти персонажа"] == ["a", "b"]


def test_apply_pending_matrix_legacy_comma_string(monkeypatch):
    mod = _load_stage1()
    state = {
        mod._MATRIX_APPLY_PENDING: {"Варіанти фону": "a, b"},
    }
    monkeypatch.setattr(mod.st, "session_state", state, raising=False)
    mod._apply_pending_matrix()
    assert state["pl1_matrix_Варіанти фону"] == ["a", "b"]
