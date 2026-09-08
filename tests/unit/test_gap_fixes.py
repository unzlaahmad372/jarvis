"""Tests for gap fixes: intent routing, new tools, forget command, param validation."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.brain.intent_router import Intent, classify
from app.brain.param_extractor import _validate_params, extract_params
from app.brain.task_decomposer import _INTENT_TOOLS, decompose
from app.db.models import Workspace
from app.memory.manager import forget, remember, search_memories
from app.tools.base import RiskLevel, Tool, ToolResult
from app.tools.memory.tools import MemorySearchTool
from app.tools.system.tools import (
    CpuUsageTool,
    MemoryUsageTool,
    OpenApplicationTool,
    ProcessListTool,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def seed_workspace(db_session):
    result = await db_session.execute(
        select(Workspace).where(Workspace.is_default == True)  # noqa: E712
    )
    if result.scalar_one_or_none() is None:
        db_session.add(Workspace(name="default", is_default=True))
        await db_session.commit()


# ── Fix 1 & 2: Intent routing to tools ───────────────────────────────────────


def test_file_operation_intent_has_tools():
    tools = _INTENT_TOOLS[Intent.FILE_OPERATION]
    assert "list_directory" in tools
    assert "search_files" in tools
    assert "read_file" in tools


def test_memory_search_intent_has_tools():
    tools = _INTENT_TOOLS[Intent.MEMORY_SEARCH]
    assert "memory_search" in tools


def test_calendar_operation_intent_has_tools():
    tools = _INTENT_TOOLS[Intent.CALENDAR_OPERATION]
    assert "get_todays_events" in tools
    assert "list_calendar_events" in tools


def test_decompose_file_operation_returns_tools():
    tasks = decompose("list files in my documents folder")
    assert tasks[0].intent == Intent.FILE_OPERATION
    assert "list_directory" in tasks[0].tool_names


def test_decompose_memory_search_returns_tools():
    tasks = decompose("what do you know about Phoenix?")
    assert tasks[0].intent == Intent.MEMORY_SEARCH
    assert "memory_search" in tasks[0].tool_names


# ── Fix 3: New system tools ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cpu_usage_tool_no_psutil(monkeypatch):
    """Gracefully fails when psutil is not installed."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("no psutil")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    tool = CpuUsageTool()
    result = await tool.execute({})
    assert result.success is False
    assert "psutil" in result.error


