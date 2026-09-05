"""Platform (Super Admin) API — lives OUTSIDE every tenant.

The platform owner provisions tenants, suspends them, and can impersonate a
tenant's owner to support them. It never reads tenant business data directly.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from auth import create_token, get_platform_admin, hash_password, verify_password
from database import raw_db
from ai_settings import (
    PROVIDERS,
    delete_tenant_ai_settings,
    get_tenant_ai_settings,
    public_ai_settings,
    test_connection,
    upsert_tenant_ai_settings,
)
from google_oauth_settings import (
    delete_tenant_google_settings,
    get_tenant_google_settings,
    public_google_settings,
    upsert_tenant_google_settings,
)
from tenant_context import GLOBAL_COLLECTIONS
from tenant_provision import provision_tenant_defaults
from tenants import (
    RESERVED_SLUGS,
    STATUS_ACTIVE,
    STATUS_SUSPENDED,
    create_tenant_doc,
    get_tenant,
    get_tenant_by_slug,
    public_tenant,
    slugify_tenant,
)
from utils import now_iso

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/platform', tags=['platform'])

COUNTED = ('users', 'candidates', 'jobs', 'interviews', 'offers')


class PlatformLogin(BaseModel):
    email: EmailStr
    password: str


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    slug: Optional[str] = None
    plan: str = 'free'
    admin_name: str = Field(min_length=2, max_length=60)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    plan: Optional[str] = None


class OwnerPasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class TenantAISettings(BaseModel):
    provider: str
    model: Optional[str] = None
    # Empty / omitted api_key on PUT means "keep the key already on file".
    api_key: Optional[str] = None


class TenantAITest(BaseModel):
    provider: str
    model: Optional[str] = None
    api_key: Optional[str] = None


class TenantGoogleSettings(BaseModel):
    client_id: str = Field(min_length=1)
    # Empty / omitted client_secret on PUT means "keep the secret already on file".
    client_secret: Optional[str] = None


@router.post('/login')
async def platform_login(body: PlatformLogin):
    admin = await raw_db.platform_admins.find_one({'email': body.email.lower()})
    if not admin or not verify_password(body.password, admin.get('password_hash', '')):
        raise HTTPException(status_code=401, detail='Invalid email or password')
    if not admin.get('active', True):
        raise HTTPException(status_code=403, detail='Account deactivated')
    await raw_db.platform_admins.update_one({'id': admin['id']}, {'$set': {'last_login': now_iso()}})
    token = create_token(admin['id'], tenant_id=None, kind='platform')
    safe = {k: v for k, v in admin.items() if k not in ('_id', 'password_hash')}
    return {'token': token, 'admin': safe}


@router.get('/me')
async def platform_me(admin: dict = Depends(get_platform_admin)):
    return admin


@router.post('/change-password')
async def change_owner_password(body: OwnerPasswordChange, admin: dict = Depends(get_platform_admin)):
    """Lets the platform owner rotate their own password from the control panel.
    Marks the account self-managed so the .env-based startup reconciler stops
    overwriting it on the next boot."""
    from routes_auth import _validate_password_strength

    current = await raw_db.platform_admins.find_one({'id': admin['id']})
    if not current or not verify_password(body.current_password, current.get('password_hash', '')):
        raise HTTPException(status_code=400, detail='Current password is incorrect')
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail='New password must be different from the current one')
    _validate_password_strength(body.new_password)
    await raw_db.platform_admins.update_one(
        {'id': admin['id']},
        {'$set': {
            'password_hash': hash_password(body.new_password),
            'password_updated_at': now_iso(),
            'self_managed': True,
        }},
    )
    logger.warning('Platform owner %s changed their own password', current['email'])
    return {'ok': True, 'message': 'Password updated. Use it the next time you sign in.'}


async def _tenant_row(t: dict) -> dict:
    row = public_tenant(t)
    counts = {}
    for coll in COUNTED:
        counts[coll] = await raw_db[coll].count_documents({'tenant_id': t['id']})
    row['counts'] = counts
    row['created_at'] = t.get('created_at')
    row['ai'] = await public_ai_settings(t['id'])
    row['google'] = await public_google_settings(t['id'])
    return row


@router.get('/tenants')
async def list_tenants(admin: dict = Depends(get_platform_admin)):
    tenants = await raw_db.tenants.find({}, {'_id': 0}).sort('created_at', 1).to_list(500)
    return [await _tenant_row(t) for t in tenants]


@router.get('/stats')
async def platform_stats(admin: dict = Depends(get_platform_admin)):
    total = await raw_db.tenants.count_documents({})
    active = await raw_db.tenants.count_documents({'status': STATUS_ACTIVE})
    return {
        'tenants': total,
        'active_tenants': active,
        'suspended_tenants': total - active,
        'users': await raw_db.users.count_documents({}),
        'candidates': await raw_db.candidates.count_documents({}),
        'jobs': await raw_db.jobs.count_documents({}),
    }


@router.post('/tenants')
async def create_tenant(body: TenantCreate, admin: dict = Depends(get_platform_admin)):
    slug = slugify_tenant(body.slug or body.name)
    if len(slug) < 2:
        raise HTTPException(status_code=422, detail='Slug must be at least 2 characters (letters/numbers)')
    if slug in RESERVED_SLUGS:
        raise HTTPException(status_code=422, detail=f'"{slug}" is a reserved URL. Please choose another slug.')
    if await get_tenant_by_slug(slug):
        raise HTTPException(status_code=409, detail=f'A workspace with the slug "{slug}" already exists')
    tenant = await create_tenant_doc(body.name.strip(), slug, plan=body.plan, created_by=admin['id'])
    owner = await provision_tenant_defaults(tenant['id'], body.admin_name.strip(), body.admin_email, body.admin_password)
    logger.info('Provisioned tenant %s (%s) with owner %s', tenant['name'], slug, owner['email'])
    return {'tenant': public_tenant(tenant), 'owner': owner, 'login_url': f'/{slug}/login'}


@router.patch('/tenants/{tenant_id}')
async def update_tenant(tenant_id: str, body: TenantUpdate, admin: dict = Depends(get_platform_admin)):
    t = await get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail='Tenant not found')
    updates = {}
    if body.name:
        updates['name'] = body.name.strip()
    if body.plan:
        updates['plan'] = body.plan
    if body.status:
        if body.status not in (STATUS_ACTIVE, STATUS_SUSPENDED):
            raise HTTPException(status_code=422, detail='status must be active or suspended')
        updates['status'] = body.status
    if not updates:
        return public_tenant(t)
    updates['updated_at'] = now_iso()
    await raw_db.tenants.update_one({'id': tenant_id}, {'$set': updates})
    return public_tenant(await get_tenant(tenant_id))


@router.delete('/tenants/{tenant_id}')
async def delete_tenant(tenant_id: str, admin: dict = Depends(get_platform_admin)):
    """Permanently deletes the tenant and every row it owns."""
    t = await get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail='Tenant not found')
    deleted = {}
    for name in await raw_db.list_collection_names():
        if name in GLOBAL_COLLECTIONS or name.startswith('system.'):
            continue
        res = await raw_db[name].delete_many({'tenant_id': tenant_id})
        if res.deleted_count:
            deleted[name] = res.deleted_count
    await raw_db.tenants.delete_one({'id': tenant_id})
    logger.warning('Platform owner %s deleted tenant %s: %s', admin['email'], t['slug'], deleted)
    return {'ok': True, 'deleted': deleted}


@router.post('/tenants/{tenant_id}/impersonate')
async def impersonate_tenant(tenant_id: str, admin: dict = Depends(get_platform_admin)):
    """Issues a normal tenant token for that workspace's owner, so support can
    see exactly what the customer sees."""
    t = await get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail='Tenant not found')
    owner = await raw_db.users.find_one(
        {'tenant_id': tenant_id, 'role': {'$in': ['super_admin', 'admin']}, 'active': True},
        {'_id': 0, 'password_hash': 0},
        sort=[('created_at', 1)],
    )
    if not owner:
        raise HTTPException(status_code=404, detail='This workspace has no active admin to impersonate')
    token = create_token(owner['id'], tenant_id=tenant_id, kind='user')
    logger.warning('Platform owner %s impersonating %s in tenant %s', admin['email'], owner['email'], t['slug'])
    return {'token': token, 'user': owner, 'tenant': public_tenant(t)}


# ----------------------------------------------------------------------------
# Per-tenant AI provider configuration (control-panel only)
# ----------------------------------------------------------------------------
@router.get('/ai/providers')
async def ai_providers(admin: dict = Depends(get_platform_admin)):
    """The provider catalog for the control-panel dropdown."""
    return [
        {'id': pid, 'label': meta['label'], 'default_model': meta['default_model'], 'key_hint': meta.get('key_hint')}
        for pid, meta in PROVIDERS.items()
    ]


@router.get('/tenants/{tenant_id}/ai')
async def get_tenant_ai(tenant_id: str, admin: dict = Depends(get_platform_admin)):
    t = await get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail='Tenant not found')
    return await public_ai_settings(tenant_id)


@router.put('/tenants/{tenant_id}/ai')
async def set_tenant_ai(tenant_id: str, body: TenantAISettings, admin: dict = Depends(get_platform_admin)):
    t = await get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail='Tenant not found')
    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=422, detail=f'Unknown provider "{body.provider}"')
    existing = await get_tenant_ai_settings(tenant_id)
    key = (body.api_key or '').strip()
    if not key:
        # No new key typed — keep whatever is already on file (lets the owner
        # change provider/model without re-pasting the secret).
        key = (existing or {}).get('api_key')
    model = (body.model or '').strip() or None
    await upsert_tenant_ai_settings(tenant_id, body.provider, model, key, admin['email'])
    logger.info('Platform owner %s set AI provider=%s for tenant %s', admin['email'], body.provider, t['slug'])
    return await public_ai_settings(tenant_id)


@router.delete('/tenants/{tenant_id}/ai')
async def clear_tenant_ai(tenant_id: str, admin: dict = Depends(get_platform_admin)):
    t = await get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail='Tenant not found')
    await delete_tenant_ai_settings(tenant_id)
    logger.info('Platform owner %s cleared AI config for tenant %s', admin['email'], t['slug'])
    return {'ok': True}


@router.post('/tenants/{tenant_id}/ai/test')
async def test_tenant_ai(tenant_id: str, body: TenantAITest, admin: dict = Depends(get_platform_admin)):
    t = await get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail='Tenant not found')
    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=422, detail=f'Unknown provider "{body.provider}"')
    key = (body.api_key or '').strip()
    if not key:
        key = (await get_tenant_ai_settings(tenant_id) or {}).get('api_key')
    if not key:
        return {'ok': False, 'message': 'No API key to test — enter one first.'}
    ok, message = await test_connection(body.provider, (body.model or '').strip() or None, key)
    return {'ok': ok, 'message': message}


# ----------------------------------------------------------------------------
# Per-tenant Google OAuth (Calendar + Gmail) client (control-panel only)
# ----------------------------------------------------------------------------
@router.get('/tenants/{tenant_id}/google')
async def get_tenant_google(tenant_id: str, admin: dict = Depends(get_platform_admin)):
    t = await get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail='Tenant not found')
    return await public_google_settings(tenant_id)


@router.put('/tenants/{tenant_id}/google')
async def set_tenant_google(tenant_id: str, body: TenantGoogleSettings, admin: dict = Depends(get_platform_admin)):
    t = await get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail='Tenant not found')
    existing = await get_tenant_google_settings(tenant_id)
    secret = (body.client_secret or '').strip()
    if not secret and existing and existing.get('client_secret_encrypted'):
        # No new secret typed — keep the encrypted one already on file by
        # passing a sentinel through upsert would double-encrypt it, so
        # short-circuit and only patch client_id instead.
        from crypto_utils import decrypt_str
        secret = decrypt_str(existing['client_secret_encrypted'])
    await upsert_tenant_google_settings(tenant_id, body.client_id.strip(), secret, admin['email'])
    logger.info('Platform owner %s set Google OAuth client for tenant %s', admin['email'], t['slug'])
    return await public_google_settings(tenant_id)


@router.delete('/tenants/{tenant_id}/google')
async def clear_tenant_google(tenant_id: str, admin: dict = Depends(get_platform_admin)):
    t = await get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail='Tenant not found')
    await delete_tenant_google_settings(tenant_id)
    logger.info('Platform owner %s cleared Google OAuth client for tenant %s', admin['email'], t['slug'])
    return {'ok': True}
