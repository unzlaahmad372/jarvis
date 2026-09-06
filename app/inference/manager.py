"""InferenceManager — protects the host from LLM resource exhaustion.

Enforces:
- maximum concurrent LLM requests (semaphore)
- per-request timeout
- maximum queue depth (reject early rather than silently queue forever)
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any, TypeVar

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class InferenceQueueFullError(Exception):
    """Raised when the inference queue is at capacity."""


class InferenceBusyError(Exception):
    """Raised when the system cannot accept more requests right now."""


class InferenceManager:
    """Bounded concurrency manager for LLM inference calls."""

    def __init__(
        self,
        max_concurrent: int = 2,
        timeout_seconds: int = 120,
        max_queue_length: int = 10,
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timeout = timeout_seconds
        self._max_queue = max_queue_length
        self._queued = 0
        self._max_concurrent = max_concurrent

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    @property
    def timeout_seconds(self) -> int:
        return self._timeout

    async def run(
        self,
        coro_fn: Callable[[], Coroutine[Any, Any, T]],
        *,
        request_id: str = "unknown",
    ) -> T:
        """Execute a coroutine under concurrency and timeout constraints.

        Args:
            coro_fn: Zero-argument async callable that performs the LLM call.
            request_id: Correlation ID for logging.

        Raises:
            InferenceQueueFullError: Queue is at capacity.
            asyncio.TimeoutError: Request exceeded the configured timeout.
        """
        if self._queued >= self._max_queue:
            logger.warning(
                "inference_queue_full",
                queued=self._queued,
                max_queue=self._max_queue,
                request_id=request_id,
            )
            raise InferenceQueueFullError(
                f"JARVIS is currently busy. Please try again shortly. "
                f"(queue={self._queued}/{self._max_queue})"
            )

        self._queued += 1
        logger.debug("inference_queued", queued=self._queued, request_id=request_id)
        acquired = False

        try:
            async with self._semaphore:
                acquired = True
                self._queued -= 1
                logger.debug("inference_started", request_id=request_id)
                result: T = await asyncio.wait_for(coro_fn(), timeout=self._timeout)
                logger.debug("inference_completed", request_id=request_id)
                return result
        except TimeoutError:
            logger.warning(
                "inference_timeout",
                timeout=self._timeout,
                request_id=request_id,
            )
            raise
        except Exception:
            # Only decrement if we never acquired the semaphore (still queued)
            if not acquired and self._queued > 0:
                self._queued -= 1
            raise

    async def stream(
        self,
        gen_fn: Callable[[], AsyncGenerator[str, None]],
        *,
        request_id: str = "unknown",
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from an async generator under concurrency constraints.

        Acquires the semaphore for the full duration of the stream.
        """
        if self._queued >= self._max_queue:
            raise InferenceQueueFullError(
                f"JARVIS is currently busy. (queue={self._queued}/{self._max_queue})"
            )

        self._queued += 1
        try:
            async with self._semaphore:
                self._queued -= 1
                logger.debug("inference_stream_started", request_id=request_id)
                async for token in gen_fn():
                    yield token
                logger.debug("inference_stream_completed", request_id=request_id)
        except Exception:
            if self._queued > 0:
                self._queued -= 1
            raise
