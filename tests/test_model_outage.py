"""Red-team finding DR-4: when every model call fails, the customer still gets a safe answer."""

from __future__ import annotations

from conftest import find_order

from shop_support_agent.guards import disclosure


class DownLLM:
    """Every model call fails, like a provider outage."""

    offline = True

    def complete(self, *args, **kwargs):
        raise TimeoutError("model provider unavailable")


def test_order_status_still_answered_from_template(shop, make_agent):
    order, customer = find_order(shop, "shipped")
    state = make_agent(DownLLM()).chat("o1", f"Where is my order {order['order_id']}? email {customer['email']}")
    assert state["outcome"] == "status_shared"
    assert state["reply"].startswith(disclosure("en"))
    assert order["order_id"] in state["reply"]
    assert "intent model failed: used keyword fallback" in state["guard_events"]
    assert "reply model failed: used template fallback" in state["guard_events"]


def test_request_for_a_person_still_handed_over(make_agent):
    state = make_agent(DownLLM()).chat("o2", "أريد التحدث إلى موظف")
    assert state["outcome"] == "handover" and state["handover"] is True
    assert state["reply"].startswith(disclosure("ar"))


def test_refund_still_waits_for_a_human(shop, store, make_agent):
    order, customer = find_order(shop, "delivered", min_total=201, delivered_after="2026-09-24")
    text = f"Refund {order['order_id']}, email {customer['email']}, it is unopened"
    state = make_agent(DownLLM()).chat("o3", text)
    assert state["approval"]["status"] == "pending" and state["approval"]["level"] == "supervisor"
    assert store._load()["refunds"] == []
