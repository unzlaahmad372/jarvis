"""ToolExecutor — validates policy, runs tool, writes audit log."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.confirmation import get_confirmation_store
from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import ToolExecution
from app.tools.base import (
    PolicyDecision,
    PolicyDecisionType,
    RiskLevel,
    ToolRequest,
    ToolResult,
)
from app.tools.policy import PolicyEngine
from app.tools.registry import ToolRegistry

logger = get_logger(__name__)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, settings: Settings) -> None:
        self._registry = registry
        self._policy = PolicyEngine(settings)
        self._max_output = settings.max_tool_output_size

    async def execute(
        self,
        request: ToolRequest,
        session: AsyncSession,
    ) -> tuple[ToolResult, PolicyDecision]:
        tool = self._registry.get(request.tool_name)
        if tool is None:
            decision = PolicyDecision(
                decision=PolicyDecisionType.DENY,
                risk_level=RiskLevel.READ_ONLY,
                tool_name=request.tool_name,
                policy_rule="UNKNOWN_TOOL",
                reason=f"Tool '{request.tool_name}' is not registered.",
            )
            result = ToolResult(
                tool_name=request.tool_name,
                success=False,
                output="",
                error=f"Unknown tool: {request.tool_name}",
            )
            await self._write_audit(session, request, result, decision, duration_ms=0)
            return result, decision

        # Validate confirmation token BEFORE calling PolicyEngine.
        # confirmed=True is only set when ConfirmationStore.consume() succeeds,
        # preventing any raw string from bypassing SENSITIVE/DANGEROUS checks.
        confirmed = False
        if request.confirmation_id:
            store = get_confirmation_store()
            ok, reason = store.consume(
                request.confirmation_id, request.tool_name, request.parameters
            )
            if not ok:
                decision = PolicyDecision(
                    decision=PolicyDecisionType.DENY,
                    risk_level=tool.risk_level,
                    tool_name=request.tool_name,
                    policy_rule="INVALID_CONFIRMATION",
                    reason=reason,
                )
                result = ToolResult(
                    tool_name=request.tool_name,
                    success=False,
                    output="",
                    error=reason,
                )
                await self._write_audit(session, request, result, decision, duration_ms=0)
                return result, decision
            confirmed = True

        decision = self._policy.evaluate(request, tool.risk_level, confirmed=confirmed)

        if not decision.allowed:
            result = ToolResult(
                tool_name=request.tool_name,
                success=False,
                output="",
                error=decision.reason,
            )
            await self._write_audit(session, request, result, decision, duration_ms=0)
            return result, decision

        # Execute
        start = datetime.now(UTC)
        try:
            result = await tool.execute(request.parameters)
        except Exception as exc:
            duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
            result = ToolResult(
                tool_name=request.tool_name,
                success=False,
                output="",
                error=str(exc),
            )
            await self._write_audit(session, request, result, decision, duration_ms)
            logger.error("tool_execution_error", tool=request.tool_name, error=str(exc))
            return result, decision

        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)

        # Enforce output size limit
        if len(result.output) > self._max_output:
            result = ToolResult(
                tool_name=result.tool_name,
                success=result.success,
                output=result.output[: self._max_output],
                error=result.error,
                truncated=True,
            )

        await self._write_audit(session, request, result, decision, duration_ms)
        logger.info(
            "tool_executed",
            tool=request.tool_name,
            success=result.success,
            duration_ms=duration_ms,
        )
        return result, decision

    async def _write_audit(
        self,
        session: AsyncSession,
        request: ToolRequest,
        result: ToolResult,
        decision: PolicyDecision,
        duration_ms: int,
    ) -> None:
        # Sanitise parameters — never log file contents or sensitive values
        safe_params = {
            k: v
            for k, v in request.parameters.items()
            if k not in ("content", "data", "secret", "password", "token")
        }
        entry = ToolExecution(
            tool_name=request.tool_name,
            risk_level=decision.risk_level.value,
            policy_rule=decision.policy_rule,
            policy_decision=decision.decision.value,
            parameters_sanitized=json.dumps(safe_params),
            success=result.success,
            error=result.error,
            duration_ms=duration_ms,
        )
        session.add(entry)
        await session.flush()
