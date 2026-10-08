"""CRM exposed as an MCP server (official `mcp` Python SDK, v2).

`MCPServer` is the v2 name of FastMCP: same decorator style (@server.tool()).

Run over stdio (for MCP Inspector or Claude Desktop):
    python -m shop_support_agent.crm_server
Inspect it:
    npx @modelcontextprotocol/inspector python -m shop_support_agent.crm_server

The agent calls these tools through CrmMcpClient, which speaks real MCP to the
server in-process (no subprocess, no network).
"""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache

from mcp import Client
from mcp.server.mcpserver import MCPServer

from .crm import CrmStore


@lru_cache(maxsize=1)
def default_store() -> CrmStore:
    return CrmStore()


def build_server(store: CrmStore | None = None) -> MCPServer:
    server = MCPServer(
        "lumi-crm",
        instructions="CRM for the fictional Lumi Skin shop. Refunds and address changes are only "
        "queued for human approval; these tools never move money or change data on their own.",
    )

    def crm() -> CrmStore:
        return store or default_store()

    @server.tool()
    def get_customer(customer_id: str) -> dict:
        """Get a customer's profile, orders, recent notes and open tickets."""
        return crm().get_customer(customer_id)

    @server.tool()
    def add_note(customer_id: str, note: str) -> dict:
        """Add an internal note to a customer's record."""
        return crm().add_note(customer_id, note)

    @server.tool()
    def create_ticket(customer_id: str, subject: str, summary: str, priority: str = "normal") -> dict:
        """Open a support ticket for the human team (used for handover and complaints)."""
        return crm().create_ticket(customer_id or None, subject, summary, priority)

    @server.tool()
    def request_refund(order_id: str, customer_id: str, amount_aed: float, reason: str) -> dict:
        """Queue a refund for human approval. Refunds above AED 200 need a supervisor. Never pays out."""
        return crm().request_refund(order_id, customer_id, amount_aed, reason)

    @server.tool()
    def update_address(order_id: str, customer_id: str, new_address: str) -> dict:
        """Queue a delivery-address change for human approval (only before the order ships)."""
        return crm().update_address(order_id, customer_id, new_address)

    return server


server = build_server()


class CrmMcpClient:
    """Synchronous wrapper so the (synchronous) LangGraph nodes can call MCP tools."""

    def __init__(self, mcp_server: MCPServer | None = None):
        self.server = mcp_server or server

    async def _call(self, tool: str, arguments: dict) -> dict:
        async with Client(self.server) as client:
            result = await client.call_tool(tool, arguments)
        text = result.content[0].text if result.content else "{}"
        if result.is_error:
            return {"ok": False, "error": text}
        return json.loads(text)

    def call(self, tool: str, **arguments) -> dict:
        return asyncio.run(self._call(tool, arguments))

    async def list_tool_names(self) -> list[str]:
        async with Client(self.server) as client:
            listing = await client.list_tools()
        return [tool.name for tool in listing.tools]


if __name__ == "__main__":
    server.run()  # stdio transport by default
