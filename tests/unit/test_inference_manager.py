"""Tests for InferenceManager — concurrency limits and timeout enforcement."""

from __future__ import annotations

import asyncio

import pytest

from app.inference.manager import InferenceManager, InferenceQueueFullError


@pytest.mark.asyncio
async def test_normal_execution():
    mgr = InferenceManager(max_concurrent=2, timeout_seconds=5, max_queue_length=10)

    async def work() -> str:
        return "result"

    result = await mgr.run(work)
    assert result == "result"


@pytest.mark.asyncio
async def test_timeout_raises():
    mgr = InferenceManager(max_concurrent=1, timeout_seconds=1, max_queue_length=5)

    async def slow_work():
        await asyncio.sleep(10)

    with pytest.raises(asyncio.TimeoutError):
        await mgr.run(slow_work)


@pytest.mark.asyncio
async def test_queue_full_raises():
    mgr = InferenceManager(max_concurrent=1, timeout_seconds=30, max_queue_length=0)

    async def work():
        return "ok"

    with pytest.raises(InferenceQueueFullError):
        await mgr.run(work)


@pytest.mark.asyncio
async def test_concurrent_limit_respected():
    """Only max_concurrent tasks should run simultaneously."""
    mgr = InferenceManager(max_concurrent=2, timeout_seconds=10, max_queue_length=10)
    active = 0
    max_active = 0

    async def work():
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        return "done"

    await asyncio.gather(*[mgr.run(work) for _ in range(4)])
    assert max_active <= 2


@pytest.mark.asyncio
async def test_exception_propagates():
    mgr = InferenceManager(max_concurrent=1, timeout_seconds=5, max_queue_length=5)

    async def failing_work():
        raise ValueError("something went wrong")

    with pytest.raises(ValueError, match="something went wrong"):
        await mgr.run(failing_work)


def test_invalid_max_concurrent():
    with pytest.raises(ValueError):
        InferenceManager(max_concurrent=0)
