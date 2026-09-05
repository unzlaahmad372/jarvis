"""Unit tests for Phase 5 — Voice settings endpoint."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_voice_settings_defaults(test_client) -> None:
    resp = await test_client.get("/api/v1/voice/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    assert "auto_speak" in data
    assert isinstance(data["enabled"], bool)
    assert isinstance(data["auto_speak"], bool)


@pytest.mark.asyncio
async def test_voice_settings_enabled_by_default(test_client) -> None:
    resp = await test_client.get("/api/v1/voice/settings")
    assert resp.status_code == 200
    data = resp.json()
    # Default config has enable_voice=True, voice_auto_speak=True
    assert data["enabled"] is True
    assert data["auto_speak"] is True
