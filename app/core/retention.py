"""Data retention enforcement for JARVIS.

Purges records that have exceeded their configured retention period:
  - Conversations (and their messages/summaries via CASCADE)
  - ToolExecution audit log entries

Retention periods are read from Settings:
  - conversation_retention_days  (default 365)
  - tool_log_retention_days      (default 90)

Design:
  - RetentionEnforcer.run() is idempotent and safe to call repeatedly.
  - Returns a RetentionResult describing what was deleted.
  - Never deletes Memories (those are durable until explicitly forgotten).
  - Never deletes Documents (those are managed via the documents API).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import AutomationExecution, Conversation, ToolExecution

logger = get_logger(__name__)


class RetentionResult(BaseModel):
    conversations_deleted: int = 0
    tool_executions_deleted: int = 0
    automation_executions_deleted: int = 0
    errors: list[str] = Field(default_factory=list)
    total_deleted: int = 0

    def _recompute_total(self) -> None:
        self.total_deleted = (
            self.conversations_deleted
            + self.tool_executions_deleted
            + self.automation_executions_deleted
        )


class RetentionEnforcer:
    """Enforces data retention policies by purging expired records."""

    def __init__(
        self,
        conversation_retention_days: int = 365,
        tool_log_retention_days: int = 90,
        automation_log_retention_days: int = 90,
    ) -> None:
        self._conv_days = conversation_retention_days
        self._tool_days = tool_log_retention_days
        self._auto_days = automation_log_retention_days

    async def run(self, session: AsyncSession) -> RetentionResult:
        """Execute all retention policies.  Commits the session on success."""
        result = RetentionResult()
        now = datetime.now(UTC)

        # ── Conversations ─────────────────────────────────────────────────────
        try:
            conv_cutoff = now - timedelta(days=self._conv_days)
            # Fetch IDs first to count them (CASCADE handles messages/summaries)
            rows = await session.execute(
                select(Conversation.id).where(Conversation.updated_at < conv_cutoff)
            )
            conv_ids = [r[0] for r in rows.fetchall()]
            if conv_ids:
                await session.execute(
                    delete(Conversation).where(Conversation.id.in_(conv_ids))
                )
                result.conversations_deleted = len(conv_ids)
                logger.info(
                    "retention_conversations_purged",
                    count=len(conv_ids),
                    cutoff=conv_cutoff.isoformat(),
                )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"conversations: {exc}")
            logger.error("retention_conversations_error", error=str(exc))

        # ── Tool execution audit log ──────────────────────────────────────────
        try:
            tool_cutoff = now - timedelta(days=self._tool_days)
            del_result = await session.execute(
                delete(ToolExecution).where(ToolExecution.created_at < tool_cutoff)
            )
            result.tool_executions_deleted = getattr(del_result, "rowcount", 0) or 0
            if result.tool_executions_deleted:
                logger.info(
                    "retention_tool_executions_purged",
                    count=result.tool_executions_deleted,
                    cutoff=tool_cutoff.isoformat(),
                )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"tool_executions: {exc}")
            logger.error("retention_tool_executions_error", error=str(exc))

        # ── Automation execution history ──────────────────────────────────────
        try:
            auto_cutoff = now - timedelta(days=self._auto_days)
            del_result = await session.execute(
                delete(AutomationExecution).where(
                    AutomationExecution.created_at < auto_cutoff
                )
            )
            result.automation_executions_deleted = getattr(del_result, "rowcount", 0) or 0
            if result.automation_executions_deleted:
                logger.info(
                    "retention_automation_executions_purged",
                    count=result.automation_executions_deleted,
                    cutoff=auto_cutoff.isoformat(),
                )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"automation_executions: {exc}")
            logger.error("retention_automation_executions_error", error=str(exc))

        await session.commit()
        result._recompute_total()
        logger.info(
            "retention_run_complete",
            total_deleted=result.total_deleted,
            errors=len(result.errors),
        )
        return result