@pytest.mark.asyncio
async def test_memory_usage_tool_no_psutil(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("no psutil")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    tool = MemoryUsageTool()
    result = await tool.execute({})
    assert result.success is False
    assert "psutil" in result.error


@pytest.mark.asyncio
async def test_process_list_tool_no_psutil(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("no psutil")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    tool = ProcessListTool()
    result = await tool.execute({})
    assert result.success is False
    assert "psutil" in result.error


def test_system_operation_intent_has_new_tools():
    tools = _INTENT_TOOLS[Intent.SYSTEM_OPERATION]
    assert "cpu_usage" in tools
    assert "memory_usage" in tools
    assert "process_list" in tools


# ── Fix 4: Forget command ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_forget_command_removes_memory(db_session):
    m = await remember(db_session, "Phoenix GA target is Q3")
    await db_session.commit()
    assert m.id is not None

    deleted = await forget(db_session, m.id)
    await db_session.commit()
    assert deleted is True

    results = await search_memories(db_session, "Phoenix")
    assert all(r.id != m.id for r in results)


@pytest.mark.asyncio
async def test_forget_nonexistent_returns_false(db_session):
    assert await forget(db_session, 999999) is False


# ── Fix 5: Param validation ───────────────────────────────────────────────────


def test_validate_params_removes_unknown_keys():
    schema = {"path": {"type": "string"}}
    result = _validate_params({"path": "/data", "evil": "injected"}, schema)
    assert "evil" not in result
    assert result["path"] == "/data"


def test_validate_params_coerces_integer():
    schema = {"limit": {"type": "integer"}}
    result = _validate_params({"limit": "10"}, schema)
    assert result["limit"] == 10


def test_validate_params_drops_null_values():
    schema = {"path": {"type": "string"}, "pattern": {"type": "string"}}
    result = _validate_params({"path": "/data", "pattern": None}, schema)
    assert "pattern" not in result
    assert result["path"] == "/data"


def test_validate_params_empty_schema():
    result = _validate_params({"anything": "value"}, {})
    assert result == {}


@pytest.mark.asyncio
async def test_extract_params_validates_output():
    """LLM returning hallucinated keys should have them stripped."""
    fake_llm = MagicMock()
    fake_response = MagicMock()
    fake_response.content = '{"path": "/data/docs", "injected_key": "bad"}'
    fake_llm.complete = AsyncMock(return_value=fake_response)

    schema = {"path": {"type": "string", "description": "Directory path"}}
    result = await extract_params("list my docs folder", "list_directory", schema, fake_llm)
    assert "injected_key" not in result
    assert result.get("path") == "/data/docs"


@pytest.mark.asyncio
async def test_extract_params_returns_empty_on_no_json():
    fake_llm = MagicMock()
    fake_response = MagicMock()
    fake_response.content = "I cannot determine the parameters."
    fake_llm.complete = AsyncMock(return_value=fake_response)

    schema = {"path": {"type": "string"}}
    result = await extract_params("some message", "list_directory", schema, fake_llm)
    assert result == {}


@pytest.mark.asyncio
async def test_extract_params_empty_schema_skips_llm():
    fake_llm = MagicMock()
    fake_llm.complete = AsyncMock()
    result = await extract_params("anything", "system_info", {}, fake_llm)
    assert result == {}
    fake_llm.complete.assert_not_called()


# ── Fix 6: Forget cascade (vector index) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_forget_does_not_raise_when_chroma_missing(db_session, monkeypatch):
    """forget() must succeed even if Chroma is unavailable."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "chromadb":
            raise ImportError("no chromadb")
        return real_import(name, *args, **kwargs)

    m = await remember(db_session, "test memory for cascade")
    await db_session.commit()

    monkeypatch.setattr(builtins, "__import__", mock_import)
    deleted = await forget(db_session, m.id)
    await db_session.commit()
    assert deleted is True


# ── Fix 7: open_application tool ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_application_rejects_unknown_app():
    tool = OpenApplicationTool()
    result = await tool.execute({"app_name": "rm -rf /"})
    assert result.success is False
    assert "not in the permitted" in result.error


@pytest.mark.asyncio
async def test_open_application_rejects_empty_name():
    tool = OpenApplicationTool()
    result = await tool.execute({"app_name": ""})
    assert result.success is False
    assert "required" in result.error


@pytest.mark.asyncio
async def test_open_application_allowed_name_calls_subprocess(monkeypatch):
    import subprocess
    launched = []

    def fake_popen(args, **kwargs):
        launched.append(args)
        return MagicMock()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    tool = OpenApplicationTool()
    result = await tool.execute({"app_name": "notepad"})
    assert result.success is True
    assert len(launched) == 1


# ── Fix 2: MemorySearchTool unit test ─────────────────────────────────────────


def test_memory_search_tool_schema():
    tool = MemorySearchTool()
    assert tool.name == "memory_search"
    assert tool.risk_level == RiskLevel.READ_ONLY
    assert "query" in tool.parameters_schema


@pytest.mark.asyncio
async def test_memory_search_tool_requires_query():
    tool = MemorySearchTool()
    result = await tool.execute({"query": ""})
    assert result.success is False
    assert "required" in result.error


# ── Calendar intent routing ───────────────────────────────────────────────────


def test_classify_calendar_today():
    intent, method = classify("what's on my calendar today?")
    assert intent == Intent.CALENDAR_OPERATION
    assert method == "keyword"


def test_classify_calendar_schedule():
    intent, _ = classify("show me my schedule for this week")
    assert intent == Intent.CALENDAR_OPERATION


def test_classify_calendar_meetings():
    intent, _ = classify("do I have any meetings tomorrow?")
    assert intent == Intent.CALENDAR_OPERATION
