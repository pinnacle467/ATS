"""Candidate self-scheduling routes.

Recruiter side (auth, admin/recruiter): create a scheduling request, preview
slots, manage the public link. Candidate side (PUBLIC, token-based, no login):
view the request, fetch available slots, book / reschedule / cancel.

Interview records live in the existing `interviews` collection (extended with
scheduling_* fields). Booked self-scheduled interviews behave like any other
interview (they appear on the normal Interviews calendar once scheduled_at is
set). Unbooked requests are hidden from the legacy list.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import get_current_user, require_roles
from database import db
from google_calendar import create_event, delete_event, get_credentials_for_user, update_event
from google.auth.exceptions import GoogleAuthError, RefreshError
from googleapiclient.errors import HttpError
from scheduling_engine import generate_slots, get_scheduling_settings, is_slot_free
from scheduling_emails import human_time, queue_scheduling_email
from utils import clean, log_activity, log_audit, new_id, notify, now_iso

logger = logging.getLogger(__name__)
router = APIRouter(tags=['scheduling'])

ACTIVE_LINK_STATUSES = {'draft', 'link_sent', 'awaiting_candidate', 'reschedule_requested'}


def _app_base() -> str:
    return os.environ.get('APP_BASE_URL', '').rstrip('/')


def _token() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------- models -----

class SchedulingRequestCreate(BaseModel):
    candidate_id: str
    job_id: Optional[str] = None
    stage: Optional[str] = None
    title: Optional[str] = None
    type: str = 'technical'
    duration_min: int = 60
    interviewer_ids: list[str]
    attendee_emails: list[str] = []
    date_range_start: str  # YYYY-MM-DD
    date_range_end: str    # YYYY-MM-DD
    timezone: Optional[str] = None
    instructions: Optional[str] = None
    slot_interval_min: Optional[int] = None


class BookRequest(BaseModel):
    slot_start_utc: str
    timezone: Optional[str] = None


class CancelRequest(BaseModel):
    reason: Optional[str] = None


# ---------------------------------------------------------------- helpers ----

def _display_status(iv: dict) -> str:
    """Status shown on the recruiter dashboard — folds link_disabled/expired
    into the base scheduling_status so the UI has one field to badge/filter on."""
    s = iv.get('scheduling_status')
    if s in ('scheduled', 'cancelled', 'booking'):
        return s
    if iv.get('link_disabled'):
        return 'link_disabled'
    active, reason = _link_active(iv)
    if not active and reason == 'link_expired':
        return 'expired'
    return s or 'draft'


async def _enrich_request(iv: dict) -> dict:
    cand = await db.candidates.find_one({'id': iv.get('candidate_id')}, {'_id': 0, 'name': 1, 'email': 1}) or {}
    job = await db.jobs.find_one({'id': iv.get('job_id')}, {'_id': 0, 'title': 1}) or {}
    users = {u['id']: u for u in await db.users.find({'id': {'$in': iv.get('interviewer_ids', [])}}, {'_id': 0, 'id': 1, 'name': 1, 'email': 1}).to_list(50)}
    out = dict(iv)
    out['candidate_name'] = cand.get('name')
    out['candidate_email'] = cand.get('email')
    out['job_title'] = job.get('title')
    out['interviewers'] = [{'id': i, 'name': users.get(i, {}).get('name', '?'), 'email': users.get(i, {}).get('email')} for i in iv.get('interviewer_ids', [])]
    out['scheduling_link'] = f"{_app_base()}/schedule/interview/{iv['scheduling_token']}" if iv.get('scheduling_token') else None
    out['display_status'] = _display_status(iv)
    return clean(out)


async def _find_by_token(token: str) -> dict:
    iv = await db.interviews.find_one({'scheduling_token': token})
    if not iv:
        raise HTTPException(status_code=404, detail='Scheduling link not found')
    return iv


def _link_active(iv: dict) -> tuple[bool, str]:
    if iv.get('link_disabled'):
        return False, 'link_disabled'
    exp = iv.get('scheduling_token_expires_at')
    if exp:
        try:
            if datetime.fromisoformat(exp.replace('Z', '+00:00')) < datetime.now(timezone.utc):
                return False, 'link_expired'
        except (ValueError, AttributeError):
            pass
    return True, 'ok'


async def _organizer_creds(iv: dict):
    """Google creds of the recruiter who created the request (the event organizer).
    Never raises: a stale/expired token that fails to refresh is treated the
    same as "not connected" (returns None) so booking degrades gracefully
    instead of hard-failing."""
    u = await db.users.find_one({'id': iv.get('created_by')})
    if not u:
        return None, None
    try:
        return await get_credentials_for_user(u), u
    except Exception as e:  # noqa: BLE001 — invalid_client / invalid_grant / RefreshError
        logger.warning('organizer google creds unavailable for interview %s: %s', iv.get('id'), e)
        return None, u


async def _public_view(iv: dict) -> dict:
    cand = await db.candidates.find_one({'id': iv.get('candidate_id')}, {'_id': 0, 'name': 1, 'email': 1}) or {}
    job = await db.jobs.find_one({'id': iv.get('job_id')}, {'_id': 0, 'title': 1}) or {}
    settings = await get_scheduling_settings()
    users = await db.users.find({'id': {'$in': iv.get('interviewer_ids', [])}}, {'_id': 0, 'name': 1}).to_list(50)
    return {
        'status': iv.get('scheduling_status'),
        'booked': iv.get('scheduling_status') == 'scheduled',
        'company_name': (await db.career_settings.find_one({'key': 'singleton'}, {'_id': 0, 'company_name': 1}) or {}).get('company_name') or 'Our Company',
        'logo_url': f"{_app_base()}/api/career/public/logo",
        'job_title': job.get('title'),
        'stage': iv.get('stage'),
        'title': iv.get('title') or (f"{(iv.get('type') or 'interview').replace('_', ' ').title()} Interview"),
        'type': iv.get('type'),
        'duration_min': iv.get('duration_min'),
        'instructions': iv.get('instructions'),
        'candidate_name': cand.get('name'),
        'candidate_email': cand.get('email'),
        'date_range_start': iv.get('date_range_start'),
        'date_range_end': iv.get('date_range_end'),
        'generation_timezone': settings.get('timezone'),
        'allow_reschedule': True,
        'allow_cancel': True,
        # only present once booked
        'scheduled_at': iv.get('scheduled_at'),
        'video_link': iv.get('video_link'),
        'google_event_link': iv.get('google_event_link'),
        'interviewer_names': [u.get('name') for u in users],
    }


# ---------------------------------------------------------- recruiter API ----

@router.get('/scheduling/settings')
async def get_settings(user: dict = Depends(require_roles('admin', 'recruiter'))):
    return await get_scheduling_settings()


class SettingsUpdate(BaseModel):
    working_days: Optional[list[int]] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    timezone: Optional[str] = None
    min_notice_hours: Optional[int] = None
    max_horizon_days: Optional[int] = None
    slot_interval_min: Optional[int] = None
    reminder_offsets_hours: Optional[list[int]] = None


@router.put('/scheduling/settings')
async def update_settings(body: SettingsUpdate, user: dict = Depends(require_roles('admin'))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.settings.update_one({'key': 'scheduling'}, {'$set': updates}, upsert=True)
    await log_audit(user, 'scheduling.settings_updated', 'settings', 'scheduling', str(updates))
    return await get_scheduling_settings()


@router.get('/scheduling/interviewer-status')
async def interviewer_status(ids: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    id_list = [i for i in ids.split(',') if i]
    users = {u['id']: u for u in await db.users.find({'id': {'$in': id_list}}).to_list(50)}
    out = []
    for iid in id_list:
        u = users.get(iid, {})
        avail = await db.availability.count_documents({'user_id': iid})
        out.append({
            'id': iid,
            'name': u.get('name', '?'),
            'email': u.get('email'),
            'google_calendar_connected': bool(u.get('google_tokens')),
            'has_working_hours': avail > 0,
        })
    return {'interviewers': out}


@router.post('/scheduling/requests')
async def create_request(body: SchedulingRequestCreate, user: dict = Depends(require_roles('admin', 'recruiter'))):
    cand = await db.candidates.find_one({'id': body.candidate_id})
    if not cand:
        raise HTTPException(status_code=404, detail='Candidate not found')
    if not body.interviewer_ids:
        raise HTTPException(status_code=422, detail='At least one interviewer is required')
    settings = await get_scheduling_settings()
    horizon_days = int(settings.get('max_horizon_days', 14))
    iv = {
        'id': new_id(),
        'candidate_id': body.candidate_id,
        'job_id': body.job_id or cand.get('job_id'),
        'stage': body.stage or cand.get('stage'),
        'title': body.title,
        'type': body.type,
        'duration_min': body.duration_min,
        'interviewer_ids': body.interviewer_ids,
        'attendee_emails': body.attendee_emails or [],
        'date_range_start': body.date_range_start,
        'date_range_end': body.date_range_end,
        'timezone': body.timezone or settings.get('timezone') or 'UTC',
        'instructions': body.instructions,
        'slot_interval_min': body.slot_interval_min or settings.get('slot_interval_min', 30),
        'self_scheduled': True,
        'scheduling_status': 'draft',
        'status': 'pending',            # not yet on the calendar
        'scheduled_at': None,
        'scheduling_token': _token(),
        'scheduling_token_expires_at': (datetime.now(timezone.utc) + timedelta(days=horizon_days + 30)).isoformat(),
        'link_disabled': False,
        'scheduling_link_sent_at': None,
        'link_opened_at': None,
        'candidate_booked_at': None,
        'reminders_sent': [],
        'enable_gemini_ai': True,
        'created_by': user['id'],
        'created_at': now_iso(),
        'updated_at': now_iso(),
    }
    await db.interviews.insert_one(iv)
    await log_activity(user, 'interview_request_created', f"created a scheduling request for {cand['name']}", candidate_id=cand['id'], job_id=iv['job_id'])
    await log_audit(user, 'scheduling.request_created', 'interview', iv['id'], f"{body.type} for {cand['name']}")
    await log_audit(user, 'scheduling.link_generated', 'interview', iv['id'], 'scheduling link generated')
    return await _enrich_request(iv)


@router.get('/scheduling/requests')
async def list_requests(status: Optional[str] = None, candidate_id: Optional[str] = None,
                        user: dict = Depends(require_roles('admin', 'recruiter'))):
    q = {'self_scheduled': True}
    if status:
        q['scheduling_status'] = status
    if candidate_id:
        q['candidate_id'] = candidate_id
    items = await db.interviews.find(q, {'_id': 0}).sort('created_at', -1).to_list(1000)
    return [await _enrich_request(iv) for iv in items]


@router.get('/scheduling/requests/{req_id}')
async def get_request(req_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    iv = await db.interviews.find_one({'id': req_id}, {'_id': 0})
    if not iv:
        raise HTTPException(status_code=404, detail='Request not found')
    return await _enrich_request(iv)


@router.get('/scheduling/requests/{req_id}/timeline')
async def request_timeline(req_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    """Full audit trail for one scheduling request (link generated → sent →
    opened → booked/rescheduled/cancelled), most-recent first."""
    iv = await db.interviews.find_one({'id': req_id}, {'_id': 0, 'id': 1})
    if not iv:
        raise HTTPException(status_code=404, detail='Request not found')
    rows = await db.audit_log.find(
        {'entity_type': 'interview', 'entity_id': req_id},
        {'_id': 0},
    ).sort('created_at', -1).to_list(200)
    return {'entries': clean(rows)}


@router.get('/scheduling/requests/{req_id}/slots')
async def preview_slots(req_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    iv = await db.interviews.find_one({'id': req_id})
    if not iv:
        raise HTTPException(status_code=404, detail='Request not found')
    settings = await get_scheduling_settings()
    if iv.get('slot_interval_min'):
        settings = {**settings, 'slot_interval_min': iv['slot_interval_min']}
    if iv.get('timezone'):
        settings = {**settings, 'timezone': iv['timezone']}
    return await generate_slots(iv['interviewer_ids'], iv['duration_min'],
                                iv['date_range_start'], iv['date_range_end'], settings,
                                exclude_interview_id=iv['id'])


@router.post('/scheduling/requests/{req_id}/send-link')
async def send_link(req_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    iv = await db.interviews.find_one({'id': req_id})
    if not iv:
        raise HTTPException(status_code=404, detail='Request not found')
    cand = await db.candidates.find_one({'id': iv['candidate_id']}, {'_id': 0}) or {}
    job = await db.jobs.find_one({'id': iv.get('job_id')}, {'_id': 0, 'title': 1}) or {}
    link = f"{_app_base()}/schedule/interview/{iv['scheduling_token']}"
    email_res = await queue_scheduling_email('scheduling_invite', cand.get('email'), {
        'candidate_name': cand.get('name', 'there'),
        'job_title': job.get('title', 'the role'),
        'interview_stage': iv.get('stage') or 'interview',
        'duration': iv.get('duration_min'),
        'instructions': iv.get('instructions') or '',
        'scheduling_link': link,
    }, meta={'interview_id': iv['id'], 'candidate_id': iv['candidate_id']})
    new_status = 'awaiting_candidate' if iv.get('scheduling_status') in ('draft', 'link_sent') else iv.get('scheduling_status')
    await db.interviews.update_one({'id': req_id}, {'$set': {
        'scheduling_status': new_status, 'scheduling_link_sent_at': now_iso(), 'updated_at': now_iso(),
    }})
    await log_audit(user, 'scheduling.link_sent', 'interview', iv['id'], f"invite queued to {cand.get('email')}")
    await log_activity(user, 'scheduling_link_sent', f"sent scheduling link to {cand.get('name')}", candidate_id=iv['candidate_id'], job_id=iv.get('job_id'))
    return {'ok': True, 'scheduling_link': link, 'email': email_res}


@router.post('/scheduling/requests/{req_id}/disable-link')
async def disable_link(req_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    res = await db.interviews.update_one({'id': req_id}, {'$set': {'link_disabled': True, 'updated_at': now_iso()}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail='Request not found')
    await log_audit(user, 'scheduling.link_disabled', 'interview', req_id, '')
    return {'ok': True}


@router.post('/scheduling/requests/{req_id}/regenerate-link')
async def regenerate_link(req_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    iv = await db.interviews.find_one({'id': req_id})
    if not iv:
        raise HTTPException(status_code=404, detail='Request not found')
    tok = _token()
    settings = await get_scheduling_settings()
    await db.interviews.update_one({'id': req_id}, {'$set': {
        'scheduling_token': tok, 'link_disabled': False,
        'scheduling_token_expires_at': (datetime.now(timezone.utc) + timedelta(days=int(settings.get('max_horizon_days', 14)) + 30)).isoformat(),
        'updated_at': now_iso(),
    }})
    await log_audit(user, 'scheduling.link_regenerated', 'interview', req_id, '')
    return {'ok': True, 'scheduling_link': f"{_app_base()}/schedule/interview/{tok}"}


# ------------------------------------------------------------- public API ----

@router.get('/schedule/{token}')
async def public_get(token: str):
    iv = await _find_by_token(token)
    active, reason = _link_active(iv)
    if not active and iv.get('scheduling_status') != 'scheduled':
        return {'error': reason, **{k: (await _public_view(iv)).get(k) for k in ('company_name', 'logo_url')}}
    # mark opened (first time only)
    if not iv.get('link_opened_at'):
        await db.interviews.update_one({'id': iv['id']}, {'$set': {'link_opened_at': now_iso()}})
        if iv.get('scheduling_status') == 'awaiting_candidate' or iv.get('scheduling_status') == 'link_sent':
            actor = await db.users.find_one({'id': iv.get('created_by')}, {'_id': 0}) or {}
            await log_audit(actor, 'scheduling.candidate_opened', 'interview', iv['id'], 'candidate opened scheduling page')
    return await _public_view(iv)


@router.get('/schedule/{token}/slots')
async def public_slots(token: str, tz: Optional[str] = Query(None)):
    iv = await _find_by_token(token)
    active, reason = _link_active(iv)
    if not active:
        raise HTTPException(status_code=410, detail=reason)
    settings = await get_scheduling_settings()
    if iv.get('slot_interval_min'):
        settings = {**settings, 'slot_interval_min': iv['slot_interval_min']}
    if iv.get('timezone'):
        settings = {**settings, 'timezone': iv['timezone']}
    result = await generate_slots(iv['interviewer_ids'], iv['duration_min'],
                                  iv['date_range_start'], iv['date_range_end'], settings,
                                  exclude_interview_id=iv['id'])
    # Never leak interviewer identities/busy details to the public page.
    result.pop('interviewers', None)
    return result


async def _create_calendar_event(iv: dict) -> dict:
    """Create the Google Calendar event + Meet using the organizer's creds.
    Returns {'synced':bool,'event_id','event_link','video_link'} or raises on a
    real Google failure (so the caller can refuse to mark the interview booked)."""
    creds, organizer = await _organizer_creds(iv)
    if not creds:
        return {'synced': False}  # graceful: nobody connected yet
    cand = await db.candidates.find_one({'id': iv['candidate_id']}, {'_id': 0}) or {}
    job = await db.jobs.find_one({'id': iv.get('job_id')}, {'_id': 0}) or {}
    interviewers = await db.users.find({'id': {'$in': iv['interviewer_ids']}}, {'_id': 0, 'email': 1}).to_list(50)
    attendees = [i['email'] for i in interviewers if i.get('email')]
    if cand.get('email'):
        attendees.append(cand['email'])
    attendees.extend([e for e in (iv.get('attendee_emails') or []) if e])
    start = datetime.fromisoformat(iv['scheduled_at'].replace('Z', '+00:00'))
    end = start + timedelta(minutes=iv['duration_min'])
    title = iv.get('title') or f"Interview – {cand.get('name', '')} – {job.get('title', '')}"
    desc_lines = [
        f"Candidate: {cand.get('name', '')}",
        f"Role: {job.get('title', '')}",
        f"Stage: {iv.get('stage') or ''}",
    ]
    if iv.get('instructions'):
        desc_lines += ['', 'Instructions:', iv['instructions']]
    desc_lines += ['', f"Candidate profile: {_app_base()}/candidates/{iv['candidate_id']}"]
    try:
        event = create_event(
            creds, summary=title, description='\n'.join(desc_lines),
            start_iso=start.isoformat(), end_iso=end.isoformat(),
            attendee_emails=attendees, add_meet=True,
        )
    except (GoogleAuthError, RefreshError) as e:
        # Organizer's Google auth is broken (e.g. old OAuth client). Degrade
        # gracefully — book the interview without a calendar event; recruiter
        # can reconnect Google and re-sync later.
        logger.warning('calendar auth failed for %s — booking without event: %s', iv['id'], e)
        return {'synced': False, 'degraded_reason': 'auth'}
    except HttpError as e:
        if getattr(e, 'resp', None) is not None and e.resp.status in (401, 403):
            logger.warning('calendar auth (%s) failed for %s — booking without event', e.resp.status, iv['id'])
            return {'synced': False, 'degraded_reason': 'auth'}
        raise  # genuine API failure with valid creds → let caller refuse booking
    return {
        'synced': True,
        'event_id': event['id'],
        'event_link': event.get('htmlLink'),
        'video_link': event.get('hangoutLink'),
    }


@router.post('/schedule/{token}/book')
async def public_book(token: str, body: BookRequest):
    iv = await _find_by_token(token)
    active, reason = _link_active(iv)
    if not active:
        raise HTTPException(status_code=410, detail=reason)
    if iv.get('scheduling_status') == 'scheduled':
        raise HTTPException(status_code=409, detail='already_booked')
    try:
        start_utc = datetime.fromisoformat(body.slot_start_utc.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail='Invalid slot_start_utc')

    # Atomic claim so two concurrent candidate clicks can't both proceed.
    claimed = await db.interviews.find_one_and_update(
        {'id': iv['id'], 'scheduling_status': {'$in': list(ACTIVE_LINK_STATUSES)}},
        {'$set': {'scheduling_status': 'booking'}},
    )
    if not claimed:
        raise HTTPException(status_code=409, detail='already_booked')
    prev_status = claimed.get('scheduling_status')
    try:
        free, why, _ = await is_slot_free(iv['interviewer_ids'], start_utc, iv['duration_min'], exclude_interview_id=iv['id'])
        if not free:
            await db.interviews.update_one({'id': iv['id']}, {'$set': {'scheduling_status': prev_status}})
            code = 409 if why == 'slot_taken' else 503
            raise HTTPException(status_code=code, detail=why)

        # tentatively set the time, then try to create the calendar event
        await db.interviews.update_one({'id': iv['id']}, {'$set': {
            'scheduled_at': start_utc.isoformat(),
            'candidate_timezone': body.timezone,
        }})
        iv['scheduled_at'] = start_utc.isoformat()
        try:
            cal = await _create_calendar_event(iv)
        except Exception as e:  # noqa: BLE001 — real Google failure: do NOT confirm
            logger.warning('calendar event creation failed for %s: %s', iv['id'], e)
            await db.interviews.update_one({'id': iv['id']}, {'$set': {'scheduling_status': prev_status, 'scheduled_at': None}})
            raise HTTPException(status_code=502, detail='calendar_error')

        updates = {
            'scheduling_status': 'scheduled',
            'status': 'scheduled',
            'candidate_booked_at': now_iso(),
            'calendar_synced': cal.get('synced', False),
            'updated_at': now_iso(),
        }
        if cal.get('synced'):
            updates['google_event_id'] = cal.get('event_id')
            updates['google_event_link'] = cal.get('event_link')
            if cal.get('video_link'):
                updates['video_link'] = cal.get('video_link')
        await db.interviews.update_one({'id': iv['id']}, {'$set': updates})
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        await db.interviews.update_one({'id': iv['id']}, {'$set': {'scheduling_status': prev_status, 'scheduled_at': None}})
        logger.exception('booking failed for %s', iv['id'])
        raise HTTPException(status_code=500, detail='booking_failed') from e

    fresh = await db.interviews.find_one({'id': iv['id']}, {'_id': 0})
    await _post_booking_side_effects(fresh, kind='book')
    return await _public_view(fresh)


@router.post('/schedule/{token}/reschedule')
async def public_reschedule(token: str, body: BookRequest):
    iv = await _find_by_token(token)
    active, reason = _link_active(iv)
    if not active:
        raise HTTPException(status_code=410, detail=reason)
    if iv.get('scheduling_status') != 'scheduled':
        raise HTTPException(status_code=409, detail='not_booked')
    try:
        start_utc = datetime.fromisoformat(body.slot_start_utc.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail='Invalid slot_start_utc')
    free, why, _ = await is_slot_free(iv['interviewer_ids'], start_utc, iv['duration_min'], exclude_interview_id=iv['id'])
    if not free:
        raise HTTPException(status_code=409 if why == 'slot_taken' else 503, detail=why)
    old_time = iv.get('scheduled_at')
    await db.interviews.update_one({'id': iv['id']}, {'$set': {
        'scheduled_at': start_utc.isoformat(), 'candidate_timezone': body.timezone,
        'reminders_sent': [], 'updated_at': now_iso(),
    }})
    iv['scheduled_at'] = start_utc.isoformat()
    # Update the existing Google event in place (never create a duplicate).
    if iv.get('google_event_id'):
        creds, _org = await _organizer_creds(iv)
        if creds:
            try:
                end = start_utc + timedelta(minutes=iv['duration_min'])
                update_event(creds, iv['google_event_id'], start_iso=start_utc.isoformat(), end_iso=end.isoformat())
            except Exception as e:  # noqa: BLE001
                logger.warning('reschedule calendar update failed for %s: %s', iv['id'], e)
    actor = await db.users.find_one({'id': iv.get('created_by')}, {'_id': 0}) or {}
    await log_audit(actor, 'scheduling.rescheduled', 'interview', iv['id'], f"moved from {old_time} to {start_utc.isoformat()}")
    fresh = await db.interviews.find_one({'id': iv['id']}, {'_id': 0})
    await _post_booking_side_effects(fresh, kind='reschedule')
    return await _public_view(fresh)


@router.post('/schedule/{token}/cancel')
async def public_cancel(token: str, body: CancelRequest):
    iv = await _find_by_token(token)
    if iv.get('scheduling_status') == 'cancelled':
        return await _public_view(iv)
    creds, _org = await _organizer_creds(iv)
    if iv.get('google_event_id') and creds:
        try:
            delete_event(creds, iv['google_event_id'])
        except Exception as e:  # noqa: BLE001
            logger.warning('cancel calendar delete failed for %s: %s', iv['id'], e)
    await db.interviews.update_one({'id': iv['id']}, {'$set': {
        'scheduling_status': 'cancelled', 'status': 'cancelled',
        'cancelled_at': now_iso(), 'cancellation_reason': body.reason or 'Cancelled by candidate',
        'updated_at': now_iso(),
    }})
    fresh = await db.interviews.find_one({'id': iv['id']}, {'_id': 0})
    await _post_booking_side_effects(fresh, kind='cancel', reason=body.reason)
    return await _public_view(fresh)


async def _post_booking_side_effects(iv: dict, kind: str, reason: str | None = None):
    """Queue emails, notify interviewers, write audit/activity after a
    book/reschedule/cancel."""
    cand = await db.candidates.find_one({'id': iv['candidate_id']}, {'_id': 0}) or {}
    job = await db.jobs.find_one({'id': iv.get('job_id')}, {'_id': 0, 'title': 1}) or {}
    interviewers = await db.users.find({'id': {'$in': iv.get('interviewer_ids', [])}}, {'_id': 0, 'id': 1, 'name': 1, 'email': 1}).to_list(50)
    tz = iv.get('candidate_timezone') or iv.get('timezone') or 'UTC'
    when = human_time(iv.get('scheduled_at'), iv.get('duration_min', 60), tz)
    meet = iv.get('video_link') or 'To be shared'
    actor = await db.users.find_one({'id': iv.get('created_by')}, {'_id': 0}) or {}
    link = f"{_app_base()}/schedule/interview/{iv['scheduling_token']}"

    if kind in ('book', 'reschedule'):
        ekind = 'interview_confirmation_candidate' if kind == 'book' else 'interview_reschedule'
        base_ctx = {
            'candidate_name': cand.get('name', 'there'), 'recipient_name': cand.get('name', 'there'),
            'job_title': job.get('title', 'the role'), 'interview_stage': iv.get('stage') or 'interview',
            'when': when, 'meet_link': meet, 'scheduling_link': link,
        }
        await queue_scheduling_email(ekind, cand.get('email'), base_ctx,
                                     meta={'interview_id': iv['id'], 'candidate_id': iv['candidate_id']})
        for it in interviewers:
            ikind = 'interview_confirmation_interviewer' if kind == 'book' else 'interview_reschedule'
            ictx = {
                'interviewer_name': it.get('name', 'there'), 'recipient_name': it.get('name', 'there'),
                'candidate_name': cand.get('name', ''), 'job_title': job.get('title', ''),
                'interview_stage': iv.get('stage') or 'interview', 'when': when, 'meet_link': meet,
                'candidate_link': f"{_app_base()}/candidates/{iv['candidate_id']}",
                'scorecard_link': f"{_app_base()}/interviews",
            }
            await queue_scheduling_email(ikind, it.get('email'), ictx, meta={'interview_id': iv['id']})
            await notify(it['id'], 'interview',
                         f"{cand.get('name', 'A candidate')} booked a {iv.get('stage') or ''} interview" if kind == 'book'
                         else f"Interview with {cand.get('name', 'candidate')} was rescheduled", '/interviews')
        action = 'scheduling.candidate_booked' if kind == 'book' else 'scheduling.rescheduled'
        await log_audit(actor, action, 'interview', iv['id'], f"{cand.get('name', '')} — {when}")
        if iv.get('calendar_synced'):
            await log_audit(actor, 'scheduling.calendar_event_created' if kind == 'book' else 'scheduling.calendar_event_updated', 'interview', iv['id'], meet)
        await log_activity(actor, 'interview_scheduled' if kind == 'book' else 'interview_rescheduled',
                           f"{cand.get('name', 'Candidate')} booked {iv.get('stage') or 'an'} interview for {when}" if kind == 'book'
                           else f"interview for {cand.get('name', 'candidate')} rescheduled to {when}",
                           candidate_id=iv['candidate_id'], job_id=iv.get('job_id'))
    elif kind == 'cancel':
        ctx = {'recipient_name': cand.get('name', 'there'), 'job_title': job.get('title', 'the role'),
               'interview_stage': iv.get('stage') or 'interview', 'when': when,
               'cancel_reason': reason or ''}
        await queue_scheduling_email('interview_cancel', cand.get('email'), ctx, meta={'interview_id': iv['id'], 'candidate_id': iv['candidate_id']})
        for it in interviewers:
            await queue_scheduling_email('interview_cancel', it.get('email'), {**ctx, 'recipient_name': it.get('name', 'there')}, meta={'interview_id': iv['id']})
            await notify(it['id'], 'interview', f"Interview with {cand.get('name', 'candidate')} was cancelled", '/interviews')
        await log_audit(actor, 'scheduling.cancelled', 'interview', iv['id'], reason or 'cancelled by candidate')
        await log_activity(actor, 'interview_cancelled', f"interview for {cand.get('name', 'candidate')} was cancelled", candidate_id=iv['candidate_id'], job_id=iv.get('job_id'))
