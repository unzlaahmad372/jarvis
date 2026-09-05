"""Unit tests for Phase 3 — Memory manager and API."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import Memory, Workspace
from app.memory.manager import (
    build_memory_context_slot,
    forget,
    list_memories,
    purge_all_memories,
    remember,
    search_memories,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def seed_workspace(db_session):
    """Ensure a default workspace exists for every test."""
    result = await db_session.execute(
        select(Workspace).where(Workspace.is_default == True)  # noqa: E712
    )
    if result.scalar_one_or_none() is None:
        db_session.add(Workspace(name="default", is_default=True))
        await db_session.commit()


# ── remember ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remember_creates_memory(db_session):
    m = await remember(db_session, "Phoenix GA target is Q3")
    await db_session.commit()
    assert m.id is not None
    assert m.content == "Phoenix GA target is Q3"
    assert m.category == "fact"
    assert m.importance == 5
    assert m.confidence == 1.0
    assert m.data_classification == "PERSONAL"


@pytest.mark.asyncio
async def test_remember_custom_fields(db_session):
    m = await remember(
        db_session,
        "Prefer dark mode",
        category="preference",
        importance=8,
        confidence=0.9,
        source="manual",
        data_classification="PUBLIC",
    )
    await db_session.commit()
    assert m.category == "preference"
    assert m.importance == 8
    assert m.confidence == 0.9
    assert m.source == "manual"
    assert m.data_classification == "PUBLIC"


@pytest.mark.asyncio
async def test_remember_clamps_importance(db_session):
    m = await remember(db_session, "test", importance=99)
    await db_session.commit()
    assert m.importance == 10


@pytest.mark.asyncio
async def test_remember_invalid_category_falls_back(db_session):
    m = await remember(db_session, "test", category="nonsense")
    await db_session.commit()
    assert m.category == "other"


# ── search_memories ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_finds_matching_memory(db_session):
    await remember(db_session, "Phoenix GA target is Q3")
    await remember(db_session, "Kubernetes cluster uses 16 nodes")
    await db_session.commit()

    results = await search_memories(db_session, "Phoenix")
    assert len(results) == 1
    assert "Phoenix" in results[0].content


@pytest.mark.asyncio
async def test_search_returns_empty_for_no_match(db_session):
    await remember(db_session, "Some unrelated fact")
    await db_session.commit()
    results = await search_memories(db_session, "zzznomatch")
    assert results == []


@pytest.mark.asyncio
async def test_search_updates_last_accessed(db_session):
    m = await remember(db_session, "dairy farm plan")
    await db_session.commit()
    assert m.last_accessed_at is None

    results = await search_memories(db_session, "dairy")
    await db_session.commit()
    assert results[0].last_accessed_at is not None


# ── list_memories ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_memories_returns_all(db_session):
    await remember(db_session, "fact one")
    await remember(db_session, "fact two")
    await db_session.commit()
    results = await list_memories(db_session)
    assert len(results) >= 2


@pytest.mark.asyncio
async def test_list_memories_filters_by_category(db_session):
    await remember(db_session, "I prefer dark mode", category="preference")
    await remember(db_session, "Phoenix is Q3", category="decision")
    await db_session.commit()

    prefs = await list_memories(db_session, category="preference")
    assert all(m.category == "preference" for m in prefs)


# ── forget ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_forget_removes_memory(db_session):
    m = await remember(db_session, "to be forgotten")
    await db_session.commit()

    deleted = await forget(db_session, m.id)
    await db_session.commit()
    assert deleted is True

    result = await db_session.execute(select(Memory).where(Memory.id == m.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_forget_returns_false_for_missing(db_session):
    deleted = await forget(db_session, 99999)
    assert deleted is False


# ── purge_all_memories ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_purge_removes_all(db_session):
    await remember(db_session, "one")
    await remember(db_session, "two")
    await remember(db_session, "three")
    await db_session.commit()

    count = await purge_all_memories(db_session)
    await db_session.commit()
    assert count == 3

    remaining = await list_memories(db_session)
    assert remaining == []


# ── build_memory_context_slot ─────────────────────────────────────────────────


def _make_memory(content: str, category: str = "fact") -> Memory:
    m = Memory()
    m.content = content
    m.category = category
    m.importance = 5
    return m


def test_build_memory_slot_empty():
    assert build_memory_context_slot([], token_budget=512) is None


def test_build_memory_slot_basic():
    memories = [_make_memory("Phoenix GA is Q3"), _make_memory("Prefer dark mode", "preference")]
    slot = build_memory_context_slot(memories, token_budget=512)
    assert slot is not None
    assert slot.priority == 5
    assert "Phoenix" in slot.content
    assert "dark mode" in slot.content


def test_build_memory_slot_respects_budget():
    # Create many memories that would exceed a tiny budget
    memories = [_make_memory(f"memory item number {i} with some extra text") for i in range(50)]
    slot = build_memory_context_slot(memories, token_budget=30)
    assert slot is not None
    assert slot.token_count <= 30


# ── Memory API endpoints ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_create_memory(test_client):
    resp = await test_client.post(
        "/api/v1/memory",
        json={"content": "Phoenix GA target is Q3", "category": "decision", "importance": 9},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "Phoenix GA target is Q3"
    assert data["category"] == "decision"
    assert data["importance"] == 9


@pytest.mark.asyncio
async def test_api_list_memories(test_client):
    await test_client.post("/api/v1/memory", json={"content": "list test memory"})
    resp = await test_client.get("/api/v1/memory")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_api_delete_memory(test_client):
    create = await test_client.post("/api/v1/memory", json={"content": "delete me"})
    memory_id = create.json()["id"]

    resp = await test_client.delete(f"/api/v1/memory/{memory_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


@pytest.mark.asyncio
async def test_api_delete_missing_memory(test_client):
    resp = await test_client.delete("/api/v1/memory/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_purge_memories(test_client):
    await test_client.post("/api/v1/memory", json={"content": "purge me 1"})
    await test_client.post("/api/v1/memory", json={"content": "purge me 2"})

    resp = await test_client.delete("/api/v1/memory")
    assert resp.status_code == 200
    assert resp.json()["purged"] >= 2
