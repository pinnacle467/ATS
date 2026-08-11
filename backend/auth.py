import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from database import db, raw_db
from tenant_context import set_tenant_id

JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-secret')
JWT_ALGO = 'HS256'
TOKEN_EXPIRE_HOURS = 24 * 7

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_token(user_id: str, tenant_id: str = None, kind: str = 'user') -> str:
    payload = {
        'sub': user_id,
        'tid': tenant_id,
        'kind': kind,
        'exp': datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def _decode(credentials) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated')
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail='Token expired')
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail='Invalid token')


async def get_platform_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Platform (Super Admin) identity — lives outside every tenant."""
    payload = _decode(credentials)
    if payload.get('kind') != 'platform':
        raise HTTPException(status_code=403, detail='Platform access required')
    admin = await raw_db.platform_admins.find_one({'id': payload.get('sub')}, {'_id': 0, 'password_hash': 0})
    if not admin or not admin.get('active', True):
        raise HTTPException(status_code=401, detail='Platform account not found')
    return admin


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    from tenants import STATUS_SUSPENDED, get_tenant

    payload = _decode(credentials)
    if payload.get('kind', 'user') != 'user':
        raise HTTPException(status_code=403, detail='This token cannot access workspace data')
    user_id = payload.get('sub')
    tenant_id = payload.get('tid')
    if not tenant_id:
        raise HTTPException(status_code=401, detail='Token is missing a workspace. Please sign in again.')
    tenant = await get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=401, detail='Workspace no longer exists')
    if tenant.get('status') == STATUS_SUSPENDED:
        raise HTTPException(status_code=403, detail='This workspace has been suspended. Contact support.')
    # Every DB call for the rest of this request is now locked to this tenant.
    set_tenant_id(tenant_id)
    user = await db.users.find_one({'id': user_id}, {'_id': 0, 'password_hash': 0})
    if not user:
        raise HTTPException(status_code=401, detail='User not found')
    if not user.get('active', True):
        raise HTTPException(status_code=403, detail='Account deactivated')
    return user


def require_roles(*roles):
    """Check that user's role satisfies at least one of the required role names.
    Uses the ROLE_ALIASES mapping so legacy role names still work and super_admin
    passes any check that admin or recruiter would pass.
    """
    from permissions import role_satisfies

    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if not role_satisfies(user.get('role', ''), roles):
            raise HTTPException(status_code=403, detail='Insufficient permissions')
        return user
    return checker


async def interviewer_candidate_ids(user_id: str):
    """Candidate ids an interviewer is allowed to see (assigned interviews)."""
    ids = await db.interviews.distinct('candidate_id', {'interviewer_ids': user_id})
    return ids
