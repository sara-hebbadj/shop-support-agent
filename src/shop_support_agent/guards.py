"""Deterministic guardrails. These are plain Python checks, so a prompt cannot switch them off.

1. Verification: order details only after the order ID and email match (agent.verify).
2. Approval gating: refunds and address changes are only queued; a human decides (crm.py).
3. Refund threshold: refunds above AED 200 must be approved by a supervisor (crm.approval_level).
4. Output check: a reply may not contain another customer's email, phone, name or order ID.
5. AI disclosure: the first reply always starts with a fixed "I am an AI assistant" line.
"""

from __future__ import annotations

from .config import REFUND_ESCALATION_AED
from .data import ShopData
from .rules import TEMPLATES

NEEDS_VERIFICATION = {"order_status", "return_refund", "address_change"}


def disclosure(language: str) -> str:
    return TEMPLATES.get(language, TEMPLATES["en"])["disclosure"]


def find_leaks(reply: str, shop: ShopData, allowed_customer_id: str | None, public_text: str) -> list[str]:
    """Return other customers' data found in the reply.

    public_text = what the customer typed + the policy/FAQ text shown to the model.
    Repeating something from there is not a leak (e.g. the order ID the customer gave
    us, or the example ID "LS-10001" in the FAQ). Data from anywhere else is a leak.
    """
    reply_lower = reply.lower()
    typed = public_text.lower()
    leaks = []
    for customer in shop.customers.values():
        if customer["id"] == allowed_customer_id:
            continue
        for value in (customer["email"], customer["phone"], customer["name"], customer["address"]):
            if value.lower() in reply_lower and value.lower() not in typed:
                leaks.append(value)
    for order_id, order in shop.orders.items():
        if order["customer_id"] != allowed_customer_id and order_id.lower() in reply_lower \
                and order_id.lower() not in typed:
            leaks.append(order_id)
    return leaks


def approval_problems(approval: dict | None) -> list[str]:
    """Check a queued action before the customer is told about it."""
    if not approval:
        return []
    problems = []
    if approval.get("status") != "pending":
        problems.append("agent-created approval is not pending")
    if approval.get("action") == "refund" and approval.get("amount_aed", 0) > REFUND_ESCALATION_AED \
            and approval.get("level") != "supervisor":
        problems.append("refund above AED 200 not escalated to a supervisor")
    return problems
