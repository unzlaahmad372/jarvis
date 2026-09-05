"""Automation scheduler — persistent APScheduler-backed job runner.

Safety rules (non-negotiable):
- Permission ceiling: READ_ONLY or LOW_RISK only. SENSITIVE/DANGEROUS never auto-approved.
- Overlap policies: SKIP (default), QUEUE, REPLACE, ALLOW.
- A scheduled job cannot grant itself additional privileges.
- Retries use exponential backoff and never make destructive actions less safe.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

# ── Overlap policy constants ──────────────────────────────────────────────────

OVERLAP_SKIP = "SKIP"
OVERLAP_QUEUE = "QUEUE"
OVERLAP_REPLACE = "REPLACE"
OVERLAP_ALLOW = "ALLOW"

VALID_OVERLAP_POLICIES = {OVERLAP_SKIP, OVERLAP_QUEUE, OVERLAP_REPLACE, OVERLAP_ALLOW}

# ── Permission ceiling constants ──────────────────────────────────────────────

CEILING_READ_ONLY = "READ_ONLY"
CEILING_LOW_RISK = "LOW_RISK"

VALID_PERMISSION_CEILINGS = {CEILING_READ_ONLY, CEILING_LOW_RISK}

# ── Execution status constants ────────────────────────────────────────────────

STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_PARTIAL = "PARTIAL"
STATUS_SKIPPED = "SKIPPED"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_CANCELLED = "CANCELLED"


class JobSpec:
    """Validated specification for a scheduled automation job."""

    def __init__(
        self,
        name: str,
        schedule: str,
        action_type: str,
        action_payload: dict[str, Any],
        description: str | None = None,
        permission_ceiling: str = CEILING_READ_ONLY,
        overlap_policy: str = OVERLAP_SKIP,
        enabled: bool = True,
    ) -> None:
        if not name.strip():
            raise ValueError("Job name must not be empty.")
        if not schedule.strip():
            raise ValueError("Job schedule must not be empty.")
        if permission_ceiling not in VALID_PERMISSION_CEILINGS:
            raise ValueError(
                f"Invalid permission_ceiling '{permission_ceiling}'. "
                f"Allowed: {VALID_PERMISSION_CEILINGS}"
            )
        if overlap_policy not in VALID_OVERLAP_POLICIES:
            raise ValueError(
                f"Invalid overlap_policy '{overlap_policy}'. "
                f"Allowed: {VALID_OVERLAP_POLICIES}"
            )
        self.name = name
        self.schedule = schedule
        self.action_type = action_type
        self.action_payload = action_payload
        self.description = description
        self.permission_ceiling = permission_ceiling
        self.overlap_policy = overlap_policy
        self.enabled = enabled


class ExecutionRecord:
    """In-memory record of a single job execution."""

    def __init__(self, job_name: str, scheduled_time: datetime) -> None:
        self.execution_id = str(uuid.uuid4())
        self.job_name = job_name
        self.scheduled_time = scheduled_time
        self.actual_start_time: datetime | None = None
        self.completion_time: datetime | None = None
        self.status: str = STATUS_RUNNING
        self.result_summary: str | None = None
        self.error: str | None = None
        self.retry_count: int = 0

    def complete(self, summary: str) -> None:
        self.status = STATUS_SUCCESS
        self.result_summary = summary
        self.completion_time = datetime.now(UTC)

    def fail(self, error: str) -> None:
        self.status = STATUS_FAILED
        self.error = error
        self.completion_time = datetime.now(UTC)

    def skip(self, reason: str) -> None:
        self.status = STATUS_SKIPPED
        self.result_summary = reason
        self.completion_time = datetime.now(UTC)

    def cancel(self) -> None:
        self.status = STATUS_CANCELLED
        self.completion_time = datetime.now(UTC)

    @property
    def duration_ms(self) -> int | None:
        if self.actual_start_time and self.completion_time:
            delta = self.completion_time - self.actual_start_time
            return int(delta.total_seconds() * 1000)
        return None


class SchedulerBackend(ABC):
    """Abstract scheduler backend — real uses APScheduler, fake uses in-memory."""

    @abstractmethod
    def add_job(self, spec: JobSpec) -> None: ...

    @abstractmethod
    def remove_job(self, name: str) -> None: ...

    @abstractmethod
    def pause_job(self, name: str) -> None: ...

    @abstractmethod
    def resume_job(self, name: str) -> None: ...

    @abstractmethod
    def list_jobs(self) -> list[str]: ...

    @abstractmethod
    def is_running(self, name: str) -> bool: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def shutdown(self) -> None: ...


class FakeSchedulerBackend(SchedulerBackend):
    """Deterministic in-memory scheduler for tests — no wall-clock dependency."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobSpec] = {}
        self._running: set[str] = set()
        self._started = False

    def add_job(self, spec: JobSpec) -> None:
        self._jobs[spec.name] = spec

    def remove_job(self, name: str) -> None:
        self._jobs.pop(name, None)
        self._running.discard(name)

    def pause_job(self, name: str) -> None:
        if name not in self._jobs:
            raise KeyError(f"Job '{name}' not found.")

    def resume_job(self, name: str) -> None:
        if name not in self._jobs:
            raise KeyError(f"Job '{name}' not found.")

    def list_jobs(self) -> list[str]:
        return list(self._jobs.keys())

    def is_running(self, name: str) -> bool:
        return name in self._running

    def mark_running(self, name: str) -> None:
        self._running.add(name)

    def mark_done(self, name: str) -> None:
        self._running.discard(name)

    def start(self) -> None:
        self._started = True

    def shutdown(self) -> None:
        self._started = False

    @property
    def started(self) -> bool:
        return self._started


