"""Memory manager — CRUD and search for long-term memories.

Memories are created explicitly (via 'remember' commands or the API).
They are never auto-created from every conversation turn.

Search strategy (Phase 39):
  1. If an embedding provider is available, embed the query and search
     the memory Chroma collection by cosine similarity.
  2. Fall back to SQL LIKE when no embedding provider is configured.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.context_builder import ContextSlot, estimate_tokens
from app.core.logging import get_logger
from app.db.models import Memory, Workspace

if TYPE_CHECKING:
    from app.knowledge.embeddings import EmbeddingProvider

logger = get_logger(__name__)

MEMORY_COLLECTION = "jarvis_memory"
VALID_CATEGORIES = {"preference", "decision", "fact", "project", "entity", "other"}
VALID_CLASSIFICATIONS = {"PUBLIC", "PERSONAL", "CONFIDENTIAL", "SECRET"}


async def _vector_search_memories(
    session: AsyncSession,
    query: str,
    embedding_provider: "EmbeddingProvider",
    workspace_id: int,
    limit: int,
) -> list[Memory] | None:
    """Search memories by embedding similarity. Returns None on any failure."""
    try:
        import chromadb
        from app.core.config import get_settings

        settings = get_settings()
        persist_dir = settings.indexes_dir / "memory"
        persist_dir.mkdir(parents=True, exist_ok=True)

        client = chromadb.PersistentClient(path=str(persist_dir))
        collection = client.get_or_create_collection(MEMORY_COLLECTION)

        if collection.count() == 0:
            return None

        embed_result = await embedding_provider.embed([query])
        if not embed_result.vectors:
            return None
        query_vector = embed_result.vectors[0]

        results = collection.query(
            query_embeddings=[query_vector],  # type: ignore[arg-type]
            n_results=min(limit, collection.count()),
            where={"workspace_id": workspace_id},
            include=["metadatas", "distances"],
        )

        ids_list = (results.get("ids") or [[]])[0]
        if not ids_list:
            return None

        memory_ids = [int(mid) for mid in ids_list]
        result = await session.execute(
            select(Memory).where(Memory.id.in_(memory_ids))
        )
        rows = {m.id: m for m in result.scalars().all()}
        return [rows[mid] for mid in memory_ids if mid in rows]

    except Exception as exc:
        logger.debug("vector_memory_search_failed", error=str(exc))
        return None


async def _index_memory(memory: Memory, embedding_provider: "EmbeddingProvider | None" = None) -> None:
    """Add or update a memory's embedding in the Chroma memory collection."""
    try:
        import chromadb
        from app.core.config import get_settings

        settings = get_settings()
        persist_dir = settings.indexes_dir / "memory"
        persist_dir.mkdir(parents=True, exist_ok=True)

        client = chromadb.PersistentClient(path=str(persist_dir))
        collection = client.get_or_create_collection(MEMORY_COLLECTION)

        # Use injected provider if available, otherwise construct a one-shot provider
        provider = embedding_provider
        if provider is None:
            from app.knowledge.embeddings import OllamaEmbeddingProvider
            provider = OllamaEmbeddingProvider(
                base_url=settings.ollama_url,
                model=settings.embedding_model,
            )

        embed_result = await provider.embed([memory.content])
        if not embed_result.vectors:
            return

        collection.upsert(
            ids=[str(memory.id)],
            embeddings=[embed_result.vectors[0]],  # type: ignore[arg-type]
            documents=[memory.content],
            metadatas=[{"workspace_id": memory.workspace_id, "category": memory.category}],
        )
    except Exception as exc:
        logger.debug("memory_index_failed", memory_id=memory.id, error=str(exc))


async def _default_workspace_id(session: AsyncSession) -> int:
    result = await session.execute(select(Workspace).where(Workspace.is_default == True))  # noqa: E712
    ws = result.scalar_one_or_none()
    if ws is None:
        raise RuntimeError("No default workspace found")
    return ws.id


async def remember(
    session: AsyncSession,
    content: str,
    *,
    category: str = "fact",
    importance: int = 5,
    confidence: float = 1.0,
    source: str | None = None,
    data_classification: str = "PERSONAL",
    workspace_id: int | None = None,
    embedding_provider: "EmbeddingProvider | None" = None,
) -> Memory:
    """Create a new memory entry."""
    if category not in VALID_CATEGORIES:
        category = "other"
    if data_classification not in VALID_CLASSIFICATIONS:
        data_classification = "PERSONAL"
    importance = max(1, min(10, importance))
    confidence = max(0.0, min(1.0, confidence))

    wid = workspace_id or await _default_workspace_id(session)
    memory = Memory(
        workspace_id=wid,
        content=content,
        category=category,
        importance=importance,
        confidence=confidence,
        source=source,
        data_classification=data_classification,
    )
    session.add(memory)
    await session.flush()
    await session.refresh(memory)
    logger.info("memory_created", memory_id=memory.id, category=category)
    # Index embedding best-effort — never blocks memory creation
    await _index_memory(memory, embedding_provider)
    return memory


