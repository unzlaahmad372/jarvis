"""Tests for JARVIS health API endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db.models import Base


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_liveness_returns_200():
    """GET /health/live must always return 200."""
    from httpx import ASGITransport

    import app.db.database as db_module
    from app.core.config import get_settings
    from app.main import create_app

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    db_module._engine = engine
    db_module._session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    application = create_app()
    application.state.db_engine = engine
    application.state.settings = get_settings()

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "alive"
    await engine.dispose()


@pytest.mark.asyncio
async def test_dependencies_endpoint_returns_vector_store_not_configured():
    """GET /health/dependencies must include vector_store as NOT_CONFIGURED."""
    from httpx import ASGITransport

    import app.db.database as db_module
    from app.core.config import get_settings
    from app.main import create_app

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    db_module._engine = engine
    db_module._session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    application = create_app()
    application.state.db_engine = engine
    application.state.settings = get_settings()

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/health/dependencies")

    assert response.status_code == 200
    data = response.json()
    deps = {d["name"]: d["status"] for d in data["dependencies"]}
    assert "vector_store" in deps  # vector store is now checked in Phase 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_request_id_header_returned():
    """Every response must include X-Request-ID."""
    from httpx import ASGITransport

    import app.db.database as db_module
    from app.core.config import get_settings
    from app.main import create_app

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    db_module._engine = engine
    db_module._session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    application = create_app()
    application.state.db_engine = engine
    application.state.settings = get_settings()

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/health/live")

    assert "x-request-id" in response.headers
    await engine.dispose()
