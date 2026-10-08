"""Generate the synthetic "Lumi Skin" shop dataset (fictional skincare shop).

Everything here is invented: products, customers, orders, tracking events and
policies. Fake people use @example.com emails and +971 50 000 xxxx phones.

Run:  python generate.py            (writes files next to this script)
      python generate.py --out DIR  (writes files into DIR)

The random seed is fixed (42), so every run produces identical files.
Only the Python standard library is used, so it runs anywhere.
"""

from __future__ import annotations

import argparse
import csv
import random
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

SEED = 42
TODAY = date(2026, 10, 8)  # the "current date" of the fictional shop

# --------------------------------------------------------------------------
# Products: 8 per category. (name, skin_type, key_ingredients, price_aed)
# --------------------------------------------------------------------------
PRODUCTS = {
    "cleanser": [
        ("Gentle Foam Cleanser", "all", "glycerin; green tea", 59),
        ("Rice Water Gel Cleanser", "combination", "rice extract; panthenol", 65),
        ("Oat Milk Cream Cleanser", "dry", "colloidal oat; shea butter", 69),
        ("Green Tea Clarifying Cleanser", "oily", "green tea; zinc PCA", 62),
        ("Micellar Cleansing Water", "sensitive", "micelles; cucumber extract", 49),
        ("Salicylic Acne Cleanser", "oily", "salicylic acid 2%; tea tree", 72),
        ("Ceramide Hydrating Cleanser", "dry", "ceramides; hyaluronic acid", 75),
        ("Camellia Cleansing Balm", "all", "camellia oil; vitamin E", 89),
    ],
    "serum": [
        ("Niacinamide 10% + Zinc Serum", "oily", "niacinamide 10%; zinc 1%", 79),
        ("Vitamin C Brightening Serum", "all", "vitamin C 15%; ferulic acid", 149),
        ("Hyaluronic Hydra Serum", "dry", "hyaluronic acid; panthenol", 99),
        ("Retinol 0.3% Night Serum", "combination", "retinol 0.3%; squalane", 139),
        ("Snail Mucin Repair Essence", "all", "snail mucin 96%; allantoin", 109),
        ("Centella Calming Ampoule", "sensitive", "centella asiatica; madecassoside", 119),
        ("Peptide Firming Serum", "dry", "peptides; niacinamide", 189),
        ("Azelaic Acid Clarity Serum", "sensitive", "azelaic acid 10%; allantoin", 129),
    ],
    "moisturiser": [
        ("Ceramide Barrier Cream", "dry", "ceramides; cholesterol; fatty acids", 119),
        ("Oil-Free Water Gel", "oily", "hyaluronic acid; aloe vera", 89),
        ("Squalane Night Cream", "dry", "squalane; peptides", 149),
        ("Cica Recovery Balm", "sensitive", "centella asiatica; panthenol", 99),
        ("Rose Hydration Cream", "all", "rose water; glycerin", 95),
        ("Panthenol Soothing Cream", "sensitive", "panthenol 5%; madecassoside", 85),
        ("Mattifying Day Moisturiser", "oily", "niacinamide; silica", 92),
        ("Rich Shea Moisturiser", "dry", "shea butter; ceramides", 105),
    ],
    "sunscreen": [
        ("Daily Fluid SPF 50+", "all", "UV filters; niacinamide", 89),
        ("Mineral Sunscreen SPF 50", "sensitive", "zinc oxide; titanium dioxide", 99),
        ("Tinted Sun Cream SPF 30", "combination", "iron oxides; vitamin E", 95),
        ("Sun Stick SPF 50+", "all", "UV filters; jojoba oil", 79),
        ("Matte Sun Gel SPF 50", "oily", "UV filters; silica", 85),
        ("Kids Gentle Sunscreen SPF 50", "sensitive", "zinc oxide; aloe vera", 75),
        ("Hydrating Sun Serum SPF 40", "dry", "UV filters; hyaluronic acid", 109),
        ("Body Sun Lotion SPF 30", "all", "UV filters; shea butter", 69),
    ],
    "mask": [
        ("Kaolin Clay Purifying Mask", "oily", "kaolin clay; niacinamide", 79),
        ("Overnight Sleeping Mask", "dry", "hyaluronic acid; squalane", 95),
        ("Honey Glow Mask", "all", "honey; propolis", 89),
        ("Charcoal Pore Mask", "oily", "charcoal; salicylic acid", 72),
        ("Hydrogel Eye Patches (30 pairs)", "all", "caffeine; peptides", 65),
        ("Aloe Sheet Mask (5 pack)", "sensitive", "aloe vera; allantoin", 45),
        ("AHA Peel Mask", "combination", "glycolic acid; lactic acid", 99),
        ("Cica Soothing Sheet Mask (5 pack)", "sensitive", "centella asiatica; panthenol", 55),
    ],
}

