from datetime import datetime, timedelta, timezone
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user, require_roles
from database import db
from google_calendar import create_event, delete_event, free_busy, get_credentials_for_user, update_event
from feedback_emails import send_scorecard_request
from utils import clean, log_activity, log_audit, new_id, notify, now_iso

router = APIRouter(tags=['interviews'])

DEFAULT_ATTRS = ['Communication', 'Technical Skill', 'Problem Solving', 'Culture Fit']


async def _sync_calendar_on_create(user: dict, iv: dict, cand: dict):
    creds = await get_credentials_for_user(user)
    if not creds:
        return
    interviewers = await db.users.find({'id': {'$in': iv['interviewer_ids']}}, {'_id': 0, 'email': 1}).to_list(20)
    attendees = [i['email'] for i in interviewers if i.get('email')] + ([cand['email']] if cand.get('email') else [])
    start = datetime.fromisoformat(iv['scheduled_at'].replace('Z', '+00:00'))
    end = start + timedelta(minutes=iv['duration_min'])
    try:
        event = create_event(
            creds,
            summary=f"Interview: {cand['name']} ({iv['type'].replace('_', ' ').title()})",
            description=(iv.get('notes') or '') + f"\n\nCandidate profile: {os.environ['APP_BASE_URL']}/candidates/{cand['id']}",
            start_iso=start.isoformat(), end_iso=end.isoformat(),
            attendee_emails=attendees, location=iv.get('location'), add_meet=not bool(iv.get('video_link')),
        )
    except Exception:
        return
    meet_link = event.get('hangoutLink')
    updates = {'google_event_id': event['id'], 'google_event_link': event.get('htmlLink'), 'calendar_synced': True}
    if meet_link and not iv.get('video_link'):
        updates['video_link'] = meet_link
    await db.interviews.update_one({'id': iv['id']}, {'$set': updates})


async def _sync_calendar_on_update(user: dict, iv: dict, updates: dict):
    if not iv.get('google_event_id'):
        return
    creds = await get_credentials_for_user(user)
    if not creds:
        return
    try:
        if updates.get('status') == 'cancelled':
            delete_event(creds, iv['google_event_id'])
            return
        fields = {}
        if 'scheduled_at' in updates or 'duration_min' in updates:
            start = datetime.fromisoformat(updates.get('scheduled_at', iv['scheduled_at']).replace('Z', '+00:00'))
            end = start + timedelta(minutes=updates.get('duration_min', iv['duration_min']))
            fields['start_iso'] = start.isoformat()
            fields['end_iso'] = end.isoformat()
        if 'interviewer_ids' in updates:
            interviewers = await db.users.find({'id': {'$in': updates['interviewer_ids']}}, {'_id': 0, 'email': 1}).to_list(20)
            cand = await db.candidates.find_one({'id': iv['candidate_id']}, {'_id': 0, 'email': 1})
            fields['attendee_emails'] = [i['email'] for i in interviewers if i.get('email')] + ([cand['email']] if cand and cand.get('email') else [])
        if 'location' in updates:
            fields['location'] = updates['location']
        if fields:
            update_event(creds, iv['google_event_id'], **fields)
    except Exception:
        return


class InterviewCreate(BaseModel):
    candidate_id: str
    job_id: Optional[str] = None
    stage: Optional[str] = None
    type: str = 'phone_screen'  # phone_screen | technical | panel | onsite
    interviewer_ids: list[str]
    scheduled_at: str  # ISO datetime (UTC)
    timezone: Optional[str] = None  # IANA tz name, e.g. 'America/New_York'
    duration_min: int = 60
    location: Optional[str] = None
    video_link: Optional[str] = None
    notes: Optional[str] = None


class InterviewUpdate(BaseModel):
    stage: Optional[str] = None
    type: Optional[str] = None
    interviewer_ids: Optional[list[str]] = None
    scheduled_at: Optional[str] = None
    timezone: Optional[str] = None
    duration_min: Optional[int] = None
    location: Optional[str] = None
    video_link: Optional[str] = None
    status: Optional[str] = None


class ScorecardSubmit(BaseModel):
    ratings: dict  # attribute -> 1-5
    overall: int
    recommendation: str  # strong_yes | yes | no | strong_no
    notes: Optional[str] = None


class AvailabilitySlot(BaseModel):
    user_id: Optional[str] = None
    day_of_week: int  # 0=Mon .. 6=Sun
    start_time: str  # "09:00"
    end_time: str  # "17:00"


