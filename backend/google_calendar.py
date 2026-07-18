"""Google Calendar integration: OAuth token exchange/refresh + event CRUD helpers."""
import os

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build

from database import db

CLIENT_ID = os.environ['GOOGLE_CLIENT_ID']
CLIENT_SECRET = os.environ['GOOGLE_CLIENT_SECRET']
REDIRECT_URI = f"{os.environ['APP_BASE_URL']}/api/oauth/calendar/callback"
SCOPES = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/gmail.send',
          'https://www.googleapis.com/auth/userinfo.email', 'openid']
AUTH_URI = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URI = 'https://oauth2.googleapis.com/token'


def authorization_url(state: str) -> str:
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'state': state,
    }
    return AUTH_URI + '?' + '&'.join(f'{k}={requests.utils.quote(v)}' for k, v in params.items())


def exchange_code(code: str) -> dict:
    resp = requests.post(TOKEN_URI, data={
        'code': code,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code',
    })
    resp.raise_for_status()
    return resp.json()


def get_userinfo(access_token: str) -> dict:
    resp = requests.get('https://www.googleapis.com/oauth2/v2/userinfo', headers={'Authorization': f'Bearer {access_token}'})
    resp.raise_for_status()
    return resp.json()


async def get_credentials_for_user(user_doc: dict) -> Credentials | None:
    tokens = user_doc.get('google_tokens')
    if not tokens:
        return None
    creds = Credentials(
        token=tokens.get('access_token'),
        refresh_token=tokens.get('refresh_token'),
        token_uri=TOKEN_URI,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        await db.users.update_one({'id': user_doc['id']}, {'$set': {'google_tokens.access_token': creds.token}})
    return creds


def _service(creds: Credentials):
    return build('calendar', 'v3', credentials=creds, cache_discovery=False)


def free_busy(creds: Credentials, time_min_iso: str, time_max_iso: str, calendar_id: str = 'primary') -> list[dict]:
    body = {'timeMin': time_min_iso, 'timeMax': time_max_iso, 'items': [{'id': calendar_id}]}
    resp = _service(creds).freebusy().query(body=body).execute()
    busy = []
    for cal in resp.get('calendars', {}).values():
        busy.extend(cal.get('busy', []))
    return busy


def create_event(creds: Credentials, summary: str, description: str, start_iso: str, end_iso: str,
                  attendee_emails: list[str], location: str = None, add_meet: bool = True) -> dict:
    body = {
        'summary': summary,
        'description': description,
        'start': {'dateTime': start_iso},
        'end': {'dateTime': end_iso},
        'attendees': [{'email': e} for e in attendee_emails if e],
    }
    if location:
        body['location'] = location
    if add_meet:
        body['conferenceData'] = {'createRequest': {'requestId': f'ats-{start_iso}', 'conferenceSolutionKey': {'type': 'hangoutsMeet'}}}
    return _service(creds).events().insert(
        calendarId='primary', body=body, conferenceDataVersion=1 if add_meet else 0, sendUpdates='all',
    ).execute()


def update_event(creds: Credentials, event_id: str, **fields) -> dict:
    service = _service(creds)
    event = service.events().get(calendarId='primary', eventId=event_id).execute()
    if 'start_iso' in fields:
        event['start'] = {'dateTime': fields['start_iso']}
    if 'end_iso' in fields:
        event['end'] = {'dateTime': fields['end_iso']}
    if 'attendee_emails' in fields:
        event['attendees'] = [{'email': e} for e in fields['attendee_emails'] if e]
    if 'location' in fields:
        event['location'] = fields['location']
    return service.events().update(calendarId='primary', eventId=event_id, body=event, sendUpdates='all').execute()


def delete_event(creds: Credentials, event_id: str):
    _service(creds).events().delete(calendarId='primary', eventId=event_id, sendUpdates='all').execute()
