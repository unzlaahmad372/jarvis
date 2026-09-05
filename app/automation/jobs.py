"""Automation job definitions and DB persistence helpers."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.scheduler import (
    CEILING_READ_ONLY,
    OVERLAP_SKIP,
    AutomationScheduler,
    FakeSchedulerBackend,
    JobSpec,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import AutomationExecution, AutomationJob

logger = get_logger(__name__)

# Module-level singleton scheduler (replaced in tests via dependency injection)
_scheduler: AutomationScheduler | None = None


def get_scheduler() -> AutomationScheduler:
    global _scheduler
    if _scheduler is None:
        settings = get_settings()
        backend = FakeSchedulerBackend()  # Real APScheduler backend added in future milestone
        _scheduler = AutomationScheduler(backend, max_jobs=settings.automation_max_jobs)
        _scheduler.start()
    return _scheduler


def reset_scheduler(scheduler: AutomationScheduler | None = None) -> None:
    """Replace the module-level scheduler — used in tests."""
    global _scheduler
    _scheduler = scheduler


async def create_job(
    session: AsyncSession,
    name: str,
    schedule: str,
    action_type: str,
    action_payload: dict[str, Any],
    description: str | None = None,
    permission_ceiling: str = CEILING_READ_ONLY,
    overlap_policy: str = OVERLAP_SKIP,
) -> AutomationJob:
    """Persist a new job to the DB and register it with the scheduler."""
    spec = JobSpec(
        name=name,
        schedule=schedule,
        action_type=action_type,
        action_payload=action_payload,
        description=description,
        permission_ceiling=permission_ceiling,
        overlap_policy=overlap_policy,
    )
    get_scheduler().add_job(spec)

    job = AutomationJob(
        name=name,
        description=description,
        schedule=schedule,
        action_type=action_type,
        action_payload=json.dumps(action_payload),
        permission_ceiling=permission_ceiling,
        overlap_policy=overlap_policy,
        enabled=True,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    logger.info("automation_job_created", name=name, schedule=schedule)
    return job


async def list_jobs(session: AsyncSession) -> list[AutomationJob]:
    result = await session.execute(select(AutomationJob).order_by(AutomationJob.id))
    return list(result.scalars().all())


async def get_job(session: AsyncSession, job_id: int) -> AutomationJob | None:
    return await session.get(AutomationJob, job_id)


async def delete_job(session: AsyncSession, job_id: int) -> bool:
    job = await session.get(AutomationJob, job_id)
    if not job:
        return False
    try:
        get_scheduler().remove_job(job.name)
    except Exception:  # noqa: BLE001
        logger.debug("scheduler_remove_job_skipped", name=job.name)
    await session.delete(job)
    await session.commit()
    logger.info("automation_job_deleted", job_id=job_id, name=job.name)
    return True


async def toggle_job(session: AsyncSession, job_id: int, enabled: bool) -> AutomationJob | None:
    job = await session.get(AutomationJob, job_id)
    if not job:
        return None
    job.enabled = enabled
    try:
        if enabled:
            get_scheduler().enable_job(job.name)
        else:
            get_scheduler().disable_job(job.name)
    except Exception:  # noqa: BLE001
        logger.debug("scheduler_toggle_job_skipped", name=job.name)
    await session.commit()
    await session.refresh(job)
    return job


async def record_execution_start(
    session: AsyncSession,
    job: AutomationJob,
    scheduled_time: datetime,
) -> AutomationExecution:
    """Persist an execution record when a job fires."""
    execution_id = str(uuid.uuid4())
    exec_rec = AutomationExecution(
        job_id=job.id,
        execution_id=execution_id,
        scheduled_time=scheduled_time,
        actual_start_time=datetime.now(UTC),
        status="RUNNING",
    )
    session.add(exec_rec)
    await session.commit()
    await session.refresh(exec_rec)
    return exec_rec


async def record_execution_end(
    session: AsyncSession,
    exec_rec: AutomationExecution,
    status: str,
    result_summary: str | None = None,
    error: str | None = None,
) -> AutomationExecution:
    exec_rec.status = status
    exec_rec.completion_time = datetime.now(UTC)
    exec_rec.result_summary = result_summary
    exec_rec.error = error
    await session.commit()
    await session.refresh(exec_rec)
    return exec_rec


async def list_executions(
    session: AsyncSession, job_id: int, limit: int = 20
) -> list[AutomationExecution]:
    result = await session.execute(
        select(AutomationExecution)
        .where(AutomationExecution.job_id == job_id)
        .order_by(AutomationExecution.scheduled_time.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
