"""Compare saved runs side by side, per language, optionally on the same conversation IDs.

Reads the .jsonl files written by evals.run (nothing is re-run, no model is called) and writes one CSV.

  python -m evals.compare --out evals/results/comparison_2026-10-08.csv \
      evals/results/rules_none_2026-10-08.jsonl evals/results/agent_cheap_2026-10-08.jsonl ...
  # same 30 conversations as the MODEL_MAIN run, for a fair cheap-vs-main comparison:
  python -m evals.compare --ids-from evals/results/agent_main_10perlang_2026-10-08.jsonl --out ... <runs>
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from .scoring import summarise


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def violation_types(records: list[dict]) -> str:
    """e.g. "missing_ai_disclosure: 40; claimed_action_without_system: 3" (counted per conversation)."""
    counts = Counter(v for r in records for v in set(r["score"]["violations"]))
    return "; ".join(f"{name}: {n}" for name, n in counts.most_common()) or "none"


def compare(paths: list[Path], ids: set[str] | None = None) -> list[dict]:
    rows = []
    for path in paths:
        records = [r for r in load(path) if ids is None or r["id"] in ids]
        for row in summarise(records):
            group = records if row["language"] == "all" else [r for r in records if r["language"] == row["language"]]
            rows.append({"run": path.stem, **row,
                         "outcome_ok_n": sum(r["score"]["outcome_ok"] for r in group),  # ignoring violations
                         "task_success_n": sum(r["score"]["task_success"] for r in group),
                         "tool_use_correct_n": sum(r["score"]["tool_use_correct"] for r in group),
                         "decision_correct_n": sum(r["score"]["decision_correct"] for r in group),
                         "violation_types": violation_types(group)})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Side-by-side table of saved evaluation runs")
    parser.add_argument("runs", nargs="+", type=Path, help="results .jsonl files from evals.run")
    parser.add_argument("--ids-from", type=Path, help="only the conversation IDs present in this run")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    ids = {r["id"] for r in load(args.ids_from)} if args.ids_from else None
    rows = compare(args.runs, ids)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(f"{row['run']:<34} {row['language']:<4} n={row['n']:<4} outcome={row['outcome_ok_n']} "
              f"task={row['task_success_n']} "
              f"tools={row['tool_use_correct_n']} decision={row['decision_correct_n']} "
              f"viol_convs={row['conversations_with_violations']} cost={row['avg_cost_usd']} "
              f"ms={row['avg_latency_ms']} tone={row['avg_judge_tone']} help={row['avg_judge_helpfulness']}")
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
