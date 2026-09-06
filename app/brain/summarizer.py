"""On-demand conversation summarizer (Phase 29).

Produces a concise, structured summary of a conversation on request.
Distinct from compaction (which is internal context management) —
this is a user-facing feature that returns a readable summary.
"""

from __future__ import annotations

from app.db.models import Conversation, Message
from app.llm.base import LLMProvider

_SUMMARY_SYSTEM = "You are a helpful assistant that summarizes conversations concisely."

_SUMMARY_PROMPT = """\
Summarize the following conversation in 3-5 sentences. \
Focus on: the main topic, key decisions or conclusions, and any action items. \
Be concise and factual.

CONVERSATION:
{transcript}

SUMMARY:"""

_MAX_TRANSCRIPT_CHARS = 12_000


def _build_transcript(messages: list[Message]) -> str:
    lines = []
    for m in messages:
        role = "User" if m.role == "user" else "JARVIS"
        lines.append(f"{role}: {m.content}")
    transcript = "\n".join(lines)
    if len(transcript) > _MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:_MAX_TRANSCRIPT_CHARS] + "\n[... truncated ...]"
    return transcript


async def summarize_conversation(
    conversation: Conversation,
    messages: list[Message],
    llm: LLMProvider,
) -> str:
    """Return a human-readable summary of the conversation.

    Falls back to a simple message-count description if the LLM call fails.
    """
    if not messages:
        return "Empty conversation."
    try:
        transcript = _build_transcript(messages)
        prompt = _SUMMARY_PROMPT.format(transcript=transcript)
        response = await llm.complete(prompt, system=_SUMMARY_SYSTEM)
        return response.content.strip()
    except Exception:  # noqa: BLE001
        return (
            f"Conversation '{conversation.title or f'#{conversation.id}'}' "
            f"with {len(messages)} messages."
        )
