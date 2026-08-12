"""Per-tenant AI provider configuration.

Instead of a single global XAI_API_KEY in backend/.env, every workspace (tenant)
can be assigned its OWN provider + model + API key from the platform control panel.
All six providers are reached through the OpenAI-compatible SDK (AsyncOpenAI) by
swapping the base_url — so one code path serves Grok, Claude, OpenAI, DeepSeek,
Gemini and Kimi.

Keys are stored in the GLOBAL `tenant_ai_settings` collection (never tenant-scoped,
never exposed through tenant-facing endpoints). They are stored as-is (the platform
owner explicitly accepted this) and only ever returned masked.
"""
import logging
from typing import Optional, Tuple

from openai import AsyncOpenAI

from database import raw_db
from tenant_context import get_tenant_id
from utils import now_iso

logger = logging.getLogger(__name__)

COLL = 'tenant_ai_settings'

# provider_id -> metadata. `base_url=None` means the OpenAI SDK default.
# `reasoning_effort` marks providers whose chat.completions accept the
# `reasoning_effort` param (only xAI Grok in the current line-up).
PROVIDERS = {
    'grok': {
        'label': 'xAI Grok',
        'base_url': 'https://api.x.ai/v1',
        'default_model': 'grok-4',
        'reasoning_effort': True,
        'key_hint': 'xai-…',
    },
    'claude': {
        'label': 'Anthropic Claude',
        'base_url': 'https://api.anthropic.com/v1/',
        'default_model': 'claude-sonnet-4-5',
        'reasoning_effort': False,
        'key_hint': 'sk-ant-…',
    },
    'openai': {
        'label': 'OpenAI',
        'base_url': 'https://api.openai.com/v1',
        'default_model': 'gpt-4o',
        'reasoning_effort': False,
        'key_hint': 'sk-…',
    },
    'deepseek': {
        'label': 'DeepSeek',
        'base_url': 'https://api.deepseek.com',
        'default_model': 'deepseek-chat',
        'reasoning_effort': False,
        'key_hint': 'sk-…',
    },
    'gemini': {
        'label': 'Google Gemini',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/',
        'default_model': 'gemini-2.5-flash',
        'reasoning_effort': False,
        'key_hint': 'AIza…',
    },
    'kimi': {
        'label': 'Moonshot Kimi',
        'base_url': 'https://api.moonshot.ai/v1',
        'default_model': 'kimi-k2',
        'reasoning_effort': False,
        'key_hint': 'sk-…',
    },
}


class AIConfigError(Exception):
    """Raised when the current workspace has no usable AI provider configured."""


def build_client(provider: str, api_key: str) -> AsyncOpenAI:
    meta = PROVIDERS[provider]
    kwargs = {'api_key': api_key, 'timeout': 90.0}
    if meta.get('base_url'):
        kwargs['base_url'] = meta['base_url']
    return AsyncOpenAI(**kwargs)


def supports_reasoning_effort(provider: str) -> bool:
    return bool(PROVIDERS.get(provider, {}).get('reasoning_effort'))


def default_model(provider: str) -> Optional[str]:
    return PROVIDERS.get(provider, {}).get('default_model')


def mask_key(k: Optional[str]) -> Optional[str]:
    if not k:
        return None
    k = str(k)
    if len(k) <= 8:
        return '••••'
    return f'{k[:4]}••••{k[-4:]}'


async def get_tenant_ai_settings(tenant_id: str) -> Optional[dict]:
    if not tenant_id:
        return None
    return await raw_db[COLL].find_one({'tenant_id': tenant_id}, {'_id': 0})


async def upsert_tenant_ai_settings(tenant_id: str, provider: str, model: Optional[str],
                                    api_key: Optional[str], updated_by: str) -> dict:
    doc = {
        'tenant_id': tenant_id,
        'provider': provider,
        'model': (model or None),
        'api_key': (api_key or None),
        'updated_by': updated_by,
        'updated_at': now_iso(),
    }
    await raw_db[COLL].update_one({'tenant_id': tenant_id}, {'$set': doc}, upsert=True)
    return doc


async def delete_tenant_ai_settings(tenant_id: str) -> None:
    await raw_db[COLL].delete_one({'tenant_id': tenant_id})


async def public_ai_settings(tenant_id: str) -> dict:
    s = await get_tenant_ai_settings(tenant_id)
    if not s:
        return {'configured': False, 'provider': None, 'model': None, 'key_masked': None}
    provider = s.get('provider')
    return {
        'configured': bool(s.get('api_key')),
        'provider': provider,
        'model': s.get('model') or default_model(provider),
        'key_masked': mask_key(s.get('api_key')),
    }


async def resolve_for_current_tenant() -> Tuple[str, str, str]:
    """Return (provider, model, api_key) for the tenant in the current request
    context. Raises AIConfigError with a human-readable message when unset."""
    tid = get_tenant_id()
    if not tid:
        raise AIConfigError('No workspace context for this AI request.')
    s = await get_tenant_ai_settings(tid)
    if not s or not s.get('api_key'):
        raise AIConfigError(
            'No AI provider is configured for this workspace. Ask the platform '
            'owner to add an API key in the control panel.'
        )
    provider = s.get('provider') or 'grok'
    if provider not in PROVIDERS:
        raise AIConfigError(f'Unknown AI provider "{provider}" configured for this workspace.')
    model = s.get('model') or default_model(provider)
    return provider, model, s['api_key']


def _friendly_error(exc: Exception) -> str:
    status = getattr(exc, 'status_code', None)
    msg = str(exc)
    if status in (401, 403):
        return 'The API key was rejected (401/403). Double-check the key and that it is active.'
    if status == 404:
        return 'Model or endpoint not found (404). Check the model name for this provider.'
    if status == 429:
        return 'Rate limited (429) — the key works but the account is over its quota right now.'
    if 'model' in msg.lower() and 'not' in msg.lower():
        return f'Model error: {msg[:200]}'
    return f'Connection failed: {msg[:200]}'


async def test_connection(provider: str, model: Optional[str], api_key: str) -> Tuple[bool, str]:
    """Live-validate a key with a tiny 'ping' completion."""
    if provider not in PROVIDERS:
        return False, f'Unknown provider "{provider}".'
    if not api_key:
        return False, 'No API key provided.'
    use_model = (model or '').strip() or default_model(provider)
    try:
        client = build_client(provider, api_key)
        kwargs = {
            'model': use_model,
            'messages': [{'role': 'user', 'content': 'ping'}],
            'max_tokens': 8,
        }
        if supports_reasoning_effort(provider):
            kwargs['reasoning_effort'] = 'low'
        await client.chat.completions.create(**kwargs)
        return True, f'Connected to {PROVIDERS[provider]["label"]} using model "{use_model}".'
    except Exception as e:  # noqa: BLE001 — surface any failure to the operator
        logger.warning('AI test_connection failed for provider=%s model=%s: %s', provider, use_model, e)
        return False, _friendly_error(e)