async def _enrich(interviews: list) -> list:
    cands = {c['id']: c for c in await db.candidates.find({}, {'_id': 0, 'id': 1, 'name': 1, 'job_id': 1, 'email': 1, 'current_title': 1}).to_list(3000)}
    jobs = {j['id']: j for j in await db.jobs.find({}, {'_id': 0, 'id': 1, 'title': 1}).to_list(500)}
    users = {u['id']: u for u in await db.users.find({}, {'_id': 0, 'id': 1, 'name': 1, 'email': 1}).to_list(500)}
    for iv in interviews:
        c = cands.get(iv.get('candidate_id'), {})
        iv['candidate_name'] = c.get('name', 'Unknown')
        iv['candidate_email'] = c.get('email')
        iv['candidate_title'] = c.get('current_title')
        iv['job_title'] = jobs.get(iv.get('job_id') or c.get('job_id'), {}).get('title')
        iv['interviewers'] = [
            {'id': i, 'name': users.get(i, {}).get('name', '?'), 'email': users.get(i, {}).get('email')}
            for i in iv.get('interviewer_ids', [])
        ]
        iv['interviewer_names'] = [x['name'] for x in iv['interviewers']]
        iv.setdefault('timezone', 'UTC')
        sc = await db.scorecards.find({'interview_id': iv['id']}, {'_id': 0}).to_list(20)
        iv['scorecards_submitted'] = len(sc)
    return interviews


