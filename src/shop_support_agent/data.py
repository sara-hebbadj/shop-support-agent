"""Read-only access to the synthetic Lumi Skin data in data/*.csv.

Everything that can change during a demo (addresses, notes, tickets, approvals)
lives in crm.py instead, so this module never writes files.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from .config import DATA_DIR, RETURN_WINDOW_DAYS, SHOP_TODAY


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@dataclass
class ShopData:
    products: list[dict]
    customers: dict[str, dict]
    orders: dict[str, dict]
    items_by_order: dict[str, list[dict]] = field(default_factory=dict)
    events_by_tracking: dict[str, list[dict]] = field(default_factory=dict)

    # ---------------- lookups ----------------
    def customer_for_order(self, order_id: str) -> dict | None:
        order = self.orders.get(order_id)
        return self.customers.get(order["customer_id"]) if order else None

    def verify(self, order_id: str, email: str) -> str | None:
        """Return the customer ID only if the order exists AND its email matches."""
        customer = self.customer_for_order(order_id)
        if customer and customer["email"].lower() == email.strip().lower():
            return customer["id"]
        return None

    def order_view(self, order_id: str) -> dict | None:
        """The order fields we are allowed to show a verified customer."""
        order = self.orders.get(order_id)
        if not order:
            return None
        names = {p["id"]: p["name"] for p in self.products}
        lines = [
            {"product": names.get(i["product_id"], i["product_id"]), "qty": int(i["qty"]),
             "unit_price_aed": int(i["unit_price_aed"])}
            for i in self.items_by_order.get(order_id, [])
        ]
        return {
            "order_id": order_id,
            "status": order["status"],
            "order_date": order["order_date"],
            "shipped_date": order["shipped_date"] or None,
            "delivered_date": order["delivered_date"] or None,
            "tracking_id": order["tracking_id"] or None,
            "total_aed": int(order["total_aed"]),
            "payment_method": order["payment_method"],
            "destination_country": order["destination_country"],
            "items": lines,
        }

    def tracking_events(self, tracking_id: str) -> list[dict]:
        return self.events_by_tracking.get(tracking_id, [])

    def search_products(self, skin_type: str | None = None, category: str | None = None,
                        limit: int = 3) -> list[dict]:
        """Simple filter: matching skin type ('all' matches everyone) and category, in stock first."""
        results = []
        for product in self.products:
            if category and product["category"] != category:
                continue
            if skin_type and product["skin_type"] not in (skin_type, "all"):
                continue
            results.append(product)
        # Exact skin-type matches first, then in-stock items, then cheaper first.
        results.sort(key=lambda p: (p["skin_type"] != skin_type, int(p["stock"]) == 0, int(p["price_aed"])))
        return results[:limit]


def return_eligibility(order: dict, reason: str | None, today: str = SHOP_TODAY) -> tuple[bool, str]:
    """Deterministic returns policy check. Returns (eligible, short_reason_code).

    reason: 'unopened', 'opened', 'damaged', 'wrong_item' or None (unknown).
    """
    if order["status"] != "delivered":
        return False, f"status_{order['status']}"
    days = (date.fromisoformat(today) - date.fromisoformat(order["delivered_date"])).days
    if reason in ("damaged", "wrong_item"):
        # Faulty or wrong items must be reported within 48 hours of delivery.
        return (days <= 2, "damaged_ok" if days <= 2 else "damaged_too_late")
    if days > RETURN_WINDOW_DAYS:
        return False, "outside_14_days"
    if reason == "opened":
        return False, "opened"
    return True, "unopened_within_14_days"


@lru_cache(maxsize=4)
def load_shop_data(data_dir: str = str(DATA_DIR)) -> ShopData:
    folder = Path(data_dir)
    products = _read_csv(folder / "products.csv")
    customers = {c["id"]: c for c in _read_csv(folder / "customers.csv")}
    orders = {o["order_id"]: o for o in _read_csv(folder / "orders.csv")}
    items: dict[str, list[dict]] = {}
    for line in _read_csv(folder / "order_items.csv"):
        items.setdefault(line["order_id"], []).append(line)
    events: dict[str, list[dict]] = {}
    for event in _read_csv(folder / "tracking_events.csv"):
        events.setdefault(event["tracking_id"], []).append(event)
    return ShopData(products, customers, orders, items, events)
