import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from auth import create_token, get_current_user, hash_password, verify_password
from database import db
from email_sender import build_reset_password_email, send_email
from tenant_context import set_tenant_id
from tenants import STATUS_SUSPENDED, get_tenant_by_slug, public_tenant
from utils import log_audit, now_iso

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/auth', tags=['auth'])

# ---- Constants ----------------------------------------------------------
RESET_TOKEN_TTL_MINUTES = 60
FORGOT_RATE_LIMIT_PER_HOUR = 5  # per email
MIN_PASSWORD_LEN = 8


# ---- Helpers ------------------------------------------------------------
def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _validate_password_strength(pw: str) -> None:
    if not pw or len(pw) < MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400, detail=f'Password must be at least {MIN_PASSWORD_LEN} characters')
    if pw.lower() == pw or pw.upper() == pw:
        raise HTTPException(status_code=400, detail='Password must contain both upper and lower case letters')
    if not any(c.isdigit() for c in pw):
        raise HTTPException(status_code=400, detail='Password must contain at least one number')


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---- Models -------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ---- Endpoints ----------------------------------------------------------
@router.post('/login')
async def login(body: LoginRequest, request: Request):
    slug = (body.tenant_slug or request.headers.get('X-Tenant-Slug') or '').strip().lower()
    if not slug:
        raise HTTPException(status_code=400, detail='Workspace is required. Use your workspace sign-in link.')
    tenant = await get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail='Workspace not found')
    if tenant.get('status') == STATUS_SUSPENDED:
        raise HTTPException(status_code=403, detail='This workspace has been suspended. Contact support.')
    set_tenant_id(tenant['id'])

    user = await db.users.find_one({'email': body.email.lower()})
    if not user or not verify_password(body.password, user.get('password_hash', '')):
        raise HTTPException(status_code=401, detail='Invalid email or password')
    if not user.get('active', True):
        raise HTTPException(status_code=403, detail='Account deactivated. Contact your admin.')
    await db.users.update_one({'id': user['id']}, {'$set': {'last_login': now_iso()}})
    await log_audit({'id': user['id'], 'name': user['name']}, 'login', 'user', user['id'], f"{user['email']} logged in")
    token = create_token(user['id'], tenant_id=tenant['id'], kind='user')
    safe = {k: v for k, v in user.items() if k not in ('_id', 'password_hash')}
    return {'token': token, 'user': safe, 'tenant': public_tenant(tenant)}


@router.get('/me')
async def me(user: dict = Depends(get_current_user)):
    return user


@router.post('/forgot-password')
async def forgot_password(body: ForgotPasswordRequest, request: Request):
    """Generate a password-reset token and email it to the user.

    Always returns success to prevent user enumeration. Rate-limited per email.
    Requires a workspace (X-Tenant-Slug) since emails are unique per tenant.
    """
    email = body.email.lower().strip()
    generic_ok = {'ok': True, 'message': 'If an account exists for that email, a reset link has been sent.'}

    slug = (request.headers.get('X-Tenant-Slug') or '').strip().lower()
    tenant = await get_tenant_by_slug(slug) if slug else None
    if not tenant:
        raise HTTPException(status_code=400, detail='Workspace is required. Open your workspace sign-in page first.')
    set_tenant_id(tenant['id'])

    # Rate limit: max N attempts per email per hour
    since = _now_utc() - timedelta(hours=1)
    recent = await db.password_resets.count_documents({
        'email': email,
        'created_at': {'$gte': since.isoformat()},
    })
    if recent >= FORGOT_RATE_LIMIT_PER_HOUR:
        logger.warning(f'[forgot-password] rate limit hit for {email}')
        return generic_ok

    user = await db.users.find_one({'email': email})
    if not user or not user.get('active', True):
        # Do not reveal — still return success
        logger.info(f'[forgot-password] no active user for {email}')
        return generic_ok

    # Generate token (32 bytes → 43-char urlsafe string). Store only the SHA-256 hash.
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now_dt = _now_utc()
    expires_at = now_dt + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

    ip = request.client.host if request.client else ''
    reset_doc = {
        'id': secrets.token_hex(12),
        'user_id': user['id'],
        'tenant_id': tenant['id'],
        'email': email,
        'token_hash': token_hash,
        'created_at': now_dt.isoformat(),
        'expires_at': expires_at.isoformat(),
        'used_at': None,
        'ip': ip,
    }
    await db.password_resets.insert_one(reset_doc)

    # Invalidate any previous still-valid unused tokens for this user
    await db.password_resets.update_many(
        {
            'user_id': user['id'],
            'used_at': None,
            'token_hash': {'$ne': token_hash},
            'expires_at': {'$gte': now_dt.isoformat()},
        },
        {'$set': {'used_at': now_dt.isoformat(), 'invalidated': True}},
    )

    base_url = os.environ.get('APP_BASE_URL', '').rstrip('/')
    reset_url = f'{base_url}/reset-password?token={raw_token}'

    html, text = build_reset_password_email(user.get('name', ''), reset_url, expires_minutes=RESET_TOKEN_TTL_MINUTES)
    try:
        await send_email(
            to=email,
            subject='Reset your Pinnacle ATS password',
            html=html,
            text=text,
        )
    except Exception as e:
        logger.error(f'[forgot-password] resend failed for {email}: {e}')
        # Do not leak email-delivery failure to the client — still return generic ok.
        # (Optionally: raise 500 in dev to help debug.)
        return generic_ok

    await log_audit(
        {'id': user['id'], 'name': user.get('name', '')},
        'password_reset_requested', 'user', user['id'],
        f'Password reset requested for {email}',
    )
    return generic_ok


