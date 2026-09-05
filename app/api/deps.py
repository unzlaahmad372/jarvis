"""FastAPI dependency injection for JARVIS."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.database import get_session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session, closing it after the request."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


def get_orchestrator(request: Request) -> object:
    """Return the shared ChatOrchestrator from app.state."""
    return request.app.state.orchestrator


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
