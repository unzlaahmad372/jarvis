"""Unit tests for the chat and conversations API endpoints."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Workspace

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _seed_workspace(session: AsyncSession) -> Workspace:
    ws = Workspace(name="default", description="test", is_default=True)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


# ── Chat endpoint tests ───────────────────────────────────────────────────────


class TestChatEndpointNonStreaming:
    async def test_new_conversation_created(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        resp = await test_client.post(
            "/api/v1/chat",
            json={"message": "Hello JARVIS", "stream": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_id"] >= 1
        assert data["message"]["role"] == "assistant"
        assert data["message"]["content"]

    async def test_continues_existing_conversation(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        # First turn
        r1 = await test_client.post(
            "/api/v1/chat",
            json={"message": "First message", "stream": False},
        )
        assert r1.status_code == 200
        conv_id = r1.json()["conversation_id"]

        # Second turn in same conversation
        r2 = await test_client.post(
            "/api/v1/chat",
            json={"message": "Second message", "conversation_id": conv_id, "stream": False},
        )
        assert r2.status_code == 200
        assert r2.json()["conversation_id"] == conv_id

    async def test_invalid_conversation_id_returns_404(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        resp = await test_client.post(
            "/api/v1/chat",
            json={"message": "Hello", "conversation_id": 99999, "stream": False},
        )
        assert resp.status_code == 404

    async def test_empty_message_rejected(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post(
            "/api/v1/chat",
            json={"message": "", "stream": False},
        )
        assert resp.status_code == 422

    async def test_response_includes_token_usage(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        resp = await test_client.post(
            "/api/v1/chat",
            json={"message": "Token test", "stream": False},
        )
        assert resp.status_code == 200
        usage = resp.json()["token_usage"]
        assert "input_tokens" in usage
        assert "output_tokens" in usage


class TestChatEndpointStreaming:
    async def test_streaming_returns_sse_events(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        resp = await test_client.post(
            "/api/v1/chat",
            json={"message": "Stream test", "stream": True},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = resp.text
        assert "data:" in body
        assert "RESPONSE_COMPLETE" in body

    async def test_streaming_contains_thinking_event(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        resp = await test_client.post(
            "/api/v1/chat",
            json={"message": "Think test", "stream": True},
        )
        assert "THINKING" in resp.text


# ── Conversations endpoint tests ──────────────────────────────────────────────


class TestConversationsEndpoint:
    async def test_list_empty(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.get("/api/v1/conversations")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_chat(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        await test_client.post(
            "/api/v1/chat",
            json={"message": "Hello", "stream": False},
        )
        resp = await test_client.get("/api/v1/conversations")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_get_conversation_with_messages(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        chat_resp = await test_client.post(
            "/api/v1/chat",
            json={"message": "Detail test", "stream": False},
        )
        conv_id = chat_resp.json()["conversation_id"]

        resp = await test_client.get(f"/api/v1/conversations/{conv_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == conv_id
        assert len(data["messages"]) == 2  # user + assistant
        roles = [m["role"] for m in data["messages"]]
        assert "user" in roles
        assert "assistant" in roles

    async def test_get_nonexistent_conversation_returns_404(
        self, test_client: AsyncClient
    ) -> None:
        resp = await test_client.get("/api/v1/conversations/99999")
        assert resp.status_code == 404

    async def test_conversation_title_set_from_first_message(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed_workspace(db_session)
        await test_client.post(
            "/api/v1/chat",
            json={"message": "My first question", "stream": False},
        )
        resp = await test_client.get("/api/v1/conversations")
        conv = resp.json()[0]
        # Title is now LLM-generated (FakeLLMProvider returns fixed text) — just assert it's set
        assert conv["title"] is not None
        assert len(conv["title"]) > 0
