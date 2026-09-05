"""Database engine and session management for JARVIS.

Uses SQLite in WAL mode for better concurrent read performance.
All database access goes through the async session factory.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine(database_url: str, database_dir: Path) -> AsyncEngine:
    """Create the async SQLAlchemy engine with WAL mode enabled."""
    database_dir.mkdir(parents=True, exist_ok=True)

    # aiosqlite requires the aiosqlite driver
    connect_args: dict[str, object] = {}
    kwargs: dict[str, object] = {}

    if "sqlite" in database_url:
        connect_args = {
            "timeout": 30,
            "check_same_thread": False,
        }
        # For in-memory SQLite (tests), use StaticPool
        if ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs["connect_args"] = connect_args

    engine = create_async_engine(
        database_url,
        echo=False,
        **kwargs,
    )
    return engine


async def init_db(database_url: str, database_dir: Path) -> AsyncEngine:
    """Initialise the database engine and enable WAL mode."""
    global _engine, _session_factory

    _engine = _build_engine(database_url, database_dir)
    _session_factory = async_sessionmaker(
        _engine, expire_on_commit=False, class_=AsyncSession
    )

    # Enable WAL mode for SQLite
    if "sqlite" in database_url and ":memory:" not in database_url:
        from sqlalchemy import event

        @event.listens_for(_engine.sync_engine, "connect")
        def set_wal_mode(dbapi_conn, connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    logger.info("database_initialised", url=database_url.split("///")[-1])
    return _engine


async def close_db() -> None:
    """Dispose the database engine on shutdown."""
    global _engine
    if _engine:
        await _engine.dispose()
        logger.info("database_closed")


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _session_factory
