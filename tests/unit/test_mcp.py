"""Tests for Phase 13 — MCP client, adapter, registry, and route."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp.adapter import MCPToolAdapter
from app.mcp.client import MCPClient, MCPError
from app.mcp.registry import MCPServerRegistry, reset_mcp_registry
from app.tools.base import RiskLevel
from app.tools.registry import ToolRegistry

# ── MCPClient ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_client_http_list_tools() -> None:
    client = MCPClient(server_id="test", transport="http", command=None, url="http://localhost:9000/mcp")

    responses = [
        # initialize response
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": "2024-11-05", "capabilities": {}},
        },
        # tools/list response
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"tools": [{"name": "echo", "description": "Echo tool", "inputSchema": {}}]},
        },
    ]
    call_count = 0

    async def fake_post(url: str, json: Any = None, **kwargs: Any) -> MagicMock:
        nonlocal call_count
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = responses[call_count]
        resp.raise_for_status = MagicMock()
        call_count += 1
        return resp

    mock_http = AsyncMock()
    mock_http.post = fake_post
    mock_http.aclose = AsyncMock()
    client._http = mock_http

    # Skip actual start, manually call _initialize
    with patch.object(client, "_notify", new=AsyncMock()):
        await client._initialize()

    tools = await client.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"


@pytest.mark.asyncio
async def test_mcp_client_error_response_raises() -> None:
    client = MCPClient(server_id="test", transport="http", command=None, url="http://localhost:9000/mcp")

    async def fake_post(url: str, json: Any = None, **kwargs: Any) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32600, "message": "Invalid"},
        }
        resp.raise_for_status = MagicMock()
        return resp

    mock_http = AsyncMock()
    mock_http.post = fake_post
    client._http = mock_http

    with pytest.raises(MCPError, match="MCP error"):
        await client._call("tools/list", {})


# ── MCPToolAdapter ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_adapter_name_prefixed() -> None:
    client = MCPClient(server_id="myserver", transport="http", command=None, url=None)
    tool_def = {"name": "search", "description": "Search tool", "inputSchema": {}}
    adapter = MCPToolAdapter(client, tool_def, RiskLevel.READ_ONLY)
    assert adapter.name == "mcp.myserver.search"
    assert adapter.risk_level == RiskLevel.READ_ONLY


@pytest.mark.asyncio
async def test_mcp_adapter_execute_success() -> None:
    client = MCPClient(server_id="s", transport="http", command=None, url=None)
    client.call_tool = AsyncMock(return_value={"content": [{"text": "hello world"}]})  # type: ignore[method-assign]
    tool_def = {"name": "greet", "description": "", "inputSchema": {}}
    adapter = MCPToolAdapter(client, tool_def)
    result = await adapter.execute({"name": "Alice"})
    assert result.success
    assert "hello world" in result.output


@pytest.mark.asyncio
async def test_mcp_adapter_execute_error() -> None:
    client = MCPClient(server_id="s", transport="http", command=None, url=None)
    client.call_tool = AsyncMock(side_effect=Exception("connection refused"))  # type: ignore[method-assign]
    tool_def = {"name": "fail", "description": "", "inputSchema": {}}
    adapter = MCPToolAdapter(client, tool_def)
    result = await adapter.execute({})
    assert not result.success
    assert "connection refused" in (result.error or "")


# ── MCPServerRegistry ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_registry_empty_config() -> None:
    reset_mcp_registry()
    reg = MCPServerRegistry()
    tool_reg = ToolRegistry()
    await reg.start_all("", tool_reg)
    assert reg.list_servers() == []


@pytest.mark.asyncio
async def test_registry_invalid_json() -> None:
    reset_mcp_registry()
    reg = MCPServerRegistry()
    tool_reg = ToolRegistry()
    await reg.start_all("not-json", tool_reg)  # should not raise
    assert reg.list_servers() == []


@pytest.mark.asyncio
async def test_registry_server_failure_skipped() -> None:
    reset_mcp_registry()
    reg = MCPServerRegistry()
    tool_reg = ToolRegistry()
    config = json.dumps([{"id": "bad", "transport": "http", "url": "http://127.0.0.1:1/mcp"}])
    await reg.start_all(config, tool_reg)  # connection refused — should not raise
    assert reg.list_servers() == []


@pytest.mark.asyncio
async def test_registry_get_unknown_server() -> None:
    reset_mcp_registry()
    reg = MCPServerRegistry()
    assert reg.get_server_tools("nonexistent") is None


@pytest.mark.asyncio
async def test_registry_stop_all_empty() -> None:
    reset_mcp_registry()
    reg = MCPServerRegistry()
    await reg.stop_all()  # should not raise


# ── MCP API route ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_route_list_servers(test_client: Any) -> None:
    from app.mcp.registry import reset_mcp_registry
    reset_mcp_registry()
    resp = await test_client.get("/api/v1/mcp/servers")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_mcp_route_unknown_server_404(test_client: Any) -> None:
    from app.mcp.registry import reset_mcp_registry
    reset_mcp_registry()
    resp = await test_client.get("/api/v1/mcp/servers/nonexistent/tools")
    assert resp.status_code == 404
