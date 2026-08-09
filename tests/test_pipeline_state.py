"""Тести синхронізації стану конвеєра між етапами."""

import streamlit as st

from state.pipeline_state import (
    APPROVED_CONTENT,
    MINT_ASSETS,
    ensure_mint_queue_from_approved,
    sync_mint_queue_from_approved,
)


class _FakeSessionState(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def test_sync_mint_queue_from_approved(monkeypatch):
    fake = _FakeSessionState({
        APPROVED_CONTENT: [{"name": "Token #1", "path": "/tmp/1.png", "prompt": "owl"}],
        MINT_ASSETS: [],
    })
    monkeypatch.setattr(st, "session_state", fake)
    n = sync_mint_queue_from_approved()
    assert n == 1
    assert len(fake[MINT_ASSETS]) == 1
    assert fake[MINT_ASSETS][0]["prompt"] == "owl"
    assert fake[MINT_ASSETS] is not fake[APPROVED_CONTENT]


def test_ensure_mint_queue_idempotent(monkeypatch):
    fake = _FakeSessionState({
        APPROVED_CONTENT: [{"path": "a"}],
        MINT_ASSETS: [{"path": "b"}],
    })
    monkeypatch.setattr(st, "session_state", fake)
    assert ensure_mint_queue_from_approved() == 1
    assert fake[MINT_ASSETS][0]["path"] == "b"
