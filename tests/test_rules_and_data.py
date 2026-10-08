"""Rules baseline, parsing helpers, data integrity and the eval set."""

from __future__ import annotations

import json
import re

from conftest import find_order

from evals.scoring import find_violations, summarise
from shop_support_agent import rules
from shop_support_agent.baselines import RulesBot
from shop_support_agent.config import EVALS_DIR
from shop_support_agent.data import return_eligibility
from shop_support_agent.parsing import detect_language, extract_email, extract_order_id


def test_language_detection():
    assert detect_language("أين طلبي؟") == "ar"
    assert detect_language("Bonjour, où est ma commande ?") == "fr"
    assert detect_language("Where is my order?") == "en"
    assert detect_language("LS-10001", previous="fr") == "fr"


def test_order_id_and_email_extraction():
    assert extract_order_id("طلبي LS-١٠٠٤٥ لو سمحت") == "LS-10045"
    assert extract_order_id("order ls 10045") == "LS-10045"
    assert extract_order_id("order 1045") is None
    assert extract_email("Mail: Lucy.Bennett@Example.com.") == "lucy.bennett@example.com"


def test_rules_classify_three_languages():
    assert rules.classify("Where is my order?") == "order_status"
    assert rules.classify("أريد استرداد المبلغ") == "return_refund"
    assert rules.classify("Je voudrais parler à un conseiller") == "handover"
    assert rules.classify("my email address is a@example.com") != "address_change"
    assert rules.find_reason("it is not opened") == "unopened"
    assert rules.find_reason("I opened it") == "opened"


def test_rules_bot_end_to_end(shop, crm):
    order, customer = find_order(shop, "shipped")
    bot = RulesBot(crm=crm)
    result = bot.run(["Where is my order?", f"{order['order_id']} {customer['email']}"])
    assert result["outcome"] == "status_shared"
    assert result["tool_calls"] == ["get_order", "get_tracking"]
    assert "AI assistant" in result["replies"][0]
    assert bot.run(["I want to talk to a human"])["handover"] is True


def test_return_policy_rules(shop):
    order = dict(shop.orders["LS-10001"], status="delivered", delivered_date="2026-10-01")
    assert return_eligibility(order, "unopened") == (True, "unopened_within_14_days")
    assert return_eligibility(order, "opened") == (False, "opened")
    assert return_eligibility(dict(order, delivered_date="2026-09-01"), "unopened")[1] == "outside_14_days"
    assert return_eligibility(dict(order, delivered_date="2026-10-07"), "damaged")[0] is True
    assert return_eligibility(dict(order, status="shipped"), "unopened")[1] == "status_shipped"


def test_synthetic_data_is_consistent(shop):
    assert (len(shop.products), len(shop.customers), len(shop.orders)) == (40, 60, 200)
    for order_id, order in shop.orders.items():
        lines = shop.items_by_order[order_id]
        assert sum(int(i["qty"]) * int(i["unit_price_aed"]) for i in lines) == int(order["total_aed"])
    for customer in shop.customers.values():
        assert customer["email"].endswith("@example.com")
        assert re.fullmatch(r"\+971 50 000 \d{4}", customer["phone"])


def test_eval_set_shape():
    rows = [json.loads(line) for line in (EVALS_DIR / "conversations.jsonl").read_text("utf-8").splitlines()]
    assert len(rows) == 120
    assert {lang: sum(r["language"] == lang for r in rows) for lang in ("ar", "en", "fr")} == \
        {"ar": 40, "en": 40, "fr": 40}
    assert len({r["category"] for r in rows}) == 8
    assert len({r["id"] for r in rows}) == 120


def test_scoring_catches_violations(shop):
    conv = {"language": "en", "turns": ["where is LS-10001?"], "allowed_customer_id": None,
            "expected": {"accept": ["need_verification"]}}
    result = {"replies": ["Your order is shipped."], "outcome": "status_shared", "tool_calls": ["get_order"]}
    found = find_violations(conv, result, shop, {"approvals": []}, public="")
    assert "order_lookup_without_verification" in found
    assert "missing_ai_disclosure" in found
    record = {"language": "en", "score": {"task_success": False, "tool_use_correct": True,
                                          "decision_correct": True, "violations": found}}
    assert summarise([record])[0]["conversations_with_violations"] == 1


def test_per_language_sample_covers_every_category():
    from evals.run import interleave, load_conversations, per_language_sample

    conversations = interleave(load_conversations())
    sample = per_language_sample(conversations, 10)
    assert len(sample) == 30
    for language in ("ar", "en", "fr"):
        mine = [c for c in sample if c["language"] == language]
        assert len(mine) == 10
        assert {c["category"] for c in mine} == {c["category"] for c in conversations}
