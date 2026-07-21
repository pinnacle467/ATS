import logging
import os
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from auth import get_current_user
from database import db
from google_calendar import authorization_url, exchange_code, get_credentials_for_user, get_userinfo, list_events
from utils import clean, log_activity, new_id, notify, now_iso

router = APIRouter(tags=['calendar'])
logger = logging.getLogger(__name__)

APP_BASE_URL = os.environ['APP_BASE_URL']

# Heuristics used by /calendar/sync-interviews to guess a sensible interview
# `type` from an event summary. Order matters — first match wins.
_TYPE_KEYWORDS = [
    ('phone_screen', re.compile(r'\b(phone\s*screen|phone[- ]interview|screening\s*call|recruiter\s*screen)\b', re.I)),
    ('technical',    re.compile(r'\b(technical|coding|system\s*design|tech\s*interview|live\s*coding|pairing)\b', re.I)),
    ('onsite',       re.compile(r'\b(on[- ]?site|final\s*round|super\s*day|loop)\b', re.I)),
    ('panel',        re.compile(r'\b(panel|group\s*interview)\b', re.I)),
]


def _guess_interview_type(summary: str) -> str:
    s = summary or ''
    for label, pattern in _TYPE_KEYWORDS:
        if pattern.search(s):
            return label
    return 'phone_screen'  # sane default for an ambiguous "Interview with X"


@router.get('/oauth/google/login')
async def google_login(return_to: str = '/interviews', user: dict = Depends(get_current_user)):
    # Encode the return path into state so the callback can redirect the user
    # back to wherever they clicked Connect from (e.g. /my-integrations).
    # Whitelist to same-origin paths only.
    if not isinstance(return_to, str) or not return_to.startswith('/') or return_to.startswith('//'):
        return_to = '/interviews'
    state = f"{user['id']}|{return_to}"
    return {'authorization_url': authorization_url(state=state)}


@router.get('/oauth/calendar/callback')
async def google_callback(code: str = None, state: str = None, error: str = None):
    # Split state back into user_id + return_to (fallback to /interviews)
    user_id = state
    return_to = '/interviews'
    if state and '|' in state:
        try:
            user_id, return_to = state.split('|', 1)
            if not return_to.startswith('/') or return_to.startswith('//'):
                return_to = '/interviews'
        except Exception:
            user_id, return_to = state, '/interviews'
    if error or not code or not user_id:
        logger.error(f'Google calendar callback missing code/state, error={error}')
        return RedirectResponse(f'{APP_BASE_URL}{return_to}?calendar=error')
    try:
        tokens = exchange_code(code)
        info = get_userinfo(tokens['access_token'])
    except Exception:
        logger.exception('Google calendar token exchange failed')
        return RedirectResponse(f'{APP_BASE_URL}{return_to}?calendar=error')
    await db.users.update_one({'id': user_id}, {'$set': {
        'google_tokens': tokens,
        'google_calendar_email': info.get('email'),
        'google_calendar_connected_at': now_iso(),
    }})
    return RedirectResponse(f'{APP_BASE_URL}{return_to}?calendar=connected')


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


