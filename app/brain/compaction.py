"""Conversation compaction — summarises older turns to free context budget.

When a conversation's recent history exceeds the configured token budget,
the oldest unsummarised messages are compacted into a ConversationSummary.
The original messages are retained; only the context window is trimmed.
"""

from __future__ import annotations

from app.brain.context_builder import ContextSlot, estimate_tokens
from app.core.logging import get_logger
from app.db.models import Conversation, ConversationSummary, Message

logger = get_logger(__name__)

COMPACTION_PROMPT_VERSION = "1.0"


def _messages_to_text(messages: list[Message]) -> str:
    """Render messages as a plain transcript for summarisation."""
    lines = []
    for m in messages:
        role = m.role.upper()
        lines.append(f"{role}: {m.content}")
    return "\n\n".join(lines)


def select_messages_to_compact(
    messages: list[Message],
    history_token_budget: int,
    keep_recent: int = 4,
) -> list[Message]:
    """Return the oldest messages that should be compacted.

    Strategy:
    - Always keep the most recent `keep_recent` messages verbatim.
    - Of the remaining older messages, compact those that push the total
      over `history_token_budget`.

    Returns an empty list if no compaction is needed.
    """
    if len(messages) <= keep_recent:
        return []

    candidates = messages[:-keep_recent]  # oldest messages
    recent = messages[-keep_recent:]

    recent_tokens = sum(estimate_tokens(m.content) for m in recent)
    candidate_tokens = sum(estimate_tokens(m.content) for m in candidates)

    if recent_tokens + candidate_tokens <= history_token_budget:
        return []  # fits within budget — no compaction needed

    # Compact all candidates (simplest safe strategy)
    return candidates


def build_history_slots(
    messages: list[Message],
    summaries: list[ConversationSummary],
    history_token_budget: int,
) -> list[ContextSlot]:
    """Build ContextSlots for conversation history.

    Summaries are included at priority 7 (older), recent messages at priority 6.
    """
    slots: list[ContextSlot] = []

    # Find the highest sequence covered by any summary
    max_summarised_seq = max((s.to_sequence for s in summaries), default=-1)

    # Include the most recent summary if present
    if summaries:
        latest_summary = max(summaries, key=lambda s: s.to_sequence)
        slots.append(
            ContextSlot(
                name="conversation_summary",
                content=f"[Earlier conversation summary]\n{latest_summary.summary}",
                priority=7,
            )
        )

    # Include recent messages not covered by any summary
    recent_messages = [m for m in messages if m.sequence > max_summarised_seq]
    if recent_messages:
        history_text = _messages_to_text(recent_messages)
        slots.append(
            ContextSlot(
                name="conversation_history",
                content=f"[Recent conversation]\n{history_text}",
                priority=6,
            )
        )

    return slots


async def compact_conversation(
    conversation: Conversation,
    messages_to_compact: list[Message],
    llm_provider: object,  # LLMProvider — avoid circular import
) -> ConversationSummary:
    """Summarise a list of messages using the LLM and return a new summary object.

    The caller is responsible for persisting the returned summary.
    """
    from app.llm.base import LLMProvider

    provider: LLMProvider = llm_provider  # type: ignore[assignment]

    transcript = _messages_to_text(messages_to_compact)
    prompt = (
        "Summarise the following conversation excerpt concisely. "
        "Focus on: key decisions, important facts, named entities, and unresolved questions. "
        "Be factual and brief.\n\n"
        f"{transcript}"
    )

    system = (
        "You are a conversation summariser. "
        "Produce a concise factual summary. "
        "Do not add information not present in the transcript."
    )

    try:
        response = await provider.complete(prompt, system=system)
        summary_text = response.content
        model_used = response.model
    except Exception:
        logger.exception("compaction_failed", conversation_id=conversation.id)
        # Fallback: use a simple concatenation rather than failing the whole request
        summary_text = f"[Compaction failed — {len(messages_to_compact)} messages omitted]"
        model_used = None

    from_seq = min(m.sequence for m in messages_to_compact)
    to_seq = max(m.sequence for m in messages_to_compact)

    summary = ConversationSummary(
        conversation_id=conversation.id,
        summary=summary_text,
        from_sequence=from_seq,
        to_sequence=to_seq,
        summarizer_model=model_used,
        prompt_version=COMPACTION_PROMPT_VERSION,
        token_count=estimate_tokens(summary_text),
    )

    logger.info(
        "conversation_compacted",
        conversation_id=conversation.id,
        messages_compacted=len(messages_to_compact),
        from_seq=from_seq,
        to_seq=to_seq,
    )

    return summary
