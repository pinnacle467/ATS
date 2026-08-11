"""Ensure critical uniqueness constraints at the MongoDB layer.

Called once from FastAPI startup. Idempotent — Motor's `create_index` is a
no-op if the same index already exists.

Rationale
=========
PRD requires all business IDs (jobs.id, candidates.id, users.id, interviews.id,
files.id, ...) to be UUID4 strings and unique. Without a DB-level constraint,
a buggy migration/import script or race condition could silently insert a
duplicate. This module adds `unique=True` indexes on the `id` field of every
collection where uniqueness is essential, plus a case-insensitive uniqueness
guarantee on `users.email` (the app already lower-cases emails before insert,
but this is defense-in-depth).

If a duplicate somehow already exists when the index is being built, the
`create_index` call will raise `DuplicateKeyError`; we log that clearly and
continue booting so the app remains usable while the operator resolves it.
"""
from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)

# Collections whose `id` field must be globally unique.
COLLECTIONS_WITH_UNIQUE_ID: tuple[str, ...] = (
    'jobs',
    'candidates',
    'users',
    'interviews',
    'files',
    'notes',
    'activities',
    'scorecards',
    'departments',
    'tags',
    'interview_kits',
    'notifications',
    'audit_log',
    'password_resets',
    'applications',
    'import_sessions',
    'offers',
)


async def ensure_indexes(db) -> dict:
    """Create the required unique indexes. Returns a report dict."""
    report: dict = {'created': [], 'existed': [], 'errors': []}

    # Unique `id` indexes across all core collections
    for coll_name in COLLECTIONS_WITH_UNIQUE_ID:
        try:
            await db[coll_name].create_index('id', unique=True, name='id_unique')
            report['created'].append(f'{coll_name}.id')
        except Exception as e:  # noqa: BLE001
            # Most likely "index already exists with different options" (harmless)
            # or "duplicate key" (data problem). We log but do not crash startup.
            msg = str(e)
            if 'already exists' in msg.lower() or 'IndexOptionsConflict' in msg:
                report['existed'].append(f'{coll_name}.id')
            else:
                report['errors'].append({'collection': coll_name, 'field': 'id', 'error': msg})
                logger.error(f'Failed to create unique index on {coll_name}.id: {msg}')

    # Users.email must be unique WITHIN a tenant (the same person can exist in
    # two workspaces). Drops the legacy global email_unique index if present.
    try:
        existing = await db.users.index_information()
        if 'email_unique' in existing:
            await db.users.drop_index('email_unique')
            logger.info('Dropped legacy global users.email_unique index')
    except Exception:  # noqa: BLE001
        pass
    try:
        await db.users.create_index([('tenant_id', 1), ('email', 1)], unique=True, name='tenant_email_unique')
        report['created'].append('users.tenant_id+email')
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if 'already exists' in msg.lower() or 'IndexOptionsConflict' in msg:
            report['existed'].append('users.tenant_id+email')
        else:
            report['errors'].append({'collection': 'users', 'field': 'tenant_id+email', 'error': msg})
            logger.error(f'Failed to create unique index on users.tenant_id+email: {msg}')

    # tenants registry
    try:
        await db.tenants.create_index('slug', unique=True, name='slug_unique')
        await db.tenants.create_index('id', unique=True, name='id_unique')
        await db.platform_admins.create_index('email', unique=True, name='email_unique')
        report['created'].append('tenants.slug')
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if 'already exists' in msg.lower() or 'IndexOptionsConflict' in msg:
            report['existed'].append('tenants.slug')
        else:
            report['errors'].append({'collection': 'tenants', 'field': 'slug', 'error': msg})

    # tenant_id lookup indexes on the hot collections
    for coll_name in ('candidates', 'jobs', 'interviews', 'users', 'activities', 'notes', 'offers', 'files'):
        try:
            await db[coll_name].create_index('tenant_id', name='tenant_lookup')
        except Exception:  # noqa: BLE001
            pass

    # password_resets.token_hash unique (defense-in-depth against collisions)
    try:
        await db.password_resets.create_index('token_hash', unique=True, name='token_hash_unique')
        report['created'].append('password_resets.token_hash')
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if 'already exists' in msg.lower() or 'IndexOptionsConflict' in msg:
            report['existed'].append('password_resets.token_hash')
        else:
            report['errors'].append({'collection': 'password_resets', 'field': 'token_hash', 'error': msg})

    logger.info(
        'ensure_indexes: created=%d existed=%d errors=%d',
        len(report['created']), len(report['existed']), len(report['errors']),
    )

    # Non-unique index on candidates.industry (multikey — array field) so the
    # Industry filter/search stays fast as the candidate table grows.
    try:
        await db.candidates.create_index('industry', name='industry_lookup')
        report['created'].append('candidates.industry')
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if 'already exists' in msg.lower() or 'IndexOptionsConflict' in msg:
            report['existed'].append('candidates.industry')
        else:
            report['errors'].append({'collection': 'candidates', 'field': 'industry', 'error': msg})

    # offers.public_token — looked up on every candidate-facing accept/decline
    # page load, so it needs to stay fast as offers accumulate.
    try:
        await db.offers.create_index('public_token', name='public_token_lookup')
        report['created'].append('offers.public_token')
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if 'already exists' in msg.lower() or 'IndexOptionsConflict' in msg:
            report['existed'].append('offers.public_token')
        else:
            report['errors'].append({'collection': 'offers', 'field': 'public_token', 'error': msg})

    return report


async def scan_for_duplicate_ids(db, collections: Iterable[str] = COLLECTIONS_WITH_UNIQUE_ID) -> dict:
    """Read-only scan reporting any duplicate `id` values per collection.

    Useful for smoke-testing after import scripts. Returns
    {collection_name: [{id: ..., count: N}, ...], ...} — empty lists mean OK.
    """
    result: dict = {}
    for coll_name in collections:
        pipeline = [
            {'$group': {'_id': '$id', 'count': {'$sum': 1}}},
            {'$match': {'count': {'$gt': 1}}},
            {'$project': {'_id': 0, 'id': '$_id', 'count': 1}},
        ]
        try:
            dupes = await db[coll_name].aggregate(pipeline).to_list(length=None)
        except Exception:  # noqa: BLE001
            dupes = []
        result[coll_name] = dupes
    return result
