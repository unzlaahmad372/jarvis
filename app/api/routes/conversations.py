"""Conversation management endpoints.

GET   /api/v1/conversations          — list all conversations
GET   /api/v1/conversations/search   — search by title or message content
GET   /api/v1/conversations/{id}     — get conversation with messages
PATCH /api/v1/conversations/{id}     — rename conversation
POST  /api/v1/conversations/{id}/summarize — generate on-demand summary (Phase 29)
POST  /api/v1/conversations/{id}/tags     — generate topic tags (Phase 30)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.api.deps import DbSession, get_orchestrator
from app.api.schemas.chat import ConversationDetail, ConversationOut, MessageOut, TokenUsage
from app.db.models import Conversation, Message

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


class ConversationPatch(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


@router.get("", summary="List conversations")
async def list_conversations(session: DbSession) -> list[ConversationOut]:
    result = await session.execute(
        select(Conversation).order_by(Conversation.updated_at.desc())
    )
    return [ConversationOut.model_validate(c) for c in result.scalars().all()]


@router.get("/search", summary="Search conversations by title or message content")
async def search_conversations(
    session: DbSession,
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=100),
) -> list[ConversationOut]:
    pattern = f"%{q}%"
    result = await session.execute(
        select(Conversation)
        .where(
            or_(
                Conversation.title.ilike(pattern),
                Conversation.id.in_(
                    select(Message.conversation_id)
                    .where(Message.content.ilike(pattern))
                    .distinct()
                ),
            )
        )
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    return [ConversationOut.model_validate(c) for c in result.scalars().all()]


@router.patch("/{conversation_id}", summary="Rename conversation", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: int,
    body: ConversationPatch,
    session: DbSession,
) -> ConversationOut:
    result = await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )
    conv.title = body.title
    await session.commit()
    return ConversationOut.model_validate(conv)


@router.get("/{conversation_id}", summary="Get conversation with messages")
async def get_conversation(
    conversation_id: int, session: DbSession
) -> ConversationDetail:
    result = await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    msg_result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sequence)
    )
    messages = msg_result.scalars().all()

    return ConversationDetail(
        id=conv.id,
        workspace_id=conv.workspace_id,
        title=conv.title,
        total_input_tokens=conv.total_input_tokens,
        total_output_tokens=conv.total_output_tokens,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            MessageOut(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                sequence=m.sequence,
                model=m.model,
                provider=m.provider,
                token_usage=TokenUsage(
                    input_tokens=m.input_tokens,
                    output_tokens=m.output_tokens,
                    context_tokens=m.context_tokens,
                ),
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


class SummaryOut(BaseModel):
    conversation_id: int
    title: str | None
    message_count: int
    summary: str


class TagsOut(BaseModel):
    conversation_id: int
    tags: list[str]


@router.post(
    "/{conversation_id}/summarize",
    summary="Generate an on-demand summary of a conversation",
    response_model=SummaryOut,
)
async def summarize_conversation(
    conversation_id: int,
    session: DbSession,
    request: Request,
) -> SummaryOut:
    """Use the LLM to produce a concise summary of the full conversation."""
    from app.brain.orchestrator import ChatOrchestrator
    from app.brain.summarizer import summarize_conversation as _summarize

    conv = (await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )).scalar_one_or_none()
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    messages = (await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sequence)
    )).scalars().all()

    orchestrator: ChatOrchestrator = get_orchestrator(request)  # type: ignore[assignment]
    summary = await _summarize(conv, list(messages), orchestrator._llm)  # noqa: SLF001

    return SummaryOut(
        conversation_id=conv.id,
        title=conv.title,
        message_count=len(messages),
        summary=summary,
    )


@router.post(
    "/{conversation_id}/tags",
    summary="Generate topic tags for a conversation",
    response_model=TagsOut,
)
async def tag_conversation(
    conversation_id: int,
    session: DbSession,
    request: Request,
) -> TagsOut:
    """Use the LLM to produce topic tags and persist them on the conversation."""
    from app.brain.orchestrator import ChatOrchestrator
    from app.brain.tagger import generate_tags

    conv = (await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )).scalar_one_or_none()
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    messages = (await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sequence)
    )).scalars().all()

    transcript = "\n".join(f"{m.role}: {m.content}" for m in messages)
    orchestrator: ChatOrchestrator = get_orchestrator(request)  # type: ignore[assignment]
    tags = await generate_tags(transcript, orchestrator._llm)  # noqa: SLF001

    conv.tags = ", ".join(tags)
    await session.commit()

    return TagsOut(conversation_id=conv.id, tags=tags)
