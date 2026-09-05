"""ToolRegistry — central register of all available JARVIS tools."""

from __future__ import annotations

from app.core.logging import get_logger
from app.tools.base import RiskLevel, Tool

logger = get_logger(__name__)


class ToolRegistry:
    """Holds all registered tools. Tools register themselves at startup."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        logger.info("tool_registered", name=tool.name, risk=tool.risk_level)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self, max_risk: RiskLevel | None = None) -> list[Tool]:
        tools = list(self._tools.values())
        if max_risk is None:
            return tools
        order = [RiskLevel.READ_ONLY, RiskLevel.LOW_RISK, RiskLevel.SENSITIVE, RiskLevel.DANGEROUS]
        cutoff = order.index(max_risk)
        return [t for t in tools if order.index(t.risk_level) <= cutoff]

    def names(self) -> list[str]:
        return list(self._tools.keys())


# Module-level singleton — populated at startup
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_registry() -> None:
    """Reset registry — used in tests only."""
    global _registry
    _registry = None
