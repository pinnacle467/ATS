"""Shared xAI Grok client for all ATS LLM call sites.

The xAI API is OpenAI-compatible — we point the standard OpenAI SDK at
`https://api.x.ai/v1` with `XAI_API_KEY`. The `reasoning_effort` param
(supported values: 'none', 'low', 'medium', 'high') lets each call site
pick how much reasoning the model does before answering.

All four ATS use cases route through `grok_json()` below:
  - Resume parsing            → reasoning_effort='none' (structured extraction)
  - Reply parsing             → reasoning_effort='none' (structured extraction)
  - Fit scoring (admin)       → reasoning_effort='low'  (light reasoning)
  - Fit preview (career)      → reasoning_effort='low'  (light reasoning)

Concurrency is capped by the module-level `LLM_SEMAPHORE` (already used by
`llm_helper.send_with_retry`); we reuse it here to avoid hammering the
xAI account concurrency limit.
"""
import asyncio
import json
import logging
import os
import random
import re
from typing import Optional

from openai import AsyncOpenAI, APIStatusError, RateLimitError

from llm_helper import LLM_SEMAPHORE

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get('GROK_MODEL', 'grok-4.3')
XAI_BASE_URL = 'https://api.x.ai/v1'
MAX_RETRIES = 5
BASE_BACKOFF_SEC = 2.0

# Lazily-built client (avoids reading the env at import time before load_dotenv)
_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get('XAI_API_KEY')
        if not api_key:
            raise RuntimeError('XAI_API_KEY is not set in backend/.env')
        _client = AsyncOpenAI(api_key=api_key, base_url=XAI_BASE_URL, timeout=90.0)
    return _client


def _strip_fences(raw: str) -> str:
    raw = (raw or '').strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
    return raw


async def grok_completion(
    *,
    system: str,
    user: str,
    reasoning_effort: str = 'low',
    model: Optional[str] = None,
    max_tokens: int = 4096,
) -> str:
    """Send one chat completion to Grok and return the raw text of the first choice.

    Retries on rate-limit / concurrency / transient 5xx responses with exponential
    backoff + jitter, up to MAX_RETRIES. Non-transient errors bubble up immediately.
    """
    client = _get_client()
    model = model or DEFAULT_MODEL
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        async with LLM_SEMAPHORE:
            try:
                completion = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {'role': 'system', 'content': system},
                        {'role': 'user', 'content': user},
                    ],
                    reasoning_effort=reasoning_effort,
                    max_tokens=max_tokens,
                )
                return completion.choices[0].message.content or ''
            except (RateLimitError, APIStatusError) as e:
                last_exc = e
                status = getattr(e, 'status_code', None)
                if isinstance(e, APIStatusError) and status is not None and status < 500 and status != 429:
                    raise
            except Exception as e:  # network / timeout — treat as transient
                last_exc = e
        wait = BASE_BACKOFF_SEC * (2 ** attempt) + random.uniform(0, 0.5)
        logger.warning(
            'Grok call rate-limited/transient (attempt %s/%s), backing off %.1fs: %s',
            attempt + 1, MAX_RETRIES, wait, last_exc,
        )
        await asyncio.sleep(wait)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError('Grok call failed with no exception recorded')


async def grok_json(
    *,
    system: str,
    user: str,
    reasoning_effort: str = 'low',
    model: Optional[str] = None,
    max_tokens: int = 4096,
    retry_on_bad_json: bool = True,
) -> dict:
    """Send a chat completion expecting a JSON object back.

    If the first response isn't valid JSON, we optionally do one polite retry
    asking the model to return raw JSON only. Raises `json.JSONDecodeError` if
    parsing fails after the retry.
    """
    raw = await grok_completion(
        system=system, user=user, reasoning_effort=reasoning_effort,
        model=model, max_tokens=max_tokens,
    )
    try:
        return json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        if not retry_on_bad_json:
            raise
        # One retry, appending a stricter instruction
        raw2 = await grok_completion(
            system=system + '\n\nReturn ONLY a valid JSON object. No prose, no code fences.',
            user=user,
            reasoning_effort=reasoning_effort,
            model=model,
            max_tokens=max_tokens,
        )
        return json.loads(_strip_fences(raw2))
