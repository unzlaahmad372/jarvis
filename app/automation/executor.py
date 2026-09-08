"""AutomationExecutor — runs scheduled jobs through the policy/tool stack.

Safety rules (non-negotiable):
- Permission ceiling is enforced before every tool call.
- SENSITIVE/DANGEROUS tools are never auto-approved by the scheduler.
- Execution records are persisted to AutomationExecution regardless of outcome.
- Chat jobs run through ChatOrchestrator so all context/policy paths apply.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.automation import jobs as job_service
from app.automation.scheduler import (
    CEILING_LOW_RISK,
    CEILING_READ_ONLY,
    AutomationScheduler,
    JobSpec,
)
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.brain.orchestrator import ChatOrchestrator
    from app.tools.executor import ToolExecutor
    from app.tools.registry import ToolRegistry

logger = get_logger(__name__)

# Risk levels allowed per ceiling
_CEILING_ALLOWED: dict[str, set[str]] = {
    CEILING_READ_ONLY: {"READ_ONLY"},
    CEILING_LOW_RISK: {"READ_ONLY", "LOW_RISK"},
}


class AutomationExecutor:
    """Executes automation jobs respecting permission ceilings."""

    def __init__(
        self,
        scheduler: AutomationScheduler,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        orchestrator: ChatOrchestrator,
        session_factory: Any,
    ) -> None:
        self._scheduler = scheduler
        self._registry = tool_registry
        self._executor = tool_executor
        self._orchestrator = orchestrator
        self._session_factory = session_factory

    async def run_job(self, job_name: str, payload: dict[str, Any]) -> None:
        """Entry point called by APScheduler on each job fire."""
        from sqlalchemy import select

        from app.db.models import AutomationJob

        async with self._session_factory() as session:
            result = await session.execute(
                select(AutomationJob).where(AutomationJob.name == job_name)
            )
            job = result.scalar_one_or_none()
            if job is None or not job.enabled:
                logger.warning("automation_job_not_found_or_disabled", name=job_name)
                return

            exec_rec = await job_service.record_execution_start(
                session, job, scheduled_time=datetime.now(UTC)
            )

            try:
                action_type = job.action_type
                action_payload: dict[str, Any] = json.loads(job.action_payload)
                ceiling = job.permission_ceiling

                if action_type == "tool":
                    summary = await self._run_tool_job(action_payload, ceiling, session)
                elif action_type == "chat":
                    summary = await self._run_chat_job(action_payload, session)
                else:
                    raise ValueError(f"Unknown action_type: {action_type!r}")

                job.last_run_at = datetime.now(UTC)
                await job_service.record_execution_end(
                    session, exec_rec, status="SUCCESS", result_summary=summary
                )
                logger.info("automation_job_success", name=job_name, summary=summary[:200])

            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                await job_service.record_execution_end(
                    session, exec_rec, status="FAILED", error=error
                )
                logger.error("automation_job_failed", name=job_name, error=error)

    async def _run_tool_job(
        self,
        payload: dict[str, Any],
        ceiling: str,
        session: Any,
    ) -> str:
        """Execute a tool job, enforcing the permission ceiling."""
        from app.tools.base import ToolRequest

        tool_name: str = payload.get("tool", "")
        parameters: dict[str, Any] = payload.get("parameters", {})

        tool = self._registry.get(tool_name)
        if tool is None:
            raise ValueError(f"Tool '{tool_name}' is not registered.")

        allowed_levels = _CEILING_ALLOWED.get(ceiling, set())
        if tool.risk_level.value not in allowed_levels:
            raise PermissionError(
                f"Tool '{tool_name}' has risk level '{tool.risk_level.value}' "
                f"which exceeds the job's permission ceiling '{ceiling}'."
            )

        request = ToolRequest(tool_name=tool_name, parameters=parameters)
        result, decision = await self._executor.execute(request, session)

        if not result.success:
            raise RuntimeError(
                result.error or f"Tool '{tool_name}' failed (decision={decision.decision.value})"
            )

        return result.output[:500] if result.output else "ok"

    async def _run_chat_job(
        self,
        payload: dict[str, Any],
        session: Any,
    ) -> str:
        """Execute a chat job through the orchestrator."""
        message: str = payload.get("message", "")
        if not message:
            raise ValueError("Chat job payload must include 'message'.")

        conversation_id: int | None = payload.get("conversation_id")
        _, asst_msg, _, _, _ = await self._orchestrator.chat(
            session, message, conversation_id
        )
        return asst_msg.content[:500]
