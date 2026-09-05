"""Tests for ContextBuilder — token budget and priority enforcement."""

from __future__ import annotations

from app.brain.context_builder import BuiltContext, ContextBuilder, ContextSlot, estimate_tokens


def test_estimate_tokens_non_zero():
    assert estimate_tokens("hello world") > 0


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 1  # minimum 1


def test_effective_budget():
    cb = ContextBuilder(max_context_tokens=8192, max_response_tokens=2048, safety_margin=256)
    assert cb.effective_budget == 8192 - 2048 - 256


def test_build_returns_built_context():
    cb = ContextBuilder(max_context_tokens=8192, max_response_tokens=2048)
    result = cb.build("Hello JARVIS")
    assert isinstance(result, BuiltContext)
    assert result.user_message == "Hello JARVIS"
    assert result.system_prompt != ""


def test_system_prompt_never_truncated():
    """System instructions must survive even when budget is tight."""
    cb = ContextBuilder(max_context_tokens=500, max_response_tokens=100, safety_margin=50)
    # Add a large optional slot that should be dropped
    big_slot = ContextSlot(name="rag_chunk", content="x" * 2000, priority=4)
    result = cb.build("short question", extra_slots=[big_slot])
    # System prompt must be present
    assert result.system_prompt != ""
    # Big slot should be truncated
    assert "rag_chunk" in result.truncated_slots


def test_priority_ordering_drops_lower_priority_first():
    cb = ContextBuilder(max_context_tokens=1000, max_response_tokens=200, safety_margin=50)
    high_priority = ContextSlot(name="tool_result", content="important result", priority=3)
    low_priority = ContextSlot(name="old_history", content="x" * 3000, priority=7)
    result = cb.build("question", extra_slots=[high_priority, low_priority])
    # high priority should be included if it fits; low priority dropped first
    assert "old_history" in result.truncated_slots


def test_utilisation_percentage_calculated():
    cb = ContextBuilder(max_context_tokens=8192, max_response_tokens=2048)
    result = cb.build("test")
    assert 0.0 <= result.utilisation_pct <= 100.0


def test_total_tokens_positive():
    cb = ContextBuilder(max_context_tokens=8192, max_response_tokens=2048)
    result = cb.build("test message")
    assert result.total_tokens > 0


def test_empty_extra_slots():
    cb = ContextBuilder(max_context_tokens=8192, max_response_tokens=2048)
    result = cb.build("test", extra_slots=[])
    assert result.truncated_slots == []


def test_custom_system_prompt():
    cb = ContextBuilder(max_context_tokens=8192, max_response_tokens=2048)
    result = cb.build("test", system_prompt="Custom system instructions.")
    assert result.system_prompt == "Custom system instructions."