@router.get('/calendar/external-events')
async def list_external_events(
    time_min: str,
    time_max: str,
    user: dict = Depends(get_current_user),
):
    """Read-only overlay: return the caller's Google Calendar events within
    the given ISO window (`time_min` / `time_max`, both required, RFC3339 e.g.
    `2026-07-21T00:00:00Z`) so the frontend can render them next to real ATS
    interviews on the week/day grid.

    - Events that have already been imported as ATS interviews (matched by
      `google_event_id` on interviews) are stripped out — the ATS row is the
      canonical one for those.
    - All-day events, cancelled events, and events with no attendees other
      than the caller are still returned (a solo focus block is still useful
      "busy" context) but flagged so the frontend can style them differently.
    - Response is compact: no attendee PII beyond a count.
    - If the user has not connected Google Calendar this returns
      {"connected": false, "events": []} instead of a 400 — so the frontend
      can call this unconditionally on load without needing to check
      `/calendar/status` first.
    """
    user_doc = await db.users.find_one({'id': user['id']})
    if not user_doc:
        raise HTTPException(status_code=404, detail='User not found')
    from google_calendar import get_credentials_for_user  # local import — cheap and keeps top-of-file tidy
    creds = await get_credentials_for_user(user_doc)
    if not creds:
        return {'connected': False, 'events': []}

    # Basic sanity: reject wildly-wrong ranges. A month view is 42 days max.
    try:
        _tmin = datetime.fromisoformat(time_min.replace('Z', '+00:00'))
        _tmax = datetime.fromisoformat(time_max.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=422, detail='time_min and time_max must be ISO-8601')
    if _tmax <= _tmin:
        raise HTTPException(status_code=422, detail='time_max must be after time_min')
    if (_tmax - _tmin).days > 62:
        raise HTTPException(status_code=422, detail='Requested window is too large (max 62 days)')

    try:
        events = list_events(creds, time_min_iso=time_min, time_max_iso=time_max, max_results=500)
    except Exception as exc:
        logger.exception('external-events: list_events failed')
        exc_text = str(exc).lower()
        if 'invalid_client' in exc_text or 'invalid_grant' in exc_text or 'refresherror' in exc_text:
            raise HTTPException(status_code=400, detail='Google Calendar authorization expired — please reconnect.')
        raise HTTPException(status_code=400, detail='Could not read your Google Calendar.')

    # Which google_event_ids are already ATS interviews? Filter them out so the
    # calendar grid doesn't show the same event twice (once as blue interview
    # pill, once as grey external pill).
    ats_event_ids: set[str] = set()
    async for iv in db.interviews.find({'google_event_id': {'$exists': True, '$ne': None}}, {'_id': 0, 'google_event_id': 1}):
        gid = iv.get('google_event_id')
        if gid:
            ats_event_ids.add(gid)

    out: list[dict] = []
    my_email = (user_doc.get('email') or '').strip().lower()
    calendar_email = (user_doc.get('google_calendar_email') or '').strip().lower()
    for ev in events:
        if ev.get('status') == 'cancelled':
            continue
        eid = ev.get('id')
        if eid and eid in ats_event_ids:
            continue

        start_obj = ev.get('start') or {}
        end_obj = ev.get('end') or {}
        all_day = bool(start_obj.get('date') and not start_obj.get('dateTime'))
        start_iso = start_obj.get('dateTime') or start_obj.get('date')
        end_iso = end_obj.get('dateTime') or end_obj.get('date')
        if not start_iso or not end_iso:
            continue

        attendees = ev.get('attendees') or []
        # Filter out the caller themselves and resource rooms (email endswith .resource.calendar.google.com)
        real_attendees = [a for a in attendees
                          if not a.get('resource')
                          and (a.get('email') or '').strip().lower() not in {my_email, calendar_email, ''}]

        # Video link resolution mirrors the sync-interviews logic.
        video_link = ev.get('hangoutLink') or ''
        if not video_link:
            for ep in (ev.get('conferenceData', {}).get('entryPoints') or []):
                if ep.get('entryPointType') == 'video' and ep.get('uri'):
                    video_link = ep['uri']
                    break

        # "Am I the only person here?" — used by the frontend to style solo
        # focus blocks / self-reminders more subtly than real multi-person meetings.
        is_solo = len(real_attendees) == 0

        out.append({
            'id': eid,
            'summary': ev.get('summary') or '(no title)',
            'start': start_iso,
            'end': end_iso,
            'all_day': all_day,
            'timezone': start_obj.get('timeZone'),
            'html_link': ev.get('htmlLink'),
            'location': ev.get('location') or None,
            'video_link': video_link or None,
            'attendee_count': len(real_attendees),
            'is_solo': is_solo,
            'organizer_email': (ev.get('organizer') or {}).get('email'),
            'is_organizer': bool((ev.get('organizer') or {}).get('self')),
            'status_response': next((a.get('responseStatus') for a in attendees if a.get('self')), None),
        })

    return {
        'connected': True,
        'calendar_email': user_doc.get('google_calendar_email'),
        'events': out,
        'range': {'from': time_min, 'to': time_max},
    }


