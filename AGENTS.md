# Notes for coding agents working on this repo

Project P1 of Sara Hebbadj's portfolio: a supervised customer-service agent for the fictional shop
"Lumi Skin". Sara must be able to explain every line, so keep functions short and names plain.

## Layout

- `src/shop_support_agent/agent.py`: the LangGraph graph. Nodes are methods; routing is in `route_after_*`.
- `guards.py` + `crm.py`: the deterministic rules (verification, approval levels, leak filter, disclosure).
  **Never move these rules into a prompt.**
- `crm_server.py`: MCP server (`mcp` v2 `MCPServer`, formerly FastMCP) and `CrmMcpClient` (in-process MCP).
- `courier_api.py`: FastAPI mock + `CourierClient` (in-process via TestClient unless `COURIER_API_URL` is set).
- `llm.py`: the only place that calls a model. `FakeLLM` is for tests/dry runs/offline demo.
- `rules.py`: keyword lists and reply templates in AR/EN/FR (used by the rules baseline and `FakeLLM`).
- `evals/`: `make_conversations.py` (writes the 120 conversations), `run.py`, `scoring.py`, `judge.py`.
- `data/`: synthetic Lumi Skin data; regenerate with `python data/generate.py --out <dir>` (seed 42).

## Rules

- Tests never touch the network (a fixture blocks sockets) and never need keys. Use `FakeLLM` or a small
  fake class with a `complete()` method.
- Do not edit `evals/conversations.jsonl` by hand; change `evals/make_conversations.py` and re-run it.
  Changing the test set invalidates earlier results: say so in RESULTS.md.
- Real results go in `evals/results/`, fake ones in `evals/dry_run/`. Never copy a dry-run number into the
  README or RESULTS.md.
- Side effects must stay before `interrupt()` nodes (in `act`) or inside `CrmStore.decide()`, which is
  idempotent. LangGraph re-runs the interrupted node from the start on resume.
- Keys come from `Portfolio Projects/.env` or environment variables. Never print or commit them.
- Ask Sara before creating a GitHub repo, pushing, or deploying a Space.

## Checks before you finish

```bash
pytest -q
ruff check .
python -m evals.run --system agent --dry-run   # pipeline still works end to end
```
