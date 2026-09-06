"""Tests for Phase 29 — Conversation Intelligence (titler, summarizer, API)."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.summarizer import summarize_conversation
from app.brain.titler import generate_title
from app.db.models import Workspace
from tests.fakes.llm import FakeLLMProvider

# ── Fixtures ──────────────────────────────────────────────────────────────────


async def _seed(session: AsyncSession) -> Workspace:
    ws = Workspace(name="default", is_default=True)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


# ── Titler unit tests ─────────────────────────────────────────────────────────


class TestTitler:
    async def test_returns_llm_content(self) -> None:
        llm = FakeLLMProvider(response_text="My Custom Title")
        title = await generate_title("What is the capital of France?", llm)
        assert title == "My Custom Title"

    async def test_clamps_to_120_chars(self) -> None:
        llm = FakeLLMProvider(response_text="x" * 200)
        title = await generate_title("hello", llm)
        assert len(title) <= 120

    async def test_falls_back_on_llm_error(self) -> None:
        class ErrorLLM(FakeLLMProvider):
            async def complete(self, *a, **kw):  # type: ignore[override]
                raise RuntimeError("LLM down")

        llm = ErrorLLM()
        title = await generate_title("This is my message", llm)
        assert "This is my message" in title

    async def test_strips_quotes(self) -> None:
        llm = FakeLLMProvider(response_text='"Quoted Title"')
        title = await generate_title("hello", llm)
        assert title == "Quoted Title"

    async def test_empty_llm_response_falls_back(self) -> None:
        llm = FakeLLMProvider(response_text="")
        title = await generate_title("fallback message", llm)
        assert "fallback message" in title


# ── Summarizer unit tests ─────────────────────────────────────────────────────


class _FakeConv:
    """Minimal stand-in for Conversation ORM model in unit tests."""
    def __init__(self, id: int = 1, title: str | None = "Test conv") -> None:
        self.id = id
        self.title = title


class _FakeMsg:
    """Minimal stand-in for Message ORM model in unit tests."""
    def __init__(self, role: str, content: str, sequence: int = 0) -> None:
        self.role = role
        self.content = content
        self.sequence = sequence


class TestSummarizer:
    def _make_conv(self) -> _FakeConv:  # type: ignore[return]
        return _FakeConv()

    def _make_messages(self) -> list[_FakeMsg]:  # type: ignore[return]
        return [
            _FakeMsg("user", "What is Python?", 0),
            _FakeMsg("assistant", "Python is a programming language.", 1),
            _FakeMsg("user", "What version should I use?", 2),
            _FakeMsg("assistant", "Use Python 3.12 or newer.", 3),
        ]

    async def test_returns_llm_summary(self) -> None:
        llm = FakeLLMProvider(response_text="Discussion about Python versions.")
        conv = self._make_conv()
        result = await summarize_conversation(conv, self._make_messages(), llm)  # type: ignore[arg-type]
        assert result == "Discussion about Python versions."

    async def test_empty_conversation(self) -> None:
        llm = FakeLLMProvider()
        conv = self._make_conv()
        result = await summarize_conversation(conv, [], llm)  # type: ignore[arg-type]
        assert result == "Empty conversation."

    async def test_falls_back_on_llm_error(self) -> None:
        class ErrorLLM(FakeLLMProvider):
            async def complete(self, *a, **kw):  # type: ignore[override]
                raise RuntimeError("LLM down")

        llm = ErrorLLM()
        conv = self._make_conv()
        result = await summarize_conversation(conv, self._make_messages(), llm)  # type: ignore[arg-type]
        assert "4 messages" in result or "Test conv" in result

    async def test_long_transcript_truncated(self) -> None:
        """Transcript over 12k chars should not raise."""
        llm = FakeLLMProvider(response_text="Summary of long conversation.")
        conv = self._make_conv()
        msgs = [_FakeMsg("user" if i % 2 == 0 else "assistant", "x" * 200, i) for i in range(100)]
        result = await summarize_conversation(conv, msgs, llm)  # type: ignore[arg-type]
        assert result


# ── Summarize API endpoint ────────────────────────────────────────────────────


class TestSummarizeAPI:
    async def test_summarize_returns_200(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed(db_session)
        chat = await test_client.post(
            "/api/v1/chat", json={"message": "Tell me about Python", "stream": False}
        )
        conv_id = chat.json()["conversation_id"]

        resp = await test_client.post(f"/api/v1/conversations/{conv_id}/summarize")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_id"] == conv_id
        assert data["message_count"] >= 1
        assert isinstance(data["summary"], str)
        assert len(data["summary"]) > 0

    async def test_summarize_nonexistent_returns_404(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        resp = await test_client.post("/api/v1/conversations/99999/summarize")
        assert resp.status_code == 404

    async def test_summarize_includes_title(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed(db_session)
        chat = await test_client.post(
            "/api/v1/chat", json={"message": "Hello JARVIS", "stream": False}
        )
        conv_id = chat.json()["conversation_id"]

        resp = await test_client.post(f"/api/v1/conversations/{conv_id}/summarize")
        assert resp.status_code == 200
        data = resp.json()
        assert "title" in data  # may be None or a string


# ── Auto-title integration ────────────────────────────────────────────────────


class TestAutoTitle:
    async def test_first_message_sets_llm_title(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # After first chat turn, title should be set (LLM-generated via FakeLLMProvider)
        await _seed(db_session)
        resp = await test_client.post(
            "/api/v1/chat",
            json={"message": "What is the meaning of life?", "stream": False},
        )
        assert resp.status_code == 200
        conv_id = resp.json()["conversation_id"]

        conv_resp = await test_client.get(f"/api/v1/conversations/{conv_id}")
        title = conv_resp.json()["title"]
        # FakeLLMProvider returns a fixed response — title should be set (not None)
        assert title is not None
        assert len(title) > 0

    async def test_second_message_does_not_overwrite_title(
        self, test_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed(db_session)
        r1 = await test_client.post(
            "/api/v1/chat", json={"message": "First message", "stream": False}
        )
        conv_id = r1.json()["conversation_id"]

        # Manually set a known title
        await test_client.patch(
            f"/api/v1/conversations/{conv_id}", json={"title": "My Custom Title"}
        )

        # Second turn should not overwrite
        await test_client.post(
            "/api/v1/chat",
            json={"message": "Second message", "conversation_id": conv_id, "stream": False},
        )
        conv_resp = await test_client.get(f"/api/v1/conversations/{conv_id}")
        assert conv_resp.json()["title"] == "My Custom Title"
