"""The CRM MCP server, called through a real MCP client (in-process, no network)."""

from __future__ import annotations

import asyncio

from conftest import find_order


def test_server_lists_the_five_crm_tools(crm):
    names = asyncio.run(crm.list_tool_names())
    assert sorted(names) == ["add_note", "create_ticket", "get_customer", "request_refund", "update_address"]


def test_get_customer_and_add_note(crm, shop):
    _, customer = find_order(shop, "shipped")
    note = crm.call("add_note", customer_id=customer["id"], note="Asked about delivery")
    assert note["ok"] and note["note_id"] == "N-0001"
    profile = crm.call("get_customer", customer_id=customer["id"])
    assert profile["email"] == customer["email"]
    assert profile["notes"][-1]["note"] == "Asked about delivery"
    assert crm.call("get_customer", customer_id="C999")["ok"] is False


def test_create_ticket(crm):
    ticket = crm.call("create_ticket", customer_id="", subject="Handover", summary="Wants a person",
                      priority="urgent")
    assert ticket["ticket_id"] == "T-0001" and ticket["priority"] == "normal"  # unknown priority -> normal


def test_refund_tool_queues_for_approval(crm, store, shop):
    order, customer = find_order(shop, "delivered", min_total=201)
    result = crm.call("request_refund", order_id=order["order_id"], customer_id=customer["id"],
                      amount_aed=float(order["total_aed"]), reason="unopened")
    assert result["status"] == "pending" and result["level"] == "supervisor"
    assert store.list_approvals("pending")[0]["approval_id"] == result["approval_id"]


def test_address_tool_refuses_shipped_orders(crm, shop):
    order, customer = find_order(shop, "shipped")
    result = crm.call("update_address", order_id=order["order_id"], customer_id=customer["id"],
                      new_address="Villa 3, Street 9, Dubai")
    assert result["ok"] is False and "before shipping" in result["error"]
