# LEARN: explain and change this project in an interview

## 10-minute walkthrough script

1. **The problem (1 min).** "A skincare shop answers order, return and address questions in Arabic, English
   and French. An AI can handle the conversation, but money and personal data need rules a prompt cannot
   break. I built an agent where the model talks and plain code decides."
2. **Demo (2 min).** `python app/app.py`. Ask "Where is my order?" → it asks for order ID + email. Paste a
   demo order from the accordion → status and courier update. In French, ask for a refund of an unopened
   order above AED 200 → "a supervisor will review". Open **Approvals**, try to approve as "team" → refused;
   approve as "supervisor" → the customer gets the update in the chat. Finally ask for someone else's order
   → blocked.
3. **Graph (2 min).** Open `agent.py`, `_build()`. Walk the nodes: understand → verify → retrieve → act →
   check → respond → wait_for_approval. Point out that the routing functions are tiny `if` statements.
4. **Guardrails (2 min).** `verify()` (ID + email), `crm.approval_level()` (AED 200), `CrmStore.decide()`
   (only humans, idempotent), `guards.find_leaks()` (output filter), the fixed AI disclosure line.
5. **MCP and the courier API (1 min).** `crm_server.py`: five tools with docstrings; the agent calls them
   through a real MCP client. `courier_api.py`: two GET endpoints, a client with retries.
6. **Evaluation (2 min).** `evals/conversations.jsonl` (120, 3 languages, 8 categories), `scoring.py`
   (task success, tool use, approval/handover, violations), the rules baseline numbers in the README, and
   the hand-grading sheet that checks the LLM judge.

## 10 interview questions with short answers

1. **Why an agent and not a fixed workflow?** Customers phrase things in endless ways and three languages;
   keyword rules missed paraphrases (the rules baseline scored 63.3% task success on my 120 conversations).
   The model handles understanding and wording. But tool choice, identity checks and approvals stay as
   fixed code, so it is "an agent inside guardrails".
2. **Where did you keep rules deterministic?** Language detection, order-ID/email extraction, verification,
   the return policy check (14 days, unopened), approval levels (AED 200), the leak filter and the AI
   disclosure. Anything with money, privacy or a legal duty.
3. **How do you stop leaking another customer's data?** Order details only after the order ID and the email
   on that order match (`verify`). A verified customer asking about another order is checked again. The
   courier API never returns emails or phones. Finally `find_leaks` scans every reply for other customers'
   emails, phones, names, addresses and order IDs and replaces the reply if it finds one.
4. **How do you handle prompt injection?** Customer text and retrieved text are wrapped in tags as data;
   angle brackets are neutralised so a message cannot close the tag. More importantly, the model cannot
   approve anything: approvals live in `CrmStore.decide()`, which only the Approvals tab calls. Tests use a
   deliberately "obedient" fake model to prove a refund still waits for a human.
5. **How does human approval work in LangGraph?** `act` queues the request through the MCP tool. After the
   reply, `wait_for_approval` calls `interrupt()`, which saves state and pauses the thread. When a reviewer
   decides, the app calls `decide()` and then `graph.invoke(Command(resume=item))`, and the agent tells the
   customer the result.
6. **What happens if a retry repeats an approved action?** Nothing extra: the queue refuses a duplicate
   pending request for the same order, and `decide()` returns early if an item is already decided. The
   interrupted node has no side effects before `interrupt()`, because LangGraph re-runs it on resume.
7. **What does a conversation cost, and how would you cut it?** Two model calls per turn (intent on
   `MODEL_CHEAP`, reply on `MODEL_MAIN`); every call is logged with tokens and OpenRouter's cost in
   `traces.jsonl`. Live numbers are pending. To cut cost: cheap model for both calls on simple intents,
   template replies for fixed outcomes like "please verify", and caching policy text.
8. **How did you evaluate it?** 120 scripted conversations with expected outcome, tools and decision;
   metrics per language; two baselines (keyword rules, plain LLM without tools); an LLM judge for tone from
   a different model family; and 20 conversations I grade by hand to measure agreement with the judge.
9. **Show one failure and the fix.** The output leak filter blocked the agent's own "e.g. LS-10001" example
   because that ID belongs to a synthetic customer. I changed the filter so text from the policies or typed
   by the customer counts as public. (Replace with a failure from the live run once it exists.)
10. **What changes before connecting a real CRM such as Zoho?** OAuth and least-privilege API scopes, a real
    database and audit log instead of JSON files, PII redaction in traces, rate limits and retries with
    idempotency keys on the CRM side, a DPA and data-residency review (UAE PDPL), and a pilot with human
    review of every reply before full automation.

## 3 "change it live" exercises

1. **Change the refund threshold to AED 300.** Edit `REFUND_ESCALATION_AED` in `config.py`. Run
   `pytest tests/test_approvals.py` and fix `test_refund_threshold_is_strictly_above_200` to the new value.
   Show that a AED 250 refund is now approved by a team member.
2. **Add a new MCP tool `get_ticket_status(ticket_id)`.** Add a method to `CrmStore` that finds the ticket,
   expose it in `build_server()` with `@server.tool()` and a docstring, and update
   `test_server_lists_the_five_crm_tools`. Call it from MCP Inspector.
3. **Make angry customers wait for one helpful answer before handover.** In `route_after_check`, hand over
   only if the outcome is not `status_shared`. Re-run `python -m evals.run --system agent --dry-run` and
   show how the angry-customer category changes, then explain the trade-off.
