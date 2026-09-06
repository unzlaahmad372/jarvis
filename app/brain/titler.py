"""Conversation titler — generate a concise title from the first user message.

Called after the first turn of a new conversation.
Uses a short, cheap LLM prompt so it doesn't block the main response.
"""

from __future__ import annotations

from app.llm.base import LLMProvider

_TITLE_PROMPT = """\
Generate a short, descriptive title (5 words or fewer) for a conversation \
that starts with the following user message. \
Reply with ONLY the title — no quotes, no punctuation at the end, no explanation.

User message: {message}"""


async def generate_title(message: str, llm: LLMProvider) -> str:
    """Return a short LLM-generated title for a conversation.

    Falls back to the first 80 chars of the message if the LLM call fails.
    """
    try:
        prompt = _TITLE_PROMPT.format(message=message[:500])
        response = await llm.complete(prompt, system="You are a helpful assistant.")
        title = response.content.strip().strip('"').strip("'")
        # Clamp to 120 chars in case the model ignores the instruction
        return title[:120] if title else message[:80]
    except Exception:  # noqa: BLE001
        return message[:80]
