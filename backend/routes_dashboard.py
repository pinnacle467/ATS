from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from auth import get_current_user
from database import db
from utils import clean

router = APIRouter(tags=['dashboard'])


@router.get('/dashboard/stats')
async def stats(job_id: Optional[str] = None, department: Optional[str] = None,
                recruiter_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    job_query = {}
    if department:
        job_query['department'] = department
    jobs = await db.jobs.find(job_query, {'_id': 0}).to_list(500)
    job_ids = [j['id'] for j in jobs]
    if job_id:
        job_ids = [job_id]

    cand_query = {'job_id': {'$in': job_ids}}
    if recruiter_id:
        cand_query['recruiter_id'] = recruiter_id

    open_roles = len([j for j in jobs if j['status'] == 'open' and (not job_id or j['id'] == job_id)])
    active_candidates = await db.candidates.count_documents({**cand_query, 'status': 'active'})

    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)
    iv_query = {'scheduled_at': {'$gte': week_start.isoformat(), '$lt': week_end.isoformat()}, 'status': {'$ne': 'cancelled'}}
    if job_id:
        iv_query['job_id'] = job_id
    interviews_this_week = await db.interviews.count_documents(iv_query)

    offers = await db.candidates.count_documents({**cand_query, 'stage': 'Offer', 'status': 'active'})

    hired = await db.candidates.find({**cand_query, 'status': 'hired', 'hired_at': {'$ne': None}}, {'_id': 0}).to_list(1000)
    tth_days = []
    for h in hired:
        try:
            a = datetime.fromisoformat(h['applied_at'])
            b = datetime.fromisoformat(h['hired_at'])
            tth_days.append((b - a).days)
        except (ValueError, TypeError, KeyError):
            continue
    time_to_hire_avg = round(sum(tth_days) / len(tth_days), 1) if tth_days else None

    # pipeline snapshot: counts per stage across filtered jobs (active pipeline incl offer)
    pipeline = {}
    stage_order = []
    settings = await db.settings.find_one({'key': 'pipeline_stages'})
    if settings:
        stage_order = [s['name'] for s in settings['stages']]
    async for doc in db.candidates.aggregate([
        {'$match': cand_query},
        {'$group': {'_id': '$stage', 'count': {'$sum': 1}}},
    ]):
        pipeline[doc['_id']] = doc['count']
    ordered = [{'stage': s, 'count': pipeline.get(s, 0)} for s in stage_order] if stage_order else \
        [{'stage': k, 'count': v} for k, v in pipeline.items()]

    return {
        'open_roles': open_roles,
        'active_candidates': active_candidates,
        'interviews_this_week': interviews_this_week,
        'offers_pending': offers,
        'time_to_hire_avg': time_to_hire_avg,
        'pipeline': ordered,
    }


@router.get('/dashboard/my-tasks')
async def my_tasks(user: dict = Depends(get_current_user)):
    tasks = []
    now_iso_str = datetime.now(timezone.utc).isoformat()
    if user['role'] in ('recruiter', 'admin'):
        # candidates in Interview stage without upcoming interview -> to schedule
        q = {'stage': {'$in': ['Interview', 'Screening']}, 'status': 'active'}
        if user['role'] == 'recruiter':
            q['recruiter_id'] = user['id']
        cands = await db.candidates.find(q, {'_id': 0}).to_list(500)
        for c in cands:
            upcoming = await db.interviews.count_documents({'candidate_id': c['id'], 'status': 'scheduled', 'scheduled_at': {'$gte': now_iso_str}})
            if upcoming == 0:
                tasks.append({'type': 'schedule', 'label': f"Schedule {c['stage'].lower()} interview for {c['name']}", 'link': f"/candidates/{c['id']}"})
        # offers awaiting
        oq = {'stage': 'Offer', 'status': 'active'}
        if user['role'] == 'recruiter':
            oq['recruiter_id'] = user['id']
        offers = await db.candidates.find(oq, {'_id': 0}).to_list(100)
        for o in offers:
            tasks.append({'type': 'offer', 'label': f"Offer pending for {o['name']}", 'link': f"/candidates/{o['id']}"})
    # pending feedback for interviewer (and admins who are interviewers)
    ivs = await db.interviews.find({'interviewer_ids': user['id'], 'status': {'$in': ['feedback_pending', 'scheduled']}}, {'_id': 0}).to_list(200)
    cands = {c['id']: c for c in await db.candidates.find({}, {'_id': 0, 'id': 1, 'name': 1}).to_list(3000)}
    for iv in ivs:
        submitted = await db.scorecards.find_one({'interview_id': iv['id'], 'interviewer_id': user['id']})
        cname = cands.get(iv['candidate_id'], {}).get('name', 'candidate')
        if iv['status'] == 'feedback_pending' and not submitted:
            tasks.append({'type': 'feedback', 'label': f'Submit scorecard for {cname}', 'link': '/interviews'})
        elif iv['status'] == 'scheduled' and iv.get('scheduled_at', '') >= now_iso_str:
            tasks.append({'type': 'upcoming', 'label': f"Upcoming {iv.get('type', '').replace('_', ' ')} with {cname}", 'link': '/interviews'})
    return tasks[:15]


@router.get('/activities')
async def activities(limit: int = 20, user: dict = Depends(get_current_user)):
    items = await db.activities.find({}, {'_id': 0}).sort('created_at', -1).to_list(min(limit, 100))
    return items
