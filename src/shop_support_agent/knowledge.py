"""Policy and FAQ retrieval.

The three policy files share the same numbered sections (## 1. ... ## 9.), so one
topic map works for Arabic, English and French. Retrieval is keyword based: with
9 sections and 30 FAQs, a vector database would add cost without adding accuracy.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .config import DATA_DIR

# Which policy sections answer which intent.
INTENT_SECTIONS = {
    "order_status": [2],
    "product_advice": [8],
    "return_refund": [5, 6],
    "address_change": [4],
    "handover": [1, 9],
    "complaint": [9],
    "other_person_order": [7],
}

# Topic words in the three languages -> policy section number.
TOPIC_WORDS = {
    2: ["deliver", "shipping", "ship", "courier", "livraison", "livr", "expédi", "توصيل", "شحن", "يوصل"],
    3: ["cash", "cod", "pay", "paiement", "espèces", "الدفع", "كاش", "نقد"],
    4: ["cancel", "change", "annul", "modifier", "إلغاء", "تغيير", "تعديل"],
    5: ["return", "retour", "retourner", "إرجاع", "ارجاع", "رجع"],
    6: ["refund", "money back", "rembours", "استرداد", "استرجاع", "فلوس"],
    7: ["privacy", "data", "données", "confidential", "خصوصية", "بيانات"],
    8: ["pregnan", "enceinte", "حامل", "medical", "médical", "طبي"],
    1: ["hours", "human", "real person", "horaires", "robot", "chatbot", "ساعات", "ذكاء"],
}

FAQ_HEADING_RE = re.compile(r"^### (\d+)\. (.+)$", re.MULTILINE)
SECTION_RE = re.compile(r"^## (\d+)\. ", re.MULTILINE)


@lru_cache(maxsize=8)
def policy_sections(language: str, data_dir: str = str(DATA_DIR)) -> dict[int, str]:
    text = (Path(data_dir) / f"policies_{language}.md").read_text(encoding="utf-8")
    parts = SECTION_RE.split(text)  # [preamble, "1", body, "2", body, ...]
    return {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts), 2)}


@lru_cache(maxsize=2)
def faq_entries(data_dir: str = str(DATA_DIR)) -> list[dict]:
    text = (Path(data_dir) / "faq.md").read_text(encoding="utf-8")
    matches = list(FAQ_HEADING_RE.finditer(text))
    entries = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        entries.append({"number": int(match.group(1)), "question": match.group(2),
                        "answer": text[match.end():end].strip()})
    return entries


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) > 2}


def topic_sections(text: str) -> list[int]:
    lowered = text.lower()
    return [section for section, words in TOPIC_WORDS.items() if any(w in lowered for w in words)]


def retrieve(intent: str, language: str, message: str, max_faq: int = 2) -> list[dict]:
    """Return policy sections (in the customer's language) and the closest English FAQs."""
    sections = list(INTENT_SECTIONS.get(intent, []))
    for section in topic_sections(message):
        if section not in sections:
            sections.append(section)
    lang = language if language in ("ar", "en", "fr") else "en"
    texts = policy_sections(lang)
    results = [{"source": f"policies_{lang}.md#{n}", "text": texts[n]} for n in sections[:3] if n in texts]

    query = _words(message)
    scored = []
    for entry in faq_entries():
        overlap = len(query & _words(entry["question"] + " " + entry["answer"]))
        if overlap:
            scored.append((overlap, entry))
    scored.sort(key=lambda pair: -pair[0])
    for _, entry in scored[:max_faq]:
        results.append({"source": f"faq.md#{entry['number']}",
                        "text": f"Q: {entry['question']}\nA: {entry['answer']}"})
    return results
