"""Unit tests for Phase 9 — Advanced Agent Capabilities.

Covers:
  - ConfirmationStore: create, consume, expiry, digest mismatch, reuse prevention
  - TaskDecomposer: single intent, multi-intent splitting, conjunction detection
  - AgentPlanner v2: multi-step execution, confirmation_id in PlanStep,
    sub_tasks count, blocked plan with confirmation_id
  - Confirm REST endpoint: happy path, expired, digest mismatch, reuse, not found
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.brain.confirmation import (
    ConfirmationStore,
    _digest,
    reset_confirmation_store,
)
from app.brain.intent_router import Intent
from app.brain.planner import AgentPlanner
from app.brain.task_decomposer import decompose
from app.core.config import get_settings
from app.db.models import Workspace
from app.tools.base import RiskLevel, Tool, ToolResult
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry, reset_registry

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_registry():
    reset_registry()
    yield
    reset_registry()


@pytest.fixture(autouse=True)
def clean_confirmation_store():
    store = ConfirmationStore()
    reset_confirmation_store(store)
    yield store
    reset_confirmation_store(None)


@pytest.fixture(autouse=True)
async def seed_workspace(db_session):
    result = await db_session.execute(
        select(Workspace).where(Workspace.is_default == True)  # noqa: E712
    )
    if result.scalar_one_or_none() is None:
        db_session.add(Workspace(name="default", is_default=True))
        await db_session.commit()


@pytest.fixture
def settings():
    return get_settings()


# ── Fake tools ────────────────────────────────────────────────────────────────


class FakeReadTool(Tool):
    def __init__(self, name: str = "system_info", output: str = '{"ok":true}') -> None:
        self._name = name
        self._output = output

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Fake read tool"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        return ToolResult(tool_name=self.name, success=True, output=self._output)


class FakeSensitiveTool(Tool):
    @property
    def name(self) -> str:
        return "system_info"

    @property
    def description(self) -> str:
        return "Sensitive tool"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SENSITIVE

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        return ToolResult(tool_name=self.name, success=True, output="sensitive_data")


# ── ConfirmationStore ─────────────────────────────────────────────────────────


def test_confirmation_create_returns_pending():
    store = ConfirmationStore()
    c = store.create("my_tool", {"path": "."}, "SENSITIVE", "SENSITIVE_ACTION_CONFIRMATION")
    assert c.confirmation_id
    assert c.tool_name == "my_tool"
    assert c.risk_level == "SENSITIVE"
    assert not c.consumed
    assert c.expires_at > datetime.now(UTC)


def test_confirmation_digest_is_deterministic():
    d1 = _digest("tool_a", {"x": 1, "y": 2})
    d2 = _digest("tool_a", {"y": 2, "x": 1})  # different key order
    assert d1 == d2


def test_confirmation_consume_happy_path():
    store = ConfirmationStore()
    c = store.create("my_tool", {"path": "."}, "SENSITIVE", "RULE")
    ok, reason = store.consume(c.confirmation_id, "my_tool", {"path": "."})
    assert ok
    assert reason == "OK"
    assert store.get(c.confirmation_id).consumed  # type: ignore[union-attr]


def test_confirmation_consume_not_found():
    store = ConfirmationStore()
    ok, reason = store.consume("nonexistent-id", "tool", {})
    assert not ok
    assert "not found" in reason.lower()


def test_confirmation_consume_already_used():
    store = ConfirmationStore()
    c = store.create("my_tool", {}, "SENSITIVE", "RULE")
    store.consume(c.confirmation_id, "my_tool", {})
    ok, reason = store.consume(c.confirmation_id, "my_tool", {})
    assert not ok
    assert "already been used" in reason.lower()


def test_confirmation_consume_expired():
    store = ConfirmationStore(ttl_seconds=0)
    c = store.create("my_tool", {}, "SENSITIVE", "RULE")
    # Force expiry
    c.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    ok, reason = store.consume(c.confirmation_id, "my_tool", {})
    assert not ok
    assert "expired" in reason.lower()


def test_confirmation_consume_digest_mismatch():
    store = ConfirmationStore()
    c = store.create("my_tool", {"path": "."}, "SENSITIVE", "RULE")
    # Different parameters → different digest
    ok, reason = store.consume(c.confirmation_id, "my_tool", {"path": "/etc"})
    assert not ok
    assert "parameters changed" in reason.lower()


def test_confirmation_consume_wrong_tool_name():
    store = ConfirmationStore()
    c = store.create("tool_a", {}, "SENSITIVE", "RULE")
    ok, reason = store.consume(c.confirmation_id, "tool_b", {})
    assert not ok
    assert "parameters changed" in reason.lower()


def test_confirmation_purge_expired():
    store = ConfirmationStore(ttl_seconds=0)
    store.create("t1", {}, "SENSITIVE", "R")
    store.create("t2", {}, "SENSITIVE", "R")
    # Force expiry on all
    for c in store._pending.values():
        c.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    removed = store.purge_expired()
    assert removed == 2
    assert len(store._pending) == 0


def test_confirmation_get_returns_none_for_missing():
    store = ConfirmationStore()
    assert store.get("no-such-id") is None


# ── TaskDecomposer ────────────────────────────────────────────────────────────


def test_decompose_single_system_intent():
    tasks = decompose("show system info")
    assert len(tasks) == 1
    assert tasks[0].intent == Intent.SYSTEM_OPERATION
    assert "system_info" in tasks[0].tool_names


def test_decompose_single_general_chat():
    tasks = decompose("hello there")
    assert len(tasks) == 1
    assert tasks[0].intent == Intent.GENERAL_CHAT
    assert tasks[0].tool_names == []


def test_decompose_conjunction_two_intents():
    tasks = decompose("show system info and what did I write about the farm?")
    intents = [t.intent for t in tasks]
    assert Intent.SYSTEM_OPERATION in intents
    assert Intent.KNOWLEDGE_SEARCH in intents
    assert len(tasks) == 2


def test_decompose_conjunction_deduplicates_same_intent():
    tasks = decompose("show system info and check disk usage")
    # Both fragments → SYSTEM_OPERATION; should be deduplicated to 1
    assert len(tasks) == 1
    assert tasks[0].intent == Intent.SYSTEM_OPERATION


def test_decompose_memory_and_system():
    tasks = decompose("what do you know about Phoenix and show disk usage")
    intents = [t.intent for t in tasks]
    assert Intent.MEMORY_SEARCH in intents
    assert Intent.SYSTEM_OPERATION in intents


def test_decompose_description_truncated():
    long_msg = "show system info " + "x" * 200
    tasks = decompose(long_msg)
    assert len(tasks[0].description) <= 80


def test_decompose_empty_fragments_fallback():
    # No conjunction → single task
    tasks = decompose("what is 2 + 2?")
    assert len(tasks) == 1


# ── AgentPlanner v2 ───────────────────────────────────────────────────────────


@pytest.fixture
def registry_with_system_tools():
    r = ToolRegistry()
    r.register(FakeReadTool("system_info", '{"os":"Windows"}'))
    r.register(FakeReadTool("disk_usage", '{"used_pct":42}'))
    return r


@pytest.fixture
def planner(registry_with_system_tools, settings, clean_confirmation_store):
    executor = ToolExecutor(registry=registry_with_system_tools, settings=settings)
    return AgentPlanner(
        registry=registry_with_system_tools,
        executor=executor,
        settings=settings,
        confirmation_store=clean_confirmation_store,
    )


@pytest.mark.asyncio
async def test_planner_v2_system_intent_runs_tools(planner, db_session):
    result = await planner.plan("show system info", db_session)
    assert result.intent == Intent.SYSTEM_OPERATION
    assert len(result.steps) == 2
    assert all(s.success for s in result.steps)
    assert not result.blocked
    assert result.sub_tasks == 1


@pytest.mark.asyncio
async def test_planner_v2_multi_step_two_sub_tasks(settings, db_session, clean_confirmation_store):
    r = ToolRegistry()
    r.register(FakeReadTool("system_info", '{"os":"Windows"}'))
    r.register(FakeReadTool("disk_usage", '{"used_pct":42}'))
    executor = ToolExecutor(registry=r, settings=settings)
    p = AgentPlanner(
        registry=r, executor=executor, settings=settings,
        confirmation_store=clean_confirmation_store,
    )
    result = await p.plan("show system info and what did I write about the farm?", db_session)
    # Two sub-tasks: SYSTEM_OPERATION + KNOWLEDGE_SEARCH
    assert result.sub_tasks == 2
    # SYSTEM_OPERATION runs tools; KNOWLEDGE_SEARCH has no tools
    assert len(result.steps) >= 1


@pytest.mark.asyncio
async def test_planner_v2_sensitive_tool_creates_confirmation(
    settings, db_session, clean_confirmation_store
):
    r = ToolRegistry()
    r.register(FakeSensitiveTool())
    executor = ToolExecutor(registry=r, settings=settings)
    p = AgentPlanner(
        registry=r, executor=executor, settings=settings,
        confirmation_store=clean_confirmation_store,
    )
    result = await p.plan("show system info", db_session)
    assert result.blocked
    assert result.steps[0].requires_confirmation
    assert result.steps[0].confirmation_id is not None
    # Confirmation should be in the store
    cid = result.steps[0].confirmation_id
    assert clean_confirmation_store.get(cid) is not None


@pytest.mark.asyncio
async def test_planner_v2_general_chat_no_tools(planner, db_session):
    result = await planner.plan("hello there", db_session)
    assert result.intent == Intent.GENERAL_CHAT
    assert result.steps == []
    assert result.sub_tasks == 1


@pytest.mark.asyncio
async def test_planner_v2_context_slots_populated(planner, db_session):
    result = await planner.plan("show system info", db_session)
    assert len(result.tool_context_slots) >= 1
    assert any("system_info" in s.name for s in result.tool_context_slots)


@pytest.mark.asyncio
async def test_planner_v2_missing_tool_skipped(settings, db_session, clean_confirmation_store):
    r = ToolRegistry()
    r.register(FakeReadTool("disk_usage", '{"used_pct":10}'))
    executor = ToolExecutor(registry=r, settings=settings)
    p = AgentPlanner(
        registry=r, executor=executor, settings=settings,
        confirmation_store=clean_confirmation_store,
    )
    result = await p.plan("show system info", db_session)
    assert len(result.steps) == 1
    assert result.steps[0].tool_name == "disk_usage"


# ── Confirm REST endpoint ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_endpoint_not_found(test_client):
    resp = await test_client.post(
        "/api/v1/tools/confirm",
        json={"confirmation_id": "no-such-id", "tool_name": "system_info", "parameters": {}},
    )
    assert resp.status_code == 409
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_confirm_endpoint_happy_path(test_client):
    """Create a confirmation via the store, then consume it via the endpoint."""
    from app.brain.confirmation import get_confirmation_store

    store = get_confirmation_store()
    c = store.create("system_info", {}, "READ_ONLY", "READ_ONLY_ALLOW")

    resp = await test_client.post(
        "/api/v1/tools/confirm",
        json={
            "confirmation_id": c.confirmation_id,
            "tool_name": "system_info",
            "parameters": {},
        },
    )
    # system_info is registered in test_client fixture; should succeed
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_name"] == "system_info"


@pytest.mark.asyncio
async def test_confirm_endpoint_digest_mismatch(test_client):
    from app.brain.confirmation import get_confirmation_store

    store = get_confirmation_store()
    c = store.create("system_info", {"path": "."}, "SENSITIVE", "RULE")

    resp = await test_client.post(
        "/api/v1/tools/confirm",
        json={
            "confirmation_id": c.confirmation_id,
            "tool_name": "system_info",
            "parameters": {"path": "/etc"},  # different params
        },
    )
    assert resp.status_code == 409
    assert "parameters changed" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_confirm_endpoint_reuse_rejected(test_client):
    from app.brain.confirmation import get_confirmation_store

    store = get_confirmation_store()
    c = store.create("system_info", {}, "READ_ONLY", "READ_ONLY_ALLOW")

    # First use
    await test_client.post(
        "/api/v1/tools/confirm",
        json={"confirmation_id": c.confirmation_id, "tool_name": "system_info", "parameters": {}},
    )
    # Second use — must be rejected
    resp = await test_client.post(
        "/api/v1/tools/confirm",
        json={"confirmation_id": c.confirmation_id, "tool_name": "system_info", "parameters": {}},
    )
    assert resp.status_code == 409
    assert "already been used" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_confirmation_endpoint(test_client):
    from app.brain.confirmation import get_confirmation_store

    store = get_confirmation_store()
    c = store.create("system_info", {}, "SENSITIVE", "RULE")

    resp = await test_client.get(f"/api/v1/tools/confirmations/{c.confirmation_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["confirmation_id"] == c.confirmation_id
    assert data["tool_name"] == "system_info"
    assert data["risk_level"] == "SENSITIVE"


@pytest.mark.asyncio
async def test_get_confirmation_endpoint_not_found(test_client):
    resp = await test_client.get("/api/v1/tools/confirmations/no-such-id")
    assert resp.status_code == 404


# ── SSE payload includes sub_tasks count ─────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_sse_includes_plan_steps(test_client):
    import json

    resp = await test_client.post(
        "/api/v1/chat",
        json={"message": "show system info", "stream": True},
    )
    assert resp.status_code == 200
    events = [
        json.loads(line[len("data: "):])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    complete = next((e for e in events if e["type"] == "RESPONSE_COMPLETE"), None)
    assert complete is not None
    assert "plan_steps" in complete["payload"]
    assert complete["payload"]["intent"] == "SYSTEM_OPERATION"
