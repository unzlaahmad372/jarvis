"""Tests for Phase 18 — true token-by-token streaming."""

from __future__ import annotations

import pytest

from app.inference.manager import InferenceManager, InferenceQueueFullError
from tests.fakes.llm import FakeLLMProvider, FakeScenario

# ── FakeLLMProvider.complete_stream ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_fake_stream_yields_tokens() -> None:
    provider = FakeLLMProvider(response_text="hello world foo")
    tokens = [t async for t in provider.complete_stream("prompt")]
    assert len(tokens) > 0
    assert "".join(tokens).strip() == "hello world foo"


@pytest.mark.asyncio
async def test_fake_stream_timeout_raises() -> None:
    provider = FakeLLMProvider(scenario=FakeScenario.TIMEOUT)
    with pytest.raises(TimeoutError):
        async for _ in provider.complete_stream("prompt"):
            pass


@pytest.mark.asyncio
async def test_fake_stream_unavailable_raises() -> None:
    provider = FakeLLMProvider(scenario=FakeScenario.UNAVAILABLE)
    with pytest.raises(ConnectionError):
        async for _ in provider.complete_stream("prompt"):
            pass


# ── InferenceManager.stream ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inference_manager_stream_yields_tokens() -> None:
    manager = InferenceManager(max_concurrent=1, timeout_seconds=10, max_queue_length=5)
    provider = FakeLLMProvider(response_text="one two three")

    tokens = [
        t async for t in manager.stream(
            lambda: provider.complete_stream("test")
        )
    ]
    assert len(tokens) == 3
    assert "one" in tokens[0]


@pytest.mark.asyncio
async def test_inference_manager_stream_queue_full() -> None:
    manager = InferenceManager(max_concurrent=1, timeout_seconds=10, max_queue_length=0)
    provider = FakeLLMProvider()

    with pytest.raises(InferenceQueueFullError):
        async for _ in manager.stream(lambda: provider.complete_stream("test")):
            pass


@pytest.mark.asyncio
async def test_inference_manager_stream_respects_semaphore() -> None:
    """Only one stream runs at a time with max_concurrent=1."""
    import asyncio

    manager = InferenceManager(max_concurrent=1, timeout_seconds=10, max_queue_length=5)
    provider = FakeLLMProvider(response_text="a b c d e")

    results: list[list[str]] = []

    async def collect() -> None:
        tokens = [t async for t in manager.stream(lambda: provider.complete_stream("x"))]
        results.append(tokens)

    await asyncio.gather(collect(), collect())
    assert len(results) == 2
    for r in results:
        assert len(r) > 0


# ── OllamaProvider.complete_stream (unit — no live server) ────────────────────


@pytest.mark.asyncio
async def test_ollama_stream_parses_chunks() -> None:
    import json
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.llm.ollama import OllamaProvider

    provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

    lines = [
        json.dumps({"response": "Hello", "done": False}),
        json.dumps({"response": " world", "done": False}),
        json.dumps({"response": "", "done": True}),
    ]

    async def fake_aiter_lines():  # type: ignore[return]
        for line in lines:
            yield line

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines = fake_aiter_lines

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.llm.ollama.httpx.AsyncClient", return_value=mock_client):
        tokens = [t async for t in provider.complete_stream("hi")]

    assert tokens == ["Hello", " world"]


@pytest.mark.asyncio
async def test_ollama_stream_stops_on_done() -> None:
    import json
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.llm.ollama import OllamaProvider

    provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

    lines = [
        json.dumps({"response": "tok1", "done": False}),
        json.dumps({"response": "tok2", "done": True}),
        json.dumps({"response": "tok3", "done": False}),  # should not be yielded
    ]

    async def fake_aiter_lines():  # type: ignore[return]
        for line in lines:
            yield line

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines = fake_aiter_lines

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.llm.ollama.httpx.AsyncClient", return_value=mock_client):
        tokens = [t async for t in provider.complete_stream("hi")]

    assert tokens == ["tok1", "tok2"]
