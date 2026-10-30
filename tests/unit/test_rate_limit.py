"""Unit tests for the in-memory sliding-window rate limiter."""

from app.core.rate_limit import RateLimiter, check_rate_limit, rate_limit_manager


class TestRateLimiter:
    def test_allows_up_to_max_then_blocks(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        assert limiter.is_allowed("k") == (True, 0)
        assert limiter.is_allowed("k") == (True, 0)
        assert limiter.is_allowed("k") == (True, 0)
        allowed, retry_after = limiter.is_allowed("k")
        assert allowed is False
        assert retry_after >= 1

    def test_keys_are_independent(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("a")[0] is True
        assert limiter.is_allowed("a")[0] is False
        assert limiter.is_allowed("b")[0] is True

    def test_window_slides_and_frees_capacity(self, monkeypatch):
        import app.core.rate_limit as rl

        now = [1000.0]
        monkeypatch.setattr(rl.time, "monotonic", lambda: now[0])
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("k")[0] is True
        assert limiter.is_allowed("k")[0] is False
        now[0] += 61
        assert limiter.is_allowed("k")[0] is True

    def test_retry_after_is_positive_and_bounded(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.is_allowed("k")
        allowed, retry_after = limiter.is_allowed("k")
        assert allowed is False
        assert 1 <= retry_after <= 61

    def test_max_keys_eviction_bounds_memory(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60, max_keys=3)
        for key in ("a", "b", "c", "d"):
            limiter.is_allowed(key)
        assert len(limiter._windows) == 3
        # least recently used key ("a") was evicted
        assert "a" not in limiter._windows
        assert "d" in limiter._windows

    def test_lru_order_updates_on_access(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60, max_keys=3)
        limiter.is_allowed("a")
        limiter.is_allowed("b")
        limiter.is_allowed("c")
        limiter.is_allowed("a")  # refresh "a"; "b" becomes LRU
        limiter.is_allowed("d")
        assert "a" in limiter._windows
        assert "b" not in limiter._windows

    def test_reset_clears_state(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.is_allowed("k")
        limiter.reset()
        assert len(limiter._windows) == 0
        assert limiter.is_allowed("k")[0] is True


class TestCheckRateLimit:
    def setup_method(self):
        rate_limit_manager.reset()

    def teardown_method(self):
        rate_limit_manager.reset()

    def test_scoped_keys_do_not_collide_across_dimensions(self):
        # ip:x and widget:x with the same limits must not share a bucket
        for _ in range(10):
            assert check_rate_limit("ip:1.2.3.4", 10, 60)[0] is True
        # widget dimension still has its own budget
        assert check_rate_limit("widget:1.2.3.4", 10, 60)[0] is True

    def test_different_limits_use_different_buckets(self):
        for _ in range(10):
            assert check_rate_limit("shared", 10, 60)[0] is True
        # different max/window => different limiter instance
        assert check_rate_limit("shared", 30, 60)[0] is True

    def test_manager_reset(self):
        for _ in range(10):
            check_rate_limit("k", 10, 60)
        assert check_rate_limit("k", 10, 60)[0] is False
        rate_limit_manager.reset()
        assert check_rate_limit("k", 10, 60)[0] is True
