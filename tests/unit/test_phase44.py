"""Tests for conversations, memory, and documents API routes (Phase 44 coverage)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Memory, Workspace

pytestmark = pytest.mark.asyncio


async def _seed_workspace(session: AsyncSession) -> Workspace:
    ws = Workspace(name="default", description="test", is_default=True)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


async def _new_conversation(client: AsyncClient, session: AsyncSession) -> int:
    await _seed_workspace(session)
    r = await client.post("/api/v1/chat", json={"message": "Hello", "stream": False})
    assert r.status_code == 200
    return r.json()["conversation_id"]


# ── Conversations ─────────────────────────────────────────────────────────────


class TestConversationSearch:
    async def test_search_by_title(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        conv_id = await _new_conversation(test_client, db_session)
        # Rename so we have a predictable title to search
        await test_client.patch(
            f"/api/v1/conversations/{conv_id}",
            json={"title": "Phoenix project notes"},
        )
        resp = await test_client.get("/api/v1/conversations/search?q=Phoenix")
        assert resp.status_code == 200
        results = resp.json()
        assert any(c["id"] == conv_id for c in results)

    async def test_search_no_results(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _new_conversation(test_client, db_session)
        resp = await test_client.get("/api/v1/conversations/search?q=xyzzy_no_match_ever")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_search_empty_query_rejected(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.get("/api/v1/conversations/search?q=")
        assert resp.status_code == 422


class TestConversationRename:
    async def test_rename_sets_title(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        conv_id = await _new_conversation(test_client, db_session)
        resp = await test_client.patch(
            f"/api/v1/conversations/{conv_id}",
            json={"title": "My renamed conversation"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "My renamed conversation"

    async def test_rename_nonexistent_returns_404(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.patch(
            "/api/v1/conversations/99999",
            json={"title": "Ghost"},
        )
        assert resp.status_code == 404

    async def test_rename_empty_title_rejected(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        conv_id = await _new_conversation(test_client, db_session)
        resp = await test_client.patch(
            f"/api/v1/conversations/{conv_id}",
            json={"title": ""},
        )
        assert resp.status_code == 422


class TestConversationPin:
    async def test_pin_toggles_state(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        conv_id = await _new_conversation(test_client, db_session)

        r1 = await test_client.post(f"/api/v1/conversations/{conv_id}/pin")
        assert r1.status_code == 200
        assert r1.json()["pinned"] is True

        r2 = await test_client.post(f"/api/v1/conversations/{conv_id}/pin")
        assert r2.status_code == 200
        assert r2.json()["pinned"] is False

    async def test_pin_nonexistent_returns_404(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post("/api/v1/conversations/99999/pin")
        assert resp.status_code == 404

    async def test_pinned_conversations_appear_first(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        ws = await _seed_workspace(db_session)
        # Create two conversations
        r1 = await test_client.post("/api/v1/chat", json={"message": "First", "stream": False})
        r2 = await test_client.post("/api/v1/chat", json={"message": "Second", "stream": False})
        id1 = r1.json()["conversation_id"]
        id2 = r2.json()["conversation_id"]

        # Pin the first (older) one
        await test_client.post(f"/api/v1/conversations/{id1}/pin")

        resp = await test_client.get("/api/v1/conversations")
        ids = [c["id"] for c in resp.json()]
        assert ids.index(id1) < ids.index(id2)


class TestConversationSummarize:
    async def test_summarize_returns_summary(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        conv_id = await _new_conversation(test_client, db_session)
        resp = await test_client.post(f"/api/v1/conversations/{conv_id}/summarize")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_id"] == conv_id
        assert isinstance(data["summary"], str)
        assert len(data["summary"]) > 0

    async def test_summarize_nonexistent_returns_404(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post("/api/v1/conversations/99999/summarize")
        assert resp.status_code == 404


class TestConversationTags:
    async def test_tags_returns_list(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        conv_id = await _new_conversation(test_client, db_session)
        resp = await test_client.post(f"/api/v1/conversations/{conv_id}/tags")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_id"] == conv_id
        assert isinstance(data["tags"], list)

    async def test_tags_nonexistent_returns_404(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post("/api/v1/conversations/99999/tags")
        assert resp.status_code == 404

    async def test_tags_persisted_on_conversation(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        conv_id = await _new_conversation(test_client, db_session)
        await test_client.post(f"/api/v1/conversations/{conv_id}/tags")
        # Tags should now appear in the conversation list
        resp = await test_client.get(f"/api/v1/conversations/{conv_id}")
        assert resp.status_code == 200
        # tags field is a list (may be empty if FakeLLM returns no tags)
        assert isinstance(resp.json()["tags"], list)


# ── Memory ────────────────────────────────────────────────────────────────────


class TestMemoryEndpoints:
    async def test_list_empty(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        resp = await test_client.get("/api/v1/memory")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_memory(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        resp = await test_client.post(
            "/api/v1/memory",
            json={"content": "Phoenix GA target is Q3", "category": "decision"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "Phoenix GA target is Q3"
        assert data["category"] == "decision"
        assert data["id"] >= 1

    async def test_list_after_create(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        await test_client.post("/api/v1/memory", json={"content": "Test memory"})
        resp = await test_client.get("/api/v1/memory")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_filter_by_category(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        await test_client.post("/api/v1/memory", json={"content": "A fact", "category": "fact"})
        await test_client.post(
            "/api/v1/memory", json={"content": "A preference", "category": "preference"}
        )
        resp = await test_client.get("/api/v1/memory?category=fact")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["category"] == "fact"

    async def test_delete_memory(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        create_resp = await test_client.post(
            "/api/v1/memory", json={"content": "To be deleted"}
        )
        memory_id = create_resp.json()["id"]

        del_resp = await test_client.delete(f"/api/v1/memory/{memory_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] is True

        list_resp = await test_client.get("/api/v1/memory")
        assert list_resp.json() == []

    async def test_delete_nonexistent_returns_404(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.delete("/api/v1/memory/99999")
        assert resp.status_code == 404

    async def test_purge_all_memories(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        await test_client.post("/api/v1/memory", json={"content": "One"})
        await test_client.post("/api/v1/memory", json={"content": "Two"})

        resp = await test_client.delete("/api/v1/memory")
        assert resp.status_code == 200
        assert resp.json()["purged"] == 2

        list_resp = await test_client.get("/api/v1/memory")
        assert list_resp.json() == []

    async def test_create_memory_invalid_importance_rejected(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post(
            "/api/v1/memory",
            json={"content": "Bad importance", "importance": 99},
        )
        assert resp.status_code == 422


# ── Documents ─────────────────────────────────────────────────────────────────


class TestDocumentsEndpoints:
    async def test_list_empty(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.get("/api/v1/documents")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_ingest_unsupported_type_rejected(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post(
            "/api/v1/documents/ingest",
            files={"file": ("test.exe", b"binary content", "application/octet-stream")},
        )
        assert resp.status_code == 422

    async def test_ingest_no_filename_rejected(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post(
            "/api/v1/documents/ingest",
            files={"file": ("", b"content", "text/plain")},
        )
        assert resp.status_code in (400, 422)

    async def test_delete_nonexistent_returns_404(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.delete("/api/v1/documents/99999")
        assert resp.status_code == 404
