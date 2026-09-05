"""Prometheus client abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class PrometheusMetric:
    metric: str
    labels: dict[str, str]
    value: float
    timestamp: datetime


@dataclass
class PrometheusResult:
    query: str
    status: str  # success, error
    results: list[PrometheusMetric] = field(default_factory=list)
    error: str | None = None


class PrometheusClient(ABC):
    @abstractmethod
    async def query(self, promql: str) -> PrometheusResult: ...

    @abstractmethod
    async def query_range(
        self, promql: str, start: datetime, end: datetime, step: str = "1m"
    ) -> PrometheusResult: ...

    @abstractmethod
    async def health(self) -> bool: ...


class FakePrometheusClient(PrometheusClient):
    """Deterministic fake for tests — no real Prometheus required."""

    def __init__(
        self,
        results: dict[str, PrometheusResult] | None = None,
        unavailable: bool = False,
    ) -> None:
        _ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        self._results: dict[str, PrometheusResult] = results or {
            "up": PrometheusResult(
                query="up",
                status="success",
                results=[
                    PrometheusMetric(
                        "up",
                        {"job": "jarvis", "instance": "localhost:8000"},
                        1.0,
                        _ts,
                    ),
                ],
            ),
            "node_memory_MemAvailable_bytes": PrometheusResult(
                query="node_memory_MemAvailable_bytes",
                status="success",
                results=[
                    PrometheusMetric(
                        "node_memory_MemAvailable_bytes",
                        {"instance": "node1:9100"},
                        4294967296.0,
                        _ts,
                    ),
                ],
            ),
        }
        self._unavailable = unavailable

    def _check(self) -> None:
        if self._unavailable:
            raise ConnectionError("Prometheus is not reachable")

    async def query(self, promql: str) -> PrometheusResult:
        self._check()
        return self._results.get(
            promql,
            PrometheusResult(query=promql, status="success", results=[]),
        )

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step: str = "1m"
    ) -> PrometheusResult:
        self._check()
        return await self.query(promql)

    async def health(self) -> bool:
        if self._unavailable:
            return False
        return True


class RealPrometheusClient(PrometheusClient):
    """Wraps the Prometheus HTTP API."""

    def __init__(self, base_url: str, timeout: int = 30) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def query(self, promql: str) -> PrometheusResult:
        # TODO: implement with httpx
        return PrometheusResult(query=promql, status="success", results=[])

    async def query_range(
        self, promql: str, start: datetime, end: datetime, step: str = "1m"
    ) -> PrometheusResult:
        # TODO: implement with httpx
        return PrometheusResult(query=promql, status="success", results=[])

    async def health(self) -> bool:
        # TODO: implement with httpx
        return False