# --------------------------------------------------------------------------
# Customers: invented names from three name pools.
# --------------------------------------------------------------------------
ARABIC_FIRST = [
    "Fatima", "Mariam", "Aisha", "Noura", "Huda", "Layla", "Reem", "Salma",
    "Yasmin", "Hessa", "Omar", "Khalid", "Ahmed", "Youssef", "Hamdan", "Dana",
    "Maha", "Abdullah", "Nadia", "Amina", "Karim", "Rania", "Zainab", "Latifa",
]
ARABIC_LAST = [
    "Al Mansoori", "Al Hashimi", "Al Suwaidi", "Al Ketbi", "Haddad", "Nasser",
    "Al Falasi", "Khoury", "Saleh", "Al Nuaimi", "Al Marzouqi", "Al Shamsi",
    "Rahman", "Al Mutairi", "Al Dosari", "Al Harthy", "Benali", "El Idrissi",
    "Mansour", "Hussein", "Bakri", "Al Amiri",
]
FRENCH_FIRST = [
    "Camille", "Chloé", "Léa", "Manon", "Inès", "Julie", "Sophie", "Claire",
    "Élodie", "Mathilde", "Lucas", "Antoine", "Hugo", "Nicolas", "Pauline",
    "Margaux",
]
FRENCH_LAST = [
    "Martin", "Dubois", "Bernard", "Petit", "Moreau", "Laurent", "Lefèvre",
    "Girard", "Roux", "Fournier", "Mercier", "Blanc", "Garnier", "Faure",
    "Chevalier",
]
ENGLISH_FIRST = [
    "Emily", "Olivia", "Hannah", "Grace", "Jessica", "Amelia", "Charlotte",
    "Lucy", "Megan", "James", "Daniel", "Priya", "Anjali", "Rohan", "Maria",
    "Joy",
]
ENGLISH_LAST = [
    "Carter", "Bennett", "Wright", "Mitchell", "Hughes", "Clarke", "Hayes",
    "Morgan", "Price", "Walker", "Cooper", "Sharma", "Nair", "Mehta", "Santos",
    "Reyes",
]

UAE_CITIES = ["Dubai"] * 5 + ["Abu Dhabi"] * 3 + ["Sharjah"] * 2 + ["Ajman", "Ras Al Khaimah", "Al Ain"]
GCC_CITIES = [
    ("Riyadh", "Saudi Arabia"), ("Jeddah", "Saudi Arabia"), ("Doha", "Qatar"),
    ("Kuwait City", "Kuwait"), ("Manama", "Bahrain"), ("Muscat", "Oman"),
]
HUBS = {
    "United Arab Emirates": "Dubai Hub",
    "Saudi Arabia": "Riyadh Sorting Centre",
    "Qatar": "Doha Sorting Centre",
    "Kuwait": "Kuwait Sorting Centre",
    "Bahrain": "Manama Sorting Centre",
    "Oman": "Muscat Sorting Centre",
}

# How many orders get each status (total 200).
STATUS_COUNTS = {"processing": 15, "shipped": 30, "delivered": 120, "returned": 15, "cancelled": 20}
COD_LIMIT_AED = 1000


