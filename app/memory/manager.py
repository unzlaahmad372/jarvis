"""Memory manager — CRUD and search for long-term memories.

Memories are created explicitly (via 'remember' commands or the API).
They are never auto-created from every conversation turn.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.context_builder import ContextSlot, estimate_tokens
from app.core.logging import get_logger
from app.db.models import Memory, Workspace

logger = get_logger(__name__)

VALID_CATEGORIES = {"preference", "decision", "fact", "project", "entity", "other"}
VALID_CLASSIFICATIONS = {"PUBLIC", "PERSONAL", "CONFIDENTIAL", "SECRET"}


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
    return memory


async def search_memories(
    session: AsyncSession,
    query: str,
    *,
    workspace_id: int | None = None,
    limit: int = 10,
) -> list[Memory]:
    """Simple keyword search over memory content (case-insensitive).

    Phase 3 uses SQL LIKE search. A future phase can add vector similarity.
    """
    wid = workspace_id or await _default_workspace_id(session)
    stmt = (
        select(Memory)
        .where(Memory.workspace_id == wid)
        .where(Memory.content.ilike(f"%{query}%"))
        .order_by(Memory.importance.desc(), Memory.updated_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    memories = list(result.scalars().all())

    # Update last_accessed_at
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
    """Delete a single memory by ID. Returns True if it existed."""
    result = await session.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if memory is None:
        return False
    await session.delete(memory)
    await session.flush()
    logger.info("memory_forgotten", memory_id=memory_id)
    return True


async def purge_all_memories(session: AsyncSession, *, workspace_id: int | None = None) -> int:
    """Delete ALL memories for a workspace. Returns count removed."""
    wid = workspace_id or await _default_workspace_id(session)
    result = await session.execute(
        delete(Memory).where(Memory.workspace_id == wid).returning(Memory.id)
    )
    count = len(result.fetchall())
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
        # Trim memories until we fit
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
