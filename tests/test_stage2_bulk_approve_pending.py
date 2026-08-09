"""Pending-масове схвалення куратора (toggle pl2_approve_{i})."""

from __future__ import annotations

import streamlit as st

from ui.stage2_generator import (
    PENDING_PL2_BULK_APPROVE_KEY,
    _apply_pending_pl2_bulk_approve,
)


def test_apply_pending_pl2_bulk_approve_sets_toggles(monkeypatch):
    class FakeSessionState(dict):
        def __getattr__(self, key):
            try:
                return self[key]
            except KeyError as exc:
                raise AttributeError(key) from exc

        def __setattr__(self, key, value):
            self[key] = value

    fake = FakeSessionState({PENDING_PL2_BULK_APPROVE_KEY: [0, 2]})
    monkeypatch.setattr(st, "session_state", fake)

    _apply_pending_pl2_bulk_approve()

    assert fake["pl2_approve_0"] is True
    assert fake["pl2_approve_2"] is True
    assert PENDING_PL2_BULK_APPROVE_KEY not in fake


def test_apply_pending_pl2_bulk_approve_noop_without_pending(monkeypatch):
    class FakeSessionState(dict):
        def __getattr__(self, key):
            try:
                return self[key]
            except KeyError as exc:
                raise AttributeError(key) from exc

        def __setattr__(self, key, value):
            self[key] = value

    fake = FakeSessionState({"pl2_approve_0": False})
    monkeypatch.setattr(st, "session_state", fake)

    _apply_pending_pl2_bulk_approve()

    assert fake["pl2_approve_0"] is False
