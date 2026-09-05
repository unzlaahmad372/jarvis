"""Conversation management endpoints.

GET /api/v1/conversations          — list all conversations
GET /api/v1/conversations/{id}     — get conversation with messages
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.api.schemas.chat import ConversationDetail, ConversationOut, MessageOut, TokenUsage
from app.db.models import Conversation, Message

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.get("", summary="List conversations")
async def list_conversations(session: DbSession) -> list[ConversationOut]:
    result = await session.execute(
        select(Conversation).order_by(Conversation.updated_at.desc())
    )
    conversations = result.scalars().all()
    return [ConversationOut.model_validate(c) for c in conversations]


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
