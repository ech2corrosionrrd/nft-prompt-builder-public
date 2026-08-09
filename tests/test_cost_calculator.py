"""Тести калькулятора вартості дропу: вибір пакета + supply-sync (UX-B5)."""

import streamlit as st

from services.payment_service import PACKAGES
from ui import cost_calculator


def test_suggest_package_picks_smallest_covering():
    # Потреба вкладається у «Старт» (100 кредитів) → беремо найдешевший.
    pid, usd = cost_calculator._suggest_package(50)
    assert pid == "start"
    assert usd == PACKAGES["start"]["usd"]


def test_suggest_package_steps_up_when_needed():
    # 101 кредит уже не вкладається у «Старт» → наступний за покриттям.
    pid, _ = cost_calculator._suggest_package(101)
    assert PACKAGES[pid]["credits"] >= 101
    assert pid == "creator"


def test_suggest_package_caps_at_largest():
    # Понад найбільший пакет → найбільший (не None).
    pid, usd = cost_calculator._suggest_package(10_000_000)
    biggest = max(PACKAGES, key=lambda k: PACKAGES[k]["credits"])
    assert pid == biggest
    assert usd == PACKAGES[biggest]["usd"]


def test_apply_pending_supply_writes_widget_key(monkeypatch):
    # Pending-патерн: відкладене значення підставляється у key віджета й споживається.
    monkeypatch.setattr(st, "session_state", {cost_calculator._SUPPLY_PENDING: 25})
    cost_calculator._apply_pending_supply()
    assert st.session_state[cost_calculator._SUPPLY_KEY] == 25
    assert cost_calculator._SUPPLY_PENDING not in st.session_state


def test_apply_pending_supply_noop_without_pending(monkeypatch):
    # Без pending — нічого не чіпає (не затирає правки сесії).
    monkeypatch.setattr(st, "session_state", {cost_calculator._SUPPLY_KEY: 100})
    cost_calculator._apply_pending_supply()
    assert st.session_state[cost_calculator._SUPPLY_KEY] == 100