async def search_memories(
    session: AsyncSession,
    query: str,
    *,
    workspace_id: int | None = None,
    limit: int = 10,
    embedding_provider: "EmbeddingProvider | None" = None,
) -> list[Memory]:
    """Search memories by vector similarity (Phase 39) with SQL LIKE fallback."""
    wid = workspace_id or await _default_workspace_id(session)

    # ── Vector search (preferred) ─────────────────────────────────────────────
    if embedding_provider is not None:
        results = await _vector_search_memories(session, query, embedding_provider, wid, limit)
        if results is not None:
            now = datetime.now(UTC)
            for m in results:
                m.last_accessed_at = now
            if results:
                await session.flush()
            return results

    # ── SQL LIKE fallback ─────────────────────────────────────────────────────
    safe_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    stmt = (
        select(Memory)
        .where(Memory.workspace_id == wid)
        .where(Memory.content.ilike(f"%{safe_query}%"))
        .order_by(Memory.importance.desc(), Memory.updated_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    memories = list(result.scalars().all())

    now = datetime.now(UTC)
    for m in memories:
        m.last_accessed_at = now
    if memories:
        await session.flush()

    return memories


async def list_memories(
    session: AsyncSession,
    *,
    workspace_id: int | None = None,
    category: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Memory]:
    """List memories, optionally filtered by category."""
    wid = workspace_id or await _default_workspace_id(session)
    stmt = (
        select(Memory)
        .where(Memory.workspace_id == wid)
        .order_by(Memory.importance.desc(), Memory.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if category:
        stmt = stmt.where(Memory.category == category)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def forget(session: AsyncSession, memory_id: int) -> bool:
    """Delete a single memory by ID from SQLite and the vector index."""
    result = await session.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if memory is None:
        return False
    await session.delete(memory)
    await session.flush()
    # Remove from vector index (best-effort — never blocks deletion)
    await _delete_memory_embedding(memory_id)
    logger.info("memory_forgotten", memory_id=memory_id)
    return True


async def _delete_memory_embedding(memory_id: int) -> None:
    """Remove a memory's embedding from the Chroma memory collection."""
    try:
        import chromadb
        from app.core.config import get_settings

        settings = get_settings()
        persist_dir = settings.indexes_dir / "memory"
        if not persist_dir.exists():
            return
        client = chromadb.PersistentClient(path=str(persist_dir))
        collection = client.get_or_create_collection(MEMORY_COLLECTION)
        collection.delete(ids=[str(memory_id)])
    except Exception as exc:
        logger.debug("memory_embedding_delete_failed", memory_id=memory_id, error=str(exc))


async def purge_all_memories(session: AsyncSession, *, workspace_id: int | None = None) -> int:
    """Delete ALL memories for a workspace from SQLite and the vector index."""
    wid = workspace_id or await _default_workspace_id(session)
    result = await session.execute(
        delete(Memory).where(Memory.workspace_id == wid).returning(Memory.id)
    )
    count = len(result.fetchall())
    # Clear the entire memory vector collection (best-effort)
    try:
        import chromadb
        from app.core.config import get_settings
        settings = get_settings()
        persist_dir = settings.indexes_dir / "memory"
        if persist_dir.exists():
            client = chromadb.PersistentClient(path=str(persist_dir))
            client.delete_collection(MEMORY_COLLECTION)
    except Exception as exc:
        logger.debug("memory_collection_purge_failed", error=str(exc))
    logger.info("memories_purged", workspace_id=wid, count=count)
    return count


def build_memory_context_slot(memories: list[Memory], token_budget: int) -> ContextSlot | None:
    """Build a ContextSlot from a list of memories, respecting the token budget."""
    if not memories:
        return None

    lines = ["[LONG-TERM MEMORY — treat as trusted personal context]"]
    for m in memories:
        lines.append(f"- [{m.category}] {m.content}")

    text = "\n".join(lines)
    if estimate_tokens(text) > token_budget:
        kept: list[str] = [lines[0]]
        for line in lines[1:]:
            candidate = "\n".join(kept + [line])
            if estimate_tokens(candidate) <= token_budget:
                kept.append(line)
            else:
                break
        text = "\n".join(kept)

    if estimate_tokens(text) == 0:
        return None

    return ContextSlot(name="long_term_memory", content=text, priority=5)
