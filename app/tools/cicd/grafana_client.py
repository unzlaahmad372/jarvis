"""Grafana client abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class GrafanaDashboard:
    uid: str
    title: str
    url: str
    tags: list[str] = field(default_factory=list)
    folder: str | None = None


class GrafanaClient(ABC):
    @abstractmethod
    async def list_dashboards(self, query: str = "") -> list[GrafanaDashboard]: ...

    @abstractmethod
    async def get_dashboard(self, uid: str) -> GrafanaDashboard | None: ...

    @abstractmethod
    async def find_dashboard(self, title: str) -> GrafanaDashboard | None: ...

    @abstractmethod
    async def build_dashboard_url(
        self, uid: str, from_time: str = "now-6h", to_time: str = "now"
    ) -> str: ...

    @abstractmethod
    async def health(self) -> bool: ...


class FakeGrafanaClient(GrafanaClient):
    """Deterministic fake for tests — no real Grafana required."""

    def __init__(
        self,
        dashboards: list[GrafanaDashboard] | None = None,
        unavailable: bool = False,
        base_url: str = "http://grafana:3000",
    ) -> None:
        self._base = base_url
        self._dashboards = dashboards or [
            GrafanaDashboard(
                uid="phoenix-ci",
                title="Phoenix CI",
                url=f"{base_url}/d/phoenix-ci",
                tags=["ci", "phoenix"],
                folder="CI/CD",
            ),
            GrafanaDashboard(
                uid="mtas-infra",
                title="MTAS Infrastructure",
                url=f"{base_url}/d/mtas-infra",
                tags=["infra", "mtas"],
                folder="Infrastructure",
            ),
        ]
        self._unavailable = unavailable

    def _check(self) -> None:
        if self._unavailable:
            raise ConnectionError("Grafana is not reachable")

    async def list_dashboards(self, query: str = "") -> list[GrafanaDashboard]:
        self._check()
        if not query:
            return list(self._dashboards)
        q = query.lower()
        return [d for d in self._dashboards if q in d.title.lower()]

    async def get_dashboard(self, uid: str) -> GrafanaDashboard | None:
        self._check()
        return next((d for d in self._dashboards if d.uid == uid), None)

    async def find_dashboard(self, title: str) -> GrafanaDashboard | None:
        self._check()
        t = title.lower()
        return next((d for d in self._dashboards if t in d.title.lower()), None)

    async def build_dashboard_url(
        self, uid: str, from_time: str = "now-6h", to_time: str = "now"
    ) -> str:
        self._check()
        return f"{self._base}/d/{uid}?from={from_time}&to={to_time}"

    async def health(self) -> bool:
        return not self._unavailable


class RealGrafanaClient(GrafanaClient):
    """Wraps the Grafana HTTP API. Token comes from Settings — never logged."""

    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._token = token

    async def list_dashboards(self, query: str = "") -> list[GrafanaDashboard]:
        # TODO: implement with httpx
        return []

    async def get_dashboard(self, uid: str) -> GrafanaDashboard | None:
        # TODO: implement with httpx
        return None

    async def find_dashboard(self, title: str) -> GrafanaDashboard | None:
        # TODO: implement with httpx
        return None

    async def build_dashboard_url(
        self, uid: str, from_time: str = "now-6h", to_time: str = "now"
    ) -> str:
        return f"{self._base}/d/{uid}?from={from_time}&to={to_time}"

    async def health(self) -> bool:
        # TODO: implement with httpx
        return False
