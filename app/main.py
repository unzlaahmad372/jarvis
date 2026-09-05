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

from app.api.routes import chat as chat_router
from app.api.routes import conversations as conversations_router
from app.api.routes import documents as documents_router
from app.api.routes import health as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.database import close_db, init_db
from app.db.models import Base, Workspace

logger = get_logger(__name__)


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
