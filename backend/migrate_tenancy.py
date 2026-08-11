"""Idempotent multi-tenancy migration, runs on every startup.

1. Ensures the founding tenant ("Context66 Data" / slug `context66`) exists.
2. Backfills `tenant_id` on every tenant-owned document that lacks one.
3. Ensures the platform owner account exists in `platform_admins`.
"""
import logging
import os

from auth import hash_password, verify_password
from database import raw_db
from tenant_context import GLOBAL_COLLECTIONS
from tenants import FOUNDING_NAME, FOUNDING_SLUG, create_tenant_doc, get_tenant_by_slug
from utils import new_id, now_iso

logger = logging.getLogger(__name__)

PLATFORM_OWNER_EMAIL = os.environ.get('PLATFORM_OWNER_EMAIL', 'owner@context66.com')
PLATFORM_OWNER_PASSWORD = os.environ.get('PLATFORM_OWNER_PASSWORD', 'Owner@1234')
PLATFORM_OWNER_NAME = 'Platform Owner'


async def ensure_founding_tenant() -> dict:
    t = await get_tenant_by_slug(FOUNDING_SLUG)
    if t:
        return t
    t = await create_tenant_doc(FOUNDING_NAME, FOUNDING_SLUG, plan='enterprise', created_by='system')
    logger.info('Created founding tenant %s (%s)', t['name'], t['id'])
    return t


async def backfill_tenant_ids(tenant_id: str) -> dict:
    counts = {}
    names = await raw_db.list_collection_names()
    for name in names:
        if name in GLOBAL_COLLECTIONS or name.startswith('system.'):
            continue
        res = await raw_db[name].update_many(
            {'tenant_id': {'$exists': False}},
            {'$set': {'tenant_id': tenant_id}},
        )
        if res.modified_count:
            counts[name] = res.modified_count
    return counts


async def ensure_platform_owner() -> bool:
    """Idempotent + reconciling: creates the platform owner, and if the .env
    email/password changed, rotates the existing single owner in place."""
    email = PLATFORM_OWNER_EMAIL.lower().strip()
    existing = await raw_db.platform_admins.find_one({'email': email})
    if existing:
        if not verify_password(PLATFORM_OWNER_PASSWORD, existing.get('password_hash', '')):
            await raw_db.platform_admins.update_one(
                {'id': existing['id']},
                {'$set': {'password_hash': hash_password(PLATFORM_OWNER_PASSWORD), 'password_updated_at': now_iso()}},
            )
            logger.info('Rotated platform owner password for %s', email)
        return False

    # Email changed in .env — rotate the one existing owner instead of creating a second.
    if await raw_db.platform_admins.count_documents({}) == 1:
        current = await raw_db.platform_admins.find_one({})
        await raw_db.platform_admins.update_one(
            {'id': current['id']},
            {'$set': {
                'email': email,
                'password_hash': hash_password(PLATFORM_OWNER_PASSWORD),
                'password_updated_at': now_iso(),
            }},
        )
        logger.info('Rotated platform owner identity %s -> %s', current.get('email'), email)
        return False

    await raw_db.platform_admins.insert_one({
        'id': new_id(),
        'name': PLATFORM_OWNER_NAME,
        'email': email,
        'password_hash': hash_password(PLATFORM_OWNER_PASSWORD),
        'role': 'platform_owner',
        'active': True,
        'last_login': None,
        'created_at': now_iso(),
    })
    logger.info('Created platform owner %s', email)
    return True


async def run_tenancy_migration() -> dict:
    tenant = await ensure_founding_tenant()
    counts = await backfill_tenant_ids(tenant['id'])
    owner_created = await ensure_platform_owner()
    return {'tenant_id': tenant['id'], 'backfilled': counts, 'owner_created': owner_created}
