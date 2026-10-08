"""Gradio demo with two tabs: Customer chat and Approvals.

Run:  python app/app.py     then open http://127.0.0.1:7860

- With OPENROUTER_API_KEY set, the agent runs in demo mode on MODEL_CHEAP.
- Without a key it runs OFFLINE: replies come from fixed templates (FakeLLM), not a model.
- Each browser session may send DEMO_MESSAGE_LIMIT messages (default 20).
All data is synthetic (fictional shop "Lumi Skin").
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # run without installing the package

import gradio as gr  # noqa: E402

from shop_support_agent.agent import SupportAgent  # noqa: E402
from shop_support_agent.config import demo_message_limit, env  # noqa: E402
from shop_support_agent.crm_server import default_store  # noqa: E402
from shop_support_agent.data import load_shop_data  # noqa: E402
from shop_support_agent.llm import make_client  # noqa: E402
from shop_support_agent.rules import TEMPLATES  # noqa: E402

OFFLINE = not env("OPENROUTER_API_KEY")
LIMIT = demo_message_limit()
agent = SupportAgent(llm=make_client(offline=OFFLINE, role_override="cheap"))
store = default_store()
shop = load_shop_data()

BANNER = (
    "**Lumi Skin support agent** (fictional shop, synthetic data). You are chatting with an AI assistant. "
    "Refunds and address changes wait for a human in the **Approvals** tab; refunds above AED 200 need a "
    "supervisor.\n\n"
    + ("**Offline mode:** no API key found, so replies come from fixed templates (keyword rules), "
       "not from a language model." if OFFLINE else f"Demo mode: model `{env('MODEL_CHEAP')}`, "
       f"{LIMIT} messages per session.")
)


def demo_orders() -> list[list]:
    """A few synthetic orders to try, one per useful status."""
    rows = []
    for status in ("shipped", "processing", "delivered"):
        for order in [o for o in shop.orders.values() if o["status"] == status][:2]:
            customer = shop.customers[order["customer_id"]]
            rows.append([order["order_id"], customer["email"], status, order["total_aed"], customer["language"]])
    return rows


def new_session() -> dict:
    return {"thread_id": str(uuid.uuid4()), "count": 0, "approval_threads": {}}


def send(message: str, history: list, session: dict):
    session = session or new_session()
    history = history or []
    if not message.strip():
        return "", history, session, ""
    if session["count"] >= LIMIT:
        history.append({"role": "assistant", "content": f"Demo limit reached ({LIMIT} messages). Refresh to restart."})
        return "", history, session, ""
    session["count"] += 1
    thread = session["thread_id"]
    waiting = agent.pending_approval(thread)
    if waiting:  # the conversation is paused until a human decides (see README limitations)
        language = agent.graph.get_state({"configurable": {"thread_id": thread}}).values.get("language", "en")
        reply = TEMPLATES[language]["waiting"].format(approval_id=waiting["approval_id"])
        trace = {"paused_for_approval": waiting}
    else:
        state = agent.chat(thread, message)
        reply = state["reply"]
        approval = state.get("approval") or {}
        if approval.get("status") == "pending":
            session["approval_threads"][approval["approval_id"]] = thread
        trace = {key: state.get(key) for key in ("language", "intent", "confidence", "sentiment", "injection",
                                                 "outcome", "tool_calls", "approval", "handover", "guard_events")}
    history += [{"role": "user", "content": message}, {"role": "assistant", "content": reply}]
    return "", history, session, json.dumps(trace, ensure_ascii=False, indent=1)


def approvals_rows() -> list[list]:
    return [[a["approval_id"], a["action"], a["order_id"], a["amount_aed"], a["level"], a["status"],
             json.dumps(a["details"], ensure_ascii=False), a["decided_by"] or ""]
            for a in reversed(store.list_approvals())]


def decide(approval_id: str, role: str, approve: bool, history: list, session: dict):
    session = session or new_session()
    if not approval_id:
        return approvals_rows(), history, session, "Choose an approval ID first."
    item = store.decide(approval_id.strip(), approve, reviewer="demo reviewer", role=role)
    if not item.get("ok"):
        return approvals_rows(), history, session, f"Not applied: {item.get('error')}"
    note = f"{approval_id}: {item['status']} by {item['decided_by']}"
    thread = session["approval_threads"].pop(approval_id, None)
    waiting = agent.pending_approval(thread) if thread else None
    if waiting and waiting["approval_id"] == approval_id:  # tell the customer in their chat
        state = agent.resume(thread, item)
        history = (history or []) + [{"role": "assistant", "content": state["reply"]}]
        note += " (customer notified in the chat tab)"
    return approvals_rows(), history, session, note


with gr.Blocks(title="Lumi Skin support agent") as demo:
    session = gr.State(new_session)
    gr.Markdown(BANNER)
    with gr.Tab("Customer chat"):
        chat = gr.Chatbot(height=420, label="Chat")
        box = gr.Textbox(placeholder="Write in Arabic, English or French...", label="Your message")
        gr.Examples(["Where is my order?", "أي سيروم تنصحني به للبشرة الدهنية؟",
                     "Je voudrais retourner ma commande, les produits ne sont pas ouverts.",
                     "Can you check my sister's order LS-10050?"], inputs=box)
        with gr.Accordion("Synthetic demo orders to try (order ID + email)", open=False):
            gr.Dataframe(demo_orders(), headers=["order_id", "email", "status", "total_aed", "language"])
        with gr.Accordion("What the agent did (last turn)", open=False):
            trace = gr.Code(language="json", label="state")
    with gr.Tab("Approvals"):
        gr.Markdown("Pending refunds and address changes. Every decision is logged to `runtime/approval_log.jsonl`.")
        table = gr.Dataframe(approvals_rows, headers=["approval_id", "action", "order_id", "amount_aed", "level",
                                                      "status", "details", "decided_by"], every=5)
        with gr.Row():
            approval_id = gr.Textbox(label="Approval ID (e.g. A-0001)")
            role = gr.Radio(["team", "supervisor"], value="team", label="Reviewer role")
        with gr.Row():
            approve_btn = gr.Button("Approve", variant="primary")
            deny_btn = gr.Button("Deny")
        status = gr.Markdown()

    box.submit(send, [box, chat, session], [box, chat, session, trace])
    approve_btn.click(lambda a, r, h, s: decide(a, r, True, h, s), [approval_id, role, chat, session],
                      [table, chat, session, status])
    deny_btn.click(lambda a, r, h, s: decide(a, r, False, h, s), [approval_id, role, chat, session],
                   [table, chat, session, status])


if __name__ == "__main__":
    demo.launch()
