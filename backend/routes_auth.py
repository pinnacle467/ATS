from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from auth import create_token, get_current_user, verify_password
from database import db
from utils import log_audit, now_iso

router = APIRouter(prefix='/auth', tags=['auth'])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post('/login')
async def login(body: LoginRequest):
    user = await db.users.find_one({'email': body.email.lower()})
    if not user or not verify_password(body.password, user.get('password_hash', '')):
        raise HTTPException(status_code=401, detail='Invalid email or password')
    if not user.get('active', True):
        raise HTTPException(status_code=403, detail='Account deactivated. Contact your admin.')
    await db.users.update_one({'id': user['id']}, {'$set': {'last_login': now_iso()}})
    await log_audit({'id': user['id'], 'name': user['name']}, 'login', 'user', user['id'], f"{user['email']} logged in")
    token = create_token(user['id'])
    safe = {k: v for k, v in user.items() if k not in ('_id', 'password_hash')}
    return {'token': token, 'user': safe}


@router.get('/me')
async def me(user: dict = Depends(get_current_user)):
    return user
