"""AgentPlanner — multi-step task decomposition and tool execution.

Flow per turn:
  1. TaskDecomposer splits the message into ordered sub-tasks.
  2. Each sub-task selects tools appropriate for its intent.
  3. Tools are executed sequentially through ToolExecutor (PolicyEngine enforced).
  4. Tool results are assembled into ContextSlots for ContextBuilder.
  5. Orchestrator calls the LLM with the enriched context.

The LLM proposes; the PolicyEngine decides; the ToolExecutor runs.
The planner never bypasses the security boundary.

Confirmation flow (spec §71):
  - When a tool requires confirmation, a PendingConfirmation is created.
  - The confirmation_id is returned to the caller.
  - On the next request, the caller supplies confirmation_id in ToolRequest.
  - ConfirmationStore.consume() verifies digest + expiry before allowing execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.confirmation import ConfirmationStore, get_confirmation_store
from app.brain.context_builder import ContextSlot
from app.brain.intent_router import Intent
from app.brain.task_decomposer import decompose
from app.core.config import Settings
from app.core.logging import get_logger
from app.tools.base import PolicyDecisionType, ToolRequest
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry

logger = get_logger(__name__)

PLANNER_VERSION = "2.0"


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
    confirmation_id: str | None = None  # set when confirmation is pending


@dataclass
class PlanResult:
    """Result of running a plan for one turn."""

    intent: Intent
    classification_method: str
    steps: list[PlanStep] = field(default_factory=list)
    tool_context_slots: list[ContextSlot] = field(default_factory=list)
    blocked: bool = False  # True if a required tool was denied/needs confirmation
    sub_tasks: int = 1  # number of sub-tasks decomposed


class AgentPlanner:
    """Selects and executes tools for a given user message."""

    def __init__(
        self,
        registry: ToolRegistry,
        executor: ToolExecutor,
        settings: Settings,
        confirmation_store: ConfirmationStore | None = None,
    ) -> None:
        self._registry = registry
        self._executor = executor
        self._settings = settings
        self._confirmation_store = confirmation_store or get_confirmation_store()

    async def plan(
        self,
        message: str,
        session: AsyncSession,
    ) -> PlanResult:
        """Decompose the message into sub-tasks, run tools, return enriched context."""
        sub_tasks = decompose(message)

        # Primary intent = first sub-task's intent
        primary = sub_tasks[0]
        result = PlanResult(
            intent=primary.intent,
            classification_method=primary.classification_method,
            sub_tasks=len(sub_tasks),
        )

        for task in sub_tasks:
            if not task.tool_names:
                continue

            for tool_name in task.tool_names:
                tool = self._registry.get(tool_name)
                if tool is None:
                    continue

                params = self._build_params(tool_name, message)
                request = ToolRequest(tool_name=tool_name, parameters=params)

                tool_result, decision = await self._executor.execute(request, session)

                confirmation_id: str | None = None
                if decision.decision == PolicyDecisionType.REQUIRES_CONFIRMATION:
                    pending = self._confirmation_store.create(
                        tool_name=tool_name,
                        parameters=params,
                        risk_level=decision.risk_level.value,
                        policy_rule=decision.policy_rule,
                    )
                    confirmation_id = pending.confirmation_id

                step = PlanStep(
                    tool_name=tool_name,
                    parameters=params,
                    success=tool_result.success,
                    output=tool_result.output,
                    error=tool_result.error,
                    policy_decision=decision.decision.value,
                    requires_confirmation=(
                        decision.decision == PolicyDecisionType.REQUIRES_CONFIRMATION
                    ),
                    confirmation_id=confirmation_id,
                )
                result.steps.append(step)

                if decision.decision == PolicyDecisionType.DENY:
                    result.blocked = True
                    logger.warning("plan_step_denied", tool=tool_name, reason=decision.reason)
                    break

                if decision.decision == PolicyDecisionType.REQUIRES_CONFIRMATION:
                    result.blocked = True
                    logger.info(
                        "plan_step_needs_confirmation",
                        tool=tool_name,
                        confirmation_id=confirmation_id,
                    )
                    break

                if tool_result.success and tool_result.output:
                    slot = ContextSlot(
                        name=f"tool:{tool_name}",
                        content=f"[{tool_name} result]\n{tool_result.output}",
                        priority=3,  # between user message (2) and RAG (4)
                    )
                    result.tool_context_slots.append(slot)

            if result.blocked:
                break

        logger.info(
            "plan_complete",
            intent=result.intent,
            sub_tasks=result.sub_tasks,
            steps=len(result.steps),
            blocked=result.blocked,
        )
        return result

    def _build_params(self, tool_name: str, message: str) -> dict[str, object]:
        """Build tool parameters from the user message."""
        if tool_name == "disk_usage":
            return {"path": "."}
        return {}