def ascii_slug(text: str) -> str:
    """'Élodie Al Falasi' -> 'elodie.alfalasi' (for fake email addresses)."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    first, _, last = plain.lower().partition(" ")
    return f"{first}.{last.replace(' ', '')}"


def make_products(rng: random.Random) -> list[dict]:
    rows = []
    number = 1
    for category, items in PRODUCTS.items():
        for name, skin_type, ingredients, price in items:
            rows.append({
                "id": f"P{number:03d}",
                "name": name,
                "category": category,
                "skin_type": skin_type,
                "key_ingredients": ingredients,
                "price_aed": price,
                "stock": rng.choice([0, 0] + list(range(5, 151))),  # a few out of stock
            })
            number += 1
    return rows


def make_customers(rng: random.Random) -> list[dict]:
    # 26 Arabic, 17 French and 17 English names.
    pools = [("arabic", ARABIC_FIRST, ARABIC_LAST, 26), ("french", FRENCH_FIRST, FRENCH_LAST, 17),
             ("english", ENGLISH_FIRST, ENGLISH_LAST, 17)]
    people = []
    used_names = set()
    for pool, firsts, lasts, count in pools:
        while sum(1 for p in people if p[0] == pool) < count:
            name = f"{rng.choice(firsts)} {rng.choice(lasts)}"
            if name not in used_names:
                used_names.add(name)
                people.append((pool, name))
    rng.shuffle(people)

    phone_numbers = rng.sample(range(1000, 10000), len(people))
    gcc_slots = set(rng.sample(range(len(people)), 12))  # 12 GCC customers, 48 in the UAE
    rows = []
    for index, (pool, name) in enumerate(people):
        if pool == "arabic":
            language = rng.choices(["ar", "en", "fr"], weights=[75, 15, 10])[0]
        elif pool == "french":
            language = rng.choices(["fr", "en"], weights=[85, 15])[0]
        else:
            language = "en"
        if index in gcc_slots:
            city, country = rng.choice(GCC_CITIES)
        else:
            city, country = rng.choice(UAE_CITIES), "United Arab Emirates"
        rows.append({
            "id": f"C{index + 1:03d}",
            "name": name,
            "email": f"{ascii_slug(name)}@example.com",
            "phone": f"+971 50 000 {phone_numbers[index]}",
            "city": city,
            "country": country,
            "language": language,
            "address": f"Building {rng.randint(1, 99)}, Street {rng.randint(1, 40)}, {city}",
        })
    return rows


def pick_order_date(rng: random.Random, status: str, recent: bool) -> date:
    """Choose an order date that makes sense for the order's status."""
    if status == "processing":
        return TODAY - timedelta(days=rng.randint(0, 2))
    if status == "shipped":
        return TODAY - timedelta(days=rng.randint(2, 7))
    if recent:  # delivered recently, so still inside the 14-day return window
        return TODAY - timedelta(days=rng.randint(6, 16))
    start = date(2026, 1, 3)
    end = TODAY - timedelta(days=25)
    return start + timedelta(days=rng.randint(0, (end - start).days))


def make_orders(rng: random.Random, customers: list[dict], products: list[dict]):
    statuses = [s for s, n in STATUS_COUNTS.items() for _ in range(n)]
    rng.shuffle(statuses)
    drafts = []
    delivered_seen = 0
    for status in statuses:
        recent = False
        if status == "delivered":
            delivered_seen += 1
            recent = delivered_seen <= 25  # 25 delivered orders are still returnable
        customer = rng.choice(customers)
        drafts.append((pick_order_date(rng, status, recent), status, customer))
    drafts.sort(key=lambda d: (d[0], d[2]["id"]))  # order IDs increase with date

    orders, items, events = [], [], []
    tracking_numbers = rng.sample(range(1_000_000, 10_000_000), len(drafts))
    for number, (order_date, status, customer) in enumerate(drafts):
        order_id = f"LS-{10001 + number}"
        lines = make_order_lines(rng, order_id, products)
        total = sum(line["qty"] * line["unit_price_aed"] for line in lines)
        items.extend(lines)

        payment = "cod" if total <= COD_LIMIT_AED and rng.random() < 0.3 else "card"
        tracking_id, shipped, delivered = "", "", ""
        if status in ("shipped", "delivered", "returned"):
            tracking_id = f"TRK{tracking_numbers[number]}"
            shipped_day = order_date + timedelta(days=rng.randint(0, 1))
            shipped = shipped_day.isoformat()
            if status != "shipped":
                gcc = customer["country"] != "United Arab Emirates"
                delivered_day = shipped_day + timedelta(days=rng.randint(3, 7) if gcc else rng.randint(1, 3))
                delivered_day = min(delivered_day, TODAY - timedelta(days=1))
                delivered = delivered_day.isoformat()
            events.extend(make_tracking_events(rng, tracking_id, customer, shipped_day, delivered, status))

        orders.append({
            "order_id": order_id,
            "customer_id": customer["id"],
            "order_date": order_date.isoformat(),
            "status": status,
            "tracking_id": tracking_id,
            "total_aed": total,
            "payment_method": payment,
            "destination_country": customer["country"],
            "shipped_date": shipped,
            "delivered_date": delivered,
        })
    return orders, items, events


def make_order_lines(rng: random.Random, order_id: str, products: list[dict]) -> list[dict]:
    line_count = rng.choices([1, 2, 3, 4], weights=[45, 30, 17, 8])[0]
    chosen = rng.sample(products, line_count)
    return [
        {
            "order_id": order_id,
            "product_id": p["id"],
            "qty": rng.choices([1, 2, 3], weights=[75, 20, 5])[0],
            "unit_price_aed": p["price_aed"],
        }
        for p in chosen
    ]