@router.get('/interviews')
async def list_interviews(
    interviewer_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    q = {}
    if user['role'] == 'interviewer':
        q['interviewer_ids'] = user['id']
    elif interviewer_id:
        q['interviewer_ids'] = interviewer_id
    if candidate_id:
        q['candidate_id'] = candidate_id
    if job_id:
        q['job_id'] = job_id
    if status:
        q['status'] = status
    if from_date or to_date:
        rng = {}
        if from_date:
            rng['$gte'] = from_date
        if to_date:
            rng['$lte'] = to_date
        q['scheduled_at'] = rng
    items = await db.interviews.find(q, {'_id': 0}).sort('scheduled_at', 1).to_list(1000)
    return await _enrich(items)


@router.post('/interviews')
async def create_interview(body: InterviewCreate, user: dict = Depends(require_roles('admin', 'recruiter'))):
    cand = await db.candidates.find_one({'id': body.candidate_id})
    if not cand:
        raise HTTPException(status_code=404, detail='Candidate not found')
    iv = {
        'id': new_id(),
        'candidate_id': body.candidate_id,
        'job_id': body.job_id or cand.get('job_id'),
        'stage': body.stage or cand.get('stage'),
        'type': body.type,
        'interviewer_ids': body.interviewer_ids,
        'scheduled_at': body.scheduled_at,
        'timezone': body.timezone or 'UTC',
        'duration_min': body.duration_min,
        'location': body.location,
        'video_link': body.video_link,
        'notes': body.notes,
        'status': 'scheduled',
        'created_by': user['id'],
        'created_at': now_iso(),
    }
    await db.interviews.insert_one(iv)
    await log_activity(user, 'interview_scheduled', f"scheduled a {body.type.replace('_', ' ')} interview for {cand['name']}", candidate_id=cand['id'], job_id=iv['job_id'])
    for iid in body.interviewer_ids:
        await notify(iid, 'interview', f"You have been assigned a {body.type.replace('_', ' ')} interview with {cand['name']}", '/interviews')
    await _sync_calendar_on_create(user, iv, cand)
    return clean(await db.interviews.find_one({'id': iv['id']}, {'_id': 0}))


@router.put('/interviews/{interview_id}')
async def update_interview(interview_id: str, body: InterviewUpdate, user: dict = Depends(require_roles('admin', 'recruiter'))):
    iv = await db.interviews.find_one({'id': interview_id})
    if not iv:
        raise HTTPException(status_code=404, detail='Interview not found')
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.interviews.update_one({'id': interview_id}, {'$set': updates})
    if updates.get('status') == 'cancelled':
        cand = await db.candidates.find_one({'id': iv['candidate_id']})
        for iid in iv.get('interviewer_ids', []):
            await notify(iid, 'interview', f"Interview with {cand['name'] if cand else 'candidate'} was cancelled", '/interviews')
        await log_activity(user, 'interview_cancelled', f"cancelled interview for {cand['name'] if cand else 'candidate'}", candidate_id=iv['candidate_id'])
    await _sync_calendar_on_update(user, iv, updates)
    return clean(await db.interviews.find_one({'id': interview_id}, {'_id': 0}))


@router.post('/interviews/{interview_id}/complete')
async def complete_interview(interview_id: str, user: dict = Depends(get_current_user)):
    iv = await db.interviews.find_one({'id': interview_id})
    if not iv:
        raise HTTPException(status_code=404, detail='Interview not found')
    if user['role'] == 'interviewer' and user['id'] not in iv.get('interviewer_ids', []):
        raise HTTPException(status_code=403, detail='Not your interview')
    await db.interviews.update_one({'id': interview_id}, {'$set': {'status': 'feedback_pending', 'completed_at': now_iso()}})
    cand = await db.candidates.find_one({'id': iv['candidate_id']})
    for iid in iv.get('interviewer_ids', []):
        await notify(iid, 'feedback', f"Feedback pending for your interview with {cand['name'] if cand else 'candidate'}", '/interviews')
    await log_activity(user, 'interview_completed', f"marked interview with {cand['name'] if cand else 'candidate'} as completed", candidate_id=iv['candidate_id'])
    updated_iv = await db.interviews.find_one({'id': interview_id})
    await send_scorecard_request(updated_iv)
    return clean(updated_iv)


@router.post('/interviews/{interview_id}/scorecard')
async def submit_scorecard(interview_id: str, body: ScorecardSubmit, user: dict = Depends(get_current_user)):
    iv = await db.interviews.find_one({'id': interview_id})
    if not iv:
        raise HTTPException(status_code=404, detail='Interview not found')
    if user['id'] not in iv.get('interviewer_ids', []) and user['role'] != 'admin':
        raise HTTPException(status_code=403, detail='Only assigned interviewers can submit a scorecard')
    existing = await db.scorecards.find_one({'interview_id': interview_id, 'interviewer_id': user['id']})
    if existing:
        raise HTTPException(status_code=409, detail='You already submitted a scorecard for this interview')
    sc = {
        'id': new_id(),
        'interview_id': interview_id,
        'candidate_id': iv['candidate_id'],
        'interviewer_id': user['id'],
        'interviewer_name': user['name'],
        'ratings': body.ratings,
        'overall': body.overall,
        'recommendation': body.recommendation,
        'notes': body.notes,
        'submitted_at': now_iso(),
    }
    await db.scorecards.insert_one(sc)
    # if all interviewers submitted -> feedback_submitted
    submitted = await db.scorecards.distinct('interviewer_id', {'interview_id': interview_id})
    if set(iv.get('interviewer_ids', [])) <= set(submitted):
        await db.interviews.update_one({'id': interview_id}, {'$set': {'status': 'feedback_submitted'}})
    else:
        await db.interviews.update_one({'id': interview_id}, {'$set': {'status': 'feedback_pending'}})
    cand = await db.candidates.find_one({'id': iv['candidate_id']})
    await log_activity(user, 'feedback_submitted', f"submitted feedback for {cand['name'] if cand else 'candidate'}", candidate_id=iv['candidate_id'])
    if iv.get('created_by') and iv['created_by'] != user['id']:
        await notify(iv['created_by'], 'feedback', f"{user['name']} submitted feedback for {cand['name'] if cand else 'candidate'}", f"/candidates/{iv['candidate_id']}")
    return clean(sc)


@router.get('/interviews/{interview_id}/scorecards')
async def get_scorecards(interview_id: str, user: dict = Depends(get_current_user)):
    iv = await db.interviews.find_one({'id': interview_id})
    if not iv:
        raise HTTPException(status_code=404, detail='Interview not found')
    if user['role'] == 'interviewer' and user['id'] not in iv.get('interviewer_ids', []):
        raise HTTPException(status_code=403, detail='Not authorized')
    return clean(await db.scorecards.find({'interview_id': interview_id}, {'_id': 0}).to_list(50))


@router.get('/candidates/{candidate_id}/scorecards')
async def candidate_scorecards(candidate_id: str, user: dict = Depends(get_current_user)):
    scs = await db.scorecards.find({'candidate_id': candidate_id}, {'_id': 0}).sort('submitted_at', -1).to_list(100)
    return scs


# ---- Availability ----

@router.get('/availability/{user_id}')
async def get_availability(user_id: str, user: dict = Depends(get_current_user)):
    return clean(await db.availability.find({'user_id': user_id}, {'_id': 0}).sort('day_of_week', 1).to_list(50))


@router.post('/availability')
async def add_availability(body: AvailabilitySlot, user: dict = Depends(get_current_user)):
    target = body.user_id or user['id']
    if target != user['id'] and user['role'] != 'admin':
        raise HTTPException(status_code=403, detail='Cannot set availability for others')
    slot = {'id': new_id(), 'user_id': target, 'day_of_week': body.day_of_week,
            'start_time': body.start_time, 'end_time': body.end_time, 'created_at': now_iso()}
    await db.availability.insert_one(slot)
    return clean(slot)


@router.delete('/availability/{slot_id}')
async def delete_availability(slot_id: str, user: dict = Depends(get_current_user)):
    slot = await db.availability.find_one({'id': slot_id})
    if not slot:
        raise HTTPException(status_code=404, detail='Slot not found')
    if slot['user_id'] != user['id'] and user['role'] != 'admin':
        raise HTTPException(status_code=403, detail='Not authorized')
    await db.availability.delete_one({'id': slot_id})
    return {'ok': True}


@router.get('/interviews-availability-check')
async def check_availability(interviewer_ids: str, scheduled_at: str, duration_min: int = 60, user: dict = Depends(get_current_user)):
    """Check each interviewer: within availability slots and no conflicting interviews."""
    ids = [i for i in interviewer_ids.split(',') if i]
    try:
        start = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=422, detail='Invalid scheduled_at datetime')
    end = start + timedelta(minutes=duration_min)
    results = []
    users = {u['id']: u for u in await db.users.find({'id': {'$in': ids}}).to_list(50)}
    for iid in ids:
        u = users.get(iid, {})
        slots = await db.availability.find({'user_id': iid, 'day_of_week': start.weekday()}, {'_id': 0}).to_list(20)
        in_slot = False
        for s in slots:
            sh, sm = map(int, s['start_time'].split(':'))
            eh, em = map(int, s['end_time'].split(':'))
            slot_start = start.replace(hour=sh, minute=sm, second=0, microsecond=0)
            slot_end = start.replace(hour=eh, minute=em, second=0, microsecond=0)
            if slot_start <= start and end <= slot_end:
                in_slot = True
                break
        # conflicts
        day_start = start.replace(hour=0, minute=0).isoformat()
        day_end = start.replace(hour=23, minute=59).isoformat()
        ivs = await db.interviews.find({'interviewer_ids': iid, 'status': {'$nin': ['cancelled']},
                                        'scheduled_at': {'$gte': day_start, '$lte': day_end}}, {'_id': 0}).to_list(50)
        conflicts = []
        for iv in ivs:
            try:
                iv_start = datetime.fromisoformat(iv['scheduled_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                continue
            iv_end = iv_start + timedelta(minutes=iv.get('duration_min', 60))
            if iv_start < end and start < iv_end:
                conflicts.append({'interview_id': iv['id'], 'scheduled_at': iv['scheduled_at'], 'duration_min': iv.get('duration_min', 60)})
        google_connected = bool(u.get('google_tokens'))
        google_conflicts = []
        if google_connected:
            try:
                creds = await get_credentials_for_user(u)
                busy = free_busy(creds, day_start, day_end) if creds else []
                for b in busy:
                    b_start = datetime.fromisoformat(b['start'].replace('Z', '+00:00'))
                    b_end = datetime.fromisoformat(b['end'].replace('Z', '+00:00'))
                    if b_start < end and start < b_end:
                        google_conflicts.append({'start': b['start'], 'end': b['end']})
            except Exception:
                pass
        results.append({
            'interviewer_id': iid,
            'interviewer_name': users.get(iid, {}).get('name', '?'),
            'has_slots_defined': len(slots) > 0,
            'within_availability': in_slot if slots else None,
            'conflicts': conflicts,
            'google_calendar_connected': google_connected,
            'google_conflicts': google_conflicts,
            'available': (in_slot if slots else True) and len(conflicts) == 0 and len(google_conflicts) == 0,
        })
    return {'results': results}


# ---- Interview kits ----

@router.get('/interview-kits')
async def list_kits(stage: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {'stage': stage} if stage else {}
    return clean(await db.interview_kits.find(q, {'_id': 0}).to_list(100))


class KitBody(BaseModel):
    stage: str
    title: str
    questions: list[str] = []
    guidelines: Optional[str] = None


@router.post('/interview-kits')
async def create_kit(body: KitBody, user: dict = Depends(require_roles('admin'))):
    kit = {'id': new_id(), **body.model_dump(), 'created_at': now_iso()}
    await db.interview_kits.insert_one(kit)
    await log_audit(user, 'kit_created', 'interview_kit', kit['id'], body.title)
    return clean(kit)


@router.put('/interview-kits/{kit_id}')
async def update_kit(kit_id: str, body: KitBody, user: dict = Depends(require_roles('admin'))):
    await db.interview_kits.update_one({'id': kit_id}, {'$set': body.model_dump()})
    return clean(await db.interview_kits.find_one({'id': kit_id}, {'_id': 0}))


@router.delete('/interview-kits/{kit_id}')
async def delete_kit(kit_id: str, user: dict = Depends(require_roles('admin'))):
    await db.interview_kits.delete_one({'id': kit_id})
    return {'ok': True}