@router.post('/calendar/sync-interviews')
async def sync_interviews_from_calendar(
    days_back: int = 14,
    days_forward: int = 30,
    user: dict = Depends(get_current_user),
):
    """Pull real events from the caller's connected Google Calendar and create
    ATS interview records for any event whose attendees include a known
    candidate email. Idempotent — events already imported (matched by
    `google_event_id`) are skipped.

    Response shape (also mirrored to the UI dialog):
        {
          "imported": [ {id, candidate_name, summary, scheduled_at} … ],
          "skipped_duplicate": N,
          "skipped_no_candidate_match": N,
          "skipped_ats_created": N,     # events the ATS itself created
          "scanned": N,
          "range": {"from": iso, "to": iso}
        }
    """
    # Sanity-clamp so a rogue client can't request 10-year windows.
    days_back = max(0, min(days_back, 180))
    days_forward = max(0, min(days_forward, 180))

    # Refresh the user doc so we have the freshest google_tokens (get_credentials_for_user
    # will refresh the access token if expired).
    user_doc = await db.users.find_one({'id': user['id']})
    if not user_doc:
        raise HTTPException(status_code=404, detail='User not found')
    creds = await get_credentials_for_user(user_doc)
    if not creds:
        raise HTTPException(status_code=400, detail='Google Calendar is not connected for your account.')

    # Time window (UTC ISO with the required trailing Z that Google wants).
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=days_back)).replace(microsecond=0)
    time_max = (now + timedelta(days=days_forward)).replace(microsecond=0)
    time_min_iso = time_min.isoformat().replace('+00:00', 'Z')
    time_max_iso = time_max.isoformat().replace('+00:00', 'Z')

    try:
        events = list_events(creds, time_min_iso=time_min_iso, time_max_iso=time_max_iso, max_results=500)
    except Exception as exc:
        logger.exception('calendar sync: list_events failed')
        # Return 400 rather than 502 so Cloudflare doesn't swallow the body with
        # its own generic "origin returned an invalid response" page. This is
        # user-actionable — they need to reconnect their Google account.
        msg = 'Could not read your Google Calendar. Try disconnecting and reconnecting.'
        # If the underlying error is an auth/refresh failure, be specific.
        exc_text = str(exc).lower()
        if 'invalid_client' in exc_text or 'invalid_grant' in exc_text or 'refresherror' in exc_text:
            msg = ('Your Google Calendar authorization has expired or was revoked. '
                   'Please Disconnect and then Connect Google Calendar again.')
        raise HTTPException(status_code=400, detail=msg)

    # Pre-load all candidate emails once (lowercased) so the per-event lookup
    # is O(attendees) instead of N Mongo round-trips per event.
    candidates_by_email: dict[str, dict] = {}
    async for cand in db.candidates.find({'email': {'$exists': True, '$ne': None}}, {'_id': 0, 'id': 1, 'name': 1, 'email': 1, 'job_id': 1, 'stage': 1}):
        em = (cand.get('email') or '').strip().lower()
        if em:
            candidates_by_email[em] = cand
    users_by_email: dict[str, dict] = {}
    async for u in db.users.find({}, {'_id': 0, 'id': 1, 'name': 1, 'email': 1, 'active': 1}):
        em = (u.get('email') or '').strip().lower()
        if em:
            users_by_email[em] = u

    # Events the ATS *itself* created were already logged as interviews; use the
    # stored google_event_id set to filter them out fast.
    existing_event_ids = set()
    async for iv in db.interviews.find({'google_event_id': {'$exists': True, '$ne': None}}, {'_id': 0, 'google_event_id': 1, 'created_by': 1}):
        gid = iv.get('google_event_id')
        if gid:
            existing_event_ids.add(gid)

    imported = []
    skipped_duplicate = 0
    skipped_no_match = 0
    skipped_ats_created = 0

    for ev in events:
        if ev.get('status') == 'cancelled':
            continue
        # ATS-created events have this key we set ourselves in create_event's
        # requestId; but our dedup by google_event_id catches those too. Kept
        # as a defensive branch for events created by *older* code.
        req_id = (ev.get('conferenceData', {}).get('createRequest') or {}).get('requestId', '')
        looks_ats = isinstance(req_id, str) and req_id.startswith('ats-')

        event_id = ev.get('id')
        if event_id and event_id in existing_event_ids:
            if looks_ats:
                skipped_ats_created += 1
            else:
                skipped_duplicate += 1
            continue

        # Skip all-day events (no dateTime, only date) — interviews are timed.
        start_obj = ev.get('start') or {}
        end_obj = ev.get('end') or {}
        start_iso = start_obj.get('dateTime')
        end_iso = end_obj.get('dateTime')
        if not start_iso or not end_iso:
            continue

        # Resolve attendees against our candidate index.
        attendees = ev.get('attendees') or []
        attendee_emails = [(a.get('email') or '').strip().lower() for a in attendees]
        # Also include the event organizer / creator as a candidate for matching,
        # in case the invite was set up so the candidate is the organizer.
        org_email = ((ev.get('organizer') or {}).get('email') or '').strip().lower()
        creator_email = ((ev.get('creator') or {}).get('email') or '').strip().lower()
        candidate_email_candidates = [e for e in attendee_emails + [org_email, creator_email] if e]

        matched_candidate = None
        matched_email = None
        for em in candidate_email_candidates:
            if em in candidates_by_email:
                matched_candidate = candidates_by_email[em]
                matched_email = em
                break

        if not matched_candidate:
            skipped_no_match += 1
            continue

        # Interviewer IDs = attendees whose email is a known user (excluding
        # the matched candidate). Deduplicate & preserve order.
        interviewer_ids: list[str] = []
        seen_iids = set()
        for em in attendee_emails:
            if not em or em == matched_email:
                continue
            u = users_by_email.get(em)
            if u and u.get('id') and u['id'] not in seen_iids:
                interviewer_ids.append(u['id'])
                seen_iids.add(u['id'])
        # If no known-user attendee was found, at least assign the connecting
        # user as the interviewer so the interview is visible & assignable.
        if not interviewer_ids:
            interviewer_ids = [user['id']]

        # Duration in minutes (fallback 60).
        try:
            start_dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))
            duration_min = max(15, int((end_dt - start_dt).total_seconds() // 60))
        except Exception:
            duration_min = 60
            start_dt = None

        # Past events → feedback_pending; future events → scheduled.
        is_past = bool(start_dt and start_dt < now)
        status = 'feedback_pending' if is_past else 'scheduled'

        # Video link: prefer hangoutLink, fall back to conferenceData.entryPoints,
        # else scan the description for a common video URL.
        video_link = ev.get('hangoutLink') or ''
        if not video_link:
            for ep in (ev.get('conferenceData', {}).get('entryPoints') or []):
                if ep.get('entryPointType') == 'video' and ep.get('uri'):
                    video_link = ep['uri']
                    break
        if not video_link:
            m = re.search(r'https?://\S*(?:meet\.google|zoom\.us|teams\.microsoft|whereby|webex)\S*', ev.get('description') or '')
            if m:
                video_link = m.group(0)

        summary = ev.get('summary') or f"Interview with {matched_candidate.get('name', 'candidate')}"
        iv_type = _guess_interview_type(summary)

        iv = {
            'id': new_id(),
            'candidate_id': matched_candidate['id'],
            'job_id': matched_candidate.get('job_id'),
            'stage': matched_candidate.get('stage'),
            'type': iv_type,
            'interviewer_ids': interviewer_ids,
            'scheduled_at': start_iso,
            'timezone': (start_obj.get('timeZone') or 'UTC'),
            'duration_min': duration_min,
            'location': ev.get('location') or None,
            'video_link': video_link or None,
            'notes': None,
            'status': status,
            'created_by': user['id'],
            'created_at': now_iso(),
            # Sync-specific fields:
            'google_event_id': event_id,
            'google_event_link': ev.get('htmlLink'),
            'calendar_synced': True,
            'source': 'google_calendar_sync',
            'imported_from_email': user_doc.get('google_calendar_email'),
            'imported_summary': summary,
        }
        await db.interviews.insert_one(iv)
        existing_event_ids.add(event_id)  # so re-appearances in this same run (recurring) are deduped

        await log_activity(
            user, 'interview_imported',
            f"imported '{summary}' from Google Calendar as a {iv_type.replace('_', ' ')} interview with {matched_candidate.get('name', 'candidate')}",
            candidate_id=matched_candidate['id'], job_id=iv.get('job_id'),
        )
        # Notify interviewers other than the syncer so they know it now lives in ATS.
        for iid in interviewer_ids:
            if iid == user['id']:
                continue
            await notify(iid, 'interview', f"Imported from Google Calendar: {iv_type.replace('_', ' ')} interview with {matched_candidate.get('name', 'candidate')}", '/interviews')

        imported.append({
            'id': iv['id'],
            'candidate_id': matched_candidate['id'],
            'candidate_name': matched_candidate.get('name'),
            'summary': summary,
            'scheduled_at': start_iso,
            'type': iv_type,
            'status': status,
        })

    logger.info(
        'calendar sync (user=%s): scanned=%d imported=%d duplicate=%d ats_created=%d no_match=%d',
        user.get('email'), len(events), len(imported), skipped_duplicate, skipped_ats_created, skipped_no_match,
    )

    return clean({
        'imported': imported,
        'skipped_duplicate': skipped_duplicate,
        'skipped_no_candidate_match': skipped_no_match,
        'skipped_ats_created': skipped_ats_created,
        'scanned': len(events),
        'range': {'from': time_min_iso, 'to': time_max_iso},
    })
