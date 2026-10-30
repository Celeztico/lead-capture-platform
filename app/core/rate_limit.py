"""In-memory sliding-window rate limiter.

Provides per-key rate limiting with a sliding time window. Intended for
single-process deployments; Phase 11 will migrate to Redis-backed
distributed limiting.

Not thread-safe across processes, but sufficient for the internship core
running behind a single Uvicorn worker.
"""

import time
from collections import OrderedDict, deque


class RateLimiter:
    """Sliding-window rate limiter with bounded key storage.

    Args:
        max_requests: Maximum number of requests allowed in the window.
        window_seconds: Window size in seconds.
        max_keys: Maximum distinct keys tracked at once; the least
            recently used key is evicted beyond this bound so memory
            cannot grow without limit under diverse client traffic.
    """

    def __init__(self, max_requests: int, window_seconds: int, max_keys: int = 10_000):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        # key -> deque of request timestamps; LRU order for bounded eviction
        self._windows: OrderedDict[str, deque[float]] = OrderedDict()

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """Check whether a request is allowed for the given key.

        Returns:
            (allowed, retry_after_seconds)
        """
        now = time.monotonic()
        window = self._windows.get(key)
        if window is None:
            window = deque()
            self._windows[key] = window
            if len(self._windows) > self.max_keys:
                self._windows.popitem(last=False)
        else:
            self._windows.move_to_end(key)

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

    def reset(self) -> None:
        """Forget all tracked keys (used by tests)."""
        self._windows.clear()


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

    def reset(self) -> None:
        """Reset every managed limiter (used by tests)."""
        for limiter in self._limiters.values():
            limiter.reset()


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
