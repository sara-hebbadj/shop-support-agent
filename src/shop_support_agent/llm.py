"""The only module that talks to a language model.

- OpenRouterClient: real calls through the OpenAI-compatible SDK (OpenRouter).
- FakeLLM: a deterministic stand-in for tests, --dry-run and the offline demo.
  It is NOT a model: it uses keyword rules and templates (rules.py).

Every call is written to a traces file (JSON lines) with model, tokens, cost,
latency and outcome, so cost per conversation can be reported.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import rules
from .config import EVALS_DIR, env, model_id


class LLMNotConfigured(RuntimeError):
    """Raised when OPENROUTER_API_KEY or a model ID is missing."""


@dataclass
class LLMResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    finish_reason: str = ""


@dataclass
class Tracer:
    """Appends one JSON line per model call and keeps running totals per conversation."""

    path: Path = field(default_factory=lambda: Path(env("TRACES_PATH") or EVALS_DIR / "traces.jsonl"))
    context: dict = field(default_factory=dict)  # e.g. {"run_id": ..., "conversation_id": ...}
    totals: dict = field(default_factory=dict)  # conversation_id -> {"cost_usd", "tokens", "calls"}

    def log(self, purpose: str, result: LLMResult | None, outcome: str, model: str = "") -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            **self.context,
            "purpose": purpose,
            "model": result.model if result else model,
            "prompt_tokens": result.prompt_tokens if result else 0,
            "completion_tokens": result.completion_tokens if result else 0,
            "cost_usd": result.cost_usd if result else 0.0,
            "latency_ms": result.latency_ms if result else 0,
            "outcome": outcome,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        key = self.context.get("conversation_id", "-")
        total = self.totals.setdefault(key, {"cost_usd": 0.0, "tokens": 0, "calls": 0})
        total["cost_usd"] += record["cost_usd"]
        total["tokens"] += record["prompt_tokens"] + record["completion_tokens"]
        total["calls"] += 1

    def total_cost(self) -> float:
        return sum(t["cost_usd"] for t in self.totals.values())


class OpenRouterClient:
    def __init__(self, tracer: Tracer | None = None, role_override: str | None = None):
        from openai import OpenAI  # imported here so tests never need network setup

        key = env("OPENROUTER_API_KEY")
        if not key:
            raise LLMNotConfigured("OPENROUTER_API_KEY is not set (see .env.example)")
        self.client = OpenAI(api_key=key, base_url=env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
        self.tracer = tracer or Tracer()
        self.role_override = role_override  # e.g. "cheap" to run the whole agent on MODEL_CHEAP
        self.offline = False

    def complete(self, messages: list[dict], role: str = "main", purpose: str = "",
                 json_mode: bool = False, max_tokens: int = 500, temperature: float = 0.0) -> LLMResult:
        role = self.role_override if (self.role_override and role != "judge") else role
        model = model_id(role)
        if not model:
            raise LLMNotConfigured(f"MODEL_{role.upper()} is not set")
        extra_body = {"usage": {"include": True}}  # OpenRouter returns the cost in usage
        # Reasoning models (e.g. the judge) spend max_tokens on hidden "thinking" before the answer; in the
        # first live run that cut the judge's JSON off mid-way. Short tasks here need little reasoning.
        effort = env("REASONING_EFFORT", "low")
        if effort != "default":
            extra_body["reasoning"] = {"effort": effort}
        kwargs = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                  "extra_body": extra_body}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        start = time.perf_counter()
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as error:  # log failed calls too, then let the caller decide
            self.tracer.log(purpose, None, f"error: {type(error).__name__}", model)
            raise
        usage = response.usage
        extra = getattr(usage, "model_extra", None) or {}
        result = LLMResult(
            text=response.choices[0].message.content or "",
            model=response.model or model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cost_usd=float(extra.get("cost") or getattr(usage, "cost", 0) or 0),
            latency_ms=int((time.perf_counter() - start) * 1000),
            finish_reason=response.choices[0].finish_reason or "",
        )
        # "length" means the answer was cut off at max_tokens: say so in the trace instead of hiding it.
        self.tracer.log(purpose, result, "truncated" if result.finish_reason == "length" else "ok")
        return result


DATA_TAG_RE = re.compile(r"<customer_message>(.*?)</customer_message>", re.DOTALL)
FACTS_RE = re.compile(r"<facts>(.*?)</facts>", re.DOTALL)


class FakeLLM:
    """Deterministic offline stand-in. Outputs are labelled as fake in traces (model='fake-offline')."""

    def __init__(self, tracer: Tracer | None = None):
        self.tracer = tracer or Tracer()
        self.offline = True

    def complete(self, messages: list[dict], role: str = "main", purpose: str = "",
                 json_mode: bool = False, max_tokens: int = 500, temperature: float = 0.0) -> LLMResult:
        prompt = "\n".join(m["content"] for m in messages)
        user_part = messages[-1]["content"]  # the tagged data lives in the last (user) message
        if purpose == "intent":
            text = json.dumps(self._intent(user_part), ensure_ascii=False)
        elif purpose == "reply":
            facts = json.loads(FACTS_RE.search(user_part).group(1))
            text = rules.render_reply(facts["outcome"], facts["language"], facts)
        elif purpose == "judge":
            text = json.dumps({"tone": 3, "helpfulness": 3, "language_ok": True, "reason": "fake judge"})
        elif purpose == "plain":
            found = DATA_TAG_RE.findall(user_part)
            message = found[-1] if found else ""
            text = json.dumps({"reply": "(offline placeholder reply)", "outcome": "clarify",
                               "approval": "none", "handover": rules.classify(message) == "handover"})
        else:
            text = "(offline placeholder)"
        result = LLMResult(text=text, model="fake-offline", prompt_tokens=len(prompt) // 4,
                           completion_tokens=len(text) // 4)
        self.tracer.log(purpose, result, "ok")
        return result

    @staticmethod
    def _intent(user_part: str) -> dict:
        found = DATA_TAG_RE.findall(user_part)
        message = found[-1] if found else ""
        intent = rules.classify(message)
        return {
            "intent": intent,
            "confidence": 0.8,
            "sentiment": "angry" if rules.is_angry(message) else "calm",
            "wants_human": intent == "handover",
            "new_address": rules.find_new_address(message),
            "skin_type": rules.find_first(message, rules.SKIN_WORDS),
            "category": rules.find_first(message, rules.CATEGORY_WORDS),
            "return_reason": rules.find_reason(message),
            "injection_attempt": rules.looks_like_injection(message),
        }


def make_client(offline: bool | None = None, tracer: Tracer | None = None, role_override: str | None = None):
    """Real client when a key exists (or offline=False), otherwise the FakeLLM."""
    if offline is None:
        offline = not env("OPENROUTER_API_KEY")
    return FakeLLM(tracer) if offline else OpenRouterClient(tracer, role_override)


def parse_json(text: str) -> dict:
    """Parse a JSON object even if the model wrapped it in ```json fences or added words around it."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in model output")
    return json.loads(match.group(0))
