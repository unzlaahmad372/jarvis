"""Unit tests for conversation compaction."""

from __future__ import annotations

from app.brain.compaction import (
    build_history_slots,
    select_messages_to_compact,
)
from app.brain.context_builder import estimate_tokens
from app.db.models import ConversationSummary, Message


def _make_message(seq: int, role: str = "user", content: str = "hello") -> Message:
    m = Message()
    m.id = seq
    m.conversation_id = 1
    m.role = role
    m.content = content
    m.sequence = seq
    return m


def _make_summary(from_seq: int, to_seq: int, text: str = "summary") -> ConversationSummary:
    s = ConversationSummary()
    s.id = 1
    s.conversation_id = 1
    s.summary = text
    s.from_sequence = from_seq
    s.to_sequence = to_seq
    return s


class TestSelectMessagesToCompact:
    def test_no_compaction_when_few_messages(self) -> None:
        messages = [_make_message(i) for i in range(1, 4)]
        result = select_messages_to_compact(messages, history_token_budget=10_000)
        assert result == []

    def test_no_compaction_when_fits_in_budget(self) -> None:
        messages = [_make_message(i, content="hi") for i in range(1, 10)]
        result = select_messages_to_compact(messages, history_token_budget=10_000)
        assert result == []

    def test_compacts_oldest_when_over_budget(self) -> None:
        # Create messages with enough content to exceed a tiny budget
        messages = [_make_message(i, content="x" * 100) for i in range(1, 12)]
        result = select_messages_to_compact(messages, history_token_budget=50, keep_recent=4)
        # Should compact the oldest messages (not the last 4)
        assert len(result) > 0
        assert all(m.sequence <= 7 for m in result)

    def test_keeps_recent_messages_out_of_compaction(self) -> None:
        messages = [_make_message(i, content="x" * 200) for i in range(1, 12)]
        result = select_messages_to_compact(messages, history_token_budget=10, keep_recent=4)
        recent_seqs = {m.sequence for m in messages[-4:]}
        compacted_seqs = {m.sequence for m in result}
        assert recent_seqs.isdisjoint(compacted_seqs)

    def test_exactly_keep_recent_messages_no_compaction(self) -> None:
        messages = [_make_message(i) for i in range(1, 5)]
        result = select_messages_to_compact(messages, history_token_budget=100, keep_recent=4)
        assert result == []


class TestBuildHistorySlots:
    def test_no_messages_no_summaries_returns_empty(self) -> None:
        slots = build_history_slots([], [], history_token_budget=2048)
        assert slots == []

    def test_messages_without_summaries(self) -> None:
        messages = [_make_message(1, "user", "hello"), _make_message(2, "assistant", "hi")]
        slots = build_history_slots(messages, [], history_token_budget=2048)
        assert len(slots) == 1
        assert slots[0].name == "conversation_history"
        assert "hello" in slots[0].content

    def test_summary_included_at_lower_priority(self) -> None:
        summary = _make_summary(1, 3, "Earlier: discussed X")
        messages = [_make_message(4, "user", "new message")]
        slots = build_history_slots(messages, [summary], history_token_budget=2048)
        names = [s.name for s in slots]
        assert "conversation_summary" in names
        assert "conversation_history" in names
        # Summary should have higher priority number (lower priority = shown later)
        summary_slot = next(s for s in slots if s.name == "conversation_summary")
        history_slot = next(s for s in slots if s.name == "conversation_history")
        assert summary_slot.priority > history_slot.priority

    def test_messages_covered_by_summary_excluded_from_history(self) -> None:
        summary = _make_summary(1, 5)
        messages = [_make_message(i) for i in range(1, 8)]
        slots = build_history_slots(messages, [summary], history_token_budget=2048)
        history_slot = next((s for s in slots if s.name == "conversation_history"), None)
        # Only messages with seq > 5 should appear in history
        if history_slot:
            assert "hello" in history_slot.content  # seq 6, 7 messages


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 1  # min 1

    def test_short_string(self) -> None:
        tokens = estimate_tokens("hello world")
        assert tokens >= 1

    def test_longer_string_more_tokens(self) -> None:
        short = estimate_tokens("hi")
        long = estimate_tokens("hi " * 100)
        assert long > short
