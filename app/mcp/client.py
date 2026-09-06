"""MCPClient — communicates with a single MCP server over stdio or HTTP.

Protocol: https://modelcontextprotocol.io/specification
We implement the minimal subset needed to list and call tools:
  - initialize / initialized handshake
  - tools/list
  - tools/call

Transport:
  - stdio: launch a subprocess, write JSON-RPC to stdin, read from stdout
  - http:  POST JSON-RPC to the server URL (stateless, no SSE for now)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_JSONRPC = "2.0"
_PROTOCOL_VERSION = "2024-11-05"


class MCPError(Exception):
    pass


class MCPClient:
    """Thin async client for one MCP server."""

    def __init__(
        self,
        server_id: str,
        transport: str,
        command: list[str] | None,
        url: str | None,
    ) -> None:
        self.server_id = server_id
        self._transport = transport  # "stdio" | "http"
        self._command = command or []
        self._url = url
        self._proc: asyncio.subprocess.Process | None = None
        self._http: httpx.AsyncClient | None = None
        self._seq = 0
        self._initialized = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._transport == "stdio":
            self._proc = await asyncio.create_subprocess_exec(
                *self._command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        else:
            self._http = httpx.AsyncClient(timeout=30)
        await self._initialize()

    async def stop(self) -> None:
        if self._proc:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except Exception:  # noqa: BLE001, S110
                logger.debug("mcp_proc_terminate_error", server=self.server_id)
        if self._http:
            await self._http.aclose()
        self._initialized = False

    # ── Public API ────────────────────────────────────────────────────────────

    async def list_tools(self) -> list[dict[str, Any]]:
        resp = await self._call("tools/list", {})
        tools: list[dict[str, Any]] = resp.get("tools", [])
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = await self._call(
            "tools/call", {"name": name, "arguments": arguments}
        )
        return result

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _initialize(self) -> None:
        await self._call(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "jarvis", "version": "0.1.0"},
            },
        )
        await self._notify("notifications/initialized")
        self._initialized = True
        logger.info("mcp_initialized", server=self.server_id, transport=self._transport)

    def _next_id(self) -> int:
        self._seq += 1
        return self._seq

    async def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        msg_id = self._next_id()
        payload = {"jsonrpc": _JSONRPC, "id": msg_id, "method": method, "params": params}
        raw = await self._send(payload)
        if "error" in raw:
            raise MCPError(f"MCP error from {self.server_id}: {raw['error']}")
        result: dict[str, Any] = raw.get("result", {})
        return result

    async def _notify(self, method: str) -> None:
        payload = {"jsonrpc": _JSONRPC, "method": method, "params": {}}
        if self._transport == "stdio" and self._proc and self._proc.stdin:
            line = json.dumps(payload) + "\n"
            self._proc.stdin.write(line.encode())
            await self._proc.stdin.drain()
        elif self._http and self._url:
            await self._http.post(self._url, json=payload)

    async def _send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._transport == "stdio":
            return await self._send_stdio(payload)
        return await self._send_http(payload)

    async def _send_stdio(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._proc or not self._proc.stdin or not self._proc.stdout:
            raise MCPError(f"MCP stdio process not running for {self.server_id}")
        line = json.dumps(payload) + "\n"
        self._proc.stdin.write(line.encode())
        await self._proc.stdin.drain()
        raw = await asyncio.wait_for(self._proc.stdout.readline(), timeout=30)
        result: dict[str, Any] = json.loads(raw.decode())
        return result

    async def _send_http(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._http or not self._url:
            raise MCPError(f"MCP HTTP client not configured for {self.server_id}")
        resp = await self._http.post(self._url, json=payload)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result
