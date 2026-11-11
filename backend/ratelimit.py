"""
Small in-memory rate limiter for authentication and abuse-prone endpoints.

Good enough for a single-process deployment. If you scale to multiple
workers/instances, move the counters to Redis or a shared store.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int, max_keys: int = 5000):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            if len(self._hits) > self.max_keys:
                # Drop empty/expired buckets instead of growing without bound.
                for k in list(self._hits.keys()):
                    bucket = self._hits[k]
                    while bucket and bucket[0] < cutoff:
                        bucket.popleft()
                    if not bucket:
                        del self._hits[k]

            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= self.limit:
                return False

            bucket.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_limiter = SlidingWindowLimiter(limit=10, window_seconds=60)
signup_limiter = SlidingWindowLimiter(limit=5, window_seconds=600)
join_limiter = SlidingWindowLimiter(limit=10, window_seconds=60)
friend_request_limiter = SlidingWindowLimiter(limit=20, window_seconds=600)
password_limiter = SlidingWindowLimiter(limit=5, window_seconds=300)
sos_limiter = SlidingWindowLimiter(limit=10, window_seconds=300)

ALL_LIMITERS = (
    login_limiter,
    signup_limiter,
    join_limiter,
    friend_request_limiter,
    password_limiter,
    sos_limiter,
)


def rate_limit(limiter: SlidingWindowLimiter, scope: str):
    """FastAPI dependency factory: limits by client IP + endpoint scope."""

    async def dependency(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(f"{scope}:{client}"):
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Please wait a while and try again.",
                headers={"Retry-After": str(limiter.window_seconds)},
            )

    return dependency
