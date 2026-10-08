"""Settings, file paths and business constants in one place.

Keys are read from `Portfolio Projects/.env` (two folders above this repo) when it
exists, otherwise from normal environment variables. Keys are never printed.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
EVALS_DIR = REPO_ROOT / "evals"

# Load the shared .env first (Portfolio Projects/.env), then a local repo .env if present.
# override=False means real environment variables (e.g. Hugging Face Space secrets) win.
load_dotenv(REPO_ROOT.parent.parent / ".env", override=False)
load_dotenv(REPO_ROOT / ".env", override=False)

# ---- Business rules (deterministic, never left to the model) ----
REFUND_ESCALATION_AED = 200  # refunds above this always go to a supervisor
RETURN_WINDOW_DAYS = 14
MAX_VERIFY_ATTEMPTS = 3  # failed order-ID/email checks before a human takes over
LOW_CONFIDENCE = 0.5  # intent confidence below this -> hand over to a human
SHOP_TODAY = "2026-10-08"  # the synthetic data's "today", so return windows are stable


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def runtime_dir() -> Path:
    """Folder for mutable demo state (CRM notes, tickets, approvals). Not committed."""
    path = Path(env("SHOP_RUNTIME_DIR") or (REPO_ROOT / "runtime"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_id(role: str) -> str:
    """role is 'main', 'cheap' or 'judge' -> the model ID from MODEL_MAIN / MODEL_CHEAP / MODEL_JUDGE."""
    return env(f"MODEL_{role.upper()}")


def demo_message_limit() -> int:
    return int(env("DEMO_MESSAGE_LIMIT", "20"))
