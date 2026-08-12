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

PLATFORM_OWNER_EMAIL = os.environ.get('PLATFORM_OWNER_EMAIL', 'kangabhijeet@gmail.com')
PLATFORM_OWNER_PASSWORD = os.environ.get('PLATFORM_OWNER_PASSWORD', 'Avi@2026')
PLATFORM_OWNER_NAME = 'Abhijeet Kang'


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
    """Idempotent + reconciling: guarantees kangabhijeet@gmail.com (or whatever
    PLATFORM_OWNER_EMAIL/PASSWORD is set to) is the SOLE platform owner.

    - Creates the owner if missing (renaming a lone differently-named owner in
      place so we don't orphan the account).
    - Reconciles the password to the configured value unless the owner set their
      own password from the control panel (self_managed=True).
    - Deletes every other platform admin so there is only ever one owner.
    """
    email = PLATFORM_OWNER_EMAIL.lower().strip()
    created = False
    existing = await raw_db.platform_admins.find_one({'email': email})

    if existing:
        if not existing.get('self_managed'):
            if not verify_password(PLATFORM_OWNER_PASSWORD, existing.get('password_hash', '')):
                await raw_db.platform_admins.update_one(
                    {'id': existing['id']},
                    {'$set': {
                        'password_hash': hash_password(PLATFORM_OWNER_PASSWORD),
                        'password_updated_at': now_iso(),
                        'name': PLATFORM_OWNER_NAME,
                    }},
                )
                logger.info('Rotated platform owner password for %s', email)
    else:
        # Reuse the one existing (differently-named) owner if there is exactly one,
        # otherwise create a fresh account.
        lone = None
        if await raw_db.platform_admins.count_documents({}) == 1:
            lone = await raw_db.platform_admins.find_one({})
        if lone:
            await raw_db.platform_admins.update_one(
                {'id': lone['id']},
                {'$set': {
                    'email': email,
                    'name': PLATFORM_OWNER_NAME,
                    'password_hash': hash_password(PLATFORM_OWNER_PASSWORD),
                    'password_updated_at': now_iso(),
                    'self_managed': False,
                    'active': True,
                }},
            )
            logger.info('Rotated platform owner identity %s -> %s', lone.get('email'), email)
        else:
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
            created = True
            logger.info('Created platform owner %s', email)

    # Enforce a single owner: remove any other platform admins.
    res = await raw_db.platform_admins.delete_many({'email': {'$ne': email}})
    if res.deleted_count:
        logger.warning('Removed %s other platform admin(s); %s is now the sole owner', res.deleted_count, email)
    return created


async def run_tenancy_migration() -> dict:
    tenant = await ensure_founding_tenant()
    counts = await backfill_tenant_ids(tenant['id'])
    owner_created = await ensure_platform_owner()
    return {'tenant_id': tenant['id'], 'backfilled': counts, 'owner_created': owner_created}
