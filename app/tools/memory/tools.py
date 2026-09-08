"""Memory search tool — explicit tool wrapper around memory manager search.

Allows the AgentPlanner to invoke memory search as a named tool when the
MEMORY_SEARCH intent is detected, rather than relying solely on the implicit
search that runs for every turn in the orchestrator.
"""

from __future__ import annotations

import json
from typing import Any

from app.tools.base import RiskLevel, Tool, ToolResult


class MemorySearchTool(Tool):
    """Search long-term memories by query string."""

    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return (
            "Search long-term memories for information matching a query. "
            "Returns matching memory entries with category and importance."
        )

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "query": {"type": "string", "description": "Search query"},
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default 10)",
                "default": 10,
            },
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        from app.db.database import get_session_factory
        from app.memory.manager import search_memories

        query = str(parameters.get("query", "")).strip()
        if not query:
            return ToolResult(
                tool_name=self.name, success=False, output="", error="query is required"
            )
        limit = int(parameters.get("limit", 10))

        try:
            factory = get_session_factory()
            async with factory() as session:
                memories = await search_memories(session, query, limit=limit)
                results = [
                    {
                        "id": m.id,
                        "content": m.content,
                        "category": m.category,
                        "importance": m.importance,
                        "source": m.source,
                    }
                    for m in memories
                ]
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=json.dumps({"query": query, "results": results}),
            )
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))
