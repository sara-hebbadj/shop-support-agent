"""A tiny generic CRM with an approval queue, stored in JSON files.

Shape is similar to a real CRM (customers, notes, tickets), but it is generic and
fully local. Money and data changes never happen directly: request_refund and
update_address only *queue* an approval item. The change is applied in decide(),
which only a human reviewer calls (from the Approvals tab).
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from .config import REFUND_ESCALATION_AED, runtime_dir
from .data import ShopData, load_shop_data

EMPTY_STATE = {"notes": [], "tickets": [], "approvals": [], "address_overrides": {}, "refunds": []}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def approval_level(action: str, amount_aed: float = 0) -> str:
    """Who must approve: 'supervisor' for refunds above AED 200, otherwise 'team'."""
    if action == "refund" and amount_aed > REFUND_ESCALATION_AED:
        return "supervisor"
    return "team"


class CrmStore:
    def __init__(self, folder: Path | None = None, shop: ShopData | None = None):
        self.folder = Path(folder) if folder else runtime_dir()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.state_path = self.folder / "crm_state.json"
        self.audit_path = self.folder / "approval_log.jsonl"
        self.shop = shop or load_shop_data()
        self.lock = threading.Lock()

    # ---------------- storage ----------------
    def _load(self) -> dict:
        if not self.state_path.exists():
            return json.loads(json.dumps(EMPTY_STATE))  # deep copy
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save(self, state: dict) -> None:
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    def _audit(self, record: dict) -> None:
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def reset(self) -> None:
        with self.lock:
            self._save(json.loads(json.dumps(EMPTY_STATE)))

    # ---------------- read tools ----------------
    def get_customer(self, customer_id: str) -> dict:
        customer = self.shop.customers.get(customer_id)
        if not customer:
            return {"ok": False, "error": "customer not found"}
        state = self._load()
        orders = [
            {"order_id": o["order_id"], "status": o["status"], "order_date": o["order_date"]}
            for o in self.shop.orders.values() if o["customer_id"] == customer_id
        ]
        return {
            "ok": True,
            "customer_id": customer_id,
            "name": customer["name"],
            "email": customer["email"],
            "language": customer["language"],
            "city": customer["city"],
            "country": customer["country"],
            "address": state["address_overrides"].get(customer_id, customer["address"]),
            "orders": orders,
            "notes": [n for n in state["notes"] if n["customer_id"] == customer_id][-5:],
            "open_tickets": [t["ticket_id"] for t in state["tickets"] if t["customer_id"] == customer_id],
        }

    # ---------------- write tools that need no approval ----------------
    def add_note(self, customer_id: str, note: str, author: str = "ai_assistant") -> dict:
        with self.lock:
            state = self._load()
            record = {"note_id": f"N-{len(state['notes']) + 1:04d}", "customer_id": customer_id,
                      "note": note[:1000], "author": author, "created_at": now()}
            state["notes"].append(record)
            self._save(state)
        return {"ok": True, **record}

    def create_ticket(self, customer_id: str | None, subject: str, summary: str,
                      priority: str = "normal") -> dict:
        with self.lock:
            state = self._load()
            record = {"ticket_id": f"T-{len(state['tickets']) + 1:04d}", "customer_id": customer_id,
                      "subject": subject[:200], "summary": summary[:2000],
                      "priority": priority if priority in ("low", "normal", "high") else "normal",
                      "status": "open", "created_at": now()}
            state["tickets"].append(record)
            self._save(state)
        return {"ok": True, **record}

    # ---------------- write tools that only queue an approval ----------------
    def _queue(self, action: str, order_id: str, customer_id: str, details: dict, amount: float = 0) -> dict:
        with self.lock:
            state = self._load()
            # Idempotency: the same pending request is never queued twice.
            for item in state["approvals"]:
                if (item["action"], item["order_id"], item["status"]) == (action, order_id, "pending"):
                    return {"ok": True, "duplicate": True, **item}
            item = {
                "approval_id": f"A-{len(state['approvals']) + 1:04d}",
                "action": action,
                "order_id": order_id,
                "customer_id": customer_id,
                "amount_aed": amount,
                "details": details,
                "level": approval_level(action, amount),
                "status": "pending",
                "created_at": now(),
                "decided_by": None,
                "decided_at": None,
            }
            state["approvals"].append(item)
            self._save(state)
        self._audit({"event": "queued", **item})
        return {"ok": True, **item}

    def request_refund(self, order_id: str, customer_id: str, amount_aed: float, reason: str) -> dict:
        order = self.shop.orders.get(order_id)
        if not order or order["customer_id"] != customer_id:
            return {"ok": False, "error": "order does not belong to this customer"}
        if not 0 < amount_aed <= int(order["total_aed"]):
            return {"ok": False, "error": "refund amount must be between 0 and the order total"}
        return self._queue("refund", order_id, customer_id, {"reason": reason[:300]}, float(amount_aed))

    def update_address(self, order_id: str, customer_id: str, new_address: str) -> dict:
        order = self.shop.orders.get(order_id)
        if not order or order["customer_id"] != customer_id:
            return {"ok": False, "error": "order does not belong to this customer"}
        if order["status"] != "processing":
            return {"ok": False, "error": f"address can only change before shipping (status: {order['status']})"}
        if len(new_address.strip()) < 8:
            return {"ok": False, "error": "new address is too short"}
        return self._queue("address_change", order_id, customer_id, {"new_address": new_address.strip()[:300]})

    # ---------------- human decisions ----------------
    def list_approvals(self, status: str | None = None) -> list[dict]:
        items = self._load()["approvals"]
        return [i for i in items if status is None or i["status"] == status]

    def decide(self, approval_id: str, approve: bool, reviewer: str, role: str = "team") -> dict:
        """Apply a human decision. Safe to call twice: a decided item is never applied again."""
        with self.lock:
            state = self._load()
            item = next((i for i in state["approvals"] if i["approval_id"] == approval_id), None)
            if item is None:
                return {"ok": False, "error": "approval not found"}
            if item["status"] != "pending":
                return {"ok": True, "already_decided": True, **item}
            if approve and item["level"] == "supervisor" and role != "supervisor":
                return {"ok": False, "error": "refunds above AED 200 need a supervisor"}
            item["status"] = "approved" if approve else "denied"
            item["decided_by"] = f"{reviewer} ({role})"
            item["decided_at"] = now()
            if approve and item["action"] == "address_change":
                state["address_overrides"][item["customer_id"]] = item["details"]["new_address"]
            if approve and item["action"] == "refund":
                state["refunds"].append({"approval_id": approval_id, "order_id": item["order_id"],
                                         "amount_aed": item["amount_aed"], "status": "scheduled"})
            self._save(state)
        self._audit({"event": "decided", **item})
        return {"ok": True, **item}
