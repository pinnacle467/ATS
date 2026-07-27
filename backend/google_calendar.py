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
          'https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/meetings.space.created',
          'https://www.googleapis.com/auth/meetings.space.settings',
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
    # When refreshing, pass ONLY the scopes actually granted with this token
    # (from Google's token response's `scope` field). Passing our updated
    # global SCOPES here would trigger `invalid_scope` if we've added scopes
    # since the user last consented — they need to re-consent via the auth URL
    # to grant the newer scopes.
    granted_scope = tokens.get('scope') or ''
    granted_scopes = [s for s in granted_scope.split(' ') if s] or SCOPES
    creds = Credentials(
        token=tokens.get('access_token'),
        refresh_token=tokens.get('refresh_token'),
        token_uri=TOKEN_URI,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=granted_scopes,
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
                  attendee_emails: list[str], location: str = None, add_meet: bool = True,
                  meet_space: dict | None = None) -> dict:
    """Create a Google Calendar event.

    - If `meet_space` is provided (from google_meet.create_ai_meet_space), attach
      that specific Meet URI as the conferenceData entry — the Meet space
      already has auto Gemini notes + transcription configured.
    - Otherwise if `add_meet` is True, use the classic `createRequest` flow so
      Calendar auto-generates a plain Meet link (no Gemini artifacts).
    """
    body = {
        'summary': summary,
        'description': description,
        'start': {'dateTime': start_iso},
        'end': {'dateTime': end_iso},
        'attendees': [{'email': e} for e in attendee_emails if e],
        # Privacy: don't let attendees see the guest list or invite others.
        # Each attendee only sees themselves + the organizer on their invite.
        'guestsCanSeeOtherGuests': False,
        'guestsCanInviteOthers': False,
        'guestsCanModify': False,
        'visibility': 'private',
    }
    if location:
        body['location'] = location
    use_meet_api_version = 0
    if meet_space and meet_space.get('meeting_uri'):
        body['conferenceData'] = {
            'conferenceSolution': {'key': {'type': 'hangoutsMeet'}},
            'conferenceId': meet_space.get('meeting_code'),
            'entryPoints': [{
                'entryPointType': 'video',
                'uri': meet_space['meeting_uri'],
                'label': 'Google Meet',
            }],
        }
        use_meet_api_version = 1
    elif add_meet:
        body['conferenceData'] = {'createRequest': {'requestId': f'ats-{start_iso}', 'conferenceSolutionKey': {'type': 'hangoutsMeet'}}}
        use_meet_api_version = 1
    return _service(creds).events().insert(
        calendarId='primary', body=body, conferenceDataVersion=use_meet_api_version, sendUpdates='all',
    ).execute()


def update_event(creds: Credentials, event_id: str, **fields) -> dict:
    service = _service(creds)
    event = service.events().get(calendarId='primary', eventId=event_id).execute()
    # Preserve privacy settings on every update (Google Calendar sometimes drops them).
    event['guestsCanSeeOtherGuests'] = False
    event['guestsCanInviteOthers'] = False
    event['guestsCanModify'] = False
    event['visibility'] = 'private'
    if 'start_iso' in fields:
        event['start'] = {'dateTime': fields['start_iso']}
    if 'end_iso' in fields:
        event['end'] = {'dateTime': fields['end_iso']}
    if 'attendee_emails' in fields:
        event['attendees'] = [{'email': e} for e in fields['attendee_emails'] if e]
    if 'location' in fields:
        event['location'] = fields['location']
    if 'description' in fields:
        event['description'] = fields['description']
    if 'summary' in fields:
        event['summary'] = fields['summary']
    return service.events().update(calendarId='primary', eventId=event_id, body=event, sendUpdates='all').execute()


def delete_event(creds: Credentials, event_id: str):
    _service(creds).events().delete(calendarId='primary', eventId=event_id, sendUpdates='all').execute()


def list_events(creds: Credentials, time_min_iso: str, time_max_iso: str,
                calendar_id: str = 'primary', max_results: int = 250) -> list[dict]:
    """List real (non-recurring-master) calendar events between two ISO
    timestamps, ordered by start time. Recurring instances are expanded via
    singleEvents=True so we get one row per real occurrence.

    Used by the "Sync interviews" feature to pull events the user scheduled
    directly in Google Calendar (i.e. outside the ATS) so we can create
    matching Interview records here.
    """
    service = _service(creds)
    events: list[dict] = []
    page_token = None
    # Google caps at 2500 per page; we paginate defensively but stop at max_results.
    while True:
        page_size = min(250, max_results - len(events))
        if page_size <= 0:
            break
        resp = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min_iso,
            timeMax=time_max_iso,
            singleEvents=True,
            orderBy='startTime',
            maxResults=page_size,
            pageToken=page_token,
            showDeleted=False,
        ).execute()
        events.extend(resp.get('items', []))
        page_token = resp.get('nextPageToken')
        if not page_token:
            break
    return events
