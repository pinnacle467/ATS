"""Shared helper for calling the Emergent LLM (`emergentintegrations`).

The Emergent LLM key enforces a `concurrent_request_limit` (HTTP 429 with
`CONCURRENCY_REQUEST_LIMIT` code) — parallel `asyncio.gather` fan-out of many
resume-parse / fit-score calls will get most of them rejected. This module
provides two things every LLM call site MUST route through:

1. `LLM_SEMAPHORE` — a module-level asyncio semaphore capping concurrent LLM
   calls to `LLM_CONCURRENCY` (1 by default, safe for the free-tier Emergent
   key). Increase after upgrading the key.
2. `send_with_retry(chat, msg)` — awaits under the semaphore and retries with
   exponential backoff on 429 rate-limit / concurrency errors.
"""
import asyncio
import logging
import os
import random

logger = logging.getLogger(__name__)

# Cap parallel LLM calls. The Emergent free-tier key rejects concurrent
# requests with `CONCURRENCY_REQUEST_LIMIT`; keep at 1 unless the plan is
# upgraded.
LLM_CONCURRENCY = int(os.environ.get('LLM_CONCURRENCY', '1'))
LLM_SEMAPHORE = asyncio.Semaphore(LLM_CONCURRENCY)

MAX_RETRIES = 5
BASE_BACKOFF_SEC = 2.0


def _is_rate_limited(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        '429' in msg
        or 'concurrency_request_limit' in msg
        or 'concurrent_request_limit' in msg
        or 'rate_limit' in msg
        or 'ratelimit' in msg
    )


async def send_with_retry(chat, msg):
    """Send an LLM message under the global concurrency semaphore, retrying
    on rate-limit / concurrency errors with exponential backoff + jitter.
    Non-rate-limit errors bubble up immediately."""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        async with LLM_SEMAPHORE:
            try:
                return await chat.send_message(msg)
            except Exception as e:
                last_exc = e
                if not _is_rate_limited(e):
                    raise
                # Fall through to backoff (release the semaphore before sleeping
                # so the retry doesn't hog the slot other callers are waiting on).
        wait = BASE_BACKOFF_SEC * (2 ** attempt) + random.uniform(0, 0.5)
        logger.warning('LLM rate-limited (attempt %s/%s), backing off %.1fs: %s',
                       attempt + 1, MAX_RETRIES, wait, last_exc)
        await asyncio.sleep(wait)
    # Exhausted retries — re-raise the last rate-limit exception.
    raise last_exc  # type: ignore