class AutomationScheduler:
    """High-level automation scheduler.

    Wraps a SchedulerBackend and enforces:
    - permission ceilings (SENSITIVE/DANGEROUS never auto-approved)
    - overlap policies
    - idempotency via execution IDs
    - job count limits
    """

    def __init__(self, backend: SchedulerBackend, max_jobs: int = 50) -> None:
        self._backend = backend
        self._max_jobs = max_jobs
        self._executions: dict[str, ExecutionRecord] = {}  # execution_id -> record
        self._active_by_job: dict[str, str] = {}  # job_name -> execution_id

    def start(self) -> None:
        self._backend.start()

    def shutdown(self) -> None:
        self._backend.shutdown()

    def add_job(self, spec: JobSpec) -> None:
        """Register a new job. Raises if limit exceeded or name duplicate."""
        existing = self._backend.list_jobs()
        if spec.name in existing:
            raise ValueError(f"Job '{spec.name}' already exists.")
        if len(existing) >= self._max_jobs:
            raise ValueError(f"Job limit of {self._max_jobs} reached.")
        self._backend.add_job(spec)

    def remove_job(self, name: str) -> None:
        self._backend.remove_job(name)
        self._active_by_job.pop(name, None)

    def enable_job(self, name: str) -> None:
        self._backend.resume_job(name)

    def disable_job(self, name: str) -> None:
        self._backend.pause_job(name)

    def list_jobs(self) -> list[str]:
        return self._backend.list_jobs()

    def begin_execution(
        self,
        job_name: str,
        spec: JobSpec,
        scheduled_time: datetime,
        idempotency_key: str | None = None,
    ) -> ExecutionRecord | None:
        """Start an execution, applying overlap policy. Returns None if skipped."""
        # Idempotency check
        if idempotency_key:
            for rec in self._executions.values():
                if (
                    rec.job_name == job_name
                    and getattr(rec, "_idempotency_key", None) == idempotency_key
                    and rec.status == STATUS_SUCCESS
                ):
                    return None

        active_id = self._active_by_job.get(job_name)
        if active_id and self._executions.get(active_id, None):
            active = self._executions[active_id]
            if active.status == STATUS_RUNNING:
                if spec.overlap_policy == OVERLAP_SKIP:
                    skipped = ExecutionRecord(job_name, scheduled_time)
                    skipped.skip("Skipped: previous execution still running (SKIP policy).")
                    self._executions[skipped.execution_id] = skipped
                    return None
                elif spec.overlap_policy == OVERLAP_REPLACE:
                    active.cancel()
                    self._active_by_job.pop(job_name, None)
                # QUEUE and ALLOW fall through to create a new execution

        record = ExecutionRecord(job_name, scheduled_time)
        if idempotency_key:
            record._idempotency_key = idempotency_key  # type: ignore[attr-defined]
        record.actual_start_time = datetime.now(UTC)
        self._executions[record.execution_id] = record
        self._active_by_job[job_name] = record.execution_id
        return record

    def complete_execution(self, execution_id: str, summary: str) -> None:
        rec = self._executions[execution_id]
        rec.complete(summary)
        if self._active_by_job.get(rec.job_name) == execution_id:
            self._active_by_job.pop(rec.job_name, None)

    def fail_execution(self, execution_id: str, error: str) -> None:
        rec = self._executions[execution_id]
        rec.fail(error)
        if self._active_by_job.get(rec.job_name) == execution_id:
            self._active_by_job.pop(rec.job_name, None)

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        return self._executions.get(execution_id)

    def list_executions(self, job_name: str | None = None) -> list[ExecutionRecord]:
        recs = list(self._executions.values())
        if job_name:
            recs = [r for r in recs if r.job_name == job_name]
        return sorted(recs, key=lambda r: r.scheduled_time, reverse=True)

    def enforce_permission_ceiling(self, spec: JobSpec, requested_risk: str) -> bool:
        """Return True if the requested risk level is within the job's ceiling.

        SENSITIVE and DANGEROUS are NEVER auto-approved regardless of ceiling.
        """
        if requested_risk in ("SENSITIVE", "DANGEROUS"):
            return False
        if spec.permission_ceiling == CEILING_READ_ONLY:
            return requested_risk == "READ_ONLY"
        if spec.permission_ceiling == CEILING_LOW_RISK:
            return requested_risk in ("READ_ONLY", "LOW_RISK")
        return False
