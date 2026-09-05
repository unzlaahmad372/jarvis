"""AgentPlanner — multi-step task decomposition and tool execution.

Flow per turn:
  1. IntentRouter classifies the message.
  2. Planner selects zero or more tools appropriate for the intent.
  3. Tools are executed sequentially through ToolExecutor (PolicyEngine enforced).
  4. Tool results are assembled into ContextSlots for ContextBuilder.
  5. Orchestrator calls the LLM with the enriched context.

The LLM proposes; the PolicyEngine decides; the ToolExecutor runs.
The planner never bypasses the security boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.context_builder import ContextSlot
from app.brain.intent_router import Intent, IntentRouter
from app.core.config import Settings
from app.core.logging import get_logger
from app.tools.base import PolicyDecisionType, ToolRequest
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry

logger = get_logger(__name__)

PLANNER_VERSION = "1.0"


@dataclass
class PlanStep:
    """One executed step in a plan."""

    tool_name: str
    parameters: dict[str, object]
    success: bool
    output: str
    error: str | None = None
    policy_decision: str = "ALLOW"
    requires_confirmation: bool = False


@dataclass
class PlanResult:
    """Result of running a plan for one turn."""

    intent: Intent
    classification_method: str
    steps: list[PlanStep] = field(default_factory=list)
    tool_context_slots: list[ContextSlot] = field(default_factory=list)
    blocked: bool = False  # True if a required tool was denied/needs confirmation


# ── Intent → tool mapping ─────────────────────────────────────────────────────

# Maps intent to a list of (tool_name, parameter_builder_key).
# parameter_builder_key is used by _build_params to construct tool parameters
# from the user message.
_INTENT_TOOLS: dict[Intent, list[str]] = {
    Intent.SYSTEM_OPERATION: ["system_info", "disk_usage"],
    Intent.FILE_OPERATION: [],   # requires path extraction — skipped without explicit path
    Intent.AUTOMATION_OPERATION: [],  # REST API handles this; planner provides context only
    Intent.KNOWLEDGE_SEARCH: [],  # handled by RAG pipeline in orchestrator
    Intent.MEMORY_SEARCH: [],     # handled by memory pipeline in orchestrator
    Intent.GENERAL_CHAT: [],
}


class AgentPlanner:
    """Selects and executes tools for a given user message."""

    def __init__(
        self,
        registry: ToolRegistry,
        executor: ToolExecutor,
        settings: Settings,
    ) -> None:
        self._registry = registry
        self._executor = executor
        self._settings = settings
        self._router = IntentRouter()

    async def plan(
        self,
        message: str,
        session: AsyncSession,
    ) -> PlanResult:
        """Classify the message, run appropriate tools, return enriched context."""
        intent, method = self._router.route(message)
        result = PlanResult(intent=intent, classification_method=method)

        tool_names = _INTENT_TOOLS.get(intent, [])
        if not tool_names:
            return result

        for tool_name in tool_names:
            tool = self._registry.get(tool_name)
            if tool is None:
                continue

            params = self._build_params(tool_name, message)
            request = ToolRequest(tool_name=tool_name, parameters=params)

            tool_result, decision = await self._executor.execute(request, session)

            step = PlanStep(
                tool_name=tool_name,
                parameters=params,
                success=tool_result.success,
                output=tool_result.output,
                error=tool_result.error,
                policy_decision=decision.decision.value,
                requires_confirmation=decision.decision == PolicyDecisionType.REQUIRES_CONFIRMATION,
            )
            result.steps.append(step)

            if decision.decision == PolicyDecisionType.DENY:
                result.blocked = True
                logger.warning("plan_step_denied", tool=tool_name, reason=decision.reason)
                break

            if decision.decision == PolicyDecisionType.REQUIRES_CONFIRMATION:
                result.blocked = True
                logger.info("plan_step_needs_confirmation", tool=tool_name)
                break

            if tool_result.success and tool_result.output:
                slot = ContextSlot(
                    name=f"tool:{tool_name}",
                    content=f"[{tool_name} result]\n{tool_result.output}",
                    priority=3,  # between user message (2) and RAG (4)
                )
                result.tool_context_slots.append(slot)

        logger.info(
            "plan_complete",
            intent=intent,
            steps=len(result.steps),
            blocked=result.blocked,
        )
        return result

    def _build_params(self, tool_name: str, message: str) -> dict[str, object]:
        """Build tool parameters from the user message."""
        if tool_name == "disk_usage":
            return {"path": "."}
        return {}
