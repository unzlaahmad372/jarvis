"""Health checks for each JARVIS dependency.

Each check returns a DependencyStatus. Optional dependencies can be
DEGRADED or NOT_CONFIGURED without making the whole system unhealthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import get_logger

logger = get_logger(__name__)


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    NOT_CONFIGURED = "NOT_CONFIGURED"


@dataclass
class DependencyStatus:
    name: str
    status: HealthStatus
    detail: str | None = None


async def check_database(engine: AsyncEngine) -> DependencyStatus:
    """Verify SQLite is reachable and responsive."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return DependencyStatus(name="database", status=HealthStatus.HEALTHY)
    except Exception as exc:
        logger.warning("health_check_database_failed", error=str(exc))
        return DependencyStatus(
            name="database", status=HealthStatus.UNHEALTHY, detail=str(exc)
        )


async def check_ollama(base_url: str, model: str) -> DependencyStatus:
    """Verify Ollama is reachable and the configured model is available."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{base_url.rstrip('/')}/api/tags")
            r.raise_for_status()
            tags = r.json()

        models = [m.get("name", "") for m in tags.get("models", [])]
        model_found = any(m == model or m.startswith(f"{model}:") for m in models)

        if model_found:
            return DependencyStatus(name="ollama", status=HealthStatus.HEALTHY)
        return DependencyStatus(
            name="ollama",
            status=HealthStatus.DEGRADED,
            detail=f"Model '{model}' not found. Available: {models}",
        )
    except httpx.ConnectError:
        return DependencyStatus(
            name="ollama",
            status=HealthStatus.UNHEALTHY,
            detail=f"Ollama is not reachable at {base_url}. Is it running?",
        )
    except Exception as exc:
        logger.warning("health_check_ollama_failed", error=str(exc))
        return DependencyStatus(
            name="ollama", status=HealthStatus.UNHEALTHY, detail=str(exc)
        )


async def check_data_directory(data_dir: Path) -> DependencyStatus:
    """Verify the data directory exists and is writable."""
    try:
        if not data_dir.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
        test_file = data_dir / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return DependencyStatus(name="data_directory", status=HealthStatus.HEALTHY)
    except Exception as exc:
        return DependencyStatus(
            name="data_directory", status=HealthStatus.UNHEALTHY, detail=str(exc)
        )


async def check_vector_store(
    indexes_dir: object, embedding_model: str, index_version: str
) -> DependencyStatus:
    """Check Chroma vector store health."""
    from pathlib import Path

    from app.knowledge.vector_store import ChromaVectorStore

    try:
        store = ChromaVectorStore(
            persist_dir=Path(str(indexes_dir)),
            embedding_model=embedding_model,
            index_version=index_version,
        )
        h = await store.health()
        status_map = {
            "HEALTHY": HealthStatus.HEALTHY,
            "EMPTY": HealthStatus.HEALTHY,
            "REINDEX_REQUIRED": HealthStatus.DEGRADED,
            "UNAVAILABLE": HealthStatus.UNHEALTHY,
        }
        return DependencyStatus(
            name="vector_store",
            status=status_map.get(h.status, HealthStatus.DEGRADED),
            detail=f"{h.status} — {h.document_count} chunks, model={h.embedding_model}",
        )
    except Exception as exc:
        return DependencyStatus(
            name="vector_store", status=HealthStatus.UNHEALTHY, detail=str(exc)
        )


def check_vector_store_not_configured() -> DependencyStatus:
    """Fallback when vector store is not yet initialised."""
    return DependencyStatus(
        name="vector_store",
        status=HealthStatus.NOT_CONFIGURED,
        detail="Vector store not initialised.",
    )
