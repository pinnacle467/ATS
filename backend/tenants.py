"""Tenant registry helpers. Always uses the RAW db (tenants is a global collection)."""
import re
from typing import Optional

from database import raw_db
from utils import new_id, now_iso

FOUNDING_SLUG = 'context66'
FOUNDING_NAME = 'Context66 Data'
DEFAULT_ACCENT = '#059669'

STATUS_ACTIVE = 'active'
STATUS_SUSPENDED = 'suspended'

RESERVED_SLUGS = {
    'platform', 'api', 'admin', 'login', 'logout', 'app', 'www', 'static',
    'careers', 'career', 'schedule', 'offer', 'reset-password', 'forgot-password',
    'account', 'candidates', 'jobs', 'interviews', 'offers', 'scheduling',
    'my-integrations', 'career-portal',
}


def slugify_tenant(text: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')
    return s[:40]


def public_tenant(t: Optional[dict]) -> Optional[dict]:
    if not t:
        return None
    b = t.get('branding') or {}
    return {
        'id': t['id'],
        'name': t.get('name'),
        'slug': t.get('slug'),
        'status': t.get('status', STATUS_ACTIVE),
        'plan': t.get('plan', 'free'),
        'branding': {
            'company_name': b.get('company_name') or t.get('name'),
            'accent_color': b.get('accent_color') or DEFAULT_ACCENT,
            'logo_url': b.get('logo_url') or None,
            'tagline': b.get('tagline') or '',
        },
    }


async def get_tenant_by_slug(slug: str) -> Optional[dict]:
    if not slug:
        return None
    return await raw_db.tenants.find_one({'slug': slug.lower().strip()}, {'_id': 0})


async def get_tenant(tenant_id: str) -> Optional[dict]:
    if not tenant_id:
        return None
    return await raw_db.tenants.find_one({'id': tenant_id}, {'_id': 0})


async def create_tenant_doc(name: str, slug: str, plan: str = 'free', created_by: str = '') -> dict:
    doc = {
        'id': new_id(),
        'name': name,
        'slug': slug,
        'status': STATUS_ACTIVE,
        'plan': plan,
        'branding': {
            'company_name': name,
            'accent_color': DEFAULT_ACCENT,
            'logo_url': None,
            'tagline': '',
        },
        'created_by': created_by,
        'created_at': now_iso(),
        'updated_at': now_iso(),
    }
    await raw_db.tenants.insert_one(dict(doc))
    return doc
