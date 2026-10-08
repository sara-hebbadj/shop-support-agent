"""Small deterministic text helpers: language, order IDs, emails, safe prompt data.

These run without any model, so they are cheap, testable and cannot be talked
out of their job by a clever message.
"""

from __future__ import annotations

import re

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
ORDER_ID_RE = re.compile(r"\bLS[\s\-_]?(\d{5})\b", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
ARABIC_LETTER_RE = re.compile(r"[؀-ۿ]")
LATIN_LETTER_RE = re.compile(r"[A-Za-zÀ-ÿ]")
WORD_RE = re.compile(r"[a-zà-ÿœ']+")

FRENCH_WORDS = {
    "bonjour", "merci", "je", "j'ai", "mon", "ma", "mes", "est", "où", "commande", "livraison",
    "remboursement", "colis", "vous", "pour", "avec", "pas", "une", "des", "du", "le", "la", "les",
    "peau", "adresse", "retour", "suis", "voudrais", "pouvez", "quel", "quelle", "et", "c'est",
    "s'il", "plaît", "svp", "salut", "bonsoir", "aide", "personne", "conseiller", "il", "elle",
}
ENGLISH_WORDS = {
    "hello", "hi", "the", "my", "is", "where", "order", "please", "i", "you", "can", "refund",
    "what", "skin", "address", "return", "want", "with", "and", "for", "it", "this", "thanks",
    "how", "your", "need", "to", "of", "a", "an", "me", "help", "person", "human", "change",
}


def normalise_digits(text: str) -> str:
    """Turn Arabic-Indic digits (١٢٣) into 123 so order IDs typed in Arabic still match."""
    return text.translate(ARABIC_DIGITS)


def detect_language(text: str, previous: str | None = None) -> str:
    """Return 'ar', 'fr' or 'en'. Keeps the previous language when the message has no clues."""
    arabic = len(ARABIC_LETTER_RE.findall(text))
    latin = len(LATIN_LETTER_RE.findall(text))
    if arabic and arabic >= latin * 0.3:
        return "ar"
    words = WORD_RE.findall(text.lower())
    french = sum(w in FRENCH_WORDS for w in words) + sum(ch in "éèêàçùâîôûëïœ" for ch in text.lower())
    english = sum(w in ENGLISH_WORDS for w in words)
    if french == english == 0:
        return previous or "en"
    if french > english:
        return "fr"
    if english > french:
        return "en"
    return previous or "en"


def extract_order_id(text: str) -> str | None:
    match = ORDER_ID_RE.search(normalise_digits(text))
    return f"LS-{match.group(1)}" if match else None


def extract_email(text: str) -> str | None:
    match = EMAIL_RE.search(normalise_digits(text))
    return match.group(0).rstrip(".").lower() if match else None


def as_prompt_data(text: str, limit: int = 2000) -> str:
    """Make untrusted text safe to place inside <data> tags in a prompt.

    Angle brackets are replaced so a message cannot close the tag and pretend to be
    a system instruction. The rules that matter (verification, approval, refund
    limits) are enforced in code anyway, so this is a second layer, not the only one.
    """
    cleaned = text.replace("<", "‹").replace(">", "›")
    return cleaned[:limit]
