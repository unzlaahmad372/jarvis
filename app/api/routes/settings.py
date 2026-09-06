"""Settings API — read and patch runtime-editable settings.

Patches are persisted to the `settings` DB table (key/value store).
The in-memory pydantic-settings singleton is NOT mutated; the DB values
are the source of truth for runtime overrides and are read back on GET.

GET  /api/v1/settings   — return current settings (DB overrides merged)
POST /api/v1/settings   — patch one or more settings (persisted to DB)
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.config import get_settings
from app.db.models import Setting

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

# Fields that may be patched at runtime (excludes secrets / structural config)
_PATCHABLE = {
    "llm_model", "embedding_model", "max_context_tokens", "max_response_tokens",
    "enable_voice", "voice_auto_speak", "enable_vision", "enable_always_listening",
    "require_confirmation", "conversation_retention_days", "tool_log_retention_days",
    "log_level",
}


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


async def _load_overrides(session: DbSession) -> dict[str, str]:
    rows = (await session.execute(select(Setting))).scalars().all()
    return {r.key: r.value for r in rows if r.value is not None}


def _merge(overrides: dict[str, str]) -> SettingsOut:
    s = get_settings()

    def _get_str(field: str) -> str:
        raw = overrides.get(field)
        return raw if raw is not None else str(getattr(s, field))

    def _get_int(field: str) -> int:
        raw = overrides.get(field)
        return int(raw) if raw is not None else int(getattr(s, field))

    def _get_bool(field: str) -> bool:
        raw = overrides.get(field)
        return raw.lower() == "true" if raw is not None else bool(getattr(s, field))

    return SettingsOut(
        llm_model=_get_str("llm_model"),
        embedding_model=_get_str("embedding_model"),
        ollama_url=s.ollama_url,
        max_context_tokens=_get_int("max_context_tokens"),
        max_response_tokens=_get_int("max_response_tokens"),
        enable_voice=_get_bool("enable_voice"),
        voice_auto_speak=_get_bool("voice_auto_speak"),
        enable_vision=_get_bool("enable_vision"),
        enable_always_listening=_get_bool("enable_always_listening"),
        require_confirmation=_get_bool("require_confirmation"),
        conversation_retention_days=_get_int("conversation_retention_days"),
        tool_log_retention_days=_get_int("tool_log_retention_days"),
        log_level=_get_str("log_level"),
    )


@router.get("", response_model=SettingsOut)
async def get_settings_view(session: DbSession) -> SettingsOut:
    overrides = await _load_overrides(session)
    return _merge(overrides)


@router.post("", response_model=SettingsOut)
async def patch_settings(body: SettingsPatch, session: DbSession) -> SettingsOut:
    """Persist runtime setting overrides to the DB settings table."""
    for field, value in body.model_dump(exclude_none=True).items():
        if field not in _PATCHABLE:
            continue
        row = (await session.execute(
            select(Setting).where(Setting.key == field)
        )).scalar_one_or_none()
        if row is None:
            session.add(Setting(key=field, value=str(value)))
        else:
            row.value = str(value)
    await session.commit()
    overrides = await _load_overrides(session)
    return _merge(overrides)
