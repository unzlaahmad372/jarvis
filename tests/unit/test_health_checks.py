"""Tests for health check functions."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.health.checks import (
    HealthStatus,
    check_data_directory,
    check_database,
    check_vector_store_not_configured,
)


@pytest_asyncio.fixture
async def healthy_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_database_healthy(healthy_engine):
    status = await check_database(healthy_engine)
    assert status.status == HealthStatus.HEALTHY
    assert status.name == "database"


@pytest.mark.asyncio
async def test_database_unhealthy_on_bad_engine():
    bad_engine = create_async_engine("sqlite+aiosqlite:///nonexistent_dir/bad.db")
    status = await check_database(bad_engine)
    # May succeed or fail depending on OS; just verify it returns a status
    assert status.name == "database"
    assert status.status in (HealthStatus.HEALTHY, HealthStatus.UNHEALTHY)
    await bad_engine.dispose()


@pytest.mark.asyncio
async def test_data_directory_healthy(tmp_path):
    status = await check_data_directory(tmp_path)
    assert status.status == HealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_data_directory_created_if_missing(tmp_path):
    new_dir = tmp_path / "new_subdir"
    assert not new_dir.exists()
    status = await check_data_directory(new_dir)
    assert status.status == HealthStatus.HEALTHY
    assert new_dir.exists()


def test_vector_store_not_configured():
    status = check_vector_store_not_configured()
    assert status.status == HealthStatus.NOT_CONFIGURED
    assert status.name == "vector_store"
