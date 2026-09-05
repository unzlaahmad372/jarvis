"""Pydantic schemas for the chat API.

These are the public API contracts — kept separate from ORM models.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ── Requests ──────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """POST /api/v1/chat request body."""

    message: str = Field(..., min_length=1, max_length=32_000)
    conversation_id: int | None = Field(
        default=None,
        description="Continue an existing conversation. Omit to start a new one.",
    )
    stream: bool = Field(
        default=True,
        description="Stream the response via SSE. Set false for a single JSON response.",
    )


# ── Responses ─────────────────────────────────────────────────────────────────


class TokenUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    context_tokens: int | None = None
    context_utilisation_pct: float | None = None


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    sequence: int
    model: str | None = None
    provider: str | None = None
    token_usage: TokenUsage | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: int
    workspace_id: int
    title: str | None = None
    total_input_tokens: int
    total_output_tokens: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


class ChatResponse(BaseModel):
    """Non-streaming chat response."""

    conversation_id: int
    message: MessageOut
    token_usage: TokenUsage
    compacted: bool = False


class CitationOut(BaseModel):
    filename: str
    chunk_index: int
    page: int | None = None
    score: float


class DocumentOut(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    chunk_count: int
    embedding_model: str | None = None
    index_version: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── SSE event payloads ────────────────────────────────────────────────────────


class MemoryOut(BaseModel):
    id: int
    content: str
    category: str
    importance: int
    confidence: float
    source: str | None = None
    data_classification: str
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime | None = None

    model_config = {"from_attributes": True}


class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10_000)
    category: str = Field(default="fact")
    importance: int = Field(default=5, ge=1, le=10)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str | None = None
    data_classification: str = Field(default="PERSONAL")


# ── SSE event payloads ────────────────────────────────────────────────────────


class SSEEvent(BaseModel):
    """Envelope for all SSE events (spec §123.6)."""

    event_id: str
    request_id: str
    sequence: int
    type: str
    timestamp: datetime
    payload: dict[str, object] = {}
