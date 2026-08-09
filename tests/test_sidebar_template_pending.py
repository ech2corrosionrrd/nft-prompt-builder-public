"""Pending-key для sidebar template selectbox (Streamlit widget guard)."""

from __future__ import annotations

import streamlit as st

from state.sidebar_constants import SIDEBAR_NO_TEMPLATE
from ui import sidebar as sidebar_mod

_TEMPLATE_PICK_KEY = sidebar_mod._TEMPLATE_PICK_KEY
_TEMPLATE_PICK_PENDING = sidebar_mod._TEMPLATE_PICK_PENDING


def test_apply_pending_sidebar_template_pick(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state, raising=False)
    state[_TEMPLATE_PICK_PENDING] = SIDEBAR_NO_TEMPLATE

    sidebar_mod._apply_pending_sidebar_template_pick()

    assert _TEMPLATE_PICK_PENDING not in state
    assert state[_TEMPLATE_PICK_KEY] == SIDEBAR_NO_TEMPLATE


def test_apply_pending_noop_without_pending(monkeypatch):
    state: dict = {_TEMPLATE_PICK_KEY: "cyberpunk"}
    monkeypatch.setattr(st, "session_state", state, raising=False)

    sidebar_mod._apply_pending_sidebar_template_pick()

    assert state[_TEMPLATE_PICK_KEY] == "cyberpunk"


def test_queue_template_pick_reset(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(st, "session_state", state, raising=False)

    sidebar_mod.queue_template_pick_reset()

    assert state[_TEMPLATE_PICK_PENDING] == SIDEBAR_NO_TEMPLATE
