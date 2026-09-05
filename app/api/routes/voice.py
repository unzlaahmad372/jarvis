"""Voice endpoints — GET /api/v1/voice/settings."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas.chat import VoiceSettingsOut
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


@router.get("/settings", response_model=VoiceSettingsOut)
async def get_voice_settings() -> VoiceSettingsOut:
    settings = get_settings()
    return VoiceSettingsOut(
        enabled=settings.enable_voice,
        auto_speak=settings.voice_auto_speak,
    )
