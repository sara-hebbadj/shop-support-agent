"""The LangGraph customer-service agent.

Graph (one run per customer message):

    understand -> [handover | verify | retrieve]
    verify     -> [retrieve | respond | handover]
    retrieve   -> act -> check -> [handover | respond]
    handover   -> respond
    respond    -> [wait_for_approval | END]
    wait_for_approval  (LangGraph interrupt: pauses until a human approves or denies)

Design choice: the LLM understands the message and writes the reply; plain code decides
which tools run, checks identity and gates every money or data change.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from . import guards, prompts, rules
from .config import LOW_CONFIDENCE, MAX_VERIFY_ATTEMPTS
from .courier_api import CourierClient
from .crm_server import CrmMcpClient
from .data import ShopData, load_shop_data, return_eligibility
from .knowledge import retrieve
from .llm import FakeLLM, LLMNotConfigured, make_client, parse_json
from .parsing import detect_language, extract_email, extract_order_id


class AgentState(TypedDict, total=False):
    # Kept across turns (the checkpointer stores them per conversation thread)
    messages: Annotated[list[dict], operator.add]
    tool_calls: Annotated[list[str], operator.add]
    language: str
    verified_customer_id: str | None
    verified_order_id: str | None
    failed_verifications: int
    pending_intent: str | None  # e.g. waiting for the email to finish an order-status request
    last_order_id: str | None
    last_email: str | None
    disclosed: bool
    # Reset at the start of every turn
    intent: str
    confidence: float
    sentiment: str
    wants_human: bool
    injection: bool
    entities: dict
    docs: list[dict]
    facts: dict
    outcome: str
    approval: dict | None
    handover: bool
    guard_events: list[str]
    reply: str


class SupportAgent:
    def __init__(self, llm: Any = None, shop: ShopData | None = None, courier: CourierClient | None = None,
                 crm: CrmMcpClient | None = None, checkpointer: Any = None):
        self.llm = llm or make_client()
        self.shop = shop or load_shop_data()
        self.courier = courier or CourierClient()
        self.crm = crm or CrmMcpClient()
        self.graph = self._build(checkpointer or InMemorySaver())

    # ------------------------------------------------------------------ graph
    def _build(self, checkpointer):
        graph = StateGraph(AgentState)
        for name in ("understand", "verify", "retrieve", "act", "check", "handover", "respond",
                     "wait_for_approval"):
            graph.add_node(name, getattr(self, name))
        graph.add_edge(START, "understand")
        graph.add_conditional_edges("understand", self.route_after_understand, ["handover", "verify", "retrieve"])
        graph.add_conditional_edges("verify", self.route_after_verify, ["retrieve", "respond", "handover"])
        graph.add_edge("retrieve", "act")
        graph.add_edge("act", "check")
        graph.add_conditional_edges("check", self.route_after_check, ["handover", "respond"])
        graph.add_edge("handover", "respond")
        graph.add_conditional_edges("respond", self.route_after_respond, ["wait_for_approval", END])
        graph.add_edge("wait_for_approval", END)
        return graph.compile(checkpointer=checkpointer)

    # ------------------------------------------------------------------ public API
    def chat(self, thread_id: str, text: str) -> dict:
        """Send one customer message. Returns the final state of this turn."""
        config = {"configurable": {"thread_id": thread_id}}
        self.graph.invoke({"messages": [{"role": "user", "content": text}]}, config)
        return self.graph.get_state(config).values

    def pending_approval(self, thread_id: str) -> dict | None:
        """The approval this conversation is paused on, if any."""
        snapshot = self.graph.get_state({"configurable": {"thread_id": thread_id}})
        return snapshot.interrupts[0].value if snapshot.interrupts else None

    def resume(self, thread_id: str, decided_item: dict) -> dict:
        """Continue a paused conversation after a human decided (CrmStore.decide already applied it)."""
        config = {"configurable": {"thread_id": thread_id}}
        self.graph.invoke(Command(resume=decided_item), config)
        return self.graph.get_state(config).values

    # ------------------------------------------------------------------ nodes
    def understand(self, state: AgentState) -> dict:
        text = state["messages"][-1]["content"]
        language = detect_language(text, state.get("language"))
        order_id, email = extract_order_id(text), extract_email(text)
        info = self._classify(state["messages"][-5:-1], text)
        intent = info["intent"]

        # A message that only adds a missing detail continues the earlier request.
        pending = state.get("pending_intent")
        adds_detail = order_id or email or info["new_address"] or info["return_reason"]
        if pending and intent in ("other", "greeting", "policy_question") and adds_detail:
            intent = pending
        new_address = info["new_address"]
        if pending == "address_change" and not new_address and rules.find_first(text, {"a": rules.ADDRESS_HINTS}):
            new_address = text.strip()

        return {
            "language": language,
            "intent": intent,
            "confidence": info["confidence"],
            "sentiment": info["sentiment"],
            "wants_human": info["wants_human"],
            "injection": info["injection_attempt"] or rules.looks_like_injection(text),
            "entities": {
                "order_id": order_id or state.get("last_order_id"),
                "email": email or state.get("last_email"),
                "new_address": new_address,
                "skin_type": info["skin_type"],
                "category": info["category"],
                "return_reason": info["return_reason"],
            },
            "last_order_id": order_id or state.get("last_order_id"),
            "last_email": email or state.get("last_email"),
            # reset per-turn fields
            "docs": [], "facts": {}, "outcome": "", "approval": None, "handover": False,
            "guard_events": ["intent model failed: used keyword fallback"] if info["fallback"] else [],
            "reply": "",
        }

    def verify(self, state: AgentState) -> dict:
        """Order details only after the order ID and the email on that order match."""
        entities = state["entities"]
        order_id, email = entities["order_id"], entities["email"]
        verified = state.get("verified_customer_id")

        customer_id = self.shop.verify(order_id, email) if order_id and email else None
        if customer_id:
            return {"verified_customer_id": customer_id, "verified_order_id": order_id, "pending_intent": None,
                    "failed_verifications": 0}
        if verified and order_id and self.shop.orders.get(order_id, {}).get("customer_id") == verified:
            return {"verified_order_id": order_id, "pending_intent": None}
        if verified and not order_id and state.get("verified_order_id"):
            return {"pending_intent": None}
        if order_id and email:  # both given but they do not match: never say which part is wrong
            failures = state.get("failed_verifications", 0) + 1
            return {"outcome": "verification_failed", "failed_verifications": failures,
                    "pending_intent": state["intent"], "facts": {"verification": "failed"}}
        return {"outcome": "need_verification", "pending_intent": state["intent"],
                "facts": {"verification": "needed"}}

    def retrieve(self, state: AgentState) -> dict:
        topic = "other_person_order" if state["injection"] and state["intent"] == "other" else state["intent"]
        return {"docs": retrieve(topic, state["language"], state["messages"][-1]["content"])}

    def act(self, state: AgentState) -> dict:
        """Run the tools this intent needs. Money/data changes are only queued for approval."""
        intent, entities = state["intent"], state["entities"]
        order_id = state.get("verified_order_id")
        customer_id = state.get("verified_customer_id")
        calls: list[str] = []
        facts: dict = {"policy": state["docs"]}
        approval = None

        if intent == "order_status":
            facts["order"] = self._tool(calls, "get_order", self.courier.get_order, order_id)
            if facts["order"] and facts["order"]["tracking_id"]:
                tracking = self._tool(calls, "get_tracking", self.courier.get_tracking,
                                      facts["order"]["tracking_id"])
                facts["tracking"] = {"latest": tracking["latest"], "scans": len(tracking["events"])} \
                    if tracking else None
            outcome = "status_shared"
        elif intent == "return_refund":
            order = facts["order"] = self._tool(calls, "get_order", self.courier.get_order, order_id)
            if not entities["return_reason"]:
                outcome = "need_return_details"
                return {"outcome": outcome, "facts": facts, "tool_calls": calls, "pending_intent": "return_refund"}
            eligible, code = return_eligibility(self.shop.orders[order_id], entities["return_reason"])
            facts["return_check"] = code
            if eligible:
                approval = self._crm(calls, "request_refund", order_id=order_id, customer_id=customer_id,
                                     amount_aed=order["total_aed"], reason=entities["return_reason"])
                outcome = "refund_escalated" if approval.get("level") == "supervisor" else "refund_queued"
            else:
                outcome = "return_not_eligible"
        elif intent == "address_change":
            order = facts["order"] = self._tool(calls, "get_order", self.courier.get_order, order_id)
            if order["status"] != "processing":
                outcome = "address_change_not_possible"
            elif not entities["new_address"]:
                return {"outcome": "need_address", "facts": facts, "tool_calls": calls,
                        "pending_intent": "address_change"}
            else:
                profile = self._crm(calls, "get_customer", customer_id=customer_id)
                facts["current_address"] = profile.get("address")
                approval = self._crm(calls, "update_address", order_id=order_id, customer_id=customer_id,
                                     new_address=entities["new_address"])
                outcome = "address_change_queued" if approval.get("ok") else "address_change_not_possible"
        elif intent == "product_advice":
            facts["products"] = self._tool(calls, "search_products", self.shop.search_products,
                                           entities["skin_type"], entities["category"])
            outcome = "advice_given"
        elif intent == "policy_question":
            outcome = "policy_answered"
        elif intent == "greeting":
            outcome = "greeting"
        else:
            outcome = "refused" if state["injection"] else "clarify"

        if state["injection"] and customer_id:  # leave a security note for the human team
            self._crm(calls, "add_note", customer_id=customer_id,
                      note="Message contained instructions aimed at the assistant (possible prompt injection).")
        if approval and not approval.get("ok"):
            approval = None
        return {"outcome": outcome, "facts": facts, "tool_calls": calls, "approval": approval,
                "pending_intent": None}

    def check(self, state: AgentState) -> dict:
        """Policy check before anything is said to the customer."""
        events = guards.approval_problems(state.get("approval"))
        order = state["facts"].get("order")
        if order and self.shop.orders[order["order_id"]]["customer_id"] != state.get("verified_customer_id"):
            events.append("order of another customer reached the reply step; removed")
            return {"guard_events": events, "facts": {}, "outcome": "verification_failed", "approval": None}
        return {"guard_events": events}

    def handover(self, state: AgentState) -> dict:
        text = state["messages"][-1]["content"]
        priority = "high" if state.get("sentiment") == "angry" else "normal"
        calls: list[str] = []
        ticket = self._crm(calls, "create_ticket", customer_id=state.get("verified_customer_id") or "",
                           subject=f"Handover ({state.get('language')}, intent: {state.get('intent')})",
                           summary=f"Customer's last message: {text[:500]}", priority=priority)
        facts = {**state.get("facts", {}), "ticket": ticket}
        return {"handover": True, "outcome": "handover", "facts": facts, "tool_calls": calls}

    def respond(self, state: AgentState) -> dict:
        language = state["language"]
        facts = self._reply_facts(state)
        reply = self._write_reply(state, facts)
        # Text the customer already saw or typed is "public": repeating it is not a leak.
        public_parts = [m["content"] for m in state["messages"] if m["role"] == "user"]
        public_parts += [d["text"] for d in state.get("docs", [])]
        public_parts.append(rules.TEMPLATES[language]["need_verification"])  # contains the example ID LS-10001
        public_text = " ".join(public_parts)
        leaks = guards.find_leaks(reply, self.shop, state.get("verified_customer_id"), public_text)
        events = list(state.get("guard_events", []))
        if leaks:  # never send another customer's data, whatever the model wrote
            events.append(f"blocked reply containing other customers' data ({len(leaks)} items)")
            reply = rules.render_reply("refused", language, facts)
        if not state.get("disclosed"):
            reply = guards.disclosure(language) + "\n\n" + reply
        return {"messages": [{"role": "assistant", "content": reply}], "reply": reply, "disclosed": True,
                "guard_events": events}

    def wait_for_approval(self, state: AgentState) -> dict:
        approval = state["approval"]
        # Pause here. The app resumes with the item after a human decided in the Approvals tab.
        # Nothing before interrupt() has side effects, so re-running this node on resume is safe.
        decided = interrupt({key: approval.get(key) for key in
                             ("approval_id", "action", "order_id", "amount_aed", "level", "details")})
        approval = {**approval, **decided}
        facts = {**self._reply_facts(state), "approval": approval,
                 "outcome": "approved" if approval.get("status") == "approved" else "denied"}
        reply = self._write_reply(state, facts)
        return {"messages": [{"role": "assistant", "content": reply}], "reply": reply, "approval": approval}

    # ------------------------------------------------------------------ routing
    @staticmethod
    def route_after_understand(state: AgentState) -> str:
        if state["wants_human"] or state["confidence"] < LOW_CONFIDENCE:
            return "handover"
        return "verify" if state["intent"] in guards.NEEDS_VERIFICATION else "retrieve"

    @staticmethod
    def route_after_verify(state: AgentState) -> str:
        if state.get("outcome") in ("need_verification", "verification_failed"):
            too_many = state.get("failed_verifications", 0) >= MAX_VERIFY_ATTEMPTS
            # An angry customer goes to a person straight away instead of being asked for details.
            return "handover" if too_many or state.get("sentiment") == "angry" else "respond"
        return "retrieve"

    @staticmethod
    def route_after_check(state: AgentState) -> str:
        return "handover" if state.get("sentiment") == "angry" else "respond"

    @staticmethod
    def route_after_respond(state: AgentState) -> str:
        approval = state.get("approval")
        return "wait_for_approval" if approval and approval.get("status") == "pending" else END

    # ------------------------------------------------------------------ helpers
    def _classify(self, history: list[dict], text: str) -> dict:
        """Ask the cheap model for intent + details as JSON. Falls back to keyword rules on any error."""
        try:
            result = self.llm.complete(prompts.intent_messages(history, text), role="cheap", purpose="intent",
                                       json_mode=True, max_tokens=250)
            raw = parse_json(result.text)
        except LLMNotConfigured:
            raise
        except Exception:  # model down or bad JSON: keyword rules, and say so in guard_events
            raw = FakeLLM._intent(f"<customer_message>{text}</customer_message>")
            raw["confidence"] = 0.6
            raw["fallback"] = True
        return {**clean_intent(raw), "fallback": bool(raw.get("fallback"))}

    def _write_reply(self, state: AgentState, facts: dict) -> str:
        messages = prompts.reply_messages(state["language"], facts, state.get("docs", []),
                                          state["messages"][-5:-1], state["messages"][-1]["content"])
        try:
            return self.llm.complete(messages, role="main", purpose="reply", max_tokens=400).text.strip()
        except LLMNotConfigured:
            raise
        except Exception:  # model down: fixed template, so the customer still gets an answer (error is traced)
            return rules.render_reply(facts["outcome"], state["language"], facts)

    def _reply_facts(self, state: AgentState) -> dict:
        facts = {k: v for k, v in state.get("facts", {}).items() if k != "policy"}
        facts["policy"] = state.get("docs", [])[:1]
        return {**facts, "outcome": state.get("outcome") or "clarify", "language": state["language"],
                "approval": state.get("approval"), "verified": bool(state.get("verified_customer_id")),
                "customer_sentiment": state.get("sentiment")}

    @staticmethod
    def _tool(calls: list[str], name: str, function, *args):
        calls.append(name)
        return function(*args)

    def _crm(self, calls: list[str], tool: str, **arguments) -> dict:
        calls.append(tool)
        return self.crm.call(tool, **arguments)


def clean_intent(raw: dict) -> dict:
    """Make the model's JSON safe to use: known values only, sensible defaults."""
    def pick(value, allowed):
        return value if value in allowed else None

    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    address = raw.get("new_address")
    return {
        "intent": raw.get("intent") if raw.get("intent") in prompts.INTENTS else "other",
        "confidence": confidence,
        "sentiment": raw.get("sentiment") if raw.get("sentiment") in ("calm", "upset", "angry") else "calm",
        "wants_human": bool(raw.get("wants_human")),
        "new_address": address.strip() if isinstance(address, str) and address.strip() else None,
        "skin_type": pick(raw.get("skin_type"), ("dry", "oily", "combination", "sensitive")),
        "category": pick(raw.get("category"), ("cleanser", "serum", "moisturiser", "sunscreen", "mask")),
        "return_reason": pick(raw.get("return_reason"), ("unopened", "opened", "damaged", "wrong_item")),
        "injection_attempt": bool(raw.get("injection_attempt")),
    }
