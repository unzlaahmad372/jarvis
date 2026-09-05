"""Unit tests for Phase 9 — Advanced Agent Capabilities.

Covers:
  - IntentRouter: keyword classification, all intents, default fallback
  - AgentPlanner: tool selection per intent, tool execution, policy enforcement,
    context slot assembly, blocked plan handling
  - ChatOrchestrator: plan_result wired into chat turn, intent in SSE payload
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from app.brain.intent_router import Intent, IntentRouter, classify
from app.brain.planner import AgentPlanner, PlanResult, PlanStep
from app.core.config import get_settings
from app.db.models import Workspace
from app.tools.base import PolicyDecisionType, RiskLevel, Tool, ToolResult
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry, reset_registry

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_registry():
    reset_registry()
    yield
    reset_registry()


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


class FakeSystemTool(Tool):
    def __init__(self, name: str = "system_info", output: str = '{"os":"test"}') -> None:
        self._name = name
        self._output = output

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Fake system tool"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        return ToolResult(tool_name=self.name, success=True, output=self._output)


class FakeFailingTool(Tool):
    @property
    def name(self) -> str:
        return "system_info"

    @property
    def description(self) -> str:
        return "Always fails"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        return ToolResult(tool_name=self.name, success=False, output="", error="boom")


class FakeSensitiveTool(Tool):
    @property
    def name(self) -> str:
        return "system_info"

    @property
    def description(self) -> str:
        return "Sensitive"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SENSITIVE

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        return ToolResult(tool_name=self.name, success=True, output="sensitive")


# ── IntentRouter — keyword classification ─────────────────────────────────────


def test_classify_memory_remember():
    intent, method = classify("remember that Phoenix GA is Q3")
    assert intent == Intent.MEMORY_SEARCH
    assert method == "keyword"


def test_classify_memory_what_do_you_know():
    intent, _ = classify("what do you know about my project?")
    assert intent == Intent.MEMORY_SEARCH


def test_classify_memory_forget():
    intent, _ = classify("forget the Phoenix GA target")
    assert intent == Intent.MEMORY_SEARCH


def test_classify_knowledge_document():
    intent, method = classify("what does the PDF say about deployment?")
    assert intent == Intent.KNOWLEDGE_SEARCH
    assert method == "keyword"


def test_classify_knowledge_what_did_i_write():
    intent, _ = classify("what did I write about the dairy farm?")
    assert intent == Intent.KNOWLEDGE_SEARCH


def test_classify_file_list():
    intent, method = classify("list files in the projects folder")
    assert intent == Intent.FILE_OPERATION
    assert method == "keyword"


def test_classify_file_show_directory():
    intent, _ = classify("show me the directory contents")
    assert intent == Intent.FILE_OPERATION


def test_classify_system_cpu():
    intent, method = classify("how much CPU is being used?")
    assert intent == Intent.SYSTEM_OPERATION
    assert method == "keyword"


def test_classify_system_disk():
    intent, _ = classify("check disk usage")
    assert intent == Intent.SYSTEM_OPERATION


def test_classify_system_info():
    intent, _ = classify("show system info")
    assert intent == Intent.SYSTEM_OPERATION


def test_classify_automation_jobs():
    intent, method = classify("list my automation jobs")
    assert intent == Intent.AUTOMATION_OPERATION
    assert method == "keyword"


def test_classify_automation_trigger():
    intent, _ = classify("trigger the scheduled job")
    assert intent == Intent.AUTOMATION_OPERATION


def test_classify_general_chat_default():
    intent, method = classify("hello, how are you?")
    assert intent == Intent.GENERAL_CHAT
    assert method == "default"


def test_classify_general_chat_question():
    intent, _ = classify("what is the capital of France?")
    assert intent == Intent.GENERAL_CHAT


def test_router_route_delegates_to_classify():
    router = IntentRouter()
    intent, method = router.route("show system info")
    assert intent == Intent.SYSTEM_OPERATION
    assert method == "keyword"


# ── AgentPlanner — tool selection and execution ───────────────────────────────


@pytest.fixture
def registry_with_system_tools():
    r = ToolRegistry()
    r.register(FakeSystemTool("system_info", '{"os":"Windows","python":"3.12"}'))
    r.register(FakeSystemTool("disk_usage", '{"total_bytes":100,"used_pct":42}'))
    return r


@pytest.fixture
def planner(registry_with_system_tools, settings):
    executor = ToolExecutor(registry=registry_with_system_tools, settings=settings)
    return AgentPlanner(
        registry=registry_with_system_tools,
        executor=executor,
        settings=settings,
    )


@pytest.mark.asyncio
async def test_planner_system_intent_runs_tools(planner, db_session):
    result = await planner.plan("show system info", db_session)
    assert result.intent == Intent.SYSTEM_OPERATION
    assert len(result.steps) == 2
    assert all(s.success for s in result.steps)
    assert not result.blocked


@pytest.mark.asyncio
async def test_planner_system_intent_produces_context_slots(planner, db_session):
    result = await planner.plan("how much cpu is being used?", db_session)
    assert len(result.tool_context_slots) >= 1
    names = [s.name for s in result.tool_context_slots]
    assert any("system_info" in n for n in names)


@pytest.mark.asyncio
async def test_planner_general_chat_no_tools(planner, db_session):
    result = await planner.plan("hello there", db_session)
    assert result.intent == Intent.GENERAL_CHAT
    assert result.steps == []
    assert result.tool_context_slots == []
    assert not result.blocked


@pytest.mark.asyncio
async def test_planner_knowledge_search_no_tools(planner, db_session):
    result = await planner.plan("what did I write about the farm?", db_session)
    assert result.intent == Intent.KNOWLEDGE_SEARCH
    assert result.steps == []


@pytest.mark.asyncio
async def test_planner_memory_search_no_tools(planner, db_session):
    result = await planner.plan("remember that Phoenix is Q3", db_session)
    assert result.intent == Intent.MEMORY_SEARCH
    assert result.steps == []


@pytest.mark.asyncio
async def test_planner_failing_tool_recorded_in_steps(settings, db_session):
    r = ToolRegistry()
    r.register(FakeFailingTool())
    executor = ToolExecutor(registry=r, settings=settings)
    planner = AgentPlanner(registry=r, executor=executor, settings=settings)
    result = await planner.plan("show system info", db_session)
    assert len(result.steps) == 1
    assert result.steps[0].success is False
    assert result.steps[0].error == "boom"


@pytest.mark.asyncio
async def test_planner_sensitive_tool_blocks_plan(settings, db_session):
    r = ToolRegistry()
    r.register(FakeSensitiveTool())
    executor = ToolExecutor(registry=r, settings=settings)
    planner = AgentPlanner(registry=r, executor=executor, settings=settings)
    result = await planner.plan("show system info", db_session)
    assert result.blocked is True
    assert result.steps[0].requires_confirmation is True
    assert result.steps[0].policy_decision == PolicyDecisionType.REQUIRES_CONFIRMATION


@pytest.mark.asyncio
async def test_planner_missing_tool_skipped(settings, db_session):
    """If a tool in the intent map is not registered, it is silently skipped."""
    r = ToolRegistry()
    # Only register disk_usage, not system_info
    r.register(FakeSystemTool("disk_usage", '{"used_pct":10}'))
    executor = ToolExecutor(registry=r, settings=settings)
    planner = AgentPlanner(registry=r, executor=executor, settings=settings)
    result = await planner.plan("show system info", db_session)
    assert len(result.steps) == 1
    assert result.steps[0].tool_name == "disk_usage"


# ── PlanStep / PlanResult dataclass sanity ────────────────────────────────────


def test_plan_step_defaults():
    step = PlanStep(
        tool_name="system_info",
        parameters={},
        success=True,
        output="ok",
    )
    assert step.error is None
    assert step.requires_confirmation is False
    assert step.policy_decision == "ALLOW"


def test_plan_result_defaults():
    result = PlanResult(intent=Intent.GENERAL_CHAT, classification_method="default")
    assert result.steps == []
    assert result.tool_context_slots == []
    assert result.blocked is False


# ── Orchestrator integration via API ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_api_returns_intent_in_sse(test_client):
    """SSE RESPONSE_COMPLETE payload must include intent field."""
    import json

    resp = await test_client.post(
        "/api/v1/chat",
        json={"message": "hello", "stream": True},
    )
    assert resp.status_code == 200
    events = [
        json.loads(line[len("data: "):])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    complete = next((e for e in events if e["type"] == "RESPONSE_COMPLETE"), None)
    assert complete is not None
    assert "intent" in complete["payload"]
    assert "plan_steps" in complete["payload"]


@pytest.mark.asyncio
async def test_chat_api_system_intent_detected(test_client):
    """A system-info message should route to SYSTEM_OPERATION intent."""
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
    assert complete["payload"]["intent"] == "SYSTEM_OPERATION"


@pytest.mark.asyncio
async def test_chat_api_general_chat_intent(test_client):
    import json

    resp = await test_client.post(
        "/api/v1/chat",
        json={"message": "what is 2 + 2?", "stream": True},
    )
    assert resp.status_code == 200
    events = [
        json.loads(line[len("data: "):])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    complete = next((e for e in events if e["type"] == "RESPONSE_COMPLETE"), None)
    assert complete is not None
    assert complete["payload"]["intent"] == "GENERAL_CHAT"
    assert complete["payload"]["plan_steps"] == []
