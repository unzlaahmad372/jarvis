"""Tests for Phase 12 — Production Hardening.

Covers:
  - SecretsValidationError on default/short key with remote access enabled
  - Warnings (no raise) when remote access is disabled
  - RetentionEnforcer purges expired conversations, tool logs, automation logs
  - RetentionEnforcer leaves recent records untouched
  - RetentionEnforcer is idempotent
  - GET /api/v1/audit/tool-executions — empty, populated, filtered, paginated
  - POST /api/v1/audit/retention/run — runs and returns result
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.retention import RetentionEnforcer
from app.core.secrets import SecretsValidationError, validate_secrets
from app.db.models import (
    AutomationExecution,
    AutomationJob,
    Conversation,
    ToolExecution,
    Workspace,
)

# ── Secrets Validation ────────────────────────────────────────────────────────

_DEFAULT = "change-me-in-production-use-a-long-random-secret"
_SHORT = "tooshort"
_GOOD = "a" * 40


def test_default_key_local_only_warns():
    warnings = validate_secrets(_DEFAULT, remote_access_enabled=False)
    assert len(warnings) == 1
    assert "default" in warnings[0].lower() or "placeholder" in warnings[0].lower()


def test_default_key_remote_raises():
    with pytest.raises(SecretsValidationError, match="default"):
        validate_secrets(_DEFAULT, remote_access_enabled=True)


def test_short_key_local_only_warns():
    warnings = validate_secrets(_SHORT, remote_access_enabled=False)
    assert len(warnings) == 1
    assert "characters" in warnings[0].lower() or "short" in warnings[0].lower()


def test_short_key_remote_raises():
    with pytest.raises(SecretsValidationError):
        validate_secrets(_SHORT, remote_access_enabled=True)


def test_good_key_no_warnings():
    warnings = validate_secrets(_GOOD, remote_access_enabled=False)
    assert warnings == []


def test_good_key_remote_no_raise():
    warnings = validate_secrets(_GOOD, remote_access_enabled=True)
    assert warnings == []


def test_exactly_32_chars_ok():
    key = "x" * 32
    warnings = validate_secrets(key, remote_access_enabled=True)
    assert warnings == []


def test_31_chars_raises_remote():
    key = "x" * 31
    with pytest.raises(SecretsValidationError):
        validate_secrets(key, remote_access_enabled=True)


# ── RetentionEnforcer ─────────────────────────────────────────────────────────


async def _seed_workspace(session) -> int:
    ws = Workspace(name="test-retention", is_default=False)
    session.add(ws)
    await session.flush()
    return int(ws.id)


async def _add_conversation(session, workspace_id: int, age_days: int) -> int:
    old_ts = datetime.now(UTC) - timedelta(days=age_days)
    conv = Conversation(workspace_id=workspace_id, title="old")
    conv.updated_at = old_ts  # type: ignore[assignment]
    session.add(conv)
    await session.flush()
    return int(conv.id)


async def _add_tool_execution(session, age_days: int) -> int:
    old_ts = datetime.now(UTC) - timedelta(days=age_days)
    te = ToolExecution(
        tool_name="list_directory",
        risk_level="READ_ONLY",
        policy_rule="READ_ONLY_ALLOW",
        policy_decision="ALLOW",
        success=True,
        duration_ms=10,
    )
    te.created_at = old_ts  # type: ignore[assignment]
    session.add(te)
    await session.flush()
    return int(te.id)


async def _add_automation_execution(session, age_days: int) -> int:
    job = AutomationJob(
        name=f"job-{age_days}",
        schedule="0 8 * * *",
        action_type="chat",
        action_payload="{}",
    )
    session.add(job)
    await session.flush()

    old_ts = datetime.now(UTC) - timedelta(days=age_days)
    ae = AutomationExecution(
        job_id=job.id,
        execution_id=f"exec-{age_days}",
        scheduled_time=old_ts,
        status="SUCCESS",
    )
    ae.created_at = old_ts  # type: ignore[assignment]
    session.add(ae)
    await session.flush()
    return int(ae.id)


@pytest.mark.asyncio
async def test_retention_purges_old_conversations(db_session):
    ws_id = await _seed_workspace(db_session)
    old_id = await _add_conversation(db_session, ws_id, age_days=400)
    new_id = await _add_conversation(db_session, ws_id, age_days=10)
    await db_session.commit()

    enforcer = RetentionEnforcer(conversation_retention_days=365)
    result = await enforcer.run(db_session)

    assert result.conversations_deleted == 1
    remaining = (await db_session.execute(select(Conversation))).scalars().all()
    ids = [c.id for c in remaining]
    assert old_id not in ids
    assert new_id in ids


@pytest.mark.asyncio
async def test_retention_leaves_recent_conversations(db_session):
    ws_id = await _seed_workspace(db_session)
    await _add_conversation(db_session, ws_id, age_days=5)
    await db_session.commit()

    enforcer = RetentionEnforcer(conversation_retention_days=365)
    result = await enforcer.run(db_session)

    assert result.conversations_deleted == 0


@pytest.mark.asyncio
async def test_retention_purges_old_tool_executions(db_session):
    old_id = await _add_tool_execution(db_session, age_days=100)
    new_id = await _add_tool_execution(db_session, age_days=5)
    await db_session.commit()

    enforcer = RetentionEnforcer(tool_log_retention_days=90)
    result = await enforcer.run(db_session)

    assert result.tool_executions_deleted == 1
    remaining = (await db_session.execute(select(ToolExecution))).scalars().all()
    ids = [t.id for t in remaining]
    assert old_id not in ids
    assert new_id in ids


@pytest.mark.asyncio
async def test_retention_purges_old_automation_executions(db_session):
    old_id = await _add_automation_execution(db_session, age_days=100)
    await db_session.commit()

    enforcer = RetentionEnforcer(automation_log_retention_days=90)
    result = await enforcer.run(db_session)

    assert result.automation_executions_deleted == 1
    remaining = (await db_session.execute(select(AutomationExecution))).scalars().all()
    assert not any(ae.id == old_id for ae in remaining)


@pytest.mark.asyncio
async def test_retention_idempotent(db_session):
    ws_id = await _seed_workspace(db_session)
    await _add_conversation(db_session, ws_id, age_days=400)
    await db_session.commit()

    enforcer = RetentionEnforcer(conversation_retention_days=365)
    r1 = await enforcer.run(db_session)
    r2 = await enforcer.run(db_session)

    assert r1.conversations_deleted == 1
    assert r2.conversations_deleted == 0  # already gone


@pytest.mark.asyncio
async def test_retention_result_total_deleted(db_session):
    ws_id = await _seed_workspace(db_session)
    await _add_conversation(db_session, ws_id, age_days=400)
    await _add_tool_execution(db_session, age_days=100)
    await db_session.commit()

    enforcer = RetentionEnforcer(
        conversation_retention_days=365,
        tool_log_retention_days=90,
    )
    result = await enforcer.run(db_session)

    assert result.total_deleted == 2
    assert result.errors == []


# ── Audit REST API ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_tool_executions_empty(test_client):
    resp = await test_client.get("/api/v1/audit/tool-executions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_audit_tool_executions_populated(test_client, db_session):
    db_session.add(
        ToolExecution(
            tool_name="list_directory",
            risk_level="READ_ONLY",
            policy_rule="READ_ONLY_ALLOW",
            policy_decision="ALLOW",
            success=True,
            duration_ms=5,
        )
    )
    await db_session.commit()

    resp = await test_client.get("/api/v1/audit/tool-executions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(item["tool_name"] == "list_directory" for item in data["items"])


@pytest.mark.asyncio
async def test_audit_filter_by_tool_name(test_client, db_session):
    for name in ("tool_a", "tool_b"):
        db_session.add(
            ToolExecution(
                tool_name=name,
                risk_level="READ_ONLY",
                policy_rule="READ_ONLY_ALLOW",
                policy_decision="ALLOW",
                success=True,
                duration_ms=1,
            )
        )
    await db_session.commit()

    resp = await test_client.get("/api/v1/audit/tool-executions?tool_name=tool_a")
    assert resp.status_code == 200
    data = resp.json()
    assert all(item["tool_name"] == "tool_a" for item in data["items"])


@pytest.mark.asyncio
async def test_audit_filter_by_policy_decision(test_client, db_session):
    db_session.add(
        ToolExecution(
            tool_name="dangerous_tool",
            risk_level="DANGEROUS",
            policy_rule="DANGEROUS_DENY",
            policy_decision="DENY",
            success=False,
            duration_ms=0,
        )
    )
    await db_session.commit()

    resp = await test_client.get("/api/v1/audit/tool-executions?policy_decision=DENY")
    assert resp.status_code == 200
    data = resp.json()
    assert all(item["policy_decision"] == "DENY" for item in data["items"])


@pytest.mark.asyncio
async def test_audit_filter_by_success(test_client, db_session):
    for success in (True, False):
        db_session.add(
            ToolExecution(
                tool_name="some_tool",
                risk_level="READ_ONLY",
                policy_rule="READ_ONLY_ALLOW",
                policy_decision="ALLOW",
                success=success,
                duration_ms=1,
            )
        )
    await db_session.commit()

    resp = await test_client.get("/api/v1/audit/tool-executions?success=false")
    assert resp.status_code == 200
    data = resp.json()
    assert all(item["success"] is False for item in data["items"])


@pytest.mark.asyncio
async def test_audit_pagination(test_client, db_session):
    for i in range(5):
        db_session.add(
            ToolExecution(
                tool_name=f"tool_{i}",
                risk_level="READ_ONLY",
                policy_rule="READ_ONLY_ALLOW",
                policy_decision="ALLOW",
                success=True,
                duration_ms=i,
            )
        )
    await db_session.commit()

    resp = await test_client.get("/api/v1/audit/tool-executions?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] >= 5
    assert data["limit"] == 2
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_audit_pagination_offset(test_client, db_session):
    for i in range(4):
        db_session.add(
            ToolExecution(
                tool_name="paged_tool",
                risk_level="READ_ONLY",
                policy_rule="READ_ONLY_ALLOW",
                policy_decision="ALLOW",
                success=True,
                duration_ms=i,
            )
        )
    await db_session.commit()

    page1 = (await test_client.get("/api/v1/audit/tool-executions?limit=2&offset=0")).json()
    page2 = (await test_client.get("/api/v1/audit/tool-executions?limit=2&offset=2")).json()

    ids_p1 = {item["id"] for item in page1["items"]}
    ids_p2 = {item["id"] for item in page2["items"]}
    assert ids_p1.isdisjoint(ids_p2)


@pytest.mark.asyncio
async def test_audit_retention_run_endpoint(test_client):
    resp = await test_client.post("/api/v1/audit/retention/run")
    assert resp.status_code == 200
    data = resp.json()
    assert "conversations_deleted" in data
    assert "tool_executions_deleted" in data
    assert "total_deleted" in data
    assert "errors" in data


@pytest.mark.asyncio
async def test_audit_newest_first(test_client, db_session):
    """Audit records should be returned newest first."""
    from datetime import timedelta

    now = datetime.now(UTC)
    for i in range(3):
        te = ToolExecution(
            tool_name="ordered_tool",
            risk_level="READ_ONLY",
            policy_rule="READ_ONLY_ALLOW",
            policy_decision="ALLOW",
            success=True,
            duration_ms=i,
        )
        te.created_at = now - timedelta(hours=i)  # type: ignore[assignment]
        db_session.add(te)
    await db_session.commit()

    resp = await test_client.get(
        "/api/v1/audit/tool-executions?tool_name=ordered_tool&limit=10"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    # Newest first: duration_ms=0 was created most recently
    durations = [item["duration_ms"] for item in items]
    assert durations == sorted(durations)
