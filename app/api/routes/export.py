"""Conversation export endpoints.

GET /api/v1/export/conversations/{id}?format=markdown|json|txt
GET /api/v1/export/conversations?format=json   — export all
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.db.models import Conversation, Message

router = APIRouter(prefix="/api/v1/export", tags=["export"])


def _to_markdown(conv: Conversation, messages: list[Message]) -> str:
    title = conv.title or f"Conversation #{conv.id}"
    lines = [f"# {title}", f"*Exported {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}*", ""]
    for m in messages:
        role = "**You**" if m.role == "user" else "**JARVIS**"
        lines += [f"{role}", m.content, ""]
    return "\n".join(lines)


def _to_txt(conv: Conversation, messages: list[Message]) -> str:
    title = conv.title or f"Conversation #{conv.id}"
    lines = [title, "=" * len(title), ""]
    for m in messages:
        role = "You" if m.role == "user" else "JARVIS"
        lines += [f"[{role}]", m.content, ""]
    return "\n".join(lines)


async def _load(conversation_id: int, session: DbSession) -> tuple[Conversation, list[Message]]:
    conv = (await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    messages = (await session.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.sequence)
    )).scalars().all()
    return conv, list(messages)


@router.get("/conversations/{conversation_id}")
async def export_conversation(
    conversation_id: int,
    session: DbSession,
    fmt: str = Query("markdown", alias="format", pattern="^(markdown|json|txt)$"),
) -> Response:
    conv, messages = await _load(conversation_id, session)

    if fmt == "json":
        data = {
            "id": conv.id, "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "messages": [{"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in messages],
        }
        return Response(content=json.dumps(data, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="conv-{conv.id}.json"'})
    if fmt == "txt":
        return PlainTextResponse(_to_txt(conv, messages),
                                 headers={"Content-Disposition": f'attachment; filename="conv-{conv.id}.txt"'})
    # markdown default
    return PlainTextResponse(_to_markdown(conv, messages),
                             headers={"Content-Disposition": f'attachment; filename="conv-{conv.id}.md"'})


@router.get("/conversations")
async def export_all_conversations(
    session: DbSession,
    fmt: str = Query("json", alias="format", pattern="^(json)$"),
) -> Response:
    convs = (await session.execute(
        select(Conversation).order_by(Conversation.updated_at.desc())
    )).scalars().all()

    result = []
    for conv in convs:
        messages = (await session.execute(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.sequence)
        )).scalars().all()
        result.append({
            "id": conv.id, "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        })

    return Response(content=json.dumps(result, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="jarvis-export.json"'})
