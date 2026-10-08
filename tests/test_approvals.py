"""Approval gating and the AED 200 refund threshold."""

from __future__ import annotations

from conftest import find_order

from shop_support_agent.crm import approval_level


def test_refund_threshold_is_strictly_above_200():
    assert approval_level("refund", 200) == "team"
    assert approval_level("refund", 200.01) == "supervisor"
    assert approval_level("address_change") == "team"


def test_request_refund_only_queues(store, shop):
    order, customer = find_order(shop, "delivered", max_total=200)
    item = store.request_refund(order["order_id"], customer["id"], int(order["total_aed"]), "unopened")
    assert item["status"] == "pending" and item["level"] == "team"
    state = store._load()
    assert state["refunds"] == []  # nothing paid out before a human decides


def test_team_member_cannot_approve_large_refund(store, shop):
    order, customer = find_order(shop, "delivered", min_total=201)
    item = store.request_refund(order["order_id"], customer["id"], int(order["total_aed"]), "unopened")
    assert item["level"] == "supervisor"
    refused = store.decide(item["approval_id"], True, "amira", role="team")
    assert refused["ok"] is False
    approved = store.decide(item["approval_id"], True, "sara", role="supervisor")
    assert approved["status"] == "approved"


def test_decide_is_idempotent(store, shop):
    order, customer = find_order(shop, "delivered", max_total=200)
    item = store.request_refund(order["order_id"], customer["id"], int(order["total_aed"]), "unopened")
    store.decide(item["approval_id"], True, "sara")
    again = store.decide(item["approval_id"], True, "sara")
    assert again["already_decided"] is True
    assert len(store._load()["refunds"]) == 1  # a repeated click never pays twice


def test_denied_refund_has_no_effect(store, shop):
    order, customer = find_order(shop, "delivered", max_total=200)
    item = store.request_refund(order["order_id"], customer["id"], int(order["total_aed"]), "unopened")
    denied = store.decide(item["approval_id"], False, "sara")
    assert denied["status"] == "denied"
    assert store._load()["refunds"] == []


def test_same_pending_request_is_not_queued_twice(store, shop):
    order, customer = find_order(shop, "delivered", max_total=200)
    first = store.request_refund(order["order_id"], customer["id"], 50, "unopened")
    second = store.request_refund(order["order_id"], customer["id"], 50, "unopened")
    assert second["approval_id"] == first["approval_id"] and second["duplicate"] is True
    assert len(store.list_approvals()) == 1


def test_refund_validation(store, shop):
    order, customer = find_order(shop, "delivered")
    other = next(c for c in shop.customers.values() if c["id"] != customer["id"])
    assert store.request_refund(order["order_id"], other["id"], 10, "x")["ok"] is False
    assert store.request_refund(order["order_id"], customer["id"], 10_000, "x")["ok"] is False


def test_address_change_only_before_shipping_and_after_approval(store, shop):
    shipped, shipped_customer = find_order(shop, "shipped")
    assert store.update_address(shipped["order_id"], shipped_customer["id"], "Villa 1, Street 2, Dubai")["ok"] is False
    order, customer = find_order(shop, "processing")
    item = store.update_address(order["order_id"], customer["id"], "Villa 1, Street 2, Dubai")
    assert store._load()["address_overrides"] == {}
    store.decide(item["approval_id"], True, "sara")
    assert store.get_customer(customer["id"])["address"] == "Villa 1, Street 2, Dubai"


def test_agent_pauses_for_supervisor_and_resumes_after_decision(shop, store, make_agent):
    order, customer = find_order(shop, "delivered", min_total=201, delivered_after="2026-09-24")
    agent = make_agent()
    state = agent.chat("r1", f"I want a refund for {order['order_id']}, email {customer['email']}, it is unopened")
    assert state["outcome"] == "refund_escalated"
    pending = agent.pending_approval("r1")
    assert pending["level"] == "supervisor" and pending["amount_aed"] == int(order["total_aed"])
    assert all(a["status"] == "pending" for a in store.list_approvals())  # the agent never decides

    item = store.decide(pending["approval_id"], True, "sara", role="supervisor")
    resumed = agent.resume("r1", item)
    assert resumed["approval"]["status"] == "approved"
    assert agent.pending_approval("r1") is None


def test_agent_does_not_refund_opened_products(shop, store, make_agent):
    order, customer = find_order(shop, "delivered", delivered_after="2026-09-24")
    state = make_agent().chat("r2", f"Refund {order['order_id']} please, email {customer['email']}. I opened it.")
    assert state["outcome"] == "return_not_eligible"
    assert store.list_approvals() == []
