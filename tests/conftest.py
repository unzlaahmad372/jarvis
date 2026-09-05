"""Shared pytest fixtures for JARVIS tests."""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db.models import Base


@pytest_asyncio.fixture
async def db_engine() -> AsyncEngine:  # type: ignore[return]
    """In-memory SQLite engine for tests — never touches the real database."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncSession:  # type: ignore[return]
    """Async database session bound to the in-memory test engine."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def test_client(db_engine: AsyncEngine):  # type: ignore[return]
    """HTTPX async test client wired to the JARVIS FastAPI app.

    Uses FakeLLMProvider so tests never require a live Ollama server.
    """
    import app.api.routes.chat as chat_module
    import app.db.database as db_module
    from app.core.config import get_settings
    from app.main import create_app
    from app.security.rate_limiter import RateLimiter, reset_rate_limiter
    from tests.fakes.llm import FakeLLMProvider

    # Override DB engine with test engine
    db_module._engine = db_engine
    db_module._session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )

    # Override LLM provider with fake — no Ollama required
    chat_module.set_llm_provider(FakeLLMProvider())

    # Use a high-capacity rate limiter so tests are never blocked
    reset_rate_limiter(RateLimiter(rate_per_minute=10_000))

    # Register tools (lifespan doesn't run in test client)
    from app.main import _register_tools
    _register_tools(get_settings())

    application = create_app()
    application.state.db_engine = db_engine
    application.state.settings = get_settings()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            yield client
    finally:
        # Clean up provider override
        chat_module.set_llm_provider(None)
        reset_rate_limiter(None)
