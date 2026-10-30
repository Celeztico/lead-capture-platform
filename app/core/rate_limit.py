"""In-memory sliding-window rate limiter.

Provides per-key rate limiting with a sliding time window. Intended for
single-process deployments; Phase 11 will migrate to Redis-backed
distributed limiting.

Not thread-safe across processes, but sufficient for the internship core
running behind a single Uvicorn worker.
"""

import time
from collections import deque


class RateLimiter:
    """Token-bucket style sliding-window rate limiter.

    Args:
        max_requests: Maximum number of requests allowed in the window.
        window_seconds: Window size in seconds.
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # key -> deque of request timestamps
        self._windows: dict[str, deque[float]] = {}

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """Check whether a request is allowed for the given key.

        Returns:
            (allowed, retry_after_seconds)
        """
        now = time.monotonic()
        window = self._windows.setdefault(key, deque())

        # Remove timestamps outside the window
        cutoff = now - self.window_seconds
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) >= self.max_requests:
            # Calculate retry-after: when the oldest request exits the window
            retry_after = int(window[0] + self.window_seconds - now) + 1
            return False, max(retry_after, 1)

        window.append(now)
        return True, 0


class RateLimitManager:
    """Manages multiple rate limiters for different dimensions."""

    def __init__(self):
        self._limiters: dict[str, RateLimiter] = {}

    def get_or_create(
        self, name: str, max_requests: int, window_seconds: int
    ) -> RateLimiter:
        """Get or create a named rate limiter."""
        key = f"{name}:{max_requests}:{window_seconds}"
        if key not in self._limiters:
            self._limiters[key] = RateLimiter(max_requests, window_seconds)
        return self._limiters[key]


# Global manager instance (single-process deployment)
rate_limit_manager = RateLimitManager()


def check_rate_limit(
    key: str, max_requests: int, window_seconds: int
) -> tuple[bool, int]:
    """Convenience function to check a rate limit.

    Returns:
        (allowed, retry_after_seconds)
    """
    limiter = rate_limit_manager.get_or_create(
        "rate_limit", max_requests, window_seconds
    )
    # Use a scoped key so different limit dimensions don't collide
    scoped_key = f"{max_requests}:{window_seconds}:{key}"
    return limiter.is_allowed(scoped_key)
