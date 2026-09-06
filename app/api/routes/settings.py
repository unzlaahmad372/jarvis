"""Settings API — read and patch runtime-editable settings.

GET  /api/v1/settings   — return current editable settings
POST /api/v1/settings   — patch one or more settings (subset of config)
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class SettingsOut(BaseModel):
    llm_model: str
    embedding_model: str
    ollama_url: str
    max_context_tokens: int
    max_response_tokens: int
    enable_voice: bool
    voice_auto_speak: bool
    enable_vision: bool
    enable_always_listening: bool
    require_confirmation: bool
    conversation_retention_days: int
    tool_log_retention_days: int
    log_level: str


class SettingsPatch(BaseModel):
    llm_model: str | None = None
    embedding_model: str | None = None
    max_context_tokens: int | None = None
    max_response_tokens: int | None = None
    enable_voice: bool | None = None
    voice_auto_speak: bool | None = None
    enable_vision: bool | None = None
    enable_always_listening: bool | None = None
    require_confirmation: bool | None = None
    conversation_retention_days: int | None = None
    tool_log_retention_days: int | None = None
    log_level: str | None = None


@router.get("", response_model=SettingsOut)
async def get_settings_view() -> SettingsOut:
    s = get_settings()
    return SettingsOut(
        llm_model=s.llm_model,
        embedding_model=s.embedding_model,
        ollama_url=s.ollama_url,
        max_context_tokens=s.max_context_tokens,
        max_response_tokens=s.max_response_tokens,
        enable_voice=s.enable_voice,
        voice_auto_speak=s.voice_auto_speak,
        enable_vision=s.enable_vision,
        enable_always_listening=s.enable_always_listening,
        require_confirmation=s.require_confirmation,
        conversation_retention_days=s.conversation_retention_days,
        tool_log_retention_days=s.tool_log_retention_days,
        log_level=s.log_level,
    )


@router.post("", response_model=SettingsOut)
async def patch_settings(body: SettingsPatch) -> SettingsOut:
    """Patch runtime settings in-memory (persists until restart).
    For permanent changes, edit .env and restart JARVIS.
    """
    s = get_settings()
    for field, value in body.model_dump(exclude_none=True).items():
        if hasattr(s, field):
            object.__setattr__(s, field, value)
    return await get_settings_view()
