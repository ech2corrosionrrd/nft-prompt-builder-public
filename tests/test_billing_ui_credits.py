"""Показ кредитів замість USD у classic UI (billing_ui хелпери)."""

from unittest.mock import MagicMock, patch

import pytest

from ui import billing_ui
from ui.billing_ui import BILLING_USER_DISCONNECT_KEY, WALLET_KEY


@pytest.mark.parametrize("enforcement,label_key", [(True, "batch.est_credits"), (False, "batch.est_cost")])
def test_est_llm_metric_label(enforcement, label_key, monkeypatch):
    monkeypatch.setattr(billing_ui.billing_guard, "enforcement_enabled", lambda: enforcement)
    with patch.object(billing_ui, "t", side_effect=lambda k, **kw: k):
        assert billing_ui.est_llm_metric_label() == label_key


def test_est_llm_metric_value_credits(monkeypatch):
    monkeypatch.setattr(billing_ui.billing_guard, "enforcement_enabled", lambda: True)
    assert billing_ui.est_llm_metric_value(10, 0.05) == "10 cr"


def test_est_llm_metric_value_usd(monkeypatch):
    monkeypatch.setattr(billing_ui.billing_guard, "enforcement_enabled", lambda: False)
    assert billing_ui.est_llm_metric_value(10, 0.0512) == "$0.0512"


def test_llm_credits_units():
    assert billing_ui.llm_credits(3) == 3


def test_prompt_cost_caption_keys(monkeypatch):
    monkeypatch.setattr(billing_ui.billing_guard, "enforcement_enabled", lambda: True)
    with patch.object(billing_ui, "t", side_effect=lambda k, **kw: k) as mock_t:
        billing_ui.prompt_cost_caption("gpt-4o", 5, 0.1)
        mock_t.assert_called_once_with("coll.prompt_credits", model="gpt-4o", cr=5)

    monkeypatch.setattr(billing_ui.billing_guard, "enforcement_enabled", lambda: False)
    with patch.object(billing_ui, "t", side_effect=lambda k, **kw: k) as mock_t:
        billing_ui.prompt_cost_caption("gpt-4o", 5, 0.1)
        mock_t.assert_called_once_with("coll.prompt_cost", model="gpt-4o", cost=0.1)


def test_batch_results_credit_suffix(monkeypatch):
    monkeypatch.setattr(billing_ui.billing_guard, "enforcement_enabled", lambda: True)
    with patch.object(billing_ui, "t", side_effect=lambda k, **kw: f"{k}:{kw['cr']}"):
        assert billing_ui.batch_results_credit_suffix(4) == "batch.actual_credits:4"
    monkeypatch.setattr(billing_ui.billing_guard, "enforcement_enabled", lambda: False)
    assert billing_ui.batch_results_credit_suffix(4) == ""


def test_adopt_gateway_wallet_respects_user_disconnect(monkeypatch):
    import streamlit as st

    fake = {BILLING_USER_DISCONNECT_KEY: True, WALLET_KEY: ""}
    monkeypatch.setattr(st, "session_state", fake)
    monkeypatch.setattr(billing_ui.gateway_guard, "current_wallet", lambda: "0xGateway")
    monkeypatch.setattr(
        billing_ui.payment_service,
        "complete_wallet_sign_in",
        MagicMock(side_effect=AssertionError("must not adopt")),
    )
    billing_ui.adopt_gateway_wallet()
    assert fake[WALLET_KEY] == ""