@router.post('/reset-password')
async def reset_password(body: ResetPasswordRequest):
    """Consume a reset token and set a new password."""
    _validate_password_strength(body.new_password)
    token_hash = _hash_token(body.token)
    rec = await db.password_resets.find_one({'token_hash': token_hash})
    if not rec:
        raise HTTPException(status_code=400, detail='Invalid or expired reset link')
    if rec.get('used_at'):
        raise HTTPException(status_code=400, detail='This reset link has already been used')
    try:
        exp = datetime.fromisoformat(rec['expires_at'])
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid reset link')
    if exp < _now_utc():
        raise HTTPException(status_code=400, detail='This reset link has expired. Please request a new one.')

    # The reset link carries no workspace, so scope the request from the record.
    set_tenant_id(rec.get('tenant_id'))
    user = await db.users.find_one({'id': rec['user_id']})
    if not user or not user.get('active', True):
        raise HTTPException(status_code=400, detail='Account is not available')

    # Set new password + mark token used
    new_hash = hash_password(body.new_password)
    await db.users.update_one(
        {'id': user['id']},
        {'$set': {'password_hash': new_hash, 'password_updated_at': now_iso()}},
    )
    await db.password_resets.update_one(
        {'id': rec['id']},
        {'$set': {'used_at': _now_utc().isoformat()}},
    )
    # Invalidate any other outstanding tokens for this user
    await db.password_resets.update_many(
        {'user_id': user['id'], 'used_at': None},
        {'$set': {'used_at': _now_utc().isoformat(), 'invalidated': True}},
    )
    await log_audit(
        {'id': user['id'], 'name': user.get('name', '')},
        'password_reset', 'user', user['id'],
        f"Password reset completed for {user.get('email')}",
    )
    return {'ok': True, 'message': 'Password updated. You can now sign in with your new password.'}


@router.get('/reset-password/verify')
async def verify_reset_token(token: str):
    """Lightweight check the reset-password page calls on mount so it can
    show 'invalid / expired' state before the user fills the form."""
    if not token or len(token) < 10:
        raise HTTPException(status_code=400, detail='Invalid link')
    rec = await db.password_resets.find_one({'token_hash': _hash_token(token)}, {'_id': 0})
    if not rec:
        raise HTTPException(status_code=400, detail='Invalid or expired reset link')
    if rec.get('used_at'):
        raise HTTPException(status_code=400, detail='This reset link has already been used')
    try:
        exp = datetime.fromisoformat(rec['expires_at'])
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid reset link')
    if exp < _now_utc():
        raise HTTPException(status_code=400, detail='This reset link has expired. Please request a new one.')
    set_tenant_id(rec.get('tenant_id'))
    user = await db.users.find_one({'id': rec['user_id']}, {'_id': 0, 'email': 1, 'name': 1})
    return {'ok': True, 'email': user.get('email') if user else '', 'name': user.get('name') if user else ''}


@router.post('/change-password')
async def change_password(body: ChangePasswordRequest, current: dict = Depends(get_current_user)):
    """Change password for the currently logged-in user."""
    _validate_password_strength(body.new_password)
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail='New password must be different from current password')
    user = await db.users.find_one({'id': current['id']})
    if not user or not verify_password(body.current_password, user.get('password_hash', '')):
        raise HTTPException(status_code=400, detail='Current password is incorrect')
    new_hash = hash_password(body.new_password)
    await db.users.update_one(
        {'id': user['id']},
        {'$set': {'password_hash': new_hash, 'password_updated_at': now_iso()}},
    )
    # Invalidate all outstanding reset tokens for this user
    await db.password_resets.update_many(
        {'user_id': user['id'], 'used_at': None},
        {'$set': {'used_at': _now_utc().isoformat(), 'invalidated': True}},
    )
    await log_audit(
        {'id': user['id'], 'name': user.get('name', '')},
        'password_changed', 'user', user['id'],
        f"Password changed by user for {user.get('email')}",
    )
    return {'ok': True, 'message': 'Password updated.'}
