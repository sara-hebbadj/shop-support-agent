"""Shared test fixtures. Tests never use the network or a real model."""

from __future__ import annotations

import socket

import pytest

from shop_support_agent.agent import SupportAgent
from shop_support_agent.crm import CrmStore
from shop_support_agent.crm_server import CrmMcpClient, build_server
from shop_support_agent.data import load_shop_data
from shop_support_agent.llm import FakeLLM, Tracer


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    """Fail loudly if any test tries to open a network connection; keep runtime files in tmp."""
    def blocked(*args, **kwargs):
        raise RuntimeError("network access is not allowed in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setenv("SHOP_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("TRACES_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.delenv("COURIER_API_URL", raising=False)


@pytest.fixture
def shop():
    return load_shop_data()


@pytest.fixture
def store(tmp_path, shop):
    return CrmStore(tmp_path / "crm", shop)


@pytest.fixture
def crm(store):
    return CrmMcpClient(build_server(store))


@pytest.fixture
def make_agent(crm, tmp_path):
    """Build an agent with the offline FakeLLM, or with a custom fake model."""
    def factory(llm=None):
        return SupportAgent(llm=llm or FakeLLM(Tracer(path=tmp_path / "traces.jsonl")), crm=crm)
    return factory


def find_order(shop, status, min_total=0, max_total=10_000, delivered_after=None):
    """First order with the given properties (data is fixed by seed 42)."""
    for order in shop.orders.values():
        total = int(order["total_aed"])
        if order["status"] != status or not min_total <= total <= max_total:
            continue
        if delivered_after and order["delivered_date"] < delivered_after:
            continue
        return order, shop.customers[order["customer_id"]]
    raise LookupError("no matching order")
