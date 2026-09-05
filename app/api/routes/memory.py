"""Memory endpoints — GET/POST/DELETE /api/v1/memory."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession
from app.api.schemas.chat import MemoryCreate, MemoryOut
from app.memory.manager import forget, list_memories, purge_all_memories, remember

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


@router.get("", response_model=list[MemoryOut])
async def get_memories(
    session: DbSession,
    category: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[MemoryOut]:
    memories = await list_memories(session, category=category, limit=limit, offset=offset)
    return [MemoryOut.model_validate(m) for m in memories]


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def create_memory(body: MemoryCreate, session: DbSession) -> MemoryOut:
    memory = await remember(
        session,
        content=body.content,
        category=body.category,
        importance=body.importance,
        confidence=body.confidence,
        source=body.source,
        data_classification=body.data_classification,
    )
    await session.commit()
    return MemoryOut.model_validate(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_200_OK)
async def delete_memory(memory_id: int, session: DbSession) -> dict[str, object]:
    deleted = await forget(session, memory_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    await session.commit()
    return {"deleted": True, "memory_id": memory_id}


@router.delete("", status_code=status.HTTP_200_OK)
async def purge_memories(session: DbSession) -> dict[str, object]:
    count = await purge_all_memories(session)
    await session.commit()
    return {"purged": count}
