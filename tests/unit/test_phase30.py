"""Tests for Phase 30 — Topic Tags (tagger, API endpoint, persistence)."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.tagger import generate_tags
from app.db.models import Conversation, Workspace
from tests.fakes.llm import FakeLLMProvider


async def _seed(session: AsyncSession) -> Workspace:
    ws = Workspace(name="default", is_default=True)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


# ── Tagger unit tests ─────────────────────────────────────────────────────────


class TestTagger:
    async def test_returns_parsed_tags(self) -> None:
        llm = FakeLLMProvider(response_text="python, async, debugging")
        tags = await generate_tags("user: how do I debug async python?", llm)
        assert tags == ["python", "async", "debugging"]

    async def test_clamps_to_five(self) -> None:
        llm = FakeLLMProvider(response_text="a, b, c, d, e, f, g")
        tags = await generate_tags("some transcript", llm)
        assert len(tags) <= 5

    async def test_empty_transcript_returns_empty(self) -> None:
        llm = FakeLLMProvider(response_text="python")
        tags = await generate_tags("", llm)
        assert tags == []

    async def test_lowercases_tags(self) -> None:
        llm = FakeLLMProvider(response_text="Python, FastAPI, Docker")
        tags = await generate_tags("some text", llm)
        assert all(t == t.lower() for t in tags)

    async def test_falls_back_on_llm_error(self) -> None:
        class ErrorLLM(FakeLLMProvider):
            async def complete(self, *a, **kw):  # type: ignore[override]
                raise RuntimeError("LLM down")

        tags = await generate_tags("some text", ErrorLLM())
        assert tags == []

    async def test_strips_whitespace(self) -> None:
        llm = FakeLLMProvider(response_text="  python ,  async  , testing  ")
        tags = await generate_tags("text", llm)
        assert tags == ["python", "async", "testing"]


# ── Tags API endpoint ─────────────────────────────────────────────────────────


class TestTagsAPI:
    async def test_tag_returns_200(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed(db_session)
        chat = await test_client.post(
            "/api/v1/chat", json={"message": "Tell me about Python async", "stream": False}
        )
        conv_id = chat.json()["conversation_id"]

        resp = await test_client.post(f"/api/v1/conversations/{conv_id}/tags")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_id"] == conv_id
        assert isinstance(data["tags"], list)

    async def test_tag_nonexistent_returns_404(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post("/api/v1/conversations/99999/tags")
        assert resp.status_code == 404

    async def test_tags_persisted_on_conversation(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed(db_session)
        chat = await test_client.post(
            "/api/v1/chat", json={"message": "Explain Docker containers", "stream": False}
        )
        conv_id = chat.json()["conversation_id"]

        await test_client.post(f"/api/v1/conversations/{conv_id}/tags")

        # Verify tags are stored in DB
        conv = (await db_session.execute(
            select(Conversation).where(Conversation.id == conv_id)
        )).scalar_one()
        # tags column should be set (FakeLLMProvider returns fixed text)
        assert conv.tags is not None

    async def test_tags_appear_in_conversation_list(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed(db_session)
        chat = await test_client.post(
            "/api/v1/chat", json={"message": "What is Kubernetes?", "stream": False}
        )
        conv_id = chat.json()["conversation_id"]

        # Tag the conversation
        tag_resp = await test_client.post(f"/api/v1/conversations/{conv_id}/tags")
        expected_tags = tag_resp.json()["tags"]

        # Tags should appear in the list endpoint
        list_resp = await test_client.get("/api/v1/conversations")
        conv_data = next(c for c in list_resp.json() if c["id"] == conv_id)
        assert conv_data["tags"] == expected_tags

    async def test_conversation_out_tags_default_empty(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Conversations always return tags as a list (may be populated by auto-tag)."""
        await _seed(db_session)
        chat = await test_client.post(
            "/api/v1/chat", json={"message": "Hello", "stream": False}
        )
        conv_id = chat.json()["conversation_id"]

        list_resp = await test_client.get("/api/v1/conversations")
        conv_data = next(c for c in list_resp.json() if c["id"] == conv_id)
        # tags is always a list (auto-tag may have populated it on first turn)
        assert isinstance(conv_data["tags"], list)
