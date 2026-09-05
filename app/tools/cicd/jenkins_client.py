"""Jenkins client abstraction.

JenkinsClient is the interface all Jenkins tools use.
FakeJenkinsClient is used in tests — no real server required.
RealJenkinsClient wraps the Jenkins HTTP API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class JenkinsBuild:
    job_name: str
    build_number: int
    result: str | None  # SUCCESS, FAILURE, ABORTED, UNSTABLE, None=running
    duration_ms: int
    timestamp: datetime
    url: str
    branch: str | None = None
    failed_stage: str | None = None


@dataclass
class JenkinsJob:
    name: str
    url: str
    last_build: JenkinsBuild | None = None


class JenkinsClient(ABC):
    @abstractmethod
    async def list_jobs(self) -> list[JenkinsJob]: ...

    @abstractmethod
    async def get_job(self, job_name: str) -> JenkinsJob | None: ...

    @abstractmethod
    async def list_builds(self, job_name: str, limit: int = 10) -> list[JenkinsBuild]: ...

    @abstractmethod
    async def get_build(self, job_name: str, build_number: int) -> JenkinsBuild | None: ...

    @abstractmethod
    async def get_console_log(
        self, job_name: str, build_number: int, tail_lines: int = 100
    ) -> str: ...


class FakeJenkinsClient(JenkinsClient):
    """Deterministic fake for tests — no real Jenkins required."""

    def __init__(
        self,
        jobs: list[JenkinsJob] | None = None,
        builds: dict[str, list[JenkinsBuild]] | None = None,
        logs: dict[str, str] | None = None,
        unavailable: bool = False,
    ) -> None:
        _ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        self._jobs = jobs or [
            JenkinsJob(
                name="phoenix-build",
                url="http://jenkins/job/phoenix-build",
                last_build=JenkinsBuild(
                    job_name="phoenix-build",
                    build_number=381,
                    result="FAILURE",
                    duration_ms=43000,
                    timestamp=_ts,
                    url="http://jenkins/job/phoenix-build/381",
                    branch="main",
                    failed_stage="msST",
                ),
            ),
            JenkinsJob(
                name="mtas-deploy",
                url="http://jenkins/job/mtas-deploy",
                last_build=JenkinsBuild(
                    job_name="mtas-deploy",
                    build_number=120,
                    result="SUCCESS",
                    duration_ms=120000,
                    timestamp=_ts,
                    url="http://jenkins/job/mtas-deploy/120",
                    branch="release/2.4",
                ),
            ),
        ]
        self._builds: dict[str, list[JenkinsBuild]] = builds or {
            "phoenix-build": [
                JenkinsBuild("phoenix-build", 381, "FAILURE", 43000, _ts,
                             "http://jenkins/job/phoenix-build/381", "main", "msST"),
                JenkinsBuild("phoenix-build", 380, "SUCCESS", 38000, _ts,
                             "http://jenkins/job/phoenix-build/380", "main"),
                JenkinsBuild("phoenix-build", 379, "SUCCESS", 41000, _ts,
                             "http://jenkins/job/phoenix-build/379", "main"),
            ]
        }
        self._logs = logs or {
            "phoenix-build/381": (
                "Started by user admin\n[msST] FAILED: connection timeout\nBuild failed."
            ),
        }
        self._unavailable = unavailable

    def _check(self) -> None:
        if self._unavailable:
            raise ConnectionError("Jenkins is not reachable")

    async def list_jobs(self) -> list[JenkinsJob]:
        self._check()
        return list(self._jobs)

    async def get_job(self, job_name: str) -> JenkinsJob | None:
        self._check()
        return next((j for j in self._jobs if j.name == job_name), None)

    async def list_builds(self, job_name: str, limit: int = 10) -> list[JenkinsBuild]:
        self._check()
        return list(self._builds.get(job_name, [])[:limit])

    async def get_build(self, job_name: str, build_number: int) -> JenkinsBuild | None:
        self._check()
        return next(
            (b for b in self._builds.get(job_name, []) if b.build_number == build_number),
            None,
        )

    async def get_console_log(self, job_name: str, build_number: int, tail_lines: int = 100) -> str:
        self._check()
        key = f"{job_name}/{build_number}"
        return self._logs.get(key, f"No log found for {job_name} #{build_number}")


class RealJenkinsClient(JenkinsClient):
    """Wraps the Jenkins HTTP API. Credentials come from Settings — never logged."""

    def __init__(self, base_url: str, user: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._auth = (user, token) if user and token else None

    async def list_jobs(self) -> list[JenkinsJob]:
        # TODO: implement with httpx
        return []

    async def get_job(self, job_name: str) -> JenkinsJob | None:
        # TODO: implement with httpx
        return None

    async def list_builds(self, job_name: str, limit: int = 10) -> list[JenkinsBuild]:
        # TODO: implement with httpx
        return []

    async def get_build(self, job_name: str, build_number: int) -> JenkinsBuild | None:
        # TODO: implement with httpx
        return None

    async def get_console_log(self, job_name: str, build_number: int, tail_lines: int = 100) -> str:
        # TODO: implement with httpx
        return ""
