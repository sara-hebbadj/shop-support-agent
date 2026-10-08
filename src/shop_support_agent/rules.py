"""Keyword rules and reply templates in Arabic, English and French.

Used in two places:
1. The rules-only baseline bot (baselines.RulesBot), which routes by keywords.
2. The offline FakeLLM (llm.py), so the demo and the tests work without an API key.

The real agent does NOT use these keywords to understand customers; it asks the LLM.
"""

from __future__ import annotations

import re

# ---------------- intent keywords (lower-case substrings) ----------------
KEYWORDS = {
    "handover": ["human", "real person", "speak to someone", "talk to someone", "a person", "manager",
                 "موظف", "شخص حقيقي", "إنسان", "انسان", "بشري", "المدير",
                 "humain", "une personne", "un conseiller", "quelqu'un", "responsable"],
    "policy_question": ["policy", "how long", "how many days", "cash on delivery", "privacy", "do you deliver",
                        "سياسة", "كم يوم", "كم يستغرق", "الدفع عند الاستلام", "خصوصية", "هل توصلون",
                        "politique", "combien de temps", "paiement à la livraison", "confidentialité", "délai",
                        "livrez-vous"],
    "address_change": ["address", "عنوان", "العنوان", "adresse"],
    "return_refund": ["refund", "return", "money back", "استرداد", "ارجاع", "إرجاع", "استرجاع", "ارجع", "أرجع",
                      "rembours", "retour", "retourner", "renvoyer"],
    "order_status": ["where is", "track", "status", "shipped", "arrive", "my order", "my parcel", "package",
                     "وين", "أين", "طلبي", "تتبع", "شحنتي", "الشحنة", "متى يوصل", "وصل",
                     "où en est", "suivi", "ma commande", "mon colis", "arrivé"],
    "product_advice": ["recommend", "suggest", "serum", "cream", "skin", "moistur", "sunscreen", "cleanser",
                       "mask", "بشرة", "بشرتي", "سيروم", "كريم", "واقي", "غسول", "ماسك", "تنصح", "انصح",
                       "peau", "crème", "sérum", "conseill", "nettoyant", "masque", "écran"],
    "greeting": ["hello", "hi ", "مرحبا", "السلام", "اهلا", "أهلا", "bonjour", "salut", "bonsoir"],
}
INTENT_ORDER = ["handover", "policy_question", "address_change", "return_refund", "order_status",
                "product_advice", "greeting"]

ANGRY_WORDS = ["terrible", "worst", "angry", "unacceptable", "ridiculous", "scam", "furious", "disgusting",
               "!!!", "سيء", "زفت", "غاضب", "غير مقبول", "مهزلة", "نصب", "حرام عليكم",
               "inadmissible", "honteux", "arnaque", "furieux", "inacceptable", "scandaleux", "n'importe quoi"]
INJECTION_WORDS = ["ignore", "previous instructions", "system prompt", "you are now", "developer mode",
                   "admin mode", "تجاهل", "التعليمات", "وضع المطور", "المسؤول عن النظام",
                   "oublie", "instructions précédentes", "mode administrateur", "mode développeur"]

SKIN_WORDS = {"oily": ["oily", "دهنية", "grasse"], "dry": ["dry", "جافة", "sèche", "seche"],
              "sensitive": ["sensitive", "حساسة", "sensible"], "combination": ["combination", "مختلطة", "mixte"]}
CATEGORY_WORDS = {"serum": ["serum", "سيروم", "sérum"], "sunscreen": ["sunscreen", "spf", "واقي", "solaire"],
                  "moisturiser": ["moistur", "cream", "مرطب", "كريم", "hydratant", "crème"],
                  "cleanser": ["cleanser", "face wash", "غسول", "nettoyant"],
                  "mask": ["mask", "ماسك", "قناع", "masque"]}
