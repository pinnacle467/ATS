"""Tenant-facing workspace endpoints: public branding lookup (login page) and
white-label settings for tenant admins."""
import base64
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from typing import Optional

from auth import get_current_user, require_roles
from database import raw_db
from tenants import get_tenant, get_tenant_by_slug, public_tenant
from utils import log_audit, now_iso

router = APIRouter(tags=['tenant'])

HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
MAX_LOGO_BYTES = 400 * 1024


class BrandingUpdate(BaseModel):
    company_name: Optional[str] = Field(default=None, max_length=60)
    accent_color: Optional[str] = None
    tagline: Optional[str] = Field(default=None, max_length=120)


@router.get('/tenants/by-slug/{slug}')
async def tenant_by_slug(slug: str):
    """Unauthenticated — the login page needs the workspace name/logo/colour."""
    t = await get_tenant_by_slug(slug)
    if not t:
        raise HTTPException(status_code=404, detail='Workspace not found')
    return public_tenant(t)


@router.get('/tenant/me')
async def my_tenant(user: dict = Depends(get_current_user)):
    t = await get_tenant(user.get('tenant_id'))
    if not t:
        raise HTTPException(status_code=404, detail='Workspace not found')
    return public_tenant(t)


@router.put('/tenant/branding')
async def update_branding(body: BrandingUpdate, user: dict = Depends(require_roles('admin'))):
    tenant_id = user['tenant_id']
    t = await get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail='Workspace not found')
    updates = {}
    if body.company_name is not None:
        updates['branding.company_name'] = body.company_name.strip()
    if body.tagline is not None:
        updates['branding.tagline'] = body.tagline.strip()
    if body.accent_color is not None:
        if not HEX_RE.match(body.accent_color):
            raise HTTPException(status_code=422, detail='accent_color must be a hex value like #059669')
        updates['branding.accent_color'] = body.accent_color.lower()
    if not updates:
        return public_tenant(t)
    updates['updated_at'] = now_iso()
    await raw_db.tenants.update_one({'id': tenant_id}, {'$set': updates})
    await log_audit(user, 'branding_updated', 'tenant', tenant_id, ', '.join(updates.keys()))
    return public_tenant(await get_tenant(tenant_id))


@router.post('/tenant/logo')
async def upload_logo(file: UploadFile = File(...), user: dict = Depends(require_roles('admin'))):
    data = await file.read()
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=413, detail='Logo must be smaller than 400 KB')
    ctype = file.content_type or 'image/png'
    if not ctype.startswith('image/'):
        raise HTTPException(status_code=422, detail='Please upload an image file')
    data_url = f'data:{ctype};base64,{base64.b64encode(data).decode()}'
    await raw_db.tenants.update_one(
        {'id': user['tenant_id']},
        {'$set': {'branding.logo_url': data_url, 'updated_at': now_iso()}},
    )
    await log_audit(user, 'branding_logo_updated', 'tenant', user['tenant_id'], file.filename or '')
    return public_tenant(await get_tenant(user['tenant_id']))


@router.delete('/tenant/logo')
async def remove_logo(user: dict = Depends(require_roles('admin'))):
    await raw_db.tenants.update_one(
        {'id': user['tenant_id']},
        {'$set': {'branding.logo_url': None, 'updated_at': now_iso()}},
    )
    return public_tenant(await get_tenant(user['tenant_id']))
