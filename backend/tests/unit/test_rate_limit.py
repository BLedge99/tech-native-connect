import pytest

from app.errors import TooManyRequests
from app.services.rate_limit import SlidingWindowRateLimiter


def test_sliding_window_limit_expires_and_returns_retry_after():
    now = [100.0]
    limiter = SlidingWindowRateLimiter(clock=lambda: now[0])

    limiter.check("login", "user@example.com", limit=2, window_seconds=60)
    now[0] += 10
    limiter.check("login", "user@example.com", limit=2, window_seconds=60)

    with pytest.raises(TooManyRequests) as error:
        limiter.check("login", "user@example.com", limit=2, window_seconds=60)

    assert error.value.retry_after == 50

    now[0] += 50
    limiter.check("login", "user@example.com", limit=2, window_seconds=60)


def test_rate_limit_buckets_are_scoped_by_endpoint_and_identity():
    limiter = SlidingWindowRateLimiter(clock=lambda: 0)

    limiter.check("login", "user@example.com", limit=1, window_seconds=60)
    limiter.check("magic-link", "user@example.com", limit=1, window_seconds=60)
    limiter.check("login", "other@example.com", limit=1, window_seconds=60)


def test_rate_limiter_bounds_distinct_identity_storage():
    now = [0.0]
    limiter = SlidingWindowRateLimiter(clock=lambda: now[0])
    limiter.MAX_TRACKED_KEYS = 2
    limiter.check("login", "first@example.com", limit=1, window_seconds=60)
    limiter.check("login", "second@example.com", limit=1, window_seconds=60)

    with pytest.raises(TooManyRequests):
        limiter.check("login", "third@example.com", limit=1, window_seconds=60)

    now[0] = 60
    limiter.check("login", "third@example.com", limit=1, window_seconds=60)
