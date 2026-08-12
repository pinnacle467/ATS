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
import random
import re
from typing import Optional

from openai import AsyncOpenAI, APIStatusError, RateLimitError

from ai_settings import (  # noqa: F401 — AIConfigError re-exported for callers
    AIConfigError,
    PROVIDERS,
    build_client,
    resolve_for_current_tenant,
    supports_reasoning_effort,
)
from llm_helper import LLM_SEMAPHORE

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BASE_BACKOFF_SEC = 2.0

# Cache one AsyncOpenAI client per (provider, api_key) so we don't rebuild it on
# every call. Keys can change (owner rotates them), so we key by the pair.
_clients: dict = {}


def _client_for(provider: str, api_key: str) -> AsyncOpenAI:
    ck = (provider, api_key)
    client = _clients.get(ck)
    if client is None:
        client = build_client(provider, api_key)
        _clients[ck] = client
    return client


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
    """Send one chat completion to the workspace's configured AI provider and
    return the raw text of the first choice.

    The provider, model and API key are resolved from the CURRENT tenant's
    settings (set in the platform control panel). Retries on rate-limit /
    concurrency / transient 5xx responses with exponential backoff + jitter,
    up to MAX_RETRIES. Non-transient errors bubble up immediately.
    """
    provider, resolved_model, api_key = await resolve_for_current_tenant()
    client = _client_for(provider, api_key)
    use_model = model or resolved_model
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        async with LLM_SEMAPHORE:
            try:
                kwargs = {
                    'model': use_model,
                    'messages': [
                        {'role': 'system', 'content': system},
                        {'role': 'user', 'content': user},
                    ],
                    'max_tokens': max_tokens,
                }
                if supports_reasoning_effort(provider) and reasoning_effort:
                    kwargs['reasoning_effort'] = reasoning_effort
                completion = await client.chat.completions.create(**kwargs)
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
            'AI call (%s/%s) rate-limited/transient (attempt %s/%s), backing off %.1fs: %s',
            provider, use_model, attempt + 1, MAX_RETRIES, wait, last_exc,
        )
        await asyncio.sleep(wait)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError('AI call failed with no exception recorded')


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
