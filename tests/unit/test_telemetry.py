"""Unit tests for app.core.telemetry — Section 96 / 123.9."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Core telemetry module
# ---------------------------------------------------------------------------

def test_span_noop_without_sdk() -> None:
    from app.core.telemetry import span

    with span("test.operation", {"key": "value"}) as s:
        assert s is not None


def test_span_noop_no_attributes() -> None:
    from app.core.telemetry import span

    with span("test.no_attrs") as s:
        assert s is not None


def test_configure_telemetry_no_endpoint() -> None:
    from app.core.telemetry import configure_telemetry

    configure_telemetry(service_name="test-jarvis", otel_endpoint=None)


def test_shutdown_telemetry_safe_before_configure() -> None:
    from app.core.telemetry import shutdown_telemetry

    shutdown_telemetry()


def test_get_tracer_returns_something() -> None:
    from app.core.telemetry import get_tracer

    tracer = get_tracer()
    assert tracer is not None


def test_span_does_not_suppress_exceptions() -> None:
    from app.core.telemetry import span

    with pytest.raises(ValueError, match="boom"):
        with span("test.error"):
            raise ValueError("boom")


def test_noop_span_methods_are_safe() -> None:
    from app.core.telemetry import _NoOpSpan  # type: ignore[attr-defined]

    s = _NoOpSpan()
    s.set_attribute("k", "v")
    s.record_exception(RuntimeError("x"))
    s.set_status("ok")


# ---------------------------------------------------------------------------
# InferenceManager span instrumentation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inference_manager_run_emits_span() -> None:
    """InferenceManager.run wraps the call in an inference.run span."""
    from app.inference.manager import InferenceManager

    spans_entered: list[str] = []

    class _FakeSpanCtx:
        def __enter__(self) -> _FakeSpanCtx:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    def _fake_span(name: str, attrs: dict | None = None) -> _FakeSpanCtx:
        spans_entered.append(name)
        return _FakeSpanCtx()

    mgr = InferenceManager(max_concurrent=1, timeout_seconds=5, max_queue_length=5)

    async def _ok() -> str:
        return "ok"

    with patch("app.inference.manager.span", side_effect=_fake_span):
        result = await mgr.run(_ok, request_id="r1")

    assert result == "ok"
    assert "inference.run" in spans_entered


@pytest.mark.asyncio
async def test_inference_manager_run_span_on_timeout() -> None:
    from app.inference.manager import InferenceManager

    mgr = InferenceManager(max_concurrent=1, timeout_seconds=1, max_queue_length=5)

    async def _slow() -> str:
        await asyncio.sleep(10)
        return "never"

    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        await mgr.run(_slow, request_id="timeout-test")


# ---------------------------------------------------------------------------
# OllamaProvider span instrumentation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ollama_complete_emits_span() -> None:
    """OllamaProvider.complete wraps the HTTP call in an llm.complete span."""
    from app.llm.ollama import OllamaProvider

    spans_entered: list[str] = []

    class _FakeSpanCtx:
        def __enter__(self) -> _FakeSpanCtx:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    def _fake_span(name: str, attrs: dict | None = None) -> _FakeSpanCtx:
        spans_entered.append(name)
        return _FakeSpanCtx()

    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model="llama3.2")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "response": "hello",
        "model": "llama3.2",
        "done": True,
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.llm.ollama.span", side_effect=_fake_span), \
         patch("app.llm.ollama.httpx.AsyncClient", return_value=mock_client):
        resp = await provider.complete("hello")

    assert resp.content == "hello"
    assert "llm.complete" in spans_entered


# ---------------------------------------------------------------------------
# RAG retrieval span instrumentation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_emits_span() -> None:
    """retrieve() wraps the operation in a rag.retrieve span."""
    from app.knowledge.retrieval import retrieve

    spans_entered: list[str] = []

    class _FakeSpanCtx:
        def __enter__(self) -> _FakeSpanCtx:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    def _fake_span(name: str, attrs: dict | None = None) -> _FakeSpanCtx:
        spans_entered.append(name)
        return _FakeSpanCtx()

    mock_embed = AsyncMock()
    mock_embed.embed.return_value = MagicMock(vectors=[[0.1, 0.2]])

    mock_vs = AsyncMock()
    mock_vs.search.return_value = []

    with patch("app.knowledge.retrieval.span", side_effect=_fake_span):
        result = await retrieve(
            query="test",
            embedding_provider=mock_embed,
            vector_store=mock_vs,
        )

    assert result.chunks == []
    assert "rag.retrieve" in spans_entered


@pytest.mark.asyncio
async def test_retrieve_span_on_embed_failure() -> None:
    """retrieve() still emits span even when embedding fails."""
    from app.knowledge.retrieval import retrieve

    spans_entered: list[str] = []

    class _FakeSpanCtx:
        def __enter__(self) -> _FakeSpanCtx:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    def _fake_span(name: str, attrs: dict | None = None) -> _FakeSpanCtx:
        spans_entered.append(name)
        return _FakeSpanCtx()

    mock_embed = AsyncMock()
    mock_embed.embed.side_effect = RuntimeError("embed failed")
    mock_vs = AsyncMock()

    with patch("app.knowledge.retrieval.span", side_effect=_fake_span):
        result = await retrieve(
            query="test",
            embedding_provider=mock_embed,
            vector_store=mock_vs,
        )

    assert result.chunks == []
    assert "rag.retrieve" in spans_entered


# ---------------------------------------------------------------------------
# ToolExecutor span instrumentation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_executor_emits_span() -> None:
    """ToolExecutor.execute wraps the call in a tool.execute span."""
    from unittest.mock import AsyncMock as AM

    from app.core.config import Settings
    from app.tools.base import RiskLevel, ToolRequest, ToolResult
    from app.tools.executor import ToolExecutor
    from app.tools.registry import ToolRegistry

    spans_entered: list[str] = []

    class _FakeSpanCtx:
        def __enter__(self) -> _FakeSpanCtx:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    def _fake_span(name: str, attrs: dict | None = None) -> _FakeSpanCtx:
        spans_entered.append(name)
        return _FakeSpanCtx()

    fake_tool = MagicMock()
    fake_tool.name = "test_tool"
    fake_tool.risk_level = RiskLevel.READ_ONLY
    fake_tool.execute = AM(
        return_value=ToolResult(tool_name="test_tool", success=True, output="ok")
    )

    registry = ToolRegistry()
    registry.register(fake_tool)

    settings = Settings(
        require_confirmation=False,
        database_url="sqlite+aiosqlite:///:memory:",
    )
    executor = ToolExecutor(registry=registry, settings=settings)

    session = AM()
    session.add = MagicMock()
    session.flush = AM()

    request = ToolRequest(tool_name="test_tool", parameters={})

    with patch("app.tools.executor.span", side_effect=_fake_span):
        result, decision = await executor.execute(request, session)

    assert result.success is True
    assert "tool.execute" in spans_entered


@pytest.mark.asyncio
async def test_tool_executor_span_unknown_tool() -> None:
    """ToolExecutor.execute emits span even for unknown tools."""
    from unittest.mock import AsyncMock as AM

    from app.core.config import Settings
    from app.tools.base import ToolRequest
    from app.tools.executor import ToolExecutor
    from app.tools.registry import ToolRegistry

    spans_entered: list[str] = []

    class _FakeSpanCtx:
        def __enter__(self) -> _FakeSpanCtx:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    def _fake_span(name: str, attrs: dict | None = None) -> _FakeSpanCtx:
        spans_entered.append(name)
        return _FakeSpanCtx()

    registry = ToolRegistry()
    settings = Settings(
        require_confirmation=False,
        database_url="sqlite+aiosqlite:///:memory:",
    )
    executor = ToolExecutor(registry=registry, settings=settings)

    session = AM()
    session.add = MagicMock()
    session.flush = AM()

    request = ToolRequest(tool_name="no_such_tool", parameters={})

    with patch("app.tools.executor.span", side_effect=_fake_span):
        result, decision = await executor.execute(request, session)

    assert result.success is False
    assert "tool.execute" in spans_entered


# ---------------------------------------------------------------------------
# Config: otel_endpoint
# ---------------------------------------------------------------------------

def test_otel_endpoint_defaults_to_none() -> None:
    from app.core.config import Settings

    s = Settings(database_url="sqlite+aiosqlite:///:memory:")
    assert s.otel_endpoint is None


def test_otel_endpoint_can_be_set() -> None:
    from app.core.config import Settings

    s = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        otel_endpoint="http://localhost:4317",
    )
    assert s.otel_endpoint == "http://localhost:4317"
