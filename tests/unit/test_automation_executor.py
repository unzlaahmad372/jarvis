"""Phase 40 — AutomationExecutor tests.

Covers:
- tool job success: runs tool, persists SUCCESS execution record
- permission ceiling violation: raises PermissionError before tool runs
- unknown tool: raises ValueError
- tool failure: persists FAILED execution record
- chat job success: runs through orchestrator, persists SUCCESS
- init_executor wires executor_fn onto APSchedulerBackend
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.automation.executor import AutomationExecutor, _CEILING_ALLOWED
from app.automation.scheduler import (
    CEILING_LOW_RISK,
    CEILING_READ_ONLY,
    AutomationScheduler,
    FakeSchedulerBackend,
)
from app.tools.base import RiskLevel, ToolResult


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_tool(name: str, risk: RiskLevel, output: str = "ok", success: bool = True) -> MagicMock:
    tool = MagicMock()
    tool.risk_level = risk
    result = ToolResult(tool_name=name, success=success, output=output, error=None if success else output)
    return tool, result


def _make_executor(
    tool_name: str = "system_info",
    risk: RiskLevel = RiskLevel.READ_ONLY,
    tool_output: str = "cpu: 10%",
    tool_success: bool = True,
    chat_reply: str = "Morning briefing done.",
) -> tuple[AutomationExecutor, MagicMock, MagicMock, MagicMock]:
    """Build an AutomationExecutor with all dependencies mocked."""
    tool_mock = MagicMock()
    tool_mock.risk_level = risk
    tool_result = ToolResult(
        tool_name=tool_name,
        success=tool_success,
        output=tool_output,
        error=None if tool_success else tool_output,
    )

    registry = MagicMock()
    registry.get.return_value = tool_mock

    executor = MagicMock()
    executor.execute = AsyncMock(
        return_value=(tool_result, MagicMock(decision=MagicMock(value="ALLOW")))
    )

    asst_msg = MagicMock()
    asst_msg.content = chat_reply
    orchestrator = MagicMock()
    orchestrator.chat = AsyncMock(return_value=(MagicMock(), asst_msg, False, None, None))

    scheduler = AutomationScheduler(FakeSchedulerBackend())

    auto_exec = AutomationExecutor(
        scheduler=scheduler,
        tool_registry=registry,
        tool_executor=executor,
        orchestrator=orchestrator,
        session_factory=None,  # replaced per test
    )
    return auto_exec, registry, executor, orchestrator


def _make_db_job(
    name: str = "test-job",
    action_type: str = "tool",
    payload: dict | None = None,
    ceiling: str = CEILING_READ_ONLY,
    enabled: bool = True,
) -> MagicMock:
    job = MagicMock()
    job.name = name
    job.action_type = action_type
    job.action_payload = json.dumps(payload or {"tool": "system_info", "parameters": {}})
    job.permission_ceiling = ceiling
    job.enabled = enabled
    job.last_run_at = None
    return job


def _make_session_factory(job: MagicMock | None) -> MagicMock:
    """Return a session factory whose context manager yields a mock session."""
    exec_rec = MagicMock()
    exec_rec.id = 1

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=job)))

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=cm)
    return factory, session, exec_rec


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_job_success_persists_success_record() -> None:
    """A tool job that succeeds writes a SUCCESS execution record."""
    auto_exec, registry, executor_mock, _ = _make_executor(
        tool_name="system_info", risk=RiskLevel.READ_ONLY, tool_output="cpu: 5%"
    )
    job = _make_db_job(action_type="tool", payload={"tool": "system_info", "parameters": {}})
    factory, session, _ = _make_session_factory(job)
    auto_exec._session_factory = factory

    with (
        patch("app.automation.executor.job_service") as mock_svc,
    ):
        mock_svc.record_execution_start = AsyncMock(return_value=MagicMock(id=1))
        mock_svc.record_execution_end = AsyncMock(return_value=MagicMock())

        await auto_exec.run_job("test-job", {"tool": "system_info"})

        mock_svc.record_execution_end.assert_awaited_once()
        call_kwargs = mock_svc.record_execution_end.call_args
        assert call_kwargs.kwargs["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_tool_job_ceiling_violation_persists_failed_record() -> None:
    """A tool whose risk exceeds the job ceiling writes a FAILED record."""
    auto_exec, registry, _, _ = _make_executor(
        tool_name="open_application", risk=RiskLevel.LOW_RISK
    )
    # Job ceiling is READ_ONLY — LOW_RISK tool should be blocked
    job = _make_db_job(
        action_type="tool",
        payload={"tool": "open_application", "parameters": {}},
        ceiling=CEILING_READ_ONLY,
    )
    factory, session, _ = _make_session_factory(job)
    auto_exec._session_factory = factory

    with patch("app.automation.executor.job_service") as mock_svc:
        mock_svc.record_execution_start = AsyncMock(return_value=MagicMock(id=1))
        mock_svc.record_execution_end = AsyncMock(return_value=MagicMock())

        await auto_exec.run_job("test-job", {})

        call_kwargs = mock_svc.record_execution_end.call_args
        assert call_kwargs.kwargs["status"] == "FAILED"
        assert "ceiling" in call_kwargs.kwargs["error"].lower()


@pytest.mark.asyncio
async def test_tool_job_unknown_tool_persists_failed_record() -> None:
    """An unregistered tool name writes a FAILED record."""
    auto_exec, registry, _, _ = _make_executor()
    registry.get.return_value = None  # tool not found

    job = _make_db_job(payload={"tool": "nonexistent_tool", "parameters": {}})
    factory, _, _ = _make_session_factory(job)
    auto_exec._session_factory = factory

    with patch("app.automation.executor.job_service") as mock_svc:
        mock_svc.record_execution_start = AsyncMock(return_value=MagicMock(id=1))
        mock_svc.record_execution_end = AsyncMock(return_value=MagicMock())

        await auto_exec.run_job("test-job", {})

        call_kwargs = mock_svc.record_execution_end.call_args
        assert call_kwargs.kwargs["status"] == "FAILED"
        assert "not registered" in call_kwargs.kwargs["error"]


@pytest.mark.asyncio
async def test_tool_job_execution_failure_persists_failed_record() -> None:
    """When the tool itself fails, a FAILED record is written."""
    auto_exec, _, executor_mock, _ = _make_executor(
        tool_success=False, tool_output="disk full"
    )
    job = _make_db_job(payload={"tool": "system_info", "parameters": {}})
    factory, _, _ = _make_session_factory(job)
    auto_exec._session_factory = factory

    with patch("app.automation.executor.job_service") as mock_svc:
        mock_svc.record_execution_start = AsyncMock(return_value=MagicMock(id=1))
        mock_svc.record_execution_end = AsyncMock(return_value=MagicMock())

        await auto_exec.run_job("test-job", {})

        call_kwargs = mock_svc.record_execution_end.call_args
        assert call_kwargs.kwargs["status"] == "FAILED"


@pytest.mark.asyncio
async def test_chat_job_success_persists_success_record() -> None:
    """A chat job runs through the orchestrator and writes a SUCCESS record."""
    auto_exec, _, _, orchestrator = _make_executor(chat_reply="Briefing complete.")
    job = _make_db_job(
        action_type="chat",
        payload={"message": "Generate morning briefing."},
    )
    factory, _, _ = _make_session_factory(job)
    auto_exec._session_factory = factory

    with patch("app.automation.executor.job_service") as mock_svc:
        mock_svc.record_execution_start = AsyncMock(return_value=MagicMock(id=1))
        mock_svc.record_execution_end = AsyncMock(return_value=MagicMock())

        await auto_exec.run_job("test-job", {})

        orchestrator.chat.assert_awaited_once()
        call_kwargs = mock_svc.record_execution_end.call_args
        assert call_kwargs.kwargs["status"] == "SUCCESS"
        assert "Briefing complete." in call_kwargs.kwargs["result_summary"]


@pytest.mark.asyncio
async def test_disabled_job_skips_execution() -> None:
    """A disabled job is skipped without creating an execution record."""
    auto_exec, _, _, _ = _make_executor()
    job = _make_db_job(enabled=False)
    factory, _, _ = _make_session_factory(job)
    auto_exec._session_factory = factory

    with patch("app.automation.executor.job_service") as mock_svc:
        mock_svc.record_execution_start = AsyncMock()

        await auto_exec.run_job("test-job", {})

        mock_svc.record_execution_start.assert_not_awaited()


def test_init_executor_wires_executor_fn_onto_backend() -> None:
    """init_executor patches _executor_fn on APSchedulerBackend."""
    from app.automation.jobs import init_executor, reset_scheduler
    from app.automation.scheduler import APSchedulerBackend

    backend = MagicMock(spec=APSchedulerBackend)
    backend._executor_fn = None
    sched = AutomationScheduler(backend)
    sched.start = MagicMock()

    reset_scheduler(sched)

    registry = MagicMock()
    executor = MagicMock()
    orchestrator = MagicMock()
    session_factory = MagicMock()

    init_executor(registry, executor, orchestrator, session_factory)

    assert backend._executor_fn is not None
    reset_scheduler(None)


# ── Ceiling constant sanity ───────────────────────────────────────────────────


def test_ceiling_allowed_constants() -> None:
    assert "READ_ONLY" in _CEILING_ALLOWED[CEILING_READ_ONLY]
    assert "LOW_RISK" not in _CEILING_ALLOWED[CEILING_READ_ONLY]
    assert "LOW_RISK" in _CEILING_ALLOWED[CEILING_LOW_RISK]
    assert "SENSITIVE" not in _CEILING_ALLOWED[CEILING_LOW_RISK]
    assert "DANGEROUS" not in _CEILING_ALLOWED[CEILING_LOW_RISK]
