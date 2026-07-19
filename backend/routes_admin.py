from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from auth import get_current_user, hash_password, require_roles
from database import db
from permissions import ALL_ROLES, ROLE_ADMIN, ROLE_SUPER_ADMIN, can_manage_role, is_super_admin
from utils import clean, log_audit, new_id, now_iso

router = APIRouter(tags=['admin'])


VALID_ROLES = set(ALL_ROLES) | {'recruiter', 'interviewer'}  # legacy accepted for safety


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str  # super_admin | admin | interview_panel | vendor (legacy: recruiter, interviewer)
    title: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    title: Optional[str] = None
    password: Optional[str] = None


@router.get('/users')
async def list_users(user: dict = Depends(get_current_user)):
    """All roles need the user directory for interviewer selection / display names."""
    users = await db.users.find({}, {'_id': 0, 'password_hash': 0}).to_list(500)
    return users


@router.post('/users')
async def create_user(body: UserCreate, user: dict = Depends(require_roles('admin'))):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f'Invalid role. Must be one of: {", ".join(ALL_ROLES)}')
    # Only super_admin can create another super_admin
    if not can_manage_role(user.get('role', ''), body.role):
        raise HTTPException(status_code=403, detail=f'You do not have permission to create a user with role "{body.role}"')
    existing = await db.users.find_one({'email': body.email.lower()})
    if existing:
        raise HTTPException(status_code=409, detail='A user with this email already exists')
    u = {
        'id': new_id(),
        'name': body.name,
        'email': body.email.lower(),
        'password_hash': hash_password(body.password),
        'role': body.role,
        'title': body.title,
        'active': True,
        'last_login': None,
        'created_at': now_iso(),
    }
    await db.users.insert_one(u)
    await log_audit(user, 'user_created', 'user', u['id'], f"{body.email} as {body.role}")
    return {k: v for k, v in u.items() if k not in ('_id', 'password_hash')}


@router.put('/users/{user_id}')
async def update_user(user_id: str, body: UserUpdate, user: dict = Depends(require_roles('admin'))):
    target = await db.users.find_one({'id': user_id})
    if not target:
        raise HTTPException(status_code=404, detail='User not found')
    # Guard: only super_admin can edit another super_admin (or a user being promoted TO super_admin)
    if not can_manage_role(user.get('role', ''), target.get('role', '')):
        raise HTTPException(status_code=403, detail='You do not have permission to modify this user')
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if 'password' in updates:
        updates['password_hash'] = hash_password(updates.pop('password'))
    if 'role' in updates:
        if updates['role'] not in VALID_ROLES:
            raise HTTPException(status_code=422, detail=f'Invalid role. Must be one of: {", ".join(ALL_ROLES)}')
        if not can_manage_role(user.get('role', ''), updates['role']):
            raise HTTPException(status_code=403, detail=f'You do not have permission to assign role "{updates["role"]}"')
    await db.users.update_one({'id': user_id}, {'$set': updates})
    detail_keys = ', '.join(k for k in updates.keys() if k != 'password_hash')
    if 'role' in updates:
        await log_audit(user, 'role_changed', 'user', user_id, f"{target['email']} -> {updates['role']}")
    if 'active' in updates:
        await log_audit(user, 'user_deactivated' if not updates['active'] else 'user_activated', 'user', user_id, target['email'])
    if detail_keys and 'role' not in updates and 'active' not in updates:
        await log_audit(user, 'user_updated', 'user', user_id, detail_keys)
    return clean(await db.users.find_one({'id': user_id}, {'_id': 0, 'password_hash': 0}))


@router.delete('/users/{user_id}')
async def delete_user(user_id: str, user: dict = Depends(require_roles('admin'))):
    if user_id == user['id']:
        raise HTTPException(status_code=422, detail='You cannot delete your own account')
    target = await db.users.find_one({'id': user_id})
    if not target:
        raise HTTPException(status_code=404, detail='User not found')
    if not can_manage_role(user.get('role', ''), target.get('role', '')):
        raise HTTPException(status_code=403, detail='You do not have permission to delete this user')
    await db.users.delete_one({'id': user_id})
    await log_audit(user, 'user_deleted', 'user', user_id, target.get('email', ''))
    return {'ok': True}


# ---- Pipeline stage settings ----

class StageDef(BaseModel):
    name: str
    scorecard_attributes: list[str] = []


class PipelineUpdate(BaseModel):
    stages: list[StageDef]


@router.get('/settings/pipeline')
async def get_pipeline(user: dict = Depends(get_current_user)):
    doc = await db.settings.find_one({'key': 'pipeline_stages'}, {'_id': 0})
    if not doc:
        return {'key': 'pipeline_stages', 'stages': []}
    return doc


@router.put('/settings/pipeline')
async def update_pipeline(body: PipelineUpdate, user: dict = Depends(require_roles('admin'))):
    stages = [s.model_dump() for s in body.stages]
    await db.settings.update_one({'key': 'pipeline_stages'}, {'$set': {'stages': stages}}, upsert=True)
    await log_audit(user, 'pipeline_updated', 'settings', 'pipeline_stages', ' -> '.join(s['name'] for s in stages))
    return {'key': 'pipeline_stages', 'stages': stages}


# ---- Departments & tags ----

class NameBody(BaseModel):
    name: str


@router.get('/departments')
async def list_departments(user: dict = Depends(get_current_user)):
    return clean(await db.departments.find({}, {'_id': 0}).sort('name', 1).to_list(100))


@router.post('/departments')
async def create_department(body: NameBody, user: dict = Depends(require_roles('admin'))):
    d = {'id': new_id(), 'name': body.name, 'created_at': now_iso()}
    await db.departments.insert_one(d)
    await log_audit(user, 'department_created', 'department', d['id'], body.name)
    return clean(d)


@router.delete('/departments/{dep_id}')
async def delete_department(dep_id: str, user: dict = Depends(require_roles('admin'))):
    d = await db.departments.find_one({'id': dep_id})
    await db.departments.delete_one({'id': dep_id})
    await log_audit(user, 'department_deleted', 'department', dep_id, d.get('name', '') if d else '')
    return {'ok': True}


@router.get('/tags')
async def list_tags(user: dict = Depends(get_current_user)):
    return clean(await db.tags.find({}, {'_id': 0}).sort('name', 1).to_list(200))


@router.post('/tags')
async def create_tag(body: NameBody, user: dict = Depends(require_roles('admin', 'recruiter'))):
    existing = await db.tags.find_one({'name': body.name})
    if existing:
        return clean(existing)
    t = {'id': new_id(), 'name': body.name, 'created_at': now_iso()}
    await db.tags.insert_one(t)
    return clean(t)


@router.delete('/tags/{tag_id}')
async def delete_tag(tag_id: str, user: dict = Depends(require_roles('admin'))):
    await db.tags.delete_one({'id': tag_id})
    return {'ok': True}


# ---- Audit log ----

@router.get('/audit-log')
async def audit_log(action: Optional[str] = None, limit: int = 100, user: dict = Depends(require_roles('admin'))):
    q = {}
    if action:
        q['action'] = action
    return clean(await db.audit_log.find(q, {'_id': 0}).sort('created_at', -1).to_list(min(limit, 500)))
