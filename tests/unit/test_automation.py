"""Phase 8 — Automation tests.

Covers:
- JobSpec validation
- AutomationScheduler: add/remove/list jobs
- Overlap policies: SKIP, QUEUE, REPLACE, ALLOW
- Permission ceiling enforcement (SENSITIVE/DANGEROUS always denied)
- Idempotency
- ExecutionRecord lifecycle
- API endpoints: list, create, get, delete, enable/disable, trigger
- Disabled-503 gate
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.automation.scheduler import (
    CEILING_LOW_RISK,
    CEILING_READ_ONLY,
    OVERLAP_ALLOW,
    OVERLAP_QUEUE,
    OVERLAP_REPLACE,
    OVERLAP_SKIP,
    AutomationScheduler,
    ExecutionRecord,
    FakeSchedulerBackend,
    JobSpec,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_spec(
    name: str = "test-job",
    ceiling: str = CEILING_READ_ONLY,
    overlap: str = OVERLAP_SKIP,
) -> JobSpec:
    return JobSpec(
        name=name,
        schedule="0 8 * * *",
        action_type="tool",
        action_payload={"tool": "system_info"},
        permission_ceiling=ceiling,
        overlap_policy=overlap,
    )


def _make_scheduler(max_jobs: int = 50) -> AutomationScheduler:
    return AutomationScheduler(FakeSchedulerBackend(), max_jobs=max_jobs)


def _now() -> datetime:
    return datetime.now(UTC)


# ── JobSpec validation ────────────────────────────────────────────────────────


def test_jobspec_valid() -> None:
    spec = _make_spec()
    assert spec.name == "test-job"
    assert spec.permission_ceiling == CEILING_READ_ONLY
    assert spec.overlap_policy == OVERLAP_SKIP


def test_jobspec_empty_name_raises() -> None:
    with pytest.raises(ValueError, match="name"):
        JobSpec(name="  ", schedule="0 8 * * *", action_type="tool", action_payload={})


def test_jobspec_empty_schedule_raises() -> None:
    with pytest.raises(ValueError, match="schedule"):
        JobSpec(name="job", schedule="", action_type="tool", action_payload={})


def test_jobspec_invalid_ceiling_raises() -> None:
    with pytest.raises(ValueError, match="permission_ceiling"):
        JobSpec(
            name="job",
            schedule="0 8 * * *",
            action_type="tool",
            action_payload={},
            permission_ceiling="DANGEROUS",
        )


def test_jobspec_invalid_overlap_raises() -> None:
    with pytest.raises(ValueError, match="overlap_policy"):
        JobSpec(
            name="job",
            schedule="0 8 * * *",
            action_type="tool",
            action_payload={},
            overlap_policy="INVALID",
        )


# ── Scheduler: add / remove / list ───────────────────────────────────────────


def test_add_and_list_job() -> None:
    sched = _make_scheduler()
    sched.add_job(_make_spec("job-a"))
    assert "job-a" in sched.list_jobs()


def test_add_duplicate_raises() -> None:
    sched = _make_scheduler()
    sched.add_job(_make_spec("job-a"))
    with pytest.raises(ValueError, match="already exists"):
        sched.add_job(_make_spec("job-a"))


def test_job_limit_enforced() -> None:
    sched = _make_scheduler(max_jobs=2)
    sched.add_job(_make_spec("job-1"))
    sched.add_job(_make_spec("job-2"))
    with pytest.raises(ValueError, match="limit"):
        sched.add_job(_make_spec("job-3"))


def test_remove_job() -> None:
    sched = _make_scheduler()
    sched.add_job(_make_spec("job-a"))
    sched.remove_job("job-a")
    assert "job-a" not in sched.list_jobs()


# ── ExecutionRecord lifecycle ─────────────────────────────────────────────────


def test_execution_complete() -> None:
    rec = ExecutionRecord("job-a", _now())
    rec.actual_start_time = _now()
    rec.complete("done")
    assert rec.status == "SUCCESS"
    assert rec.result_summary == "done"
    assert rec.completion_time is not None


def test_execution_fail() -> None:
    rec = ExecutionRecord("job-a", _now())
    rec.fail("boom")
    assert rec.status == "FAILED"
    assert rec.error == "boom"


def test_execution_skip() -> None:
    rec = ExecutionRecord("job-a", _now())
    rec.skip("already running")
    assert rec.status == "SKIPPED"


def test_execution_cancel() -> None:
    rec = ExecutionRecord("job-a", _now())
    rec.cancel()
    assert rec.status == "CANCELLED"


# ── Overlap policies ──────────────────────────────────────────────────────────


def test_overlap_skip_returns_none_when_running() -> None:
    sched = _make_scheduler()
    spec = _make_spec(overlap=OVERLAP_SKIP)
    sched.add_job(spec)
    t = _now()
    first = sched.begin_execution("test-job", spec, t)
    assert first is not None
    second = sched.begin_execution("test-job", spec, t)
    assert second is None


def test_overlap_allow_creates_second_execution() -> None:
    sched = _make_scheduler()
    spec = _make_spec(overlap=OVERLAP_ALLOW)
    sched.add_job(spec)
    t = _now()
    first = sched.begin_execution("test-job", spec, t)
    second = sched.begin_execution("test-job", spec, t)
    assert first is not None
    assert second is not None
    assert first.execution_id != second.execution_id


def test_overlap_replace_cancels_first() -> None:
    sched = _make_scheduler()
    spec = _make_spec(overlap=OVERLAP_REPLACE)
    sched.add_job(spec)
    t = _now()
    first = sched.begin_execution("test-job", spec, t)
    assert first is not None
    second = sched.begin_execution("test-job", spec, t)
    assert second is not None
    assert first.status == "CANCELLED"


def test_overlap_queue_creates_second_execution() -> None:
    sched = _make_scheduler()
    spec = _make_spec(overlap=OVERLAP_QUEUE)
    sched.add_job(spec)
    t = _now()
    first = sched.begin_execution("test-job", spec, t)
    second = sched.begin_execution("test-job", spec, t)
    assert first is not None
    assert second is not None


# ── Permission ceiling enforcement ────────────────────────────────────────────


def test_read_only_ceiling_allows_read_only() -> None:
    sched = _make_scheduler()
    spec = _make_spec(ceiling=CEILING_READ_ONLY)
    assert sched.enforce_permission_ceiling(spec, "READ_ONLY") is True


def test_read_only_ceiling_denies_low_risk() -> None:
    sched = _make_scheduler()
    spec = _make_spec(ceiling=CEILING_READ_ONLY)
    assert sched.enforce_permission_ceiling(spec, "LOW_RISK") is False


def test_low_risk_ceiling_allows_read_only_and_low_risk() -> None:
    sched = _make_scheduler()
    spec = _make_spec(ceiling=CEILING_LOW_RISK)
    assert sched.enforce_permission_ceiling(spec, "READ_ONLY") is True
    assert sched.enforce_permission_ceiling(spec, "LOW_RISK") is True


def test_sensitive_always_denied_regardless_of_ceiling() -> None:
    sched = _make_scheduler()
    for ceiling in (CEILING_READ_ONLY, CEILING_LOW_RISK):
        spec = _make_spec(ceiling=ceiling)
        assert sched.enforce_permission_ceiling(spec, "SENSITIVE") is False


def test_dangerous_always_denied_regardless_of_ceiling() -> None:
    sched = _make_scheduler()
    for ceiling in (CEILING_READ_ONLY, CEILING_LOW_RISK):
        spec = _make_spec(ceiling=ceiling)
        assert sched.enforce_permission_ceiling(spec, "DANGEROUS") is False


# ── Idempotency ───────────────────────────────────────────────────────────────


def test_idempotency_key_prevents_duplicate_success() -> None:
    sched = _make_scheduler()
    spec = _make_spec()
    sched.add_job(spec)
    t = _now()
    first = sched.begin_execution("test-job", spec, t, idempotency_key="run-001")
    assert first is not None
    sched.complete_execution(first.execution_id, "done")
    second = sched.begin_execution("test-job", spec, t, idempotency_key="run-001")
    assert second is None


# ── Complete / fail execution ─────────────────────────────────────────────────


def test_complete_execution_removes_active() -> None:
    sched = _make_scheduler()
    spec = _make_spec()
    sched.add_job(spec)
    rec = sched.begin_execution("test-job", spec, _now())
    assert rec is not None
    sched.complete_execution(rec.execution_id, "ok")
    stored = sched.get_execution(rec.execution_id)
    assert stored is not None
    assert stored.status == "SUCCESS"


def test_fail_execution() -> None:
    sched = _make_scheduler()
    spec = _make_spec()
    sched.add_job(spec)
    rec = sched.begin_execution("test-job", spec, _now())
    assert rec is not None
    sched.fail_execution(rec.execution_id, "timeout")
    stored = sched.get_execution(rec.execution_id)
    assert stored is not None
    assert stored.status == "FAILED"


def test_list_executions_filtered_by_job() -> None:
    sched = _make_scheduler()
    spec_a = _make_spec("job-a")
    spec_b = _make_spec("job-b")
    sched.add_job(spec_a)
    sched.add_job(spec_b)
    t = _now()
    sched.begin_execution("job-a", spec_a, t)
    sched.begin_execution("job-b", spec_b, t)
    assert len(sched.list_executions("job-a")) == 1
    assert len(sched.list_executions("job-b")) == 1
    assert len(sched.list_executions()) == 2


# ── API endpoint tests (use async test_client from conftest) ──────────────────


@pytest.fixture()
def reset_automation_scheduler() -> object:
    """Reset the module-level scheduler singleton before/after each API test."""
    from app.automation import jobs as job_service

    test_sched = AutomationScheduler(FakeSchedulerBackend(), max_jobs=50)
    test_sched.start()
    job_service.reset_scheduler(test_sched)
    yield test_sched
    job_service.reset_scheduler(None)


_JOB = {"name": "j", "schedule": "0 8 * * *", "action_type": "tool", "action_payload": {}}


@pytest.mark.asyncio
async def test_api_list_jobs_empty(
    test_client: object, reset_automation_scheduler: object
) -> None:
    from httpx import AsyncClient

    c: AsyncClient = test_client  # type: ignore[assignment]
    resp = await c.get("/api/v1/automation/jobs")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_api_create_and_get_job(
    test_client: object, reset_automation_scheduler: object
) -> None:
    from httpx import AsyncClient

    c: AsyncClient = test_client  # type: ignore[assignment]
    payload = {
        "name": "morning-report",
        "schedule": "0 8 * * *",
        "action_type": "tool",
        "action_payload": {"tool": "system_info"},
        "permission_ceiling": "READ_ONLY",
        "overlap_policy": "SKIP",
    }
    resp = await c.post("/api/v1/automation/jobs", json=payload)
    assert resp.status_code == 201
    job = resp.json()
    assert job["name"] == "morning-report"
    assert job["enabled"] is True
    resp2 = await c.get(f"/api/v1/automation/jobs/{job['id']}")
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_api_create_duplicate_returns_400(
    test_client: object, reset_automation_scheduler: object
) -> None:
    from httpx import AsyncClient

    c: AsyncClient = test_client  # type: ignore[assignment]
    await c.post("/api/v1/automation/jobs", json=_JOB)
    resp = await c.post("/api/v1/automation/jobs", json=_JOB)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_delete_job(
    test_client: object, reset_automation_scheduler: object
) -> None:
    from httpx import AsyncClient

    c: AsyncClient = test_client  # type: ignore[assignment]
    payload = {**_JOB, "name": "delete-me"}
    job_id = (await c.post("/api/v1/automation/jobs", json=payload)).json()["id"]
    assert (await c.delete(f"/api/v1/automation/jobs/{job_id}")).status_code == 204
    assert (await c.get(f"/api/v1/automation/jobs/{job_id}")).status_code == 404


@pytest.mark.asyncio
async def test_api_enable_disable_job(
    test_client: object, reset_automation_scheduler: object
) -> None:
    from httpx import AsyncClient

    c: AsyncClient = test_client  # type: ignore[assignment]
    payload = {**_JOB, "name": "toggle-job"}
    job_id = (await c.post("/api/v1/automation/jobs", json=payload)).json()["id"]
    dis = await c.post(f"/api/v1/automation/jobs/{job_id}/disable")
    assert dis.status_code == 200
    assert dis.json()["enabled"] is False
    en = await c.post(f"/api/v1/automation/jobs/{job_id}/enable")
    assert en.status_code == 200
    assert en.json()["enabled"] is True


@pytest.mark.asyncio
async def test_api_trigger_job(
    test_client: object, reset_automation_scheduler: object
) -> None:
    from httpx import AsyncClient

    c: AsyncClient = test_client  # type: ignore[assignment]
    payload = {**_JOB, "name": "trigger-job"}
    job_id = (await c.post("/api/v1/automation/jobs", json=payload)).json()["id"]
    trig = await c.post(f"/api/v1/automation/jobs/{job_id}/trigger")
    assert trig.status_code == 202
    assert trig.json()["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_api_trigger_disabled_returns_400(
    test_client: object, reset_automation_scheduler: object
) -> None:
    from httpx import AsyncClient

    c: AsyncClient = test_client  # type: ignore[assignment]
    payload = {**_JOB, "name": "disabled-trigger"}
    job_id = (await c.post("/api/v1/automation/jobs", json=payload)).json()["id"]
    await c.post(f"/api/v1/automation/jobs/{job_id}/disable")
    assert (await c.post(f"/api/v1/automation/jobs/{job_id}/trigger")).status_code == 400


@pytest.mark.asyncio
async def test_api_get_executions(
    test_client: object, reset_automation_scheduler: object
) -> None:
    from httpx import AsyncClient

    c: AsyncClient = test_client  # type: ignore[assignment]
    payload = {**_JOB, "name": "exec-job"}
    job_id = (await c.post("/api/v1/automation/jobs", json=payload)).json()["id"]
    await c.post(f"/api/v1/automation/jobs/{job_id}/trigger")
    execs = await c.get(f"/api/v1/automation/jobs/{job_id}/executions")
    assert execs.status_code == 200
    assert len(execs.json()) == 1


def test_api_disabled_503() -> None:
    """When enable_automation=False all endpoints return 503."""
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import app

    disabled = Settings(enable_automation=False)
    with patch("app.api.routes.automation.get_settings", return_value=disabled):
        c = TestClient(app, raise_server_exceptions=False)
        assert c.get("/api/v1/automation/jobs").status_code == 503
