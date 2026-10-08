"""The FastAPI orders + courier mock and its client."""

from __future__ import annotations

import httpx
from conftest import find_order
from fastapi.testclient import TestClient

from shop_support_agent.courier_api import CourierClient, app

client = TestClient(app)


def test_get_order(shop):
    order, _ = find_order(shop, "shipped")
    response = client.get(f"/orders/{order['order_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "shipped" and body["tracking_id"] == order["tracking_id"]
    assert sum(i["qty"] * i["unit_price_aed"] for i in body["items"]) == body["total_aed"]
    assert "email" not in body  # the courier API never returns customer contact data


def test_unknown_order_is_404():
    assert client.get("/orders/LS-99999").status_code == 404


def test_tracking_events_are_in_time_order(shop):
    order, _ = find_order(shop, "delivered")
    body = client.get(f"/tracking/{order['tracking_id']}").json()
    times = [e["timestamp"] for e in body["events"]]
    assert times == sorted(times)
    assert body["latest"]["event"] == "delivered"
    assert client.get("/tracking/TRK0000000").status_code == 404


def test_client_runs_in_process_without_network(shop):
    order, _ = find_order(shop, "processing")
    courier = CourierClient()
    assert courier.get_order(order["order_id"])["tracking_id"] is None
    assert courier.get_order("LS-99999") is None


def test_client_retries_a_server_error():
    calls = []

    def flaky(request):
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"order_id": "LS-10001"})

    courier = CourierClient(base_url="http://courier.test")
    courier.http = httpx.Client(base_url="http://courier.test", transport=httpx.MockTransport(flaky))
    assert courier.get_order("LS-10001") == {"order_id": "LS-10001"}
    assert len(calls) == 2
