"""Automation API routes — Phase 8.

Endpoints:
  GET    /api/v1/automation/jobs
  POST   /api/v1/automation/jobs
  GET    /api/v1/automation/jobs/{job_id}
  DELETE /api/v1/automation/jobs/{job_id}
  POST   /api/v1/automation/jobs/{job_id}/enable
  POST   /api/v1/automation/jobs/{job_id}/disable
  GET    /api/v1/automation/jobs/{job_id}/executions
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session as get_db
from app.api.schemas.chat import (
    AutomationExecutionOut,
    AutomationJobCreate,
    AutomationJobOut,
    AutomationJobsOut,
)
from app.automation import jobs as job_service
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _check_enabled() -> None:
    if not get_settings().enable_automation:
        raise HTTPException(status_code=503, detail="Automation is disabled.")


@router.get("/jobs", response_model=AutomationJobsOut)
async def list_jobs(db: DbDep) -> AutomationJobsOut:
    _check_enabled()
    all_jobs = await job_service.list_jobs(db)
    return AutomationJobsOut(
        jobs=[AutomationJobOut.model_validate(j) for j in all_jobs],
        total=len(all_jobs),
    )


@router.post("/jobs", response_model=AutomationJobOut, status_code=201)
async def create_job(
    body: AutomationJobCreate, db: DbDep
) -> AutomationJobOut:
    _check_enabled()
    try:
        job = await job_service.create_job(
            session=db,
            name=body.name,
            schedule=body.schedule,
            action_type=body.action_type,
            action_payload=dict(body.action_payload),
            description=body.description,
            permission_ceiling=body.permission_ceiling,
            overlap_policy=body.overlap_policy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AutomationJobOut.model_validate(job)


@router.get("/jobs/{job_id}", response_model=AutomationJobOut)
async def get_job(job_id: int, db: DbDep) -> AutomationJobOut:
    _check_enabled()
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return AutomationJobOut.model_validate(job)


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: int, db: DbDep) -> None:
    _check_enabled()
    deleted = await job_service.delete_job(db, job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")


@router.post("/jobs/{job_id}/enable", response_model=AutomationJobOut)
async def enable_job(job_id: int, db: DbDep) -> AutomationJobOut:
    _check_enabled()
    job = await job_service.toggle_job(db, job_id, enabled=True)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return AutomationJobOut.model_validate(job)


@router.post("/jobs/{job_id}/disable", response_model=AutomationJobOut)
async def disable_job(job_id: int, db: DbDep) -> AutomationJobOut:
    _check_enabled()
    job = await job_service.toggle_job(db, job_id, enabled=False)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return AutomationJobOut.model_validate(job)


@router.get("/jobs/{job_id}/executions", response_model=list[AutomationExecutionOut])
async def get_executions(
    job_id: int, db: DbDep, limit: int = 20
) -> list[AutomationExecutionOut]:
    _check_enabled()
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    execs = await job_service.list_executions(db, job_id, limit=limit)
    return [AutomationExecutionOut.model_validate(e) for e in execs]


@router.post("/jobs/{job_id}/trigger", response_model=AutomationExecutionOut, status_code=202)
async def trigger_job(job_id: int, db: DbDep) -> AutomationExecutionOut:
    """Manually trigger a job execution (fires immediately, respects overlap policy)."""
    _check_enabled()
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if not job.enabled:
        raise HTTPException(status_code=400, detail="Job is disabled.")
    exec_rec = await job_service.record_execution_start(
        db, job, scheduled_time=datetime.now(UTC)
    )
    # Immediately mark as success for manual trigger (real execution is async)
    exec_rec = await job_service.record_execution_end(
        db, exec_rec, status="SUCCESS", result_summary="Manually triggered."
    )
    return AutomationExecutionOut.model_validate(exec_rec)
