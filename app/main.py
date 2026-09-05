"""JARVIS FastAPI application.

Startup sequence:
  1. Load and validate configuration
  2. Configure structured logging
  3. Initialise database (create tables + seed default workspace)
  4. Register routes
  5. Bind to 127.0.0.1 only (unless remote access explicitly enabled)
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from starlette.middleware.base import RequestResponseEndpoint

from app.api.routes import auth as auth_router
from app.api.routes import automation as automation_router
from app.api.routes import backup as backup_router
from app.api.routes import chat as chat_router
from app.api.routes import cicd as cicd_router
from app.api.routes import conversations as conversations_router
from app.api.routes import documents as documents_router
from app.api.routes import health as health_router
from app.api.routes import kubernetes as kubernetes_router
from app.api.routes import memory as memory_router
from app.api.routes import tools as tools_router
from app.api.routes import voice as voice_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.db.database import close_db, init_db
from app.db.models import Base, Workspace

logger = get_logger(__name__)


def _register_tools(settings: Settings) -> None:
    """Register all built-in tools at startup."""
    from app.tools.filesystem.access import FileAccessRegistry
    from app.tools.filesystem.tools import (
        FileMetadataTool,
        ListDirectoryTool,
        ReadFileTool,
        SearchFilesTool,
    )
    from app.tools.registry import get_registry, reset_registry
    from app.tools.system.tools import DiskUsageTool, SystemInfoTool

    reset_registry()
    registry = get_registry()

    # File access registry — allow the data directory by default
    far = FileAccessRegistry()
    far.add_root("data", settings.data_dir.resolve())

    registry.register(ListDirectoryTool(far))
    registry.register(ReadFileTool(far))
    registry.register(SearchFilesTool(far))
    registry.register(FileMetadataTool(far))
    registry.register(SystemInfoTool())
    registry.register(DiskUsageTool())

    # Kubernetes tools — registered only when enabled
    if settings.enable_kubernetes:
        from app.tools.kubernetes.client import RealKubernetesClient
        from app.tools.kubernetes.tools import (
            ClusterHealthTool,
            GetPodLogsTool,
            ListContextsTool,
            ListDeploymentsTool,
            ListNamespacesTool,
            ListPodsTool,
        )

        k8s_client = RealKubernetesClient()
        registry.register(ListContextsTool(k8s_client, settings))
        registry.register(ListNamespacesTool(k8s_client, settings))
        registry.register(ListPodsTool(k8s_client, settings))
        registry.register(GetPodLogsTool(k8s_client, settings))
        registry.register(ListDeploymentsTool(k8s_client, settings))
        registry.register(ClusterHealthTool(k8s_client, settings))


async def _seed_default_workspace() -> None:
    """Ensure a default workspace exists."""
    from app.db.database import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Workspace).where(Workspace.is_default == True)  # noqa: E712
        )
        existing = result.scalar_one_or_none()
        if not existing:
            session.add(
                Workspace(
                    name="default",
                    description="Default JARVIS workspace",
                    is_default=True,
                )
            )
            await session.commit()
            logger.info("workspace_seeded", name="default")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and shutdown."""
    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info(
        "jarvis_starting",
        version="0.1.0",
        runtime_mode=settings.runtime_mode,
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        host=settings.host,
        port=settings.port,
    )

    # Ensure data directories exist
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.database_dir.mkdir(parents=True, exist_ok=True)

    # Initialise database
    engine = await init_db(settings.database_url, settings.database_dir)

    # Create tables (Alembic handles migrations in production;
    # create_all is used here for Phase 0 simplicity)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _seed_default_workspace()

    # ── Register tools ────────────────────────────────────────────────────────
    _register_tools(settings)

    # Store shared state on app
    app.state.db_engine = engine
    app.state.settings = settings

    logger.info("jarvis_ready", host=settings.host, port=settings.port)

    yield

    logger.info("jarvis_shutting_down")
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the JARVIS FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="JARVIS",
        description="Local-first personal AI assistant",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS — explicit allow-list only, never wildcard ───────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    # ── Request ID middleware ─────────────────────────────────────────────────
    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(health_router.router)
    app.include_router(chat_router.router)
    app.include_router(conversations_router.router)
    app.include_router(documents_router.router)
    app.include_router(memory_router.router)
    app.include_router(tools_router.router)
    app.include_router(voice_router.router)
    app.include_router(kubernetes_router.router)
    app.include_router(cicd_router.router)
    app.include_router(automation_router.router)
    app.include_router(backup_router.router)
    app.include_router(auth_router.router)

    # ── Rate limiting middleware ────────────────────────────────────────────────────────────────
    if settings.rate_limit_enabled:
        from app.security.rate_limiter import get_rate_limiter

        limiter = get_rate_limiter()

        @app.middleware("http")
        async def rate_limit_middleware(
            request: Request, call_next: RequestResponseEndpoint
        ) -> Response:
            # Key by device_id from token if present, else by client IP
            key = request.client.host if request.client else "unknown"
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                # Use first 16 chars of token as key suffix (not the full secret)
                key = f"token:{auth_header[7:23]}"
            if not limiter.is_allowed(key):
                return Response(
                    content='{"error":{"code":"RATE_LIMITED","message":"Too many requests."}}',
                    status_code=429,
                    media_type="application/json",
                )
            return await call_next(request)

    return app


app = create_app()


def cli() -> None:
    """Entry point for `jarvis` CLI command."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_config=None,  # structlog handles logging
    )
