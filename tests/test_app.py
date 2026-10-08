"""The Gradio demo's Approvals tab (red-team finding DR-2) and its banner (DR-3). Skipped without Gradio."""

from __future__ import annotations

import importlib
import inspect

import pytest
from conftest import find_order


@pytest.fixture
def app_module(monkeypatch, store):
    pytest.importorskip("gradio")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")  # offline mode: no model, no network
    monkeypatch.setenv("GRADIO_ANALYTICS_ENABLED", "False")
    module = importlib.import_module("app.app")
    monkeypatch.setattr(module, "store", store)  # use the test's temporary CRM
    return module


def test_reviewer_cannot_choose_their_own_role(app_module):
    assert "role" not in inspect.signature(app_module.decide).parameters


def test_large_refund_needs_a_configured_supervisor(app_module, monkeypatch, store, shop):
    order, customer = find_order(shop, "delivered", min_total=201)
    item = store.request_refund(order["order_id"], customer["id"], int(order["total_aed"]), "unopened")

    monkeypatch.setenv("APPROVER_ROLE", "team")
    *_, note = app_module.decide(item["approval_id"], True, [], None)
    assert "Not applied" in note and store.list_approvals()[0]["status"] == "pending"

    monkeypatch.setenv("APPROVER_ROLE", "supervisor")
    monkeypatch.setenv("APPROVER_ID", "amina.k")
    *_, note = app_module.decide(item["approval_id"], True, [], None)
    decided = store.list_approvals()[0]
    assert decided["status"] == "approved" and decided["decided_by"] == "amina.k (supervisor)"


def test_banner_tells_users_in_three_languages_that_this_is_an_ai(app_module):
    banner = app_module.BANNER
    assert "AI assistant" in banner and "مساعد ذكي" in banner and "assistant IA" in banner