REASON_WORDS = [  # order matters: "not opened" must win over "opened"
    ("unopened", ["unopened", "not opened", "never opened", "sealed", "still closed", "لم أفتح", "ما فتحت",
                  "مغلق", "مقفل", "بدون فتح", "non ouvert", "pas ouvert", "jamais ouvert", "scellé", "fermé"]),
    ("damaged", ["damaged", "broken", "leak", "مكسور", "تالف", "مكسورة", "abîmé", "cassé", "endommagé"]),
    ("wrong_item", ["wrong item", "wrong product", "not what i ordered", "منتج خطأ", "منتج غلط", "غير الذي طلبت",
                    "mauvais produit", "pas ce que j'ai commandé", "erreur de produit"]),
    ("opened", ["opened", "used", "tried it", "فتحت", "استخدمت", "جربت", "ouvert", "utilisé", "essayé"]),
]
ADDRESS_RE = re.compile(
    r"(?:new address(?: is)?|change (?:it|the address) to|deliver(?: it)? to|العنوان الجديد(?: هو)?|إلى|الى|"
    r"nouvelle adresse(?: est)?|livrer à|adresse à)\s*[:\-]?\s*(.+)$",
    re.IGNORECASE,
)
ADDRESS_HINTS = ["building", "street", "villa", "apartment", "flat", "road", "مبنى", "شارع", "فيلا", "شقة",
                 "bâtiment", "rue", "immeuble", "appartement"]


