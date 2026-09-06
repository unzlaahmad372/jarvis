"""Unit tests for Phase 4 — Tools: registry, policy, executor, filesystem, API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.db.models import ToolExecution, Workspace
from app.tools.base import PolicyDecisionType, RiskLevel, Tool, ToolRequest, ToolResult
from app.tools.executor import ToolExecutor
from app.tools.filesystem.access import FileAccessRegistry, PathNotAllowedError
from app.tools.filesystem.tools import (
    FileMetadataTool,
    ListDirectoryTool,
    OpenFileTool,
    ReadFileTool,
    SearchFilesTool,
)
from app.tools.policy import PolicyEngine
from app.tools.registry import ToolRegistry, reset_registry
from app.tools.system.tools import DiskUsageTool, SystemInfoTool

# ── Fake tools ────────────────────────────────────────────────────────────────


class FakeReadOnlyTool(Tool):
    @property
    def name(self) -> str:
        return "fake_read"

    @property
    def description(self) -> str:
        return "Fake read-only tool"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        return ToolResult(tool_name=self.name, success=True, output="read result")


class FakeSensitiveTool(Tool):
    @property
    def name(self) -> str:
        return "fake_sensitive"

    @property
    def description(self) -> str:
        return "Fake sensitive tool"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SENSITIVE

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        return ToolResult(tool_name=self.name, success=True, output="sensitive result")


class FakeDangerousTool(Tool):
    @property
    def name(self) -> str:
        return "fake_dangerous"

    @property
    def description(self) -> str:
        return "Fake dangerous tool"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.DANGEROUS

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        return ToolResult(tool_name=self.name, success=True, output="dangerous result")


class FakeErrorTool(Tool):
    @property
    def name(self) -> str:
        return "fake_error"

    @property
    def description(self) -> str:
        return "Always raises"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        raise RuntimeError("tool exploded")


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
    from app.core.config import get_settings
    return get_settings()


@pytest.fixture
def registry():
    r = ToolRegistry()
    r.register(FakeReadOnlyTool())
    r.register(FakeSensitiveTool())
    r.register(FakeDangerousTool())
    r.register(FakeErrorTool())
    return r


@pytest.fixture
def executor(registry, settings):
    return ToolExecutor(registry=registry, settings=settings)


# ── ToolRegistry ──────────────────────────────────────────────────────────────


def test_registry_register_and_get():
    r = ToolRegistry()
    t = FakeReadOnlyTool()
    r.register(t)
    assert r.get("fake_read") is t


def test_registry_duplicate_raises():
    r = ToolRegistry()
    r.register(FakeReadOnlyTool())
    with pytest.raises(ValueError, match="already registered"):
        r.register(FakeReadOnlyTool())


def test_registry_list_by_max_risk():
    r = ToolRegistry()
    r.register(FakeReadOnlyTool())
    r.register(FakeSensitiveTool())
    r.register(FakeDangerousTool())
    read_only = r.list_tools(max_risk=RiskLevel.READ_ONLY)
    assert all(t.risk_level == RiskLevel.READ_ONLY for t in read_only)
    all_tools = r.list_tools()
    assert len(all_tools) == 3


def test_registry_unknown_tool_returns_none():
    r = ToolRegistry()
    assert r.get("nonexistent") is None


# ── PolicyEngine ──────────────────────────────────────────────────────────────


def test_policy_read_only_always_allowed(settings):
    engine = PolicyEngine(settings)
    req = ToolRequest(tool_name="fake_read")
    decision = engine.evaluate(req, RiskLevel.READ_ONLY)
    assert decision.decision == PolicyDecisionType.ALLOW
    assert decision.policy_rule == "READ_ONLY_ALLOW"


def test_policy_dangerous_always_requires_confirmation(settings):
    engine = PolicyEngine(settings)
    req = ToolRequest(tool_name="fake_dangerous")
    decision = engine.evaluate(req, RiskLevel.DANGEROUS)
    assert decision.decision == PolicyDecisionType.REQUIRES_CONFIRMATION
    assert decision.policy_rule == "DANGEROUS_ALWAYS_CONFIRM"


def test_policy_sensitive_without_confirmation(settings):
    engine = PolicyEngine(settings)
    req = ToolRequest(tool_name="fake_sensitive")
    decision = engine.evaluate(req, RiskLevel.SENSITIVE)
    assert decision.decision == PolicyDecisionType.REQUIRES_CONFIRMATION


def test_policy_sensitive_with_confirmation_id(settings):
    """PolicyEngine no longer trusts a raw confirmation_id string.
    confirmed=True must be passed explicitly (set by ToolExecutor after
    ConfirmationStore.consume() succeeds).
    """
    engine = PolicyEngine(settings)
    req = ToolRequest(tool_name="fake_sensitive", confirmation_id="abc-123")
    # Without confirmed=True the policy still requires confirmation
    decision = engine.evaluate(req, RiskLevel.SENSITIVE)
    assert decision.decision == PolicyDecisionType.REQUIRES_CONFIRMATION
    # With confirmed=True (set by ToolExecutor after store.consume()) it allows
    decision_confirmed = engine.evaluate(req, RiskLevel.SENSITIVE, confirmed=True)
    assert decision_confirmed.decision == PolicyDecisionType.ALLOW
    assert decision_confirmed.policy_rule == "SENSITIVE_CONFIRMED"


def test_policy_dangerous_with_confirmation_id_still_requires_confirmation(settings):
    """DANGEROUS always requires confirmation — confirmation_id does not bypass it."""
    engine = PolicyEngine(settings)
    req = ToolRequest(tool_name="fake_dangerous", confirmation_id="abc-123")
    decision = engine.evaluate(req, RiskLevel.DANGEROUS)
    assert decision.decision == PolicyDecisionType.REQUIRES_CONFIRMATION


# ── ToolExecutor ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_executor_read_only_allowed(executor, db_session):
    req = ToolRequest(tool_name="fake_read")
    result, decision = await executor.execute(req, db_session)
    await db_session.commit()
    assert result.success is True
    assert decision.allowed is True


@pytest.mark.asyncio
async def test_executor_sensitive_blocked_without_confirmation(executor, db_session):
    req = ToolRequest(tool_name="fake_sensitive")
    result, decision = await executor.execute(req, db_session)
    await db_session.commit()
    assert result.success is False
    assert decision.requires_confirmation is True


@pytest.mark.asyncio
async def test_executor_sensitive_allowed_with_confirmation(executor, db_session):
    """ToolExecutor validates confirmation_id via ConfirmationStore.consume().
    A raw string that is not in the store is rejected.
    """
    from app.brain.confirmation import get_confirmation_store
    store = get_confirmation_store()
    # Create a real confirmation token for the fake_sensitive tool
    pending = store.create("fake_sensitive", {}, "SENSITIVE", "SENSITIVE_ACTION_CONFIRMATION")
    req = ToolRequest(tool_name="fake_sensitive", confirmation_id=pending.confirmation_id)
    result, decision = await executor.execute(req, db_session)
    await db_session.commit()
    assert result.success is True
    assert decision.allowed is True


@pytest.mark.asyncio
async def test_executor_unknown_tool(executor, db_session):
    req = ToolRequest(tool_name="does_not_exist")
    result, decision = await executor.execute(req, db_session)
    await db_session.commit()
    assert result.success is False
    assert "Unknown tool" in (result.error or "")


@pytest.mark.asyncio
async def test_executor_tool_exception_handled(executor, db_session):
    req = ToolRequest(tool_name="fake_error")
    result, decision = await executor.execute(req, db_session)
    await db_session.commit()
    assert result.success is False
    assert "tool exploded" in (result.error or "")


@pytest.mark.asyncio
async def test_executor_writes_audit_log(executor, db_session):
    req = ToolRequest(tool_name="fake_read")
    await executor.execute(req, db_session)
    await db_session.commit()
    rows = (await db_session.execute(select(ToolExecution))).scalars().all()
    assert len(rows) == 1
    assert rows[0].tool_name == "fake_read"


@pytest.mark.asyncio
async def test_executor_truncates_large_output(db_session, settings):
    class BigOutputTool(FakeReadOnlyTool):
        async def execute(self, parameters: dict[str, Any]) -> ToolResult:
            return ToolResult(tool_name=self.name, success=True, output="x" * 99999)

    r = ToolRegistry()
    r.register(BigOutputTool())
    ex = ToolExecutor(registry=r, settings=settings)
    result, _ = await ex.execute(ToolRequest(tool_name="fake_read"), db_session)
    assert result.truncated is True
    assert len(result.output) <= settings.max_tool_output_size


# ── FileAccessRegistry ────────────────────────────────────────────────────────


def test_file_access_registry_allows_inside_root(tmp_path):
    far = FileAccessRegistry()
    far.add_root("tmp", tmp_path)
    child = tmp_path / "subdir" / "file.txt"
    assert far.validate(child) == child.resolve()


def test_file_access_registry_blocks_outside_root(tmp_path):
    far = FileAccessRegistry()
    far.add_root("tmp", tmp_path)
    with pytest.raises(PathNotAllowedError):
        far.validate(tmp_path / ".." / "etc" / "passwd")


def test_file_access_registry_blocks_traversal_string(tmp_path):
    far = FileAccessRegistry()
    far.add_root("tmp", tmp_path)
    with pytest.raises(PathNotAllowedError):
        far.validate(str(tmp_path) + "/../../etc/passwd")


def test_file_access_registry_is_allowed(tmp_path):
    far = FileAccessRegistry()
    far.add_root("tmp", tmp_path)
    assert far.is_allowed(tmp_path / "file.txt") is True
    assert far.is_allowed(Path("/etc/passwd")) is False


# ── Filesystem tools ──────────────────────────────────────────────────────────


@pytest.fixture
def tmp_registry(tmp_path):
    far = FileAccessRegistry()
    far.add_root("tmp", tmp_path)
    return far, tmp_path


@pytest.mark.asyncio
async def test_list_directory(tmp_registry):
    far, tmp_path = tmp_registry
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "subdir").mkdir()
    tool = ListDirectoryTool(far)
    result = await tool.execute({"path": str(tmp_path)})
    assert result.success is True
    entries = json.loads(result.output)
    names = [e["name"] for e in entries]
    assert "a.txt" in names
    assert "subdir" in names


@pytest.mark.asyncio
async def test_list_directory_blocked(tmp_registry):
    far, tmp_path = tmp_registry
    tool = ListDirectoryTool(far)
    result = await tool.execute({"path": "/etc"})
    assert result.success is False
    assert "denied" in (result.error or "").lower() or "outside" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_read_file(tmp_registry):
    far, tmp_path = tmp_registry
    f = tmp_path / "hello.txt"
    f.write_text("hello world")
    tool = ReadFileTool(far)
    result = await tool.execute({"path": str(f)})
    assert result.success is True
    assert "hello world" in result.output


@pytest.mark.asyncio
async def test_read_file_blocked(tmp_registry):
    far, _ = tmp_registry
    tool = ReadFileTool(far)
    result = await tool.execute({"path": "/etc/passwd"})
    assert result.success is False


@pytest.mark.asyncio
async def test_search_files(tmp_registry):
    far, tmp_path = tmp_registry
    (tmp_path / "report.pdf").write_text("pdf")
    (tmp_path / "notes.txt").write_text("txt")
    tool = SearchFilesTool(far)
    result = await tool.execute({"path": str(tmp_path), "pattern": "*.pdf"})
    assert result.success is True
    matches = json.loads(result.output)
    assert any("report.pdf" in m["path"] for m in matches)


@pytest.mark.asyncio
async def test_file_metadata(tmp_registry):
    far, tmp_path = tmp_registry
    f = tmp_path / "meta.txt"
    f.write_text("data")
    tool = FileMetadataTool(far)
    result = await tool.execute({"path": str(f)})
    assert result.success is True
    meta = json.loads(result.output)
    assert meta["type"] == "file"
    assert meta["size_bytes"] == 4


# ── OpenFileTool ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_file_blocked_outside_root(tmp_registry):
    far, _ = tmp_registry
    tool = OpenFileTool(far)
    result = await tool.execute({"path": "/etc/passwd"})
    assert result.success is False
    assert "denied" in (result.error or "").lower() or "outside" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_open_file_not_a_file(tmp_registry):
    far, tmp_path = tmp_registry
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    tool = OpenFileTool(far)
    result = await tool.execute({"path": str(subdir)})  # directory, not file
    assert result.success is False
    assert "Not a file" in (result.error or "")


@pytest.mark.asyncio
async def test_open_file_glob_multiple_candidates(tmp_registry):
    far, tmp_path = tmp_registry
    (tmp_path / "report1.pdf").write_bytes(b"pdf1")
    (tmp_path / "report2.pdf").write_bytes(b"pdf2")
    tool = OpenFileTool(far)
    result = await tool.execute({"path": str(tmp_path / "*.pdf")})
    assert result.success is True
    data = json.loads(result.output)
    assert "candidates" in data
    assert len(data["candidates"]) == 2


@pytest.mark.asyncio
async def test_open_file_glob_no_match(tmp_registry):
    far, tmp_path = tmp_registry
    tool = OpenFileTool(far)
    result = await tool.execute({"path": str(tmp_path / "*.xyz")})
    assert result.success is False
    assert "No files matched" in (result.error or "")


@pytest.mark.asyncio
async def test_open_file_glob_single_match_opens(tmp_registry, monkeypatch):
    """Single glob match resolves to exact path and calls OS opener."""
    far, tmp_path = tmp_registry
    f = tmp_path / "only.txt"
    f.write_text("content")

    opened: list[str] = []

    class FakeProc:
        pass

    def fake_popen(cmd: list[str], **_kwargs: object) -> FakeProc:  # noqa: ARG001
        opened.append(cmd[-1])
        return FakeProc()

    import subprocess
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    tool = OpenFileTool(far)
    result = await tool.execute({"path": str(tmp_path / "*.txt")})
    assert result.success is True
    data = json.loads(result.output)
    assert "opened" in data
    assert len(opened) == 1


@pytest.mark.asyncio
async def test_open_file_exact_path_opens(tmp_registry, monkeypatch):
    far, tmp_path = tmp_registry
    f = tmp_path / "doc.txt"
    f.write_text("hello")

    opened: list[str] = []

    class FakeProc:
        pass

    def fake_popen(cmd: list[str], **_kwargs: object) -> FakeProc:  # noqa: ARG001
        opened.append(cmd[-1])
        return FakeProc()

    import subprocess
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    tool = OpenFileTool(far)
    result = await tool.execute({"path": str(f)})
    assert result.success is True
    assert len(opened) == 1


@pytest.mark.asyncio
async def test_open_file_os_error_reported(tmp_registry, monkeypatch):
    far, tmp_path = tmp_registry
    f = tmp_path / "doc.txt"
    f.write_text("hello")

    import subprocess
    def bad_popen(*_args: object, **_kwargs: object) -> None:
        raise OSError("no application")

    monkeypatch.setattr(subprocess, "Popen", bad_popen)

    tool = OpenFileTool(far)
    result = await tool.execute({"path": str(f)})
    assert result.success is False
    assert "OS could not open" in (result.error or "")


@pytest.mark.asyncio
async def test_open_file_path_traversal_blocked(tmp_registry):
    far, tmp_path = tmp_registry
    tool = OpenFileTool(far)
    result = await tool.execute({"path": str(tmp_path) + "/../../etc/passwd"})
    assert result.success is False


# ── System tools ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_system_info():
    tool = SystemInfoTool()
    result = await tool.execute({})
    assert result.success is True
    info = json.loads(result.output)
    assert "os" in info
    assert "python_version" in info


@pytest.mark.asyncio
async def test_disk_usage():
    tool = DiskUsageTool()
    result = await tool.execute({"path": "."})
    assert result.success is True
    info = json.loads(result.output)
    assert "total_bytes" in info
    assert info["used_pct"] >= 0


# ── Tools API ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_list_tools(test_client):
    resp = await test_client.get("/api/v1/tools")
    assert resp.status_code == 200
    tools = resp.json()
    assert isinstance(tools, list)
    names = [t["name"] for t in tools]
    assert "system_info" in names
    assert "list_directory" in names


@pytest.mark.asyncio
async def test_api_execute_read_only_tool(test_client):
    resp = await test_client.post(
        "/api/v1/tools/system_info/execute",
        json={"parameters": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["policy_decision"] == "ALLOW"


@pytest.mark.asyncio
async def test_api_execute_unknown_tool(test_client):
    resp = await test_client.post(
        "/api/v1/tools/nonexistent_tool/execute",
        json={"parameters": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_api_audit_log(test_client):
    await test_client.post("/api/v1/tools/system_info/execute", json={"parameters": {}})
    resp = await test_client.get("/api/v1/tools/audit")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
