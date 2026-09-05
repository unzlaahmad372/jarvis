"""Phase 7 — CI/CD & Observability unit tests.

All tests use fake clients — no real Jenkins/Prometheus/Grafana/Spinnaker required.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.tools.cicd.grafana_client import FakeGrafanaClient
from app.tools.cicd.jenkins_client import FakeJenkinsClient
from app.tools.cicd.prometheus_client import FakePrometheusClient
from app.tools.cicd.spinnaker_client import FakeSpinnakerClient

# ── Jenkins ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_jenkins_list_jobs_returns_defaults() -> None:
    client = FakeJenkinsClient()
    jobs = await client.list_jobs()
    assert len(jobs) == 2
    assert jobs[0].name == "phoenix-build"


@pytest.mark.asyncio
async def test_jenkins_get_job_found() -> None:
    client = FakeJenkinsClient()
    job = await client.get_job("phoenix-build")
    assert job is not None
    assert job.last_build is not None
    assert job.last_build.result == "FAILURE"
    assert job.last_build.failed_stage == "msST"


@pytest.mark.asyncio
async def test_jenkins_get_job_not_found() -> None:
    client = FakeJenkinsClient()
    assert await client.get_job("nonexistent") is None


@pytest.mark.asyncio
async def test_jenkins_list_builds() -> None:
    client = FakeJenkinsClient()
    builds = await client.list_builds("phoenix-build")
    assert len(builds) == 3
    assert builds[0].build_number == 381


@pytest.mark.asyncio
async def test_jenkins_list_builds_limit() -> None:
    client = FakeJenkinsClient()
    builds = await client.list_builds("phoenix-build", limit=1)
    assert len(builds) == 1


@pytest.mark.asyncio
async def test_jenkins_list_builds_unknown_job() -> None:
    client = FakeJenkinsClient()
    assert await client.list_builds("unknown") == []


@pytest.mark.asyncio
async def test_jenkins_get_build_found() -> None:
    client = FakeJenkinsClient()
    build = await client.get_build("phoenix-build", 381)
    assert build is not None
    assert build.result == "FAILURE"


@pytest.mark.asyncio
async def test_jenkins_get_build_not_found() -> None:
    client = FakeJenkinsClient()
    assert await client.get_build("phoenix-build", 999) is None


@pytest.mark.asyncio
async def test_jenkins_console_log() -> None:
    client = FakeJenkinsClient()
    log = await client.get_console_log("phoenix-build", 381)
    assert "msST" in log


@pytest.mark.asyncio
async def test_jenkins_unavailable_raises() -> None:
    client = FakeJenkinsClient(unavailable=True)
    with pytest.raises(ConnectionError):
        await client.list_jobs()


# ── Prometheus ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prometheus_query_known() -> None:
    client = FakePrometheusClient()
    result = await client.query("up")
    assert result.status == "success"
    assert len(result.results) == 1
    assert result.results[0].value == 1.0


@pytest.mark.asyncio
async def test_prometheus_query_unknown_returns_empty() -> None:
    client = FakePrometheusClient()
    result = await client.query("unknown_metric")
    assert result.status == "success"
    assert result.results == []


@pytest.mark.asyncio
async def test_prometheus_health_available() -> None:
    client = FakePrometheusClient()
    assert await client.health() is True


@pytest.mark.asyncio
async def test_prometheus_unavailable_raises() -> None:
    client = FakePrometheusClient(unavailable=True)
    with pytest.raises(ConnectionError):
        await client.query("up")


@pytest.mark.asyncio
async def test_prometheus_health_unavailable() -> None:
    client = FakePrometheusClient(unavailable=True)
    assert await client.health() is False


# ── Grafana ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_grafana_list_dashboards_all() -> None:
    client = FakeGrafanaClient()
    dashboards = await client.list_dashboards()
    assert len(dashboards) == 2


@pytest.mark.asyncio
async def test_grafana_list_dashboards_filter() -> None:
    client = FakeGrafanaClient()
    results = await client.list_dashboards("phoenix")
    assert len(results) == 1
    assert results[0].uid == "phoenix-ci"


@pytest.mark.asyncio
async def test_grafana_get_dashboard_found() -> None:
    client = FakeGrafanaClient()
    d = await client.get_dashboard("mtas-infra")
    assert d is not None
    assert d.title == "MTAS Infrastructure"


@pytest.mark.asyncio
async def test_grafana_get_dashboard_not_found() -> None:
    client = FakeGrafanaClient()
    assert await client.get_dashboard("nonexistent") is None


@pytest.mark.asyncio
async def test_grafana_find_dashboard() -> None:
    client = FakeGrafanaClient()
    d = await client.find_dashboard("MTAS")
    assert d is not None
    assert d.uid == "mtas-infra"


@pytest.mark.asyncio
async def test_grafana_build_url() -> None:
    client = FakeGrafanaClient(base_url="http://grafana:3000")
    url = await client.build_dashboard_url("phoenix-ci", "now-1h", "now")
    assert "phoenix-ci" in url
    assert "now-1h" in url


@pytest.mark.asyncio
async def test_grafana_unavailable_raises() -> None:
    client = FakeGrafanaClient(unavailable=True)
    with pytest.raises(ConnectionError):
        await client.list_dashboards()


# ── Spinnaker ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_spinnaker_list_applications() -> None:
    client = FakeSpinnakerClient()
    apps = await client.list_applications()
    assert "phoenix" in apps


@pytest.mark.asyncio
async def test_spinnaker_list_pipelines() -> None:
    client = FakeSpinnakerClient()
    pipelines = await client.list_pipelines("phoenix")
    assert "prewash" in pipelines


@pytest.mark.asyncio
async def test_spinnaker_list_pipelines_unknown_app() -> None:
    client = FakeSpinnakerClient()
    assert await client.list_pipelines("unknown") == []


@pytest.mark.asyncio
async def test_spinnaker_list_executions() -> None:
    client = FakeSpinnakerClient()
    execs = await client.list_executions("phoenix", "prewash")
    assert len(execs) == 2
    assert execs[0].status == "TERMINAL"
    assert execs[0].id == "exec-934782"


@pytest.mark.asyncio
async def test_spinnaker_list_executions_limit() -> None:
    client = FakeSpinnakerClient()
    execs = await client.list_executions("phoenix", "prewash", limit=1)
    assert len(execs) == 1


@pytest.mark.asyncio
async def test_spinnaker_failed_stage_in_execution() -> None:
    client = FakeSpinnakerClient()
    execs = await client.list_executions("phoenix", "prewash")
    terminal_stages = [s for s in execs[0].stages if s.status == "TERMINAL"]
    assert len(terminal_stages) == 1
    assert terminal_stages[0].name == "Deploy to msST"


@pytest.mark.asyncio
async def test_spinnaker_get_execution_found() -> None:
    client = FakeSpinnakerClient()
    ex = await client.get_execution("exec-934782")
    assert ex is not None
    assert ex.application == "phoenix"


@pytest.mark.asyncio
async def test_spinnaker_get_execution_not_found() -> None:
    client = FakeSpinnakerClient()
    assert await client.get_execution("nonexistent") is None


@pytest.mark.asyncio
async def test_spinnaker_unavailable_raises() -> None:
    client = FakeSpinnakerClient(unavailable=True)
    with pytest.raises(ConnectionError):
        await client.list_applications()


# ── API endpoints — disabled returns 503 ─────────────────────────────────────

def _disabled_settings() -> Settings:
    return Settings(
        enable_jenkins=False,
        enable_prometheus=False,
        enable_grafana=False,
        enable_spinnaker=False,
    )


def test_jenkins_endpoint_disabled_503() -> None:
    from app.main import app
    with patch("app.api.routes.cicd.get_settings", return_value=_disabled_settings()):
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/api/v1/jenkins/jobs")
            assert r.status_code == 503


def test_prometheus_endpoint_disabled_503() -> None:
    from app.main import app
    with patch("app.api.routes.cicd.get_settings", return_value=_disabled_settings()):
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/api/v1/prometheus/query?q=up")
            assert r.status_code == 503


def test_grafana_endpoint_disabled_503() -> None:
    from app.main import app
    with patch("app.api.routes.cicd.get_settings", return_value=_disabled_settings()):
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/api/v1/grafana/dashboards")
            assert r.status_code == 503


def test_spinnaker_endpoint_disabled_503() -> None:
    from app.main import app
    with patch("app.api.routes.cicd.get_settings", return_value=_disabled_settings()):
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/api/v1/spinnaker/applications/phoenix/pipelines/prewash/executions")
            assert r.status_code == 503