def make_tracking_events(rng, tracking_id, customer, shipped_day, delivered, status) -> list[dict]:
    """Courier scan events for one parcel, in time order."""
    hub = HUBS[customer["country"]]
    city = customer["city"]
    clock = datetime.combine(shipped_day, datetime.min.time()) + timedelta(hours=rng.randint(9, 14))
    steps = [("picked_up", "Lumi Skin Warehouse, Dubai"), ("in_transit", hub)]
    if delivered:
        if rng.random() < 0.15:  # some parcels need a second attempt
            steps += [("out_for_delivery", city), ("failed_attempt", city)]
        steps += [("out_for_delivery", city), ("delivered", city)]
    elif rng.random() < 0.4:
        steps.append(("out_for_delivery", city))

    start = clock
    if delivered:  # last scan happens on the delivered date, between 10:00 and 18:00
        end = datetime.fromisoformat(delivered) + timedelta(hours=rng.randint(10, 18))
    else:  # still moving: last scan some hours after pickup, never after "today"
        end = min(start + timedelta(hours=rng.randint(10, 40)),
                  datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=8))
    end = max(end, start + timedelta(hours=len(steps)))
    # Spread the scans evenly between pickup and the last scan.
    gap = (end - start) / max(len(steps) - 1, 1)
    rows = []
    for index, (event, location) in enumerate(steps):
        moment = start + gap * index
        rows.append({"tracking_id": tracking_id, "timestamp": moment.isoformat(timespec="minutes"),
                     "event": event, "location": location})
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def check_reconciliation(orders: list[dict], items: list[dict]) -> int:
    """Return the number of orders whose total does not equal the sum of its lines."""
    sums: dict[str, int] = {}
    for line in items:
        sums[line["order_id"]] = sums.get(line["order_id"], 0) + line["qty"] * line["unit_price_aed"]
    return sum(1 for o in orders if sums.get(o["order_id"]) != o["total_aed"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(Path(__file__).parent), help="output folder")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rng = random.Random(SEED)
    products = make_products(rng)
    customers = make_customers(rng)
    orders, items, events = make_orders(rng, customers, products)

    write_csv(out / "products.csv", products)
    write_csv(out / "customers.csv", customers)
    write_csv(out / "orders.csv", orders)
    write_csv(out / "order_items.csv", items)
    write_csv(out / "tracking_events.csv", events)
    for name, text in TEXT_FILES.items():
        (out / name).write_text(text.strip() + "\n", encoding="utf-8")

    mismatches = check_reconciliation(orders, items)
    print(f"products={len(products)} customers={len(customers)} orders={len(orders)} "
          f"order_items={len(items)} tracking_events={len(events)} total_mismatches={mismatches}")
    if mismatches:
        raise SystemExit("order totals do not reconcile")


# --------------------------------------------------------------------------
# Text files (policies in three languages, FAQ, README)
# --------------------------------------------------------------------------
POLICIES_EN = """
# Lumi Skin customer policies

_Lumi Skin is a fictional shop. All content is synthetic, for a portfolio demo only. Last updated: 1 October 2026._

## 1. Who you are chatting with
Our chat is answered by an AI assistant. It can explain our policies, give general product guidance and look up your order after you verify it. A member of our customer care team reviews every refund and every address change, and you can ask to speak to a person at any time. Customer care hours: Monday to Saturday, 9:00 to 21:00 (UAE time).

## 2. Delivery
- We deliver in the United Arab Emirates and to the GCC: Saudi Arabia, Qatar, Kuwait, Bahrain and Oman.
- UAE: 1–3 business days after the order ships.
- GCC: 3–7 business days after the order ships.
- Orders usually ship within 1 business day. You receive a tracking ID by email when your order ships.
- Delivery is free on all orders.
- If the courier cannot deliver, they try again the next business day. After two failed attempts the parcel comes back to us and we contact you.

## 3. Cash on delivery (COD)
- Available in every country we deliver to, for orders up to AED 1,000.
- Please have the exact amount ready. Couriers may also accept a card at the door.
- Refunds for COD orders are paid by bank transfer or as store credit, as you prefer.

## 4. Changing or cancelling an order
- You can change the delivery address or cancel while the order status is "processing" (not yet shipped).
- Address changes are checked and approved by our team before they are applied.
- Once an order has shipped, the address cannot be changed. Contact us and we will help with the courier.

## 5. Returns
- You can return products within 14 days of delivery if they are unopened, unused and in the original packaging with the seal intact.
- For hygiene reasons, opened products cannot be returned unless they are faulty, damaged in transit or not what you ordered. Report these within 48 hours of delivery with a photo.
- Return pickup is free: our courier collects the parcel from your address.
- Sale items follow the same rules.

## 6. Refunds
- Every refund is reviewed and approved by a member of our team. The AI assistant can open a refund request but cannot issue a refund itself.
- Refunds above AED 200 are always escalated to a customer care supervisor.
- Approved refunds go back to the original payment method within 5–10 business days after we receive and inspect the return. COD orders are refunded by bank transfer or store credit.
- Orders cancelled before shipping are refunded in full.
- Damaged, faulty or wrong items: we refund or replace, as you prefer, after review.

## 7. Privacy
- We share order details only with the account holder, after the order ID and the email address on the order match.
- We never share one customer's information with another person, including family members, unless they verify with the order ID and email.
- We use your data only to process orders, give support and, if you opt in, send offers. We do not sell personal data.
- You can ask for a copy of your data, or for its deletion, at privacy@example.com.
- Conversations with the assistant are logged to improve the service and are reviewed by our team.

## 8. Product advice
- Our product guidance is general and is not medical advice. Patch-test new products first. If you have a skin condition, are pregnant or use a prescription treatment, please ask a dermatologist or doctor first.

## 9. Complaints
- If you are not happy, tell us. You can ask for a human agent at any time, and we aim to reply within 1 business day.
"""

POLICIES_AR = """
# سياسات متجر لومي سكين (Lumi Skin)

_لومي سكين متجر خيالي. جميع المحتويات مُصطنعة ولأغراض العرض فقط. آخر تحديث: 1 أكتوبر 2026._

## 1. مع من تتحدث؟
يتولّى الرد في هذه المحادثة مساعدٌ يعمل بالذكاء الاصطناعي. يمكنه شرح سياساتنا وتقديم إرشادات عامة عن المنتجات والاطلاع على طلبك بعد التحقق منه. يراجع أحد أعضاء فريق خدمة العملاء كلَّ طلب استرداد وكلَّ تغيير في العنوان، ويمكنك طلب التحدث إلى أحد الموظفين في أي وقت. ساعات عمل خدمة العملاء: من الاثنين إلى السبت، من الساعة 9:00 صباحًا حتى 9:00 مساءً بتوقيت الإمارات.

## 2. التوصيل
- نوصّل داخل دولة الإمارات العربية المتحدة وإلى دول الخليج: السعودية وقطر والكويت والبحرين وعُمان.
- داخل الإمارات: من يوم إلى 3 أيام عمل بعد شحن الطلب.
- دول الخليج: من 3 إلى 7 أيام عمل بعد شحن الطلب.
- نشحن الطلبات عادةً خلال يوم عمل واحد، وتصلك رسالة بالبريد الإلكتروني تتضمّن رقم التتبع عند شحن طلبك.
- التوصيل مجاني لجميع الطلبات.
- إذا تعذّر على شركة الشحن تسليم الطلب، تعيد المحاولة في يوم العمل التالي. وبعد محاولتين غير ناجحتين تعود الشحنة إلينا ونتواصل معك.

## 3. الدفع عند الاستلام
- متاح في جميع الدول التي نوصّل إليها، للطلبات التي لا تتجاوز قيمتها 1,000 درهم.
- يُرجى تجهيز المبلغ المطلوب، وقد يقبل المندوب الدفع بالبطاقة عند الباب.
- تُردّ مبالغ طلبات الدفع عند الاستلام بتحويل بنكي أو كرصيد في المتجر، حسب اختيارك.

## 4. تعديل الطلب أو إلغاؤه
- يمكنك تغيير عنوان التوصيل أو إلغاء الطلب ما دامت حالته "قيد التجهيز"، أي قبل شحنه.
- يراجع فريقنا تغييرات العنوان ويوافق عليها قبل تطبيقها.
- بعد شحن الطلب لا يمكن تغيير العنوان، لكن يمكنك التواصل معنا وسنساعدك بالتنسيق مع شركة الشحن.

## 5. الإرجاع
- يمكنك إرجاع المنتجات خلال 14 يومًا من تاريخ التسليم، بشرط أن تكون غير مفتوحة وغير مستخدمة وفي عبوتها الأصلية والختم سليم.
- لأسباب صحية، لا يمكن إرجاع المنتجات المفتوحة إلا إذا كانت معيبة أو تضررت أثناء الشحن أو كانت مختلفة عمّا طلبته. يُرجى إبلاغنا بذلك خلال 48 ساعة من التسليم مع إرفاق صورة.
- استلام المرتجعات مجاني، إذ يأتي مندوب الشحن لاستلام الطرد من عنوانك.
- تخضع المنتجات المخفّضة للقواعد نفسها.

## 6. استرداد المبالغ
- يراجع أحد أعضاء فريقنا كل طلب استرداد ويوافق عليه. يستطيع المساعد الذكي فتح طلب استرداد، لكنه لا يستطيع إصدار الاسترداد بنفسه.
- تُحال دائمًا طلبات الاسترداد التي تزيد قيمتها على 200 درهم إلى مشرف خدمة العملاء.
- تُعاد المبالغ المعتمدة إلى وسيلة الدفع الأصلية خلال 5 إلى 10 أيام عمل بعد استلام المرتجع وفحصه. أما طلبات الدفع عند الاستلام فتُردّ بتحويل بنكي أو كرصيد في المتجر.
- تُستردّ قيمة الطلبات الملغاة قبل الشحن بالكامل.
- في حال وصول منتج تالف أو معيب أو غير الذي طلبته، نردّ المبلغ أو نستبدل المنتج حسب اختيارك، وذلك بعد المراجعة.

## 7. الخصوصية
- لا نشارك تفاصيل الطلب إلا مع صاحب الحساب، وبعد التأكد من تطابق رقم الطلب مع البريد الإلكتروني المسجّل عليه.
- لا نشارك أبدًا معلومات أي عميل مع شخص آخر، حتى لو كان من أفراد العائلة، إلا بعد التحقق برقم الطلب والبريد الإلكتروني.
- نستخدم بياناتك فقط لتنفيذ الطلبات وتقديم الدعم، ولإرسال العروض إذا وافقت على ذلك. ولا نبيع البيانات الشخصية.
- يمكنك طلب نسخة من بياناتك أو حذفها عبر البريد الإلكتروني privacy@example.com.
- تُحفظ المحادثات مع المساعد لتحسين الخدمة، ويراجعها فريقنا.

## 8. نصائح المنتجات
- إرشاداتنا حول المنتجات عامة ولا تُعدّ استشارة طبية. يُنصح بتجربة أي منتج جديد على مساحة صغيرة من البشرة أولًا. وفي حال وجود مشكلة جلدية أو حمل أو استخدام علاج بوصفة طبية، يُرجى استشارة طبيب الجلدية أو الطبيب المعالج أولًا.

## 9. الشكاوى
- إذا لم تكن راضيًا عن تجربتك، أخبرنا بذلك. يمكنك طلب التحدث إلى أحد الموظفين في أي وقت، ونسعى إلى الرد خلال يوم عمل واحد.
"""

POLICIES_FR = """
# Politiques clients de Lumi Skin

_Lumi Skin est une boutique fictive. Tout le contenu est synthétique et sert uniquement à une démonstration de portfolio. Dernière mise à jour : 1er octobre 2026._

## 1. Avec qui discutez-vous ?
Ce chat est assuré par un assistant d'intelligence artificielle. Il peut expliquer nos politiques, donner des conseils généraux sur nos produits et consulter votre commande après vérification. Un membre de notre service client examine chaque remboursement et chaque changement d'adresse, et vous pouvez demander à parler à une personne à tout moment. Horaires du service client : du lundi au samedi, de 9 h à 21 h (heure des Émirats).

## 2. Livraison
- Nous livrons aux Émirats arabes unis et dans les pays du Golfe : Arabie saoudite, Qatar, Koweït, Bahreïn et Oman.
- Émirats arabes unis : 1 à 3 jours ouvrés après l'expédition.
- Pays du Golfe : 3 à 7 jours ouvrés après l'expédition.
- Les commandes sont généralement expédiées sous 1 jour ouvré. Vous recevez un numéro de suivi par e-mail dès l'expédition.
- La livraison est gratuite pour toutes les commandes.
- Si le livreur ne peut pas livrer, il repasse le jour ouvré suivant. Après deux tentatives infructueuses, le colis nous est retourné et nous vous contactons.

## 3. Paiement à la livraison
- Disponible dans tous les pays où nous livrons, pour les commandes jusqu'à 1 000 AED.
- Merci de préparer le montant exact. Le livreur peut aussi accepter la carte bancaire.
- Les commandes payées à la livraison sont remboursées par virement bancaire ou en avoir, selon votre choix.

## 4. Modifier ou annuler une commande
- Vous pouvez changer l'adresse de livraison ou annuler tant que la commande est « en préparation » (pas encore expédiée).
- Les changements d'adresse sont vérifiés et validés par notre équipe avant d'être appliqués.
- Une fois la commande expédiée, l'adresse ne peut plus être modifiée. Contactez-nous et nous vous aiderons auprès du transporteur.

## 5. Retours
- Vous pouvez retourner un produit dans les 14 jours suivant la livraison s'il est non ouvert, non utilisé, dans son emballage d'origine et avec l'opercule intact.
- Pour des raisons d'hygiène, les produits ouverts ne sont pas repris, sauf s'ils sont défectueux, abîmés pendant le transport ou différents de votre commande. Signalez-le dans les 48 heures suivant la livraison, photo à l'appui.
- L'enlèvement du retour est gratuit : notre transporteur vient chercher le colis à votre adresse.
- Les articles en promotion suivent les mêmes règles.

## 6. Remboursements
- Chaque remboursement est examiné et validé par un membre de notre équipe. L'assistant IA peut ouvrir une demande de remboursement, mais il ne peut pas effectuer le remboursement lui-même.
- Les remboursements de plus de 200 AED sont toujours transmis à un responsable du service client.
- Les remboursements validés sont versés sur le moyen de paiement d'origine sous 5 à 10 jours ouvrés, après réception et contrôle du retour. Commandes payées à la livraison : virement bancaire ou avoir.
- Les commandes annulées avant l'expédition sont remboursées intégralement.
- Produit abîmé, défectueux ou erroné : remboursement ou remplacement, selon votre choix, après vérification.

## 7. Confidentialité
- Nous ne communiquons les détails d'une commande qu'au titulaire du compte, après vérification du numéro de commande et de l'adresse e-mail associée.
- Nous ne partageons jamais les informations d'un client avec une autre personne, même un membre de sa famille, sans cette vérification.
- Nous utilisons vos données uniquement pour traiter vos commandes, vous assister et, si vous l'acceptez, vous envoyer des offres. Nous ne vendons pas de données personnelles.
- Vous pouvez demander une copie ou la suppression de vos données à privacy@example.com.
- Les conversations avec l'assistant sont enregistrées pour améliorer le service et relues par notre équipe.

## 8. Conseils produits
- Nos conseils sont généraux et ne remplacent pas un avis médical. Faites un test cutané avant d'utiliser un nouveau produit. En cas de problème de peau, de grossesse ou de traitement sur ordonnance, demandez d'abord l'avis d'un dermatologue ou d'un médecin.

## 9. Réclamations
- Si vous n'êtes pas satisfait(e), dites-le-nous. Vous pouvez demander à parler à un conseiller à tout moment ; nous nous efforçons de répondre sous 1 jour ouvré.
"""

FAQ = """
# Lumi Skin FAQ (English)

_Fictional shop. Synthetic content for a portfolio demo only._

### 1. Am I chatting with a real person?
No. You are chatting with an AI assistant. A member of our customer care team reviews refunds and address changes, and you can ask for a human at any time.

### 2. How can I track my order?
Share your order ID (for example LS-10001) and the email address you used. After we verify both, we can tell you the status and the latest courier update.

### 3. Why do you need my email to show my order?
To protect your privacy. We only show order details when the order ID and the email on the order match.

### 4. How long does delivery take in the UAE?
1–3 business days after your order ships.

### 5. How long does delivery take to Saudi Arabia, Qatar, Kuwait, Bahrain or Oman?
3–7 business days after your order ships.

### 6. How much is delivery?
Delivery is free on all orders.

### 7. When will my order ship?
Most orders ship within 1 business day. You get a tracking ID by email when it ships.

### 8. Do you offer cash on delivery?
Yes, in every country we deliver to, for orders up to AED 1,000.

### 9. The courier missed me. What happens now?
The courier tries again the next business day. After two failed attempts the parcel comes back to us and we contact you.

### 10. Can I change my delivery address?
Yes, while your order is still "processing" (not shipped). Our team approves the change before it is applied.

### 11. Can I cancel my order?
Yes, while it is still "processing". Cancelled orders are refunded in full.

### 12. What is your return policy?
You can return unopened, unused products in their original packaging within 14 days of delivery.

### 13. Can I return a product I have opened?
Only if it is faulty, damaged in transit or not what you ordered. Please report it within 48 hours of delivery with a photo.

### 14. How do I start a return?
Tell us your order ID and email. After verification we open a return request and our courier collects the parcel for free.

### 15. How long do refunds take?
5–10 business days after we receive and inspect the return. The money goes back to your original payment method.

### 16. Who approves refunds?
A member of our team approves every refund. Refunds above AED 200 always go to a supervisor.

### 17. How are cash-on-delivery orders refunded?
By bank transfer or as store credit, as you prefer.

### 18. My parcel arrived damaged. What should I do?
Send us a photo within 48 hours of delivery. After review we refund or replace the item, as you prefer.

### 19. I received the wrong product.
Sorry about that. Send a photo within 48 hours and we will arrange a free pickup and the correct item or a refund.

### 20. Which serum is good for oily skin?
Our Niacinamide 10% + Zinc Serum is popular for oily skin. This is general guidance, not medical advice.

### 21. Which products suit sensitive skin?
Look at the products marked "sensitive", such as the Centella Calming Ampoule and the Mineral Sunscreen SPF 50. Always patch-test first.

### 22. Can I use retinol and vitamin C together?
Many people use vitamin C in the morning and retinol at night. If you are pregnant or have a skin condition, ask a doctor first.

### 23. Do I need sunscreen every day?
Yes, daily sunscreen is recommended, especially in the UAE sun. Reapply every 2 hours outdoors.

### 24. Are your products safe during pregnancy?
We cannot give medical advice. Please check with your doctor, especially about retinol and strong acids.

### 25. Is a product out of stock?
Ask us about the product and we will check the current stock.

### 26. Can someone else check my order for me?
Only if they give the order ID and the email address on the order. We never share order details otherwise.

### 27. How do you use my personal data?
Only to process orders, give support and, if you opt in, send offers. We never sell personal data.

### 28. How can I delete my data?
Email privacy@example.com and we will process your request.

### 29. What are your customer care hours?
Monday to Saturday, 9:00 to 21:00 UAE time.

### 30. How do I speak to a human?
Just ask, for example "I want to talk to a person". We pass your conversation to our team, and we aim to reply within 1 business day.
"""

README = """
# Lumi Skin synthetic shop data

**All data in this folder is synthetic.** Lumi Skin is a fictional skincare shop. No real
company, customer or order data was used. People are invented, emails use `@example.com`
and phones use the fake `+971 50 000 xxxx` pattern.

Generated by `generate.py` with random seed 42 (Python standard library only):

```
python generate.py            # writes the files next to the script
python generate.py --out DIR  # or into another folder
```

The script checks that every `orders.total_aed` equals the sum of its `order_items` lines
and stops with an error if not. The shop's "today" is 2026-10-08.

## Files and columns

| File | Rows | Columns |
|---|---|---|
| `products.csv` | 40 | id (P001…), name, category (cleanser/serum/moisturiser/sunscreen/mask), skin_type (all/dry/oily/combination/sensitive), key_ingredients (`;`-separated), price_aed, stock (0 = out of stock) |
| `customers.csv` | 60 | id (C001…), name, email, phone, city, country, language (ar/en/fr), address (fictional) |
| `orders.csv` | 200 | order_id (LS-10001…), customer_id, order_date, status (processing/shipped/delivered/returned/cancelled), tracking_id (empty if not shipped), total_aed, payment_method (card/cod), destination_country, shipped_date, delivered_date |
| `order_items.csv` | 350 | order_id, product_id, qty, unit_price_aed (sum of qty × unit_price_aed = orders.total_aed) |
| `tracking_events.csv` | 654 | tracking_id, timestamp, event (picked_up/in_transit/out_for_delivery/delivered/failed_attempt), location |
| `policies_en.md`, `policies_ar.md`, `policies_fr.md` | — | Shop policies in English, Arabic and French (returns 14 days unopened, refunds with AED 200 escalation, delivery UAE 1–3 / GCC 3–7 business days, cash on delivery up to AED 1,000, privacy, AI-assistant disclosure) |
| `faq.md` | 30 | Frequently asked questions (English) |

Notes:
- Delivery is free, so an order total is exactly the sum of its lines.
- Status mix: 15 processing, 30 shipped, 120 delivered (25 of them recent, still inside
  the 14-day return window), 15 returned, 20 cancelled.
- Cash on delivery is only used for orders up to AED 1,000.

## Licence

Synthetic data, released under the MIT licence together with the code that generates it.
Credit: "shared synthetic Lumi Skin data, generated by generate.py (seed 42)".
"""

TEXT_FILES = {
    "policies_en.md": POLICIES_EN,
    "policies_ar.md": POLICIES_AR,
    "policies_fr.md": POLICIES_FR,
    "faq.md": FAQ,
    "README.md": README,
}


if __name__ == "__main__":
    main()
