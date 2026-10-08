"""Deterministic guardrails. These are plain Python checks, so a prompt cannot switch them off.

1. Verification: order details only after the order ID and email match (agent.verify).
2. Approval gating: refunds and address changes are only queued; a human decides (crm.py).
3. Refund threshold: refunds above AED 200 must be approved by a supervisor (crm.approval_level).
4. Output check: a reply may not contain another customer's email, phone, name, address, order ID or
   tracking ID, in any spelling (spaces, +971/0 prefix, Arabic-Indic digits, "at"/"dot", name order).
5. AI disclosure: the first reply always starts with a fixed "I am an AI assistant" line.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from .config import REFUND_ESCALATION_AED
from .data import ShopData
from .parsing import normalise_digits
from .rules import TEMPLATES

NEEDS_VERIFICATION = {"order_status", "return_refund", "address_change"}

# ---- Leak filter helpers. The same value can be written in many ways, so we compare normalised forms. ----
SEP = r"[\W_]*"  # spaces, dots, dashes, commas... or nothing, between the parts of a name or an address
NUMBER_RUN_RE = re.compile(r"\+?\d[\d\s\-.()/]*\d")  # "+971 50 000 4119", "050-000-4119", "(050) 0004119"
AT_WORDS_RE = re.compile(r"\s*(?:[(\[{]\s*at\s*[)\]}]|\bat\b|\barobase\b|@)\s*")  # "[at]", " at ", "arobase"
DOT_WORDS_RE = re.compile(r"[(\[{]\s*dot\s*[)\]}]|\bdot\b|\bpoint\b|نقطة")  # "(dot)", " dot ", "point"
ID_RE = re.compile(r"(?<![a-z0-9])(ls|trk)[\s\-_]?(\d{7}|\d{5})(?!\d)")  # "ls 10045", "trk-7844947"
BUILDING_WORDS = "building|bldg|batiment|immeuble|مبنى|بناية|عمارة"
STREET_WORDS = "street|st|rue|شارع"
NEVER = re.compile(r"(?!x)x")  # a pattern that matches nothing


def disclosure(language: str) -> str:
    return TEMPLATES.get(language, TEMPLATES["en"])["disclosure"]


def normalise(text: str) -> str:
    """Lower case, no accents or invisible characters, Arabic-Indic digits as 0-9 ("Élodie" -> "elodie")."""
    decomposed = unicodedata.normalize("NFKD", text)  # also turns full-width "０５０" into "050"
    kept = "".join(ch for ch in decomposed if unicodedata.category(ch) not in ("Mn", "Cf"))  # accents, zero-width
    return normalise_digits(kept).lower()


def phone_key(phone: str) -> str:
    """The digits that identify a UAE mobile number: "+971 50 000 4119" and "050 000 4119" -> "500004119"."""
    digits = re.sub(r"\D", "", normalise_digits(phone))
    for prefix in ("00971", "971", "0"):
        if digits.startswith(prefix):
            return digits[len(prefix):]
    return digits


def number_runs(text: str) -> list[str]:
    """Each group of digits with its spaces/dashes/brackets removed: "call 050-000 4119" -> ["0500004119"]."""
    return [re.sub(r"\D", "", run) for run in NUMBER_RUN_RE.findall(text)]


def email_text(text: str) -> str:
    """Undo e-mail disguises, keep only letters, digits and "@": "a dot b [at] example.com" -> "ab@examplecom"."""
    text = DOT_WORDS_RE.sub("", AT_WORDS_RE.sub("@", text))
    return re.sub(r"[^a-z0-9@]", "", text)


def email_key(email: str) -> str:
    local, _, domain = normalise(email).partition("@")
    return re.sub(r"[^a-z0-9]", "", local) + "@" + re.sub(r"[^a-z0-9]", "", domain)


def words_pattern(words: list[str]) -> str:
    return r"(?<![a-z0-9])" + SEP.join(re.escape(word) for word in words) + r"(?![a-z0-9])"


@lru_cache(maxsize=512)
def name_regex(name: str) -> re.Pattern:
    """Full name in either order, any case, accents or separators: "Emily Mitchell", "MITCHELL, Emily",
    "emily.mitchell", "EmilyMitchell". A first name alone is not flagged (many customers share one)."""
    words = re.findall(r"[a-z0-9]+", normalise(name))
    if not words:
        return NEVER
    return re.compile(words_pattern(words) + "|" + words_pattern(words[1:] + words[:1]))


@lru_cache(maxsize=512)
def address_regex(address: str) -> re.Pattern:
    """Building + street number in English, French or Arabic words: "Building 16, Street 37" also matches
    "bldg 16 st 37", "Immeuble 16, rue 37" and "مبنى ١٦، شارع ٣٧". Other address formats: exact text only."""
    numbers = re.findall(r"\d+", normalise(address))
    if len(numbers) < 2:
        return re.compile(re.escape(normalise(address)))
    building, street = numbers[:2]
    building_words, street_words = normalise(BUILDING_WORDS), normalise(STREET_WORDS)
    return re.compile(rf"(?:{building_words}){SEP}{building}{SEP}(?:{street_words}){SEP}{street}(?!\d)")


def mentioned_ids(text: str) -> set[str]:
    """Order and tracking IDs in any spacing or case: "ls 10045" -> "LS-10045", "trk 7844947" -> "TRK7844947"."""
    return {f"LS-{number}" if prefix == "ls" else f"TRK{number}" for prefix, number in ID_RE.findall(text)}


def text_forms(text: str) -> dict:
    """The normalised views of a text that the leak checks compare against."""
    normal = normalise(text)
    return {"text": normal, "numbers": number_runs(normal), "emails": email_text(normal)}


def contains(forms: dict, field: str, customer: dict) -> bool:
    """Does this text mention the customer's phone / email / name / address, in any spelling?"""
    if field == "phone":
        return any(phone_key(customer["phone"]) in run for run in forms["numbers"])
    if field == "email":
        return email_key(customer["email"]) in forms["emails"]
    if field == "name":
        return bool(name_regex(customer["name"]).search(forms["text"]))
    return bool(address_regex(customer["address"]).search(forms["text"]))


def find_leaks(reply: str, shop: ShopData, allowed_customer_id: str | None, public_text: str) -> list[str]:
    """Return other customers' data found in the reply (the stored value, one entry per field).

    public_text = what the customer typed + the policy/FAQ text shown to the model.
    Repeating something from there is not a leak (e.g. the order ID the customer gave
    us, or the example ID "LS-10001" in the FAQ). Data from anywhere else is a leak.

    Both texts are normalised first, so a value still counts when it is written differently:
    phone numbers by their digits (spaces, +971 or 0 prefix, Arabic-Indic digits), e-mails with
    "at"/"dot" disguises, full names in any order/case/accents, order and tracking IDs in any spacing.
    """
    said, public = text_forms(reply), text_forms(public_text)
    leaks = []
    for customer in shop.customers.values():
        if customer["id"] == allowed_customer_id:
            continue
        for field in ("phone", "email", "name", "address"):
            if contains(said, field, customer) and not contains(public, field, customer):
                leaks.append(customer[field])

    owner = {order_id: order["customer_id"] for order_id, order in shop.orders.items()}
    owner.update({order["tracking_id"]: order["customer_id"] for order in shop.orders.values() if order["tracking_id"]})
    for found in sorted(mentioned_ids(said["text"]) - mentioned_ids(public["text"])):
        if found in owner and owner[found] != allowed_customer_id:
            leaks.append(found)
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
