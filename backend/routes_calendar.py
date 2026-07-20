import logging
import os

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from auth import get_current_user
from database import db
from google_calendar import authorization_url, exchange_code, get_userinfo
from utils import now_iso

router = APIRouter(tags=['calendar'])
logger = logging.getLogger(__name__)

APP_BASE_URL = os.environ['APP_BASE_URL']


@router.get('/oauth/google/login')
async def google_login(user: dict = Depends(get_current_user)):
    return {'authorization_url': authorization_url(state=user['id'])}


@router.get('/oauth/calendar/callback')
async def google_callback(code: str = None, state: str = None, error: str = None):
    if error or not code or not state:
        logger.error(f'Google calendar callback missing code/state, error={error}')
        return RedirectResponse(f'{APP_BASE_URL}/interviews?calendar=error')
    try:
        tokens = exchange_code(code)
        info = get_userinfo(tokens['access_token'])
    except Exception:
        logger.exception('Google calendar token exchange failed')
        return RedirectResponse(f'{APP_BASE_URL}/interviews?calendar=error')
    await db.users.update_one({'id': state}, {'$set': {
        'google_tokens': tokens,
        'google_calendar_email': info.get('email'),
        'google_calendar_connected_at': now_iso(),
    }})
    return RedirectResponse(f'{APP_BASE_URL}/interviews?calendar=connected')


@router.get('/calendar/status')
async def calendar_status(user: dict = Depends(get_current_user)):
    u = await db.users.find_one({'id': user['id']}, {'_id': 0})
    connected = bool(u and u.get('google_tokens'))
    scopes = ((u.get('google_tokens') or {}).get('scope') or '').split(' ') if connected else []
    return {
        'connected': connected,
        'email': u.get('google_calendar_email') if connected else None,
        'scopes': [s for s in scopes if s],
        'can_read_inbox': 'https://www.googleapis.com/auth/gmail.readonly' in scopes,
        'can_send_email': 'https://www.googleapis.com/auth/gmail.send' in scopes,
    }


@router.post('/calendar/disconnect')
async def calendar_disconnect(user: dict = Depends(get_current_user)):
    await db.users.update_one({'id': user['id']}, {'$unset': {
        'google_tokens': '', 'google_calendar_email': '', 'google_calendar_connected_at': '',
    }})
    return {'ok': True}
