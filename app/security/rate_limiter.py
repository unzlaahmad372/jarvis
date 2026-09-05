"""In-process token-bucket rate limiter for Phase 11.

Limits requests per minute per client key (device_id or IP address).
No external dependencies — suitable for single-process local deployment.

For multi-process/distributed deployments a shared store (e.g. Redis) would
be needed, but that is explicitly out of scope for the local-first v0.1 build.
"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from app.core.logging import get_logger

logger = get_logger(__name__)


class TokenBucket:
    """Single token bucket for one client key."""

    def __init__(self, rate_per_minute: int) -> None:
        self._capacity = float(rate_per_minute)
        self._tokens = float(rate_per_minute)
        self._rate = rate_per_minute / 60.0  # tokens per second
        self._last_refill = time.monotonic()

    def consume(self) -> bool:
        """Attempt to consume one token. Returns True if allowed."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


class RateLimiter:
    """Thread-safe per-key rate limiter using token buckets."""

    def __init__(self, rate_per_minute: int = 60) -> None:
        self._rate = rate_per_minute
        self._buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(self._rate)
        )
        self._lock = Lock()

    def is_allowed(self, key: str) -> bool:
        """Return True if the request is within rate limits."""
        with self._lock:
            return self._buckets[key].consume()

    def reset(self, key: str) -> None:
        """Reset the bucket for a key (useful in tests)."""
        with self._lock:
            if key in self._buckets:
                del self._buckets[key]


# Module-level singleton — replaced in tests via dependency injection
_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        from app.core.config import get_settings
        settings = get_settings()
        _limiter = RateLimiter(rate_per_minute=settings.rate_limit_rpm)
    return _limiter


def reset_rate_limiter(limiter: RateLimiter | None = None) -> None:
    """Replace the module-level limiter (for tests)."""
    global _limiter
    _limiter = limiter
