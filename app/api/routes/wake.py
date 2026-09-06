"""Wake word detection — WebSocket endpoint + simple energy-based detector.

Architecture:
  - Client connects to WS /api/v1/voice/wake
  - Server streams audio chunks from client
  - When wake phrase detected, server sends {"event": "WAKE_WORD_DETECTED"}
  - Client then activates STT

Detection strategy (Phase 15 v1):
  - Keyword spotting via substring match on Whisper transcription of short chunks
  - No external wake-word engine required
  - Upgrade path: replace _detect() with openWakeWord or Porcupine

Requires: JARVIS_ENABLE_ALWAYS_LISTENING=true
"""

from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

_WAKE_PHRASES = {"hey jarvis", "jarvis", "ok jarvis"}


async def _transcribe_chunk(audio_bytes: bytes, ollama_url: str) -> str:
    """Transcribe a raw audio chunk via Whisper (if available) or return empty."""
    try:
        import httpx

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp = f.name

        async with httpx.AsyncClient(timeout=10) as client:
            with open(tmp, "rb") as audio_file:  # noqa: PTH123
                resp = await client.post(
                    f"{ollama_url}/api/transcribe",
                    files={"file": ("chunk.wav", audio_file, "audio/wav")},
                )
        Path(tmp).unlink(missing_ok=True)
        if resp.status_code == 200:
            text: str = resp.json().get("text", "")
            return text.lower()
    except Exception:  # noqa: BLE001, S110
        logger.debug("wake_transcribe_error")
    return ""


def _detect_wake_word(text: str) -> bool:
    return any(phrase in text for phrase in _WAKE_PHRASES)


@router.websocket("/wake")
async def wake_word_ws(websocket: WebSocket) -> None:
    settings = get_settings()
    if not settings.enable_always_listening:
        await websocket.close(code=4403, reason="Always-listening is disabled")
        return

    await websocket.accept()
    logger.info("wake_word_ws_connected")

    try:
        while websocket.client_state == WebSocketState.CONNECTED:
            raw = await websocket.receive()
            # Accept both binary (raw PCM/WAV) and text (base64-encoded)
            if "bytes" in raw:
                audio_bytes: bytes = raw["bytes"]
            elif "text" in raw:
                msg: dict[str, Any] = json.loads(raw["text"])
                audio_bytes = base64.b64decode(msg.get("audio", ""))
            else:
                continue

            if not audio_bytes:
                continue

            text = await _transcribe_chunk(audio_bytes, settings.ollama_url)
            if _detect_wake_word(text):
                logger.info("wake_word_detected", text=text)
                await websocket.send_json({"event": "WAKE_WORD_DETECTED", "text": text})
            else:
                await websocket.send_json({"event": "LISTENING"})

    except WebSocketDisconnect:
        logger.info("wake_word_ws_disconnected")
    except Exception as exc:  # noqa: BLE001
        logger.error("wake_word_ws_error", error=str(exc))
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011)
