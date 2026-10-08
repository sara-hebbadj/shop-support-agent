"""Mock orders + courier API (FastAPI).

Run it as a real server:   uvicorn shop_support_agent.courier_api:app --port 8001
The agent talks to it over HTTP through CourierClient. If COURIER_API_URL is not
set, CourierClient calls the same app in-process (no network), which is what the
tests, the evals and the offline demo use.

This API is "internal": it trusts its caller. Checking that a customer may see an
order happens in the agent's verify step, before this API is ever called.
"""

from __future__ import annotations

import logging
import time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from .config import env
from .data import load_shop_data

# Keep per-request logs out of the console (Starlette's TestClient logs through "httpx2").
for _name in ("httpx", "httpx2"):
    logging.getLogger(_name).setLevel(logging.WARNING)

app = FastAPI(title="Lumi Skin orders + courier mock", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/orders/{order_id}")
def get_order(order_id: str) -> dict:
    order = load_shop_data().order_view(order_id.upper())
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order


@app.get("/tracking/{tracking_id}")
def get_tracking(tracking_id: str) -> dict:
    events = load_shop_data().tracking_events(tracking_id.upper())
    if not events:
        raise HTTPException(status_code=404, detail="tracking ID not found")
    return {"tracking_id": tracking_id.upper(), "latest": events[-1], "events": events}


class CourierClient:
    """HTTP client for the mock API, with a small retry for network blips and 5xx errors."""

    def __init__(self, base_url: str | None = None, retries: int = 2):
        base_url = base_url if base_url is not None else env("COURIER_API_URL")
        self.http = httpx.Client(base_url=base_url, timeout=5.0) if base_url else TestClient(app)
        self.retries = retries

    def _get(self, path: str) -> dict | None:
        for attempt in range(self.retries + 1):
            try:
                response = self.http.get(path)
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
                time.sleep(0.2 * (attempt + 1))
                continue
            if response.status_code == 404:
                return None
            if response.status_code >= 500 and attempt < self.retries:
                time.sleep(0.2 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        return None

    def get_order(self, order_id: str) -> dict | None:
        return self._get(f"/orders/{order_id}")

    def get_tracking(self, tracking_id: str) -> dict | None:
        return self._get(f"/tracking/{tracking_id}")
