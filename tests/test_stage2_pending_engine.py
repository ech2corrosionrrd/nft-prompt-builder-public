"""Pending pl2_engine — Streamlit widget-key safe (engine winner)."""

from __future__ import annotations

import streamlit as st

from services import ai_service
from ui.stage2_generator import PENDING_PL2_ENGINE_KEY, _apply_pending_pl2_engine


def test_apply_pending_pl2_engine_sets_selectbox_value(monkeypatch):
    class FakeSessionState(dict):
        def pop(self, key, default=None):
            return super().pop(key, default)

    winner = ai_service.ENGINES[0]
    fake = FakeSessionState({PENDING_PL2_ENGINE_KEY: winner, "pl2_engine": ai_service.ENGINES[-1]})
    monkeypatch.setattr(st, "session_state", fake)
    _apply_pending_pl2_engine()
    assert fake["pl2_engine"] == winner
    assert fake["pl2_preferred_engine"] == winner
    assert PENDING_PL2_ENGINE_KEY not in fake


def test_apply_pending_ignores_unknown_engine(monkeypatch):
    class FakeSessionState(dict):
        def pop(self, key, default=None):
            return super().pop(key, default)

    fake = FakeSessionState({PENDING_PL2_ENGINE_KEY: "OpenAI DALL-E 3", "pl2_engine": ai_service.ENGINES[0]})
    monkeypatch.setattr(st, "session_state", fake)
    _apply_pending_pl2_engine()
    assert fake["pl2_engine"] == ai_service.ENGINES[0]
    assert "pl2_preferred_engine" not in fake
