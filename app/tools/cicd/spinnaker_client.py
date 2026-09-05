"""Spinnaker client abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class SpinnakerStage:
    name: str
    status: str  # SUCCEEDED, FAILED_CONTINUE, TERMINAL, RUNNING, CANCELED
    duration_ms: int
    start_time: datetime | None = None


@dataclass
class SpinnakerExecution:
    id: str
    pipeline_name: str
    application: str
    status: str
    start_time: datetime | None
    duration_ms: int
    trigger: str | None
    stages: list[SpinnakerStage]
    url: str


class SpinnakerClient(ABC):
    @abstractmethod
    async def list_applications(self) -> list[str]: ...

    @abstractmethod
    async def list_pipelines(self, application: str) -> list[str]: ...

    @abstractmethod
    async def list_executions(
        self, application: str, pipeline_name: str, limit: int = 5
    ) -> list[SpinnakerExecution]: ...

    @abstractmethod
    async def get_execution(self, execution_id: str) -> SpinnakerExecution | None: ...

    @abstractmethod
    async def health(self) -> bool: ...


class FakeSpinnakerClient(SpinnakerClient):
    """Deterministic fake for tests — no real Spinnaker required."""

    def __init__(
        self,
        applications: list[str] | None = None,
        pipelines: dict[str, list[str]] | None = None,
        executions: dict[str, list[SpinnakerExecution]] | None = None,
        unavailable: bool = False,
        base_url: str = "http://spinnaker:9000",
    ) -> None:
        _ts = datetime(2024, 1, 15, 14, 47, 0, tzinfo=UTC)
        self._base = base_url
        self._applications = applications or ["phoenix", "mtas"]
        self._pipelines = pipelines or {
            "phoenix": ["prewash", "deploy-staging", "deploy-prod"],
            "mtas": ["build-and-test", "deploy"],
        }
        self._executions: dict[str, list[SpinnakerExecution]] = executions or {
            "phoenix/prewash": [
                SpinnakerExecution(
                    id="exec-934782",
                    pipeline_name="prewash",
                    application="phoenix",
                    status="TERMINAL",
                    start_time=_ts,
                    duration_ms=1800000,
                    trigger="jenkins",
                    stages=[
                        SpinnakerStage("Bake", "SUCCEEDED", 120000, _ts),
                        SpinnakerStage("Deploy to msST", "TERMINAL", 300000, _ts),
                        SpinnakerStage("Run Tests", "CANCELED", 0, None),
                    ],
                    url=f"{base_url}/#/applications/phoenix/executions/exec-934782",
                ),
                SpinnakerExecution(
                    id="exec-934781",
                    pipeline_name="prewash",
                    application="phoenix",
                    status="SUCCEEDED",
                    start_time=_ts,
                    duration_ms=1650000,
                    trigger="jenkins",
                    stages=[
                        SpinnakerStage("Bake", "SUCCEEDED", 115000, _ts),
                        SpinnakerStage("Deploy to msST", "SUCCEEDED", 290000, _ts),
                        SpinnakerStage("Run Tests", "SUCCEEDED", 420000, _ts),
                    ],
                    url=f"{base_url}/#/applications/phoenix/executions/exec-934781",
                ),
            ]
        }
        self._unavailable = unavailable

    def _check(self) -> None:
        if self._unavailable:
            raise ConnectionError("Spinnaker is not reachable")

    async def list_applications(self) -> list[str]:
        self._check()
        return list(self._applications)

    async def list_pipelines(self, application: str) -> list[str]:
        self._check()
        return list(self._pipelines.get(application, []))

    async def list_executions(
        self, application: str, pipeline_name: str, limit: int = 5
    ) -> list[SpinnakerExecution]:
        self._check()
        key = f"{application}/{pipeline_name}"
        return list(self._executions.get(key, [])[:limit])

    async def get_execution(self, execution_id: str) -> SpinnakerExecution | None:
        self._check()
        for execs in self._executions.values():
            for ex in execs:
                if ex.id == execution_id:
                    return ex
        return None

    async def health(self) -> bool:
        return not self._unavailable


class RealSpinnakerClient(SpinnakerClient):
    """Wraps the Spinnaker Gate API. Token comes from Settings — never logged."""

    def __init__(self, gate_url: str, token: str) -> None:
        self._base = gate_url.rstrip("/")
        self._token = token

    async def list_applications(self) -> list[str]:
        # TODO: implement with httpx
        return []

    async def list_pipelines(self, application: str) -> list[str]:
        # TODO: implement with httpx
        return []

    async def list_executions(
        self, application: str, pipeline_name: str, limit: int = 5
    ) -> list[SpinnakerExecution]:
        # TODO: implement with httpx
        return []

    async def get_execution(self, execution_id: str) -> SpinnakerExecution | None:
        # TODO: implement with httpx
        return None

    async def health(self) -> bool:
        # TODO: implement with httpx
        return False