def _has_any(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


EMAIL_PHRASES = ["email address", "e-mail address", "adresse e-mail", "adresse email", "adresse mail",
                 "عنوان البريد", "عنوان الإيميل", "عنوان الايميل"]


def classify(text: str) -> str:
    lowered = f" {text.lower()} "
    for phrase in EMAIL_PHRASES:  # "email address" is not a delivery address
        lowered = lowered.replace(phrase, "email")
    for intent in INTENT_ORDER:
        if _has_any(lowered, KEYWORDS[intent]):
            return intent
    return "other"


def is_angry(text: str) -> bool:
    return _has_any(text.lower(), ANGRY_WORDS)


def looks_like_injection(text: str) -> bool:
    return _has_any(text.lower(), INJECTION_WORDS)


def find_first(text: str, table: dict[str, list[str]]) -> str | None:
    lowered = text.lower()
    return next((key for key, words in table.items() if _has_any(lowered, words)), None)


def find_reason(text: str) -> str | None:
    lowered = text.lower()
    return next((reason for reason, words in REASON_WORDS if _has_any(lowered, words)), None)


def find_new_address(text: str) -> str | None:
    match = ADDRESS_RE.search(text.strip())
    if not match:
        return None
    candidate = match.group(1).strip().strip(".")
    if any(ch.isdigit() for ch in candidate) or _has_any(candidate.lower(), ADDRESS_HINTS):
        return candidate
    return None


# ---------------- reply templates ----------------
STATUS_LABELS = {
    "en": {"processing": "being prepared", "shipped": "on its way", "delivered": "delivered",
           "returned": "returned", "cancelled": "cancelled"},
    "ar": {"processing": "قيد التجهيز", "shipped": "في الطريق إليك", "delivered": "تم توصيله",
           "returned": "تم إرجاعه", "cancelled": "ملغى"},
    "fr": {"processing": "en préparation", "shipped": "en route", "delivered": "livrée",
           "returned": "retournée", "cancelled": "annulée"},
}
EVENT_LABELS = {
    "en": {"picked_up": "picked up", "in_transit": "in transit", "out_for_delivery": "out for delivery",
           "delivered": "delivered", "failed_attempt": "delivery attempt failed"},
    "ar": {"picked_up": "تم استلام الشحنة", "in_transit": "في الطريق", "out_for_delivery": "خرجت للتوصيل",
           "delivered": "تم التسليم", "failed_attempt": "محاولة توصيل لم تنجح"},
    "fr": {"picked_up": "pris en charge", "in_transit": "en transit", "out_for_delivery": "en cours de livraison",
           "delivered": "livré", "failed_attempt": "tentative de livraison échouée"},
}
NOT_ELIGIBLE = {
    "en": {"outside_14_days": "it was delivered more than 14 days ago",
           "opened": "opened products can only be returned if they are faulty or wrong",
           "damaged_too_late": "damaged or wrong items must be reported within 48 hours of delivery",
           "status": "it has not been delivered (status: {status})"},
    "ar": {"outside_14_days": "مرّ على توصيله أكثر من 14 يومًا",
           "opened": "لا يمكن إرجاع المنتجات المفتوحة إلا إذا كانت معيبة أو مختلفة عمّا طلبته",
           "damaged_too_late": "يجب الإبلاغ عن المنتجات التالفة أو الخاطئة خلال 48 ساعة من التسليم",
           "status": "لم يتم توصيله بعد (الحالة: {status})"},
    "fr": {"outside_14_days": "elle a été livrée il y a plus de 14 jours",
           "opened": "les produits ouverts ne sont repris que s'ils sont défectueux ou erronés",
           "damaged_too_late": "un produit abîmé ou erroné doit être signalé dans les 48 heures",
           "status": "elle n'a pas été livrée (statut : {status})"},
}
TEMPLATES = {
    "en": {
        "disclosure": "Hi! I'm Lumi Skin's AI assistant, not a human. You can ask for a person at any time.",
        "greeting": "How can I help today? I can track orders, help with returns and refunds, change a "
                    "delivery address before shipping and suggest products.",
        "need_verification": "To protect your privacy, please send your order ID (for example LS-10001) and the "
                             "email address used for the order.",
        "verification_failed": "Sorry, that order ID and email address don't match our records, so I can't "
                               "share any order details. Please check both and try again.",
        "status_shared": "Your order {order_id} is {status}.",
        "status_tracking": " Latest courier update: {event} ({location}, {when}).",
        "advice_given": "You could look at: {products}. This is general guidance, not medical advice, so "
                        "please patch-test first.",
        "policy_answered": "Here is what our policy says: {policy}",
        "refund_queued": "I've sent a refund request of AED {amount} for order {order_id} to our team "
                         "(request {approval_id}). A team member must approve it before it is issued.",
        "refund_escalated": "I've sent a refund request of AED {amount} for order {order_id} (request "
                            "{approval_id}). Because it is above AED 200, a supervisor will review it.",
        "return_not_eligible": "Sorry, order {order_id} can't be returned because {reason}.",
        "address_change_queued": "I've asked our team to change the delivery address of {order_id} to "
                                 "\"{new_address}\" (request {approval_id}). It changes once approved.",
        "address_change_not_possible": "Order {order_id} is already {status}, so the address can't be changed "
                                       "now. A team member can help with the courier if needed.",
        "need_address": "Sure. Please send the full new delivery address.",
        "need_return_details": "Are the products unopened, or did they arrive damaged or wrong?",
        "handover": "I've passed our conversation to the customer care team (ticket {ticket_id}). A person "
                    "will reply within 1 business day.",
        "refused": "Sorry, I can't help with that. I only share order details with the account holder after "
                   "checking the order ID and email.",
        "clarify": "Sorry, I didn't quite understand. I can help with order tracking, returns and refunds, "
                   "address changes, delivery questions and product advice.",
        "approved": "Update on request {approval_id}: a team member approved it.",
        "denied": "Update on request {approval_id}: a team member could not approve it. Our team will "
                  "contact you with the reason.",
        "waiting": "Your request {approval_id} is waiting for a team member's review. I'll update you here.",
    },
    "ar": {
        "disclosure": "مرحبًا! أنا المساعد الذكي لمتجر لومي سكين، ولست موظفًا بشريًا. يمكنك طلب التحدث إلى أحد "
                      "الموظفين في أي وقت.",
        "greeting": "كيف يمكنني مساعدتك اليوم؟ يمكنني تتبع الطلبات، والمساعدة في الإرجاع والاسترداد، وتغيير "
                    "عنوان التوصيل قبل الشحن، واقتراح المنتجات.",
        "need_verification": "حفاظًا على خصوصيتك، يُرجى إرسال رقم الطلب (مثل LS-10001) والبريد الإلكتروني "
                             "المستخدم في الطلب.",
        "verification_failed": "عذرًا، رقم الطلب والبريد الإلكتروني غير متطابقين في سجلاتنا، لذلك لا يمكنني "
                               "مشاركة أي تفاصيل. يُرجى التحقق منهما والمحاولة مرة أخرى.",
        "status_shared": "طلبك {order_id} {status}.",
        "status_tracking": " آخر تحديث من شركة الشحن: {event} ({location}، {when}).",
        "advice_given": "يمكنك تجربة: {products}. هذه إرشادات عامة وليست استشارة طبية، لذا يُنصح بتجربة المنتج "
                        "على مساحة صغيرة من البشرة أولًا.",
        "policy_answered": "هذا ما تنص عليه سياستنا: {policy}",
        "refund_queued": "أرسلت طلب استرداد بقيمة {amount} درهم للطلب {order_id} إلى فريقنا (رقم الطلب "
                         "{approval_id}). يجب أن يوافق عليه أحد أعضاء الفريق قبل تنفيذه.",
        "refund_escalated": "أرسلت طلب استرداد بقيمة {amount} درهم للطلب {order_id} (رقم الطلب {approval_id}). "
                            "ولأن المبلغ يزيد على 200 درهم، سيراجعه أحد المشرفين.",
        "return_not_eligible": "عذرًا، لا يمكن إرجاع الطلب {order_id} لأنه {reason}.",
        "address_change_queued": "طلبت من فريقنا تغيير عنوان توصيل الطلب {order_id} إلى \"{new_address}\" "
                                 "(رقم الطلب {approval_id}). سيتغير العنوان بعد الموافقة.",
        "address_change_not_possible": "الطلب {order_id} {status} بالفعل، لذلك لا يمكن تغيير العنوان الآن. "
                                       "يمكن لأحد أعضاء الفريق مساعدتك مع شركة الشحن عند الحاجة.",
        "need_address": "بكل سرور. يُرجى إرسال عنوان التوصيل الجديد كاملًا.",
        "need_return_details": "هل المنتجات غير مفتوحة، أم وصلت تالفة أو مختلفة عمّا طلبته؟",
        "handover": "حوّلت محادثتنا إلى فريق خدمة العملاء (رقم التذكرة {ticket_id}). سيرد عليك أحد الموظفين "
                    "خلال يوم عمل واحد.",
        "refused": "عذرًا، لا يمكنني المساعدة في ذلك. لا أشارك تفاصيل الطلبات إلا مع صاحب الحساب بعد التحقق من "
                   "رقم الطلب والبريد الإلكتروني.",
        "clarify": "عذرًا، لم أفهم طلبك تمامًا. يمكنني المساعدة في تتبع الطلبات، والإرجاع والاسترداد، وتغيير "
                   "العنوان، وأسئلة التوصيل، ونصائح المنتجات.",
        "approved": "تحديث بخصوص الطلب {approval_id}: وافق عليه أحد أعضاء الفريق.",
        "denied": "تحديث بخصوص الطلب {approval_id}: لم يتمكن الفريق من الموافقة عليه، وسيتواصل معك لتوضيح السبب.",
        "waiting": "طلبك {approval_id} بانتظار مراجعة أحد أعضاء الفريق. سأبلغك بالتحديث هنا.",
    },
    "fr": {
        "disclosure": "Bonjour ! Je suis l'assistant IA de Lumi Skin, pas un humain. Vous pouvez demander à "
                      "parler à une personne à tout moment.",
        "greeting": "Comment puis-je vous aider ? Je peux suivre une commande, vous aider pour un retour ou un "
                    "remboursement, changer l'adresse avant l'expédition et conseiller des produits.",
        "need_verification": "Pour protéger vos données, merci d'indiquer votre numéro de commande (par exemple "
                             "LS-10001) et l'adresse e-mail utilisée pour la commande.",
        "verification_failed": "Désolé, ce numéro de commande et cette adresse e-mail ne correspondent pas à nos "
                               "dossiers. Je ne peux donc partager aucun détail. Merci de vérifier les deux.",
        "status_shared": "Votre commande {order_id} est {status}.",
        "status_tracking": " Dernière mise à jour du transporteur : {event} ({location}, {when}).",
        "advice_given": "Vous pouvez regarder : {products}. Ce sont des conseils généraux, pas un avis "
                        "médical ; faites d'abord un test cutané.",
        "policy_answered": "Voici ce que dit notre politique : {policy}",
        "refund_queued": "J'ai transmis une demande de remboursement de {amount} AED pour la commande "
                         "{order_id} à notre équipe (demande {approval_id}). Un membre de l'équipe doit la "
                         "valider avant le remboursement.",
        "refund_escalated": "J'ai transmis une demande de remboursement de {amount} AED pour la commande "
                            "{order_id} (demande {approval_id}). Comme elle dépasse 200 AED, un responsable "
                            "va l'examiner.",
        "return_not_eligible": "Désolé, la commande {order_id} ne peut pas être retournée car {reason}.",
        "address_change_queued": "J'ai demandé à notre équipe de changer l'adresse de livraison de {order_id} "
                                 "pour « {new_address} » (demande {approval_id}). Elle sera modifiée après "
                                 "validation.",
        "address_change_not_possible": "La commande {order_id} est déjà {status}, l'adresse ne peut donc plus "
                                       "être modifiée. Un conseiller peut vous aider auprès du transporteur.",
        "need_address": "Bien sûr. Merci d'indiquer la nouvelle adresse de livraison complète.",
        "need_return_details": "Les produits sont-ils non ouverts, ou sont-ils arrivés abîmés ou erronés ?",
        "handover": "J'ai transmis notre conversation au service client (ticket {ticket_id}). Un conseiller "
                    "vous répondra sous 1 jour ouvré.",
        "refused": "Désolé, je ne peux pas vous aider pour cela. Je ne communique les détails d'une commande "
                   "qu'au titulaire du compte, après vérification du numéro de commande et de l'e-mail.",
        "clarify": "Désolé, je n'ai pas bien compris. Je peux vous aider pour le suivi de commande, les retours "
                   "et remboursements, le changement d'adresse, la livraison et les conseils produits.",
        "approved": "Mise à jour de la demande {approval_id} : un membre de l'équipe l'a validée.",
        "denied": "Mise à jour de la demande {approval_id} : l'équipe n'a pas pu la valider et vous contactera "
                  "pour vous expliquer pourquoi.",
        "waiting": "Votre demande {approval_id} attend la validation d'un membre de l'équipe. Je vous tiendrai "
                   "informé(e) ici.",
    },
}


def render_reply(outcome: str, language: str, facts: dict) -> str:
    """Fill the template for an outcome with facts. Used offline and by the rules bot."""
    lang = language if language in TEMPLATES else "en"
    t = TEMPLATES[lang]
    order = facts.get("order") or {}
    approval = facts.get("approval") or {}
    if outcome == "status_shared":
        text = t["status_shared"].format(order_id=order.get("order_id"),
                                         status=STATUS_LABELS[lang].get(order.get("status"), order.get("status")))
        latest = (facts.get("tracking") or {}).get("latest")
        if latest:
            text += t["status_tracking"].format(event=EVENT_LABELS[lang].get(latest["event"], latest["event"]),
                                                location=latest["location"], when=latest["timestamp"][:10])
        return text
    if outcome == "advice_given":
        names = ", ".join(f"{p['name']} (AED {p['price_aed']})" for p in facts.get("products", []))
        return t["advice_given"].format(products=names or "-")
    if outcome == "policy_answered":
        docs = facts.get("policy") or [{"text": ""}]
        snippet = " ".join(docs[0]["text"].split())[:400]
        return t["policy_answered"].format(policy=snippet)
    if outcome in ("refund_queued", "refund_escalated", "address_change_queued"):
        return t[outcome].format(amount=int(approval.get("amount_aed", 0)), order_id=approval.get("order_id"),
                                 approval_id=approval.get("approval_id"),
                                 new_address=(approval.get("details") or {}).get("new_address", ""))
    if outcome == "return_not_eligible":
        code = facts.get("return_check", "")
        reason_key = "status" if code.startswith("status_") else code
        reason = NOT_ELIGIBLE[lang].get(reason_key, code).format(
            status=STATUS_LABELS[lang].get(order.get("status"), order.get("status")))
        return t["return_not_eligible"].format(order_id=order.get("order_id"), reason=reason)
    if outcome == "address_change_not_possible":
        return t[outcome].format(order_id=order.get("order_id"),
                                 status=STATUS_LABELS[lang].get(order.get("status"), order.get("status")))
    if outcome == "handover":
        return t["handover"].format(ticket_id=(facts.get("ticket") or {}).get("ticket_id", "-"))
    if outcome in ("approved", "denied", "waiting"):
        return t[outcome].format(approval_id=approval.get("approval_id"))
    return t.get(outcome, t["clarify"])
