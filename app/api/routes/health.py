"""Health endpoints for JARVIS.

GET /health/live        — Is the process alive?
GET /health/ready       — Can it serve requests?
GET /health/dependencies — Per-dependency status breakdown.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.health.checks import (
    HealthStatus,
    check_data_directory,
    check_database,
    check_ollama,
    check_vector_store,
)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", summary="Liveness probe")
async def liveness() -> JSONResponse:
    """Returns 200 if the JARVIS process is alive."""
    return JSONResponse({"status": "alive"})


@router.get("/ready", summary="Readiness probe")
async def readiness(request: Request) -> JSONResponse:
    """Returns 200 if JARVIS can serve requests (DB + Ollama healthy)."""
    state = request.app.state
    engine = getattr(state, "db_engine", None)
    settings = getattr(state, "settings", None)

    checks = []

    if engine:
        db_status = await check_database(engine)
        checks.append(db_status)
    else:
        from app.health.checks import DependencyStatus
        checks.append(
            DependencyStatus(
                name="database", status=HealthStatus.UNHEALTHY, detail="Not initialised"
            )
        )

    if settings:
        ollama_status = await check_ollama(settings.ollama_url, settings.llm_model)
        checks.append(ollama_status)

    # System is ready if all required dependencies are healthy
    required_names = {"database", "ollama"}
    all_ready = all(
        c.status == HealthStatus.HEALTHY
        for c in checks
        if c.name in required_names
    )

    http_status = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        {
            "status": "ready" if all_ready else "not_ready",
            "dependencies": [
                {"name": c.name, "status": c.status.value, "detail": c.detail}
                for c in checks
            ],
        },
        status_code=http_status,
    )


@router.get("/dependencies", summary="Dependency health breakdown")
async def dependencies(request: Request) -> JSONResponse:
    """Returns per-dependency health status. Optional deps can be DEGRADED."""
    state = request.app.state
    engine = getattr(state, "db_engine", None)
    settings = getattr(state, "settings", None)

    checks = []

    if engine:
        checks.append(await check_database(engine))
    if settings:
        checks.append(await check_ollama(settings.ollama_url, settings.llm_model))
        checks.append(await check_data_directory(settings.data_dir))
        checks.append(await check_vector_store(
            settings.indexes_dir, settings.embedding_model, settings.index_version
        ))

    # Overall JARVIS status
    required = {"database", "ollama"}
    required_statuses = [c.status for c in checks if c.name in required]
    if all(s == HealthStatus.HEALTHY for s in required_statuses):
        overall = "READY"
    elif any(s == HealthStatus.UNHEALTHY for s in required_statuses):
        overall = "UNHEALTHY"
    else:
        overall = "DEGRADED"

    return JSONResponse({
        "jarvis": overall,
        "dependencies": [
            {"name": c.name, "status": c.status.value, "detail": c.detail}
            for c in checks
        ],
    })
