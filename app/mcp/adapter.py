"""MCPToolAdapter — wraps a remote MCP tool as a JARVIS Tool.

Each tool discovered from an MCP server gets one adapter instance.
Risk level is always READ_ONLY by default; operators can override per-server
via the mcp_servers config (risk_level field).
"""

from __future__ import annotations

from typing import Any

from app.mcp.client import MCPClient
from app.tools.base import RiskLevel, Tool, ToolResult


class MCPToolAdapter(Tool):
    """Adapts a single MCP tool to the JARVIS Tool interface."""

    def __init__(
        self,
        client: MCPClient,
        tool_def: dict[str, Any],
        risk_level: RiskLevel = RiskLevel.READ_ONLY,
    ) -> None:
        self._client = client
        self._tool_def = tool_def
        self._risk = risk_level
        # Prefix name with server id to avoid collisions
        self._name = f"mcp.{client.server_id}.{tool_def['name']}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        desc: str = self._tool_def.get("description", f"MCP tool from {self._client.server_id}")
        return desc

    @property
    def risk_level(self) -> RiskLevel:
        return self._risk

    @property
    def parameters_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = self._tool_def.get("inputSchema", {})
        return schema

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        try:
            result = await self._client.call_tool(self._tool_def["name"], parameters)
            # MCP returns content array; flatten to string
            content = result.get("content", [])
            if isinstance(content, list):
                text = "\n".join(
                    c.get("text", str(c)) for c in content if isinstance(c, dict)
                ) or str(result)
            else:
                text = str(content)
            return ToolResult(tool_name=self.name, success=True, output=text)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))
