"""In-memory sliding-window rate limiter for public endpoints.

Not distributed — fine for single-node deploys behind the current supervisor+uvicorn
setup. If we ever scale horizontally, swap for a Redis-backed limiter.
"""
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException, Request

# Per-key sliding window: {key: deque[timestamp]}
_HITS: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # Trust X-Forwarded-For first hop (Kubernetes ingress terminates TLS + adds it).
    xff = request.headers.get('x-forwarded-for')
    if xff:
        return xff.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'


def check_and_record(key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
    """Return (allowed, remaining, retry_after_seconds).

    Uses a deque of timestamps within the sliding window; O(k) per call where k
    is entries in the window (bounded by `limit`, so effectively O(1) for our sizes).
    """
    now = time.time()
    cutoff = now - window_seconds
    q = _HITS[key]
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= limit:
        retry_after = int(q[0] + window_seconds - now) + 1
        return False, 0, max(retry_after, 1)
    q.append(now)
    return True, limit - len(q), 0


def enforce(request: Request, scope: str, limit: int, window_seconds: int, extra_key: Optional[str] = None):
    """Raise HTTPException(429) if the caller has exceeded the limit for `scope`.

    Key format: `{scope}:{ip}[:{extra}]`. `extra_key` can e.g. carry a job_id so
    multiple applies to different jobs from the same IP don't share a bucket.
    """
    if limit <= 0:  # disabled
        return
    ip = _client_ip(request)
    key = f'{scope}:{ip}'
    if extra_key:
        key = f'{key}:{extra_key}'
    ok, _remaining, retry_after = check_and_record(key, limit, window_seconds)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail=f'Too many requests. Try again in {retry_after} seconds.',
            headers={'Retry-After': str(retry_after)},
        )
