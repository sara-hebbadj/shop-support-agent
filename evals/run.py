"""Run the 120-conversation evaluation for the agent or a baseline.

Examples:
  python -m evals.run --system rules                       # keyword baseline, no LLM, real results
  python -m evals.run --system agent --model cheap --limit 10
  python -m evals.run --system agent --model main --judge  # full run + LLM judge for tone
  python -m evals.run --system plain --model main          # plain LLM, no tools
  python -m evals.run --system agent --dry-run             # FAKE model: proves the pipeline, NOT real results

Real runs write to evals/results/, dry runs to evals/dry_run/. Each run writes:
  <name>.jsonl          one record per conversation (replies, tools, outcome, score)
  <name>_summary.csv    metrics per language + all
  traces.jsonl          one line per model call (model, tokens, cost, latency)
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import time
from datetime import date
from pathlib import Path

from shop_support_agent.agent import SupportAgent
from shop_support_agent.baselines import PlainLLMBot, RulesBot
from shop_support_agent.config import EVALS_DIR, env
from shop_support_agent.crm import CrmStore
from shop_support_agent.crm_server import CrmMcpClient, build_server
from shop_support_agent.data import load_shop_data
from shop_support_agent.llm import FakeLLM, OpenRouterClient, Tracer

from .judge import judge_conversation
from .scoring import by_category, public_text, score, summarise

CONVERSATIONS = EVALS_DIR / "conversations.jsonl"


def load_conversations(path: Path = CONVERSATIONS) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def interleave(conversations: list[dict]) -> list[dict]:
    """Order as ar, en, fr, ar, en, fr... so --limit 10 still covers all three languages."""
    by_lang = {lang: [c for c in conversations if c["language"] == lang] for lang in ("ar", "en", "fr")}
    longest = max(len(v) for v in by_lang.values())
    return [by_lang[lang][i] for i in range(longest) for lang in ("ar", "en", "fr") if i < len(by_lang[lang])]


def run_agent(agent: SupportAgent, conv: dict) -> dict:
    start = time.perf_counter()
    state = {}
    for turn in conv["turns"]:
        state = agent.chat(conv["id"], turn)
    approval = state.get("approval") or {}
    return {
        "replies": [m["content"] for m in state["messages"] if m["role"] == "assistant"],
        "outcome": state.get("outcome"),
        "tool_calls": state.get("tool_calls", []),
        "approval": approval.get("level", "none") if approval.get("status") == "pending" else "none",
        "handover": bool(state.get("handover")),
        "guard_events": state.get("guard_events", []),
        "latency_ms": int((time.perf_counter() - start) * 1000),
    }


def build_system(name: str, llm, crm: CrmMcpClient):
    if name == "agent":
        agent = SupportAgent(llm=llm, crm=crm)
        return lambda conv: run_agent(agent, conv)
    if name == "rules":
        bot = RulesBot(crm=crm)
        return lambda conv: bot.run(conv["turns"])
    bot = PlainLLMBot(llm)
    return lambda conv: bot.run(conv["turns"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the support agent or a baseline")
    parser.add_argument("--system", choices=["agent", "rules", "plain"], default="agent")
    parser.add_argument("--model", choices=["main", "cheap"], default="cheap",
                        help="'cheap' runs every agent call on MODEL_CHEAP; 'main' uses MODEL_MAIN for replies")
    parser.add_argument("--limit", type=int, default=0, help="only the first N conversations (mixed languages)")
    parser.add_argument("--lang", choices=["ar", "en", "fr"])
    parser.add_argument("--judge", action="store_true", help="score tone/helpfulness with MODEL_JUDGE")
    parser.add_argument("--dry-run", action="store_true", help="use the FAKE model (not real results)")
    args = parser.parse_args()

    out_dir = EVALS_DIR / ("dry_run" if args.dry_run else "results")
    out_dir.mkdir(parents=True, exist_ok=True)
    model_label = "none" if args.system == "rules" else ("fake" if args.dry_run else args.model)
    subset = (f"_{args.lang}" if args.lang else "") + (f"_first{args.limit}" if args.limit else "")
    run_id = f"{args.system}_{model_label}{subset}_{date.today().isoformat()}"
    tracer = Tracer(path=out_dir / "traces.jsonl", context={"run_id": run_id})

    # Fresh CRM per run, reset before every conversation, so results do not depend on order.
    runtime = out_dir / f"runtime_{run_id}"
    store = CrmStore(runtime)
    crm = CrmMcpClient(build_server(store))

    llm = None
    if args.system != "rules":
        llm = FakeLLM(tracer) if args.dry_run else \
            OpenRouterClient(tracer, role_override="cheap" if args.model == "cheap" else None)
    run_one = build_system(args.system, llm, crm)

    conversations = interleave(load_conversations())
    if args.lang:
        conversations = [c for c in conversations if c["language"] == args.lang]
    if args.limit:
        conversations = conversations[: args.limit]

    shop, public = load_shop_data(), public_text()
    budget = float(env("MAX_COST_PER_RUN_USD", "3"))
    records = []
    for number, conv in enumerate(conversations, 1):
        store.reset()
        tracer.context["conversation_id"] = conv["id"]
        try:
            result = run_one(conv)
            error = None
        except Exception as exc:  # keep going; the error is counted in the summary
            result = {"replies": [], "outcome": "error", "tool_calls": [], "approval": "none",
                      "handover": False, "latency_ms": 0}
            error = f"{type(exc).__name__}: {exc}"[:300]
        totals = tracer.totals.get(conv["id"], {})
        record = {"id": conv["id"], "language": conv["language"], "category": conv["category"],
                  "system": args.system, "model": model_label, **result, "error": error,
                  "cost_usd": round(totals.get("cost_usd", 0.0), 6), "tokens": totals.get("tokens", 0),
                  "expected": conv["expected"]}
        record["score"] = score(conv, result, shop, store._load(), public)
        if args.judge and llm and result["replies"]:
            record["judge"] = judge_conversation(llm, conv, result["replies"])
        records.append(record)
        mark = "ok " if record["score"]["task_success"] else "BAD"
        print(f"[{number}/{len(conversations)}] {mark} {conv['id']}: {result['outcome']}")
        if tracer.total_cost() > budget:
            print(f"Stopping: cost {tracer.total_cost():.2f} USD passed MAX_COST_PER_RUN_USD={budget}")
            break

    fallbacks = sum(any("fallback" in e for e in r.get("guard_events", [])) for r in records)
    if fallbacks:
        print(f"WARNING: {fallbacks} conversations used the keyword fallback because a model call failed.")
    write_outputs(out_dir, run_id, records, args)
    shutil.rmtree(runtime, ignore_errors=True)


def write_outputs(out_dir: Path, run_id: str, records: list[dict], args) -> None:
    with (out_dir / f"{run_id}.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    rows = summarise(records)
    with (out_dir / f"{run_id}_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    with (out_dir / f"{run_id}_by_category.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["category", "n", "task_success_pct"])
        writer.writeheader()
        writer.writerows(by_category(records))

    header = "DRY RUN (fake model, NOT real results)" if args.dry_run else "Results"
    print(f"\n{header}: {run_id}")
    print("lang  n    task%  tools%  decision%  viol_convs  avg_cost_usd  avg_latency_ms")
    for row in rows:
        print(f"{row['language']:<5} {row['n']:<4} {row['task_success_pct']:<6} {row['tool_use_correct_pct']:<7} "
              f"{row['decision_correct_pct']:<10} {row['conversations_with_violations']:<11} "
              f"{row['avg_cost_usd']:<13} {row['avg_latency_ms']}")
    print(f"Saved: {out_dir / (run_id + '.jsonl')}")


if __name__ == "__main__":
    main()
