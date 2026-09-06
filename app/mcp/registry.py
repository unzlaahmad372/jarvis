"""MCPServerRegistry — manages lifecycle of all configured MCP servers.

Config format (JARVIS_MCP_SERVERS env var, JSON array):
  [
    {
      "id": "filesystem",
      "transport": "stdio",
      "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "risk_level": "READ_ONLY"
    },
    {
      "id": "my-api",
      "transport": "http",
      "url": "http://127.0.0.1:9000/mcp",
      "risk_level": "LOW_RISK"
    }
  ]
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.mcp.adapter import MCPToolAdapter
from app.mcp.client import MCPClient, MCPError
from app.tools.base import RiskLevel
from app.tools.registry import ToolRegistry

logger = get_logger(__name__)

_RISK_MAP: dict[str, RiskLevel] = {
    "READ_ONLY": RiskLevel.READ_ONLY,
    "LOW_RISK": RiskLevel.LOW_RISK,
    "SENSITIVE": RiskLevel.SENSITIVE,
    "DANGEROUS": RiskLevel.DANGEROUS,
}


class MCPServerRegistry:
    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._server_tools: dict[str, list[dict[str, Any]]] = {}

    async def start_all(self, mcp_servers_json: str, tool_registry: ToolRegistry) -> None:
        if not mcp_servers_json.strip():
            return
        try:
            configs: list[dict[str, Any]] = json.loads(mcp_servers_json)
        except json.JSONDecodeError:
            logger.error("mcp_servers_invalid_json")
            return

        for cfg in configs:
            server_id = cfg.get("id", "unknown")
            transport = cfg.get("transport", "stdio")
            command = cfg.get("command")
            url = cfg.get("url")
            risk = _RISK_MAP.get(cfg.get("risk_level", "READ_ONLY"), RiskLevel.READ_ONLY)

            client = MCPClient(server_id=server_id, transport=transport, command=command, url=url)
            try:
                await client.start()
                tools = await client.list_tools()
                self._clients[server_id] = client
                self._server_tools[server_id] = tools
                for tool_def in tools:
                    adapter = MCPToolAdapter(client, tool_def, risk)
                    try:
                        tool_registry.register(adapter)
                    except ValueError:
                        logger.warning("mcp_tool_already_registered", name=adapter.name)
                logger.info("mcp_server_started", server=server_id, tools=len(tools))
            except (MCPError, Exception) as exc:  # noqa: BLE001
                logger.error("mcp_server_failed", server=server_id, error=str(exc))

    async def stop_all(self) -> None:
        for server_id, client in self._clients.items():
            try:
                await client.stop()
                logger.info("mcp_server_stopped", server=server_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("mcp_server_stop_error", server=server_id, error=str(exc))
        self._clients.clear()
        self._server_tools.clear()

    def list_servers(self) -> list[dict[str, Any]]:
        return [
            {
                "id": sid,
                "tool_count": len(self._server_tools.get(sid, [])),
                "tools": [t.get("name") for t in self._server_tools.get(sid, [])],
            }
            for sid in self._clients
        ]

    def get_server_tools(self, server_id: str) -> list[dict[str, Any]] | None:
        if server_id not in self._clients:
            return None
        return self._server_tools.get(server_id, [])


# Module-level singleton
_mcp_registry: MCPServerRegistry | None = None


def get_mcp_registry() -> MCPServerRegistry:
    global _mcp_registry
    if _mcp_registry is None:
        _mcp_registry = MCPServerRegistry()
    return _mcp_registry


def reset_mcp_registry() -> None:
    global _mcp_registry
    _mcp_registry = None
