"""No order details before the order ID + email match, and no data from other customers."""

from __future__ import annotations

from conftest import find_order

from shop_support_agent.guards import find_leaks
from shop_support_agent.llm import LLMResult


def test_shop_verify_needs_matching_email(shop):
    order, customer = find_order(shop, "shipped")
    assert shop.verify(order["order_id"], customer["email"].upper()) == customer["id"]
    assert shop.verify(order["order_id"], "someone.else@example.com") is None
    assert shop.verify("LS-99999", customer["email"]) is None


def test_wrong_email_gets_no_order_details(shop, make_agent):
    order, _ = find_order(shop, "shipped")
    agent = make_agent()
    state = agent.chat("t1", f"Where is {order['order_id']}? my email is wrong.person@example.com")
    assert state["outcome"] == "verification_failed"
    assert "get_order" not in state["tool_calls"]
    assert order["tracking_id"] not in state["reply"]


def test_cannot_switch_to_another_customers_order(shop, make_agent):
    mine, me = find_order(shop, "shipped")
    other = next(o for o in shop.orders.values() if o["customer_id"] != me["id"] and o["tracking_id"])
    agent = make_agent()
    first = agent.chat("t2", f"Where is my order {mine['order_id']}? Email {me['email']}")
    assert first["outcome"] == "status_shared"
    second = agent.chat("t2", f"And where is order {other['order_id']}?")
    assert second["outcome"] == "verification_failed"
    assert other["tracking_id"] not in second["reply"]
    assert second["tool_calls"].count("get_order") == 1  # only the first, verified lookup


def test_missing_details_asks_for_verification(make_agent):
    state = make_agent().chat("t3", "Where is my order?")
    assert state["outcome"] == "need_verification"
    assert state["tool_calls"] == []


def test_three_failed_checks_hand_over_to_a_human(shop, make_agent):
    order, _ = find_order(shop, "shipped")
    agent = make_agent()
    for attempt in range(3):
        state = agent.chat("t4", f"Status of {order['order_id']}, email guess{attempt}@example.com")
    assert state["outcome"] == "handover"
    assert state["handover"] is True


def test_find_leaks_flags_other_customers_but_not_what_the_customer_typed(shop):
    _, me = find_order(shop, "shipped")
    other = next(c for c in shop.customers.values() if c["id"] != me["id"])
    assert find_leaks(f"Contact {other['email']}", shop, me["id"], public_text="hello") == [other["email"]]
    assert find_leaks(f"I checked {other['email']}", shop, me["id"], public_text=other["email"]) == []
    assert find_leaks(f"Your email {me['email']}", shop, me["id"], public_text="") == []


class LeakyLLM:
    """A 'bad model' that tries to put another customer's email into every reply."""

    offline = True

    def __init__(self, leaked_email):
        self.leaked_email = leaked_email

    def complete(self, messages, role="main", purpose="", **kwargs):
        if purpose == "intent":
            return LLMResult('{"intent": "greeting", "confidence": 0.9}', "leaky")
        return LLMResult(f"Sure! Another customer is {self.leaked_email}.", "leaky")


def test_reply_with_another_customers_data_is_blocked(shop, make_agent):
    victim = next(iter(shop.customers.values()))
    state = make_agent(LeakyLLM(victim["email"])).chat("t5", "hello")
    assert victim["email"] not in state["reply"]
    assert any("blocked reply" in event for event in state["guard_events"])


def test_first_reply_discloses_ai_assistant(make_agent):
    agent = make_agent()
    first = agent.chat("t6", "Bonjour")
    second = agent.chat("t6", "Quel sérum pour peau grasse ?")
    assert "assistant IA" in first["reply"]
    assert "assistant IA" not in second["reply"]
