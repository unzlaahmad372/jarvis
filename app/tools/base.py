"""Tool base types — RiskLevel, Tool ABC, ToolResult, PolicyDecision.

The LLM proposes tool calls. The deterministic PolicyEngine decides whether
they are allowed. The ToolExecutor runs them and writes the audit log.
The LLM is never the security boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    READ_ONLY = "READ_ONLY"
    LOW_RISK = "LOW_RISK"
    SENSITIVE = "SENSITIVE"
    DANGEROUS = "DANGEROUS"


class PolicyDecisionType(StrEnum):
    ALLOW = "ALLOW"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"
    DENY = "DENY"


@dataclass
class ToolRequest:
    """A request to execute a named tool with parameters."""

    tool_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    confirmation_id: str | None = None  # set when user has confirmed a SENSITIVE action


@dataclass
class ToolResult:
    """Result of a tool execution."""

    tool_name: str
    success: bool
    output: str  # always a string; structured data is JSON-serialised
    error: str | None = None
    truncated: bool = False


@dataclass
class PolicyDecision:
    """Deterministic policy decision for a tool request."""

    decision: PolicyDecisionType
    risk_level: RiskLevel
    tool_name: str
    policy_rule: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision == PolicyDecisionType.ALLOW

    @property
    def requires_confirmation(self) -> bool:
        return self.decision == PolicyDecisionType.REQUIRES_CONFIRMATION


class Tool(ABC):
    """Abstract base for all JARVIS tools.

    Every tool must declare its name, description, risk level, and
    parameter schema. The LLM sees only the name, description, and schema.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def risk_level(self) -> RiskLevel: ...

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """JSON-Schema-style dict describing accepted parameters."""
        ...

    @abstractmethod
    async def execute(self, parameters: dict[str, Any]) -> ToolResult: ...
