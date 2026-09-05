"""Chat endpoint — POST /api/v1/chat."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.deps import DbSession, SettingsDep
from app.api.schemas.chat import (
    ChatRequest,
    ChatResponse,
    MessageOut,
    TokenUsage,
)
from app.brain.orchestrator import ChatOrchestrator
from app.inference.manager import InferenceManager, InferenceQueueFullError
from app.llm.base import LLMProvider

router = APIRouter(prefix="/api/v1", tags=["chat"])

_llm_provider_override: LLMProvider | None = None


def set_llm_provider(provider: LLMProvider | None) -> None:
    global _llm_provider_override
    _llm_provider_override = provider


def _get_orchestrator(settings: object) -> ChatOrchestrator:
    from app.core.config import Settings
    from app.knowledge.embeddings import OllamaEmbeddingProvider
    from app.knowledge.vector_store import ChromaVectorStore
    from app.llm.ollama import OllamaProvider

    s: Settings = settings  # type: ignore[assignment]
    llm: LLMProvider = _llm_provider_override or OllamaProvider(
        base_url=s.ollama_url, model=s.llm_model
    )
    inference = InferenceManager(
        max_concurrent=s.max_concurrent_llm_requests,
        timeout_seconds=s.llm_request_timeout,
        max_queue_length=s.max_queue_length,
    )
    embedding = OllamaEmbeddingProvider(base_url=s.ollama_url, model=s.embedding_model)
    vector_store = ChromaVectorStore(
        persist_dir=s.indexes_dir,
        embedding_model=s.embedding_model,
        index_version=s.index_version,
    )
    return ChatOrchestrator(
        settings=s,
        llm_provider=llm,
        inference_manager=inference,
        embedding_provider=embedding,
        vector_store=vector_store,
    )


@router.post("/chat", summary="Send a chat message", response_model=None)
async def chat(
    body: ChatRequest,
    request: Request,
    session: DbSession,
    settings: SettingsDep,
) -> StreamingResponse | ChatResponse:
    """Send a message to JARVIS (stream=true for SSE, stream=false for JSON)."""
    orchestrator = _get_orchestrator(settings)

    if body.stream:
        async def _generate() -> AsyncGenerator[str, None]:
            async for chunk in orchestrator.stream_chat(
                session, body.message, body.conversation_id
            ):
                yield chunk

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        user_msg, asst_msg, compacted, rag_result = await orchestrator.chat(
            session, body.message, body.conversation_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InferenceQueueFullError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JARVIS is busy. Please try again shortly.",
        ) from exc

    token_usage = TokenUsage(
        input_tokens=asst_msg.input_tokens,
        output_tokens=asst_msg.output_tokens,
        context_tokens=asst_msg.context_tokens,
    )

    return ChatResponse(
        conversation_id=asst_msg.conversation_id,
        message=MessageOut(
            id=asst_msg.id,
            conversation_id=asst_msg.conversation_id,
            role=asst_msg.role,
            content=asst_msg.content,
            sequence=asst_msg.sequence,
            model=asst_msg.model,
            provider=asst_msg.provider,
            token_usage=token_usage,
            created_at=asst_msg.created_at,
        ),
        token_usage=token_usage,
        compacted=compacted,
    )
