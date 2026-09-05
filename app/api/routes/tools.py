"""Tools endpoints — GET/POST /api/v1/tools."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import DbSession, SettingsDep
from app.api.schemas.chat import (
    ConfirmationOut,
    ConfirmRequest,
    ToolExecuteRequest,
    ToolExecuteResponse,
    ToolExecutionOut,
    ToolOut,
)
from app.brain.confirmation import get_confirmation_store
from app.db.models import ToolExecution
from app.tools.base import ToolRequest
from app.tools.executor import ToolExecutor
from app.tools.registry import get_registry

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


@router.get("", response_model=list[ToolOut])
async def list_tools() -> list[ToolOut]:
    """List all registered tools with their metadata."""
    registry = get_registry()
    return [
        ToolOut(
            name=t.name,
            description=t.description,
            risk_level=t.risk_level.value,
            parameters_schema=t.parameters_schema,
        )
        for t in registry.list_tools()
    ]


@router.post("/{tool_name}/execute", response_model=ToolExecuteResponse)
async def execute_tool(
    tool_name: str,
    body: ToolExecuteRequest,
    session: DbSession,
    settings: SettingsDep,
) -> ToolExecuteResponse:
    """Execute a tool directly (READ_ONLY / LOW_RISK without confirmation).

    SENSITIVE and DANGEROUS tools must go through POST /tools/confirm instead.
    confirmation_id is ignored on this path — all token validation happens
    in /confirm which calls ConfirmationStore.consume() via ToolExecutor.
    """
    registry = get_registry()
    executor = ToolExecutor(registry=registry, settings=settings)

    request = ToolRequest(
        tool_name=tool_name,
        parameters=dict(body.parameters),
        confirmation_id=None,  # never trust a client-supplied id on this path
    )
    result, decision = await executor.execute(request, session)
    await session.commit()

    return ToolExecuteResponse(
        tool_name=result.tool_name,
        success=result.success,
        output=result.output,
        error=result.error,
        truncated=result.truncated,
        policy_decision=decision.decision.value,
        policy_rule=decision.policy_rule,
        reason=decision.reason,
        requires_confirmation=decision.requires_confirmation,
    )


# Deprecated: superseded by GET /api/v1/audit/tool-executions (Phase 12)
@router.get("/audit", response_model=list[ToolExecutionOut], deprecated=True)
async def get_audit_log(
    session: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ToolExecutionOut]:
    """Deprecated: use GET /api/v1/audit/tool-executions instead."""
    result = await session.execute(
        select(ToolExecution).order_by(ToolExecution.created_at.desc()).limit(limit)
    )
    return [ToolExecutionOut.model_validate(row) for row in result.scalars().all()]


@router.post("/confirm", response_model=ToolExecuteResponse)
async def confirm_and_execute(
    body: ConfirmRequest,
    session: DbSession,
    settings: SettingsDep,
) -> ToolExecuteResponse:
    """Consume a pending confirmation and execute the approved tool.

    Spec §71: the backend retrieves the stored parameters from ConfirmationStore
    so the client never needs to re-supply them (prevents parameter tampering).
    ToolExecutor validates digest, expiry, and single-use via consume().
    """
    store = get_confirmation_store()

    # Look up stored parameters BEFORE consuming — client supplies only the id
    entry = store.get(body.confirmation_id)
    if entry is None:
        raise HTTPException(status_code=409, detail="Confirmation token not found.")
    if entry.consumed:
        raise HTTPException(status_code=409, detail="Confirmation token has already been used.")

    registry = get_registry()
    executor = ToolExecutor(registry=registry, settings=settings)

    # Pass the server-stored parameters and the confirmation_id.
    # ToolExecutor will call store.consume() which validates digest/expiry/single-use.
    request = ToolRequest(
        tool_name=entry.tool_name,
        parameters=entry.parameters,
        confirmation_id=body.confirmation_id,
    )
    result, decision = await executor.execute(request, session)
    await session.commit()

    return ToolExecuteResponse(
        tool_name=result.tool_name,
        success=result.success,
        output=result.output,
        error=result.error,
        truncated=result.truncated,
        policy_decision=decision.decision.value,
        policy_rule=decision.policy_rule,
        reason=decision.reason,
        requires_confirmation=decision.requires_confirmation,
    )


@router.get("/confirmations/{confirmation_id}", response_model=ConfirmationOut)
async def get_confirmation(
    confirmation_id: str,
) -> ConfirmationOut:
    """Inspect a pending confirmation (for GUI display)."""
    store = get_confirmation_store()
    entry = store.get(confirmation_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Confirmation not found.")
    return ConfirmationOut(
        confirmation_id=entry.confirmation_id,
        tool_name=entry.tool_name,
        risk_level=entry.risk_level,
        policy_rule=entry.policy_rule,
        action_digest=entry.action_digest,
        expires_at=entry.expires_at,
    )
