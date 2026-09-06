"""Phase 30 — Topic tag generation for conversations."""

from __future__ import annotations

import logging

from app.llm.base import LLMProvider

log = logging.getLogger(__name__)

_PROMPT = """\
Read the conversation below and output 3-5 short topic tags (1-3 words each).
Return ONLY a comma-separated list, no explanations, no numbering.
Example: python, debugging, async

Conversation:
{transcript}

Tags:"""


async def generate_tags(transcript: str, llm: LLMProvider) -> list[str]:
    """Return up to 5 topic tags for the given transcript text."""
    if not transcript.strip():
        return []
    try:
        raw = await llm.complete(_PROMPT.format(transcript=transcript[:8000]))
        tags = [t.strip().lower() for t in raw.content.split(",") if t.strip()]
        return tags[:5]
    except Exception:
        log.exception("tag generation failed")
        return []
