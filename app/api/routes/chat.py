"""Chat endpoint — POST /api/v1/chat."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import DbSession, SettingsDep, get_orchestrator
from app.api.schemas.chat import (
    ChatRequest,
    ChatResponse,
    MessageOut,
    TokenUsage,
    VisionAnalyseResponse,
)
from app.brain.orchestrator import ChatOrchestrator
from app.inference.manager import InferenceQueueFullError
from app.llm.base import LLMProvider

router = APIRouter(prefix="/api/v1", tags=["chat"])

_llm_provider_override: LLMProvider | None = None


def set_llm_provider(provider: LLMProvider | None) -> None:
    global _llm_provider_override
    _llm_provider_override = provider


def build_orchestrator(settings: object) -> ChatOrchestrator:
    """Build a ChatOrchestrator.  Called once at startup from lifespan()."""
    from app.core.config import Settings
    from app.inference.manager import InferenceManager
    from app.knowledge.embeddings import OllamaEmbeddingProvider
    from app.knowledge.vector_store import ChromaVectorStore
    from app.llm.ollama import OllamaProvider
    from app.tools.executor import ToolExecutor
    from app.tools.registry import get_registry

    s: Settings = settings  # type: ignore[assignment]
    llm: LLMProvider = _llm_provider_override or OllamaProvider(
        base_url=s.ollama_url, model=s.llm_model
    )
    # Single shared InferenceManager — semaphore is shared across all requests
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
    registry = get_registry()
    executor = ToolExecutor(registry=registry, settings=s)
    return ChatOrchestrator(
        settings=s,
        llm_provider=llm,
        inference_manager=inference,
        embedding_provider=embedding,
        vector_store=vector_store,
        tool_registry=registry,
        tool_executor=executor,
    )


OrchestratorDep = Annotated[ChatOrchestrator, Depends(get_orchestrator)]


@router.post(
    "/vision/analyse",
    summary="Analyse an uploaded image",
    response_model=VisionAnalyseResponse,
)
async def vision_analyse(
    file: UploadFile,
    prompt: str = "Describe this image in detail.",
    settings: SettingsDep = ...,  # type: ignore[assignment]
) -> VisionAnalyseResponse:
    """Upload an image and get a description from the local vision model."""
    import tempfile
    from pathlib import Path

    if not settings.enable_vision:
        raise HTTPException(status_code=503, detail="Vision is not enabled")

    suffix = Path(file.filename or "img").suffix.lower()
    allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported image format: {suffix}")

    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    from app.tools.vision.tools import VisionTool
    result = await VisionTool().execute({"image_path": tmp_path, "prompt": prompt})

    from pathlib import Path as _Path
    try:
        _Path(tmp_path).unlink(missing_ok=True)
    except OSError:
        pass

    return VisionAnalyseResponse(
        success=result.success,
        description=result.output,
        error=result.error,
    )


@router.post("/chat", summary="Send a chat message", response_model=None)
async def chat(
    body: ChatRequest,
    request: Request,
    session: DbSession,
    settings: SettingsDep,
    orchestrator: OrchestratorDep,
) -> StreamingResponse | ChatResponse:
    """Send a message to JARVIS (stream=true for SSE, stream=false for JSON)."""
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
        user_msg, asst_msg, compacted, rag_result, _plan = await orchestrator.chat(
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
