"""MCP API routes — read-only introspection of connected MCP servers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.mcp.registry import get_mcp_registry

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


class MCPServerOut(BaseModel):
    id: str
    tool_count: int
    tools: list[str]


class MCPToolOut(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


@router.get("/servers", response_model=list[MCPServerOut])
async def list_mcp_servers() -> list[MCPServerOut]:
    return [MCPServerOut(**s) for s in get_mcp_registry().list_servers()]


@router.get("/servers/{server_id}/tools", response_model=list[MCPToolOut])
async def list_server_tools(server_id: str) -> list[MCPToolOut]:
    tools = get_mcp_registry().get_server_tools(server_id)
    if tools is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")
    return [
        MCPToolOut(
            name=t.get("name", ""),
            description=t.get("description", ""),
            input_schema=t.get("inputSchema", {}),
        )
        for t in tools
    ]
