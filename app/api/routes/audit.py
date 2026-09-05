"""Audit log API — Phase 12 Production Hardening.

GET /api/v1/audit/tool-executions
  Returns paginated ToolExecution records with optional filters.

POST /api/v1/audit/retention/run
  Manually trigger a retention enforcement pass.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.chat import AuditPageOut, ToolExecutionOut
from app.core.config import get_settings
from app.core.retention import RetentionEnforcer, RetentionResult
from app.db.models import ToolExecution

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/tool-executions", response_model=AuditPageOut)
async def list_tool_executions(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tool_name: str | None = Query(default=None, description="Filter by tool name"),
    policy_decision: str | None = Query(
        default=None, description="Filter by decision: ALLOW | REQUIRES_CONFIRMATION | DENY"
    ),
    success: bool | None = Query(default=None, description="Filter by success flag"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AuditPageOut:
    """Return paginated tool execution audit records, newest first."""
    base = select(ToolExecution)

    if tool_name:
        base = base.where(ToolExecution.tool_name == tool_name)
    if policy_decision:
        base = base.where(ToolExecution.policy_decision == policy_decision)
    if success is not None:
        base = base.where(ToolExecution.success == success)

    # Total count
    count_q = select(func.count()).select_from(base.subquery())
    total: int = (await session.execute(count_q)).scalar_one()

    # Paginated rows
    rows_q = base.order_by(ToolExecution.created_at.desc()).offset(offset).limit(limit)
    rows = (await session.execute(rows_q)).scalars().all()

    return AuditPageOut(
        items=[ToolExecutionOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/retention/run", response_model=RetentionResult)
async def run_retention(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RetentionResult:
    """Manually trigger a data retention enforcement pass.

    Purges conversations and tool logs that exceed their configured retention
    periods.  Safe to call repeatedly — idempotent.
    """
    settings = get_settings()
    enforcer = RetentionEnforcer(
        conversation_retention_days=settings.conversation_retention_days,
        tool_log_retention_days=settings.tool_log_retention_days,
        automation_log_retention_days=settings.tool_log_retention_days,
    )
    return await enforcer.run(session)
