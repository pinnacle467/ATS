"""Per-tenant Google OAuth (Calendar + Gmail) client credentials.

Instead of a single global GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET in backend/.env
shared by every workspace, each tenant can register its own Google Cloud OAuth
client from the platform control panel. Falls back to the deployment-wide env
credentials when a tenant hasn't configured its own, so existing setups keep
working unchanged.

Stored in the GLOBAL `tenant_google_settings` collection (never tenant-scoped,
mirrors the tenant_ai_settings pattern in ai_settings.py). The client secret is
encrypted at rest via crypto_utils (Fernet), unlike the AI provider keys.
"""
import os
from typing import Optional, Tuple

from crypto_utils import decrypt_str, encrypt_str
from database import raw_db
from utils import now_iso

COLL = 'tenant_google_settings'

_DEFAULT_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
_DEFAULT_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')


async def get_tenant_google_settings(tenant_id: str) -> Optional[dict]:
    if not tenant_id:
        return None
    return await raw_db[COLL].find_one({'tenant_id': tenant_id}, {'_id': 0})


async def upsert_tenant_google_settings(tenant_id: str, client_id: str, client_secret: Optional[str], updated_by: str) -> dict:
    doc = {
        'tenant_id': tenant_id,
        'client_id': (client_id or '').strip() or None,
        'client_secret_encrypted': encrypt_str(client_secret) if client_secret else None,
        'updated_by': updated_by,
        'updated_at': now_iso(),
    }
    await raw_db[COLL].update_one({'tenant_id': tenant_id}, {'$set': doc}, upsert=True)
    return doc


async def delete_tenant_google_settings(tenant_id: str) -> None:
    await raw_db[COLL].delete_one({'tenant_id': tenant_id})


async def public_google_settings(tenant_id: str) -> dict:
    s = await get_tenant_google_settings(tenant_id)
    if not s or not s.get('client_id'):
        return {'configured': False, 'client_id': None, 'has_secret': False}
    return {
        'configured': bool(s.get('client_id') and s.get('client_secret_encrypted')),
        'client_id': s.get('client_id'),
        'has_secret': bool(s.get('client_secret_encrypted')),
    }


async def resolve_google_credentials(tenant_id: Optional[str]) -> Tuple[str, str]:
    """Returns (client_id, client_secret) for this tenant, falling back to the
    deployment-wide env credentials if the tenant hasn't configured its own."""
    if tenant_id:
        s = await get_tenant_google_settings(tenant_id)
        if s and s.get('client_id') and s.get('client_secret_encrypted'):
            secret = decrypt_str(s['client_secret_encrypted'])
            if secret:
                return s['client_id'], secret
    return _DEFAULT_CLIENT_ID, _DEFAULT_CLIENT_SECRET
