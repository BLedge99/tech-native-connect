"""In-process sliding-window limits for the single-worker application."""

from __future__ import annotations

import hashlib
import math
import time
from collections import deque
from collections.abc import Callable

from app.errors import TooManyRequests


class SlidingWindowRateLimiter:
    MAX_TRACKED_KEYS = 10_000

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._attempts: dict[tuple[str, str], tuple[deque[float], float]] = {}
        self._checks = 0

    def check(
        self,
        scope: str,
        identity: str,
        *,
        limit: int,
        window_seconds: float,
    ) -> None:
        now = self._clock()
        key = (scope, hashlib.sha256(identity.encode("utf-8")).hexdigest())
        if key not in self._attempts and len(self._attempts) >= self.MAX_TRACKED_KEYS:
            self._prune(now)
            if len(self._attempts) >= self.MAX_TRACKED_KEYS:
                retry_after = min(
                    max(1, math.ceil(window - (now - attempts[-1])))
                    for attempts, window in self._attempts.values()
                )
                raise TooManyRequests(retry_after=retry_after)

        attempts, _ = self._attempts.setdefault(key, (deque(), window_seconds))
        cutoff = now - window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

        if len(attempts) >= limit:
            retry_after = max(1, math.ceil(window_seconds - (now - attempts[0])))
            raise TooManyRequests(retry_after=retry_after)

        attempts.append(now)
        self._checks += 1
        if self._checks % 64 == 0:
            self._prune(now)

    def _prune(self, now: float) -> None:
        stale = [
            key
            for key, (attempts, window_seconds) in self._attempts.items()
            if not attempts or now - attempts[-1] >= window_seconds
        ]
        for key in stale:
            del self._attempts[key]


auth_rate_limiter = SlidingWindowRateLimiter()
