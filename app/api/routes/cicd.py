"""CI/CD & Observability endpoints — Phase 7.

GET /api/v1/jenkins/jobs
GET /api/v1/jenkins/jobs/{job_name}/builds
GET /api/v1/prometheus/query
GET /api/v1/grafana/dashboards
GET /api/v1/spinnaker/applications/{app}/pipelines/{pipeline}/executions
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas.chat import (
    GrafanaDashboardOut,
    GrafanaDashboardsOut,
    JenkinsBuildOut,
    JenkinsJobOut,
    JenkinsJobsOut,
    PrometheusMetricOut,
    PrometheusQueryOut,
    SpinnakerExecutionOut,
    SpinnakerExecutionsOut,
    SpinnakerStageOut,
)
from app.core.config import get_settings
from app.tools.cicd.grafana_client import RealGrafanaClient
from app.tools.cicd.jenkins_client import JenkinsBuild, JenkinsJob, RealJenkinsClient
from app.tools.cicd.prometheus_client import RealPrometheusClient
from app.tools.cicd.spinnaker_client import RealSpinnakerClient

router = APIRouter(prefix="/api/v1", tags=["cicd"])

_DISABLED = "Integration is disabled"


# ── Singletons ────────────────────────────────────────────────────────────────

_jenkins: RealJenkinsClient | None = None
_prometheus: RealPrometheusClient | None = None
_grafana: RealGrafanaClient | None = None
_spinnaker: RealSpinnakerClient | None = None


def _get_jenkins() -> RealJenkinsClient:
    global _jenkins
    if _jenkins is None:
        s = get_settings()
        _jenkins = RealJenkinsClient(s.jenkins_url, s.jenkins_user, s.jenkins_token)
    return _jenkins


def _get_prometheus() -> RealPrometheusClient:
    global _prometheus
    if _prometheus is None:
        s = get_settings()
        _prometheus = RealPrometheusClient(s.prometheus_url, s.prometheus_timeout)
    return _prometheus


def _get_grafana() -> RealGrafanaClient:
    global _grafana
    if _grafana is None:
        s = get_settings()
        _grafana = RealGrafanaClient(s.grafana_url, s.grafana_token)
    return _grafana


def _get_spinnaker() -> RealSpinnakerClient:
    global _spinnaker
    if _spinnaker is None:
        s = get_settings()
        _spinnaker = RealSpinnakerClient(s.spinnaker_gate_url, s.spinnaker_token)
    return _spinnaker


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_out(b: JenkinsBuild) -> JenkinsBuildOut:
    return JenkinsBuildOut(
        job_name=b.job_name,
        build_number=b.build_number,
        result=b.result,
        duration_ms=b.duration_ms,
        timestamp=b.timestamp,
        url=b.url,
        branch=b.branch,
        failed_stage=b.failed_stage,
    )


def _job_out(j: JenkinsJob) -> JenkinsJobOut:
    return JenkinsJobOut(
        name=j.name,
        url=j.url,
        last_build=_build_out(j.last_build) if j.last_build else None,
    )


# ── Jenkins ───────────────────────────────────────────────────────────────────

@router.get("/jenkins/jobs", response_model=JenkinsJobsOut)
async def jenkins_list_jobs() -> JenkinsJobsOut:
    s = get_settings()
    if not s.enable_jenkins:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_DISABLED)
    try:
        jobs = await _get_jenkins().list_jobs()
        return JenkinsJobsOut(server=s.jenkins_url, jobs=[_job_out(j) for j in jobs])
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/jenkins/jobs/{job_name}/builds", response_model=list[JenkinsBuildOut])
async def jenkins_list_builds(
    job_name: str, limit: int = Query(default=10, ge=1, le=50)
) -> list[JenkinsBuildOut]:
    s = get_settings()
    if not s.enable_jenkins:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_DISABLED)
    try:
        builds = await _get_jenkins().list_builds(job_name, limit)
        return [_build_out(b) for b in builds]
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


# ── Prometheus ────────────────────────────────────────────────────────────────

@router.get("/prometheus/query", response_model=PrometheusQueryOut)
async def prometheus_query(
    q: str = Query(..., description="PromQL expression"),
) -> PrometheusQueryOut:
    s = get_settings()
    if not s.enable_prometheus:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_DISABLED)
    try:
        result = await _get_prometheus().query(q)
        return PrometheusQueryOut(
            query=result.query,
            status=result.status,
            results=[
                PrometheusMetricOut(
                    metric=m.metric,
                    labels=m.labels,
                    value=m.value,
                    timestamp=m.timestamp,
                )
                for m in result.results
            ],
            error=result.error,
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


# ── Grafana ───────────────────────────────────────────────────────────────────

@router.get("/grafana/dashboards", response_model=GrafanaDashboardsOut)
async def grafana_list_dashboards(
    q: str = Query(default="", description="Optional title filter")
) -> GrafanaDashboardsOut:
    s = get_settings()
    if not s.enable_grafana:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_DISABLED)
    try:
        dashboards = await _get_grafana().list_dashboards(q)
        return GrafanaDashboardsOut(
            server=s.grafana_url,
            dashboards=[
                GrafanaDashboardOut(
                    uid=d.uid, title=d.title, url=d.url, tags=d.tags, folder=d.folder
                )
                for d in dashboards
            ],
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


# ── Spinnaker ─────────────────────────────────────────────────────────────────

@router.get(
    "/spinnaker/applications/{application}/pipelines/{pipeline_name}/executions",
    response_model=SpinnakerExecutionsOut,
)
async def spinnaker_list_executions(
    application: str,
    pipeline_name: str,
    limit: int = Query(default=5, ge=1, le=20),
) -> SpinnakerExecutionsOut:
    s = get_settings()
    if not s.enable_spinnaker:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_DISABLED)
    try:
        execs = await _get_spinnaker().list_executions(application, pipeline_name, limit)
        return SpinnakerExecutionsOut(
            application=application,
            pipeline_name=pipeline_name,
            executions=[
                SpinnakerExecutionOut(
                    id=e.id,
                    pipeline_name=e.pipeline_name,
                    application=e.application,
                    status=e.status,
                    start_time=e.start_time,
                    duration_ms=e.duration_ms,
                    trigger=e.trigger,
                    stages=[
                        SpinnakerStageOut(
                            name=st.name,
                            status=st.status,
                            duration_ms=st.duration_ms,
                            start_time=st.start_time,
                        )
                        for st in e.stages
                    ],
                    url=e.url,
                )
                for e in execs
            ],
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
