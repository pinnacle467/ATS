import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import get_current_user, interviewer_candidate_ids, require_roles
from database import db
from utils import clean, log_activity, log_audit, new_id, notify, now_iso

router = APIRouter(prefix='/candidates', tags=['candidates'])


class CandidateCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None
    experience: list = []
    education: list = []
    skills: list[str] = []
    job_id: Optional[str] = None
    stage: Optional[str] = None
    source: str = 'career_site'
    recruiter_id: Optional[str] = None
    tags: list[str] = []
    resume_file_id: Optional[str] = None
    low_confidence_fields: list[str] = []
    notes: Optional[str] = None


class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None
    experience: Optional[list] = None
    education: Optional[list] = None
    skills: Optional[list[str]] = None
    job_id: Optional[str] = None
    source: Optional[str] = None
    recruiter_id: Optional[str] = None
    tags: Optional[list[str]] = None
    low_confidence_fields: Optional[list[str]] = None


class StageMove(BaseModel):
    stage: str
    reason: Optional[str] = None


class NoteCreate(BaseModel):
    text: str
    note_type: str = 'note'  # note | email_log


class BulkAction(BaseModel):
    candidate_ids: list[str]
    action: str  # move_stage | reject | tag | assign
    stage: Optional[str] = None
    reason: Optional[str] = None
    tag: Optional[str] = None
    recruiter_id: Optional[str] = None


async def _visible_query(user: dict) -> dict:
    if user['role'] == 'interviewer':
        ids = await interviewer_candidate_ids(user['id'])
        return {'id': {'$in': ids}}
    return {}


def _build_filters(q, job_id, stage, source, recruiter_id, tag, status):
    query = {}
    if q:
        query['$or'] = [
            {'name': {'$regex': q, '$options': 'i'}},
            {'email': {'$regex': q, '$options': 'i'}},
            {'current_title': {'$regex': q, '$options': 'i'}},
            {'current_company': {'$regex': q, '$options': 'i'}},
            {'skills': {'$regex': q, '$options': 'i'}},
        ]
    if job_id:
        query['job_id'] = job_id
    if stage:
        query['stage'] = stage
    if source:
        query['source'] = source
    if recruiter_id:
        query['recruiter_id'] = recruiter_id
    if tag:
        query['tags'] = tag
    if status:
        query['status'] = status
    return query


@router.get('')
async def list_candidates(
    q: Optional[str] = None,
    job_id: Optional[str] = None,
    stage: Optional[str] = None,
    source: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    tag: Optional[str] = None,
    status: Optional[str] = None,
    sort: str = 'created_at',
    order: int = -1,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    query = _build_filters(q, job_id, stage, source, recruiter_id, tag, status)
    vis = await _visible_query(user)
    query.update(vis)
    total = await db.candidates.count_documents(query)
    items = await db.candidates.find(query, {'_id': 0}).sort(sort, order).skip((page - 1) * limit).to_list(limit)
    # enrich with job title + recruiter name
    jobs = {j['id']: j for j in await db.jobs.find({}, {'_id': 0, 'id': 1, 'title': 1}).to_list(500)}
    users = {u['id']: u for u in await db.users.find({}, {'_id': 0, 'id': 1, 'name': 1}).to_list(500)}
    for c in items:
        c['job_title'] = jobs.get(c.get('job_id'), {}).get('title')
        c['recruiter_name'] = users.get(c.get('recruiter_id'), {}).get('name')
    return {'items': items, 'total': total, 'page': page, 'limit': limit}


@router.get('/export/csv')
async def export_csv(
    q: Optional[str] = None,
    job_id: Optional[str] = None,
    stage: Optional[str] = None,
    source: Optional[str] = None,
    recruiter_id: Optional[str] = None,
    tag: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(require_roles('admin', 'recruiter')),
):
    query = _build_filters(q, job_id, stage, source, recruiter_id, tag, status)
    items = await db.candidates.find(query, {'_id': 0}).sort('created_at', -1).to_list(5000)
    jobs = {j['id']: j.get('title') for j in await db.jobs.find({}, {'_id': 0, 'id': 1, 'title': 1}).to_list(500)}
    users = {u['id']: u.get('name') for u in await db.users.find({}, {'_id': 0, 'id': 1, 'name': 1}).to_list(500)}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Name', 'Email', 'Phone', 'Title', 'Company', 'Location', 'Job', 'Stage', 'Status', 'Source', 'Recruiter', 'Tags', 'Skills', 'Applied At'])
    for c in items:
        w.writerow([
            c.get('name'), c.get('email'), c.get('phone'), c.get('current_title'), c.get('current_company'),
            c.get('location'), jobs.get(c.get('job_id'), ''), c.get('stage'), c.get('status'), c.get('source'),
            users.get(c.get('recruiter_id'), ''), '; '.join(c.get('tags') or []), '; '.join(c.get('skills') or []),
            c.get('applied_at', ''),
        ])
    buf.seek(0)
    await log_audit(user, 'candidates_exported', 'candidate', 'bulk', f'{len(items)} rows')
    return StreamingResponse(iter([buf.getvalue()]), media_type='text/csv',
                             headers={'Content-Disposition': 'attachment; filename="candidates.csv"'})


@router.get('/{candidate_id}')
async def get_candidate(candidate_id: str, user: dict = Depends(get_current_user)):
    if user['role'] == 'interviewer':
        allowed = await interviewer_candidate_ids(user['id'])
        if candidate_id not in allowed:
            raise HTTPException(status_code=403, detail='Not authorized to view this candidate')
    c = await db.candidates.find_one({'id': candidate_id}, {'_id': 0})
    if not c:
        raise HTTPException(status_code=404, detail='Candidate not found')
    job = await db.jobs.find_one({'id': c.get('job_id')}, {'_id': 0}) if c.get('job_id') else None
    rec = await db.users.find_one({'id': c.get('recruiter_id')}, {'_id': 0, 'id': 1, 'name': 1}) if c.get('recruiter_id') else None
    c['job'] = job
    c['recruiter'] = rec
    return c


@router.post('')
async def create_candidate(body: CandidateCreate, user: dict = Depends(require_roles('admin', 'recruiter'))):
    stage = body.stage
    if body.job_id and not stage:
        job = await db.jobs.find_one({'id': body.job_id})
        stage = (job.get('stages') or ['Applied'])[0] if job else 'Applied'
    cand = {
        'id': new_id(),
        'name': body.name,
        'email': body.email,
        'phone': body.phone,
        'current_title': body.current_title,
        'current_company': body.current_company,
        'location': body.location,
        'experience': body.experience,
        'education': body.education,
        'skills': body.skills,
        'job_id': body.job_id,
        'stage': stage or 'Applied',
        'source': body.source,
        'recruiter_id': body.recruiter_id or user['id'],
        'tags': body.tags,
        'resume_file_id': body.resume_file_id,
        'low_confidence_fields': body.low_confidence_fields,
        'status': 'active',
        'rejection_reason': None,
        'applied_at': now_iso(),
        'hired_at': None,
        'created_at': now_iso(),
        'updated_at': now_iso(),
    }
    await db.candidates.insert_one(cand)
    await log_activity(user, 'application', f'added candidate {body.name}', candidate_id=cand['id'], job_id=body.job_id)
    if body.notes:
        await db.notes.insert_one({'id': new_id(), 'candidate_id': cand['id'], 'author_id': user['id'],
                                   'author_name': user['name'], 'text': body.notes, 'note_type': 'note', 'created_at': now_iso()})
    return clean(cand)


@router.put('/{candidate_id}')
async def update_candidate(candidate_id: str, body: CandidateUpdate, user: dict = Depends(require_roles('admin', 'recruiter'))):
    c = await db.candidates.find_one({'id': candidate_id})
    if not c:
        raise HTTPException(status_code=404, detail='Candidate not found')
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates['updated_at'] = now_iso()
    if 'recruiter_id' in updates and updates['recruiter_id'] != c.get('recruiter_id'):
        await notify(updates['recruiter_id'], 'assignment', f"Candidate {c['name']} was assigned to you", f"/candidates/{candidate_id}")
    await db.candidates.update_one({'id': candidate_id}, {'$set': updates})
    return clean(await db.candidates.find_one({'id': candidate_id}, {'_id': 0}))


@router.post('/{candidate_id}/move-stage')
async def move_stage(candidate_id: str, body: StageMove, user: dict = Depends(require_roles('admin', 'recruiter'))):
    c = await db.candidates.find_one({'id': candidate_id})
    if not c:
        raise HTTPException(status_code=404, detail='Candidate not found')
    old = c.get('stage')
    updates = {'stage': body.stage, 'updated_at': now_iso()}
    if body.stage == 'Hired':
        updates['status'] = 'hired'
        updates['hired_at'] = now_iso()
    elif body.stage == 'Rejected':
        updates['status'] = 'rejected'
        updates['rejection_reason'] = body.reason
    else:
        updates['status'] = 'active'
    await db.candidates.update_one({'id': candidate_id}, {'$set': updates})
    await log_activity(user, 'stage_change', f"moved {c['name']} from {old} to {body.stage}", candidate_id=candidate_id, job_id=c.get('job_id'))
    await log_audit(user, 'stage_change', 'candidate', candidate_id, f'{old} -> {body.stage}')
    if body.stage == 'Offer' and c.get('recruiter_id') and c['recruiter_id'] != user['id']:
        await notify(c['recruiter_id'], 'offer', f"{c['name']} moved to Offer stage", f"/candidates/{candidate_id}")
    return clean(await db.candidates.find_one({'id': candidate_id}, {'_id': 0}))


@router.post('/bulk-action')
async def bulk_action(body: BulkAction, user: dict = Depends(require_roles('admin', 'recruiter'))):
    count = 0
    for cid in body.candidate_ids:
        c = await db.candidates.find_one({'id': cid})
        if not c:
            continue
        if body.action == 'move_stage' and body.stage:
            updates = {'stage': body.stage, 'updated_at': now_iso()}
            if body.stage == 'Hired':
                updates.update({'status': 'hired', 'hired_at': now_iso()})
            elif body.stage == 'Rejected':
                updates.update({'status': 'rejected', 'rejection_reason': body.reason})
            await db.candidates.update_one({'id': cid}, {'$set': updates})
            await log_activity(user, 'stage_change', f"moved {c['name']} from {c.get('stage')} to {body.stage}", candidate_id=cid)
        elif body.action == 'reject':
            await db.candidates.update_one({'id': cid}, {'$set': {'stage': 'Rejected', 'status': 'rejected', 'rejection_reason': body.reason, 'updated_at': now_iso()}})
            await log_activity(user, 'stage_change', f"rejected {c['name']}" + (f' ({body.reason})' if body.reason else ''), candidate_id=cid)
        elif body.action == 'tag' and body.tag:
            await db.candidates.update_one({'id': cid}, {'$addToSet': {'tags': body.tag}, '$set': {'updated_at': now_iso()}})
        elif body.action == 'assign' and body.recruiter_id:
            await db.candidates.update_one({'id': cid}, {'$set': {'recruiter_id': body.recruiter_id, 'updated_at': now_iso()}})
            await notify(body.recruiter_id, 'assignment', f"Candidate {c['name']} was assigned to you", f'/candidates/{cid}')
        count += 1
    await log_audit(user, f'bulk_{body.action}', 'candidate', 'bulk', f'{count} candidates')
    return {'ok': True, 'count': count}


@router.delete('/{candidate_id}')
async def delete_candidate(candidate_id: str, user: dict = Depends(require_roles('admin'))):
    c = await db.candidates.find_one({'id': candidate_id})
    if not c:
        raise HTTPException(status_code=404, detail='Candidate not found')
    await db.candidates.delete_one({'id': candidate_id})
    await db.notes.delete_many({'candidate_id': candidate_id})
    await log_audit(user, 'candidate_deleted', 'candidate', candidate_id, c.get('name', ''))
    return {'ok': True}


@router.post('/{candidate_id}/notes')
async def add_note(candidate_id: str, body: NoteCreate, user: dict = Depends(get_current_user)):
    if user['role'] == 'interviewer':
        allowed = await interviewer_candidate_ids(user['id'])
        if candidate_id not in allowed:
            raise HTTPException(status_code=403, detail='Not authorized')
    c = await db.candidates.find_one({'id': candidate_id})
    if not c:
        raise HTTPException(status_code=404, detail='Candidate not found')
    note = {'id': new_id(), 'candidate_id': candidate_id, 'author_id': user['id'], 'author_name': user['name'],
            'text': body.text, 'note_type': body.note_type, 'created_at': now_iso()}
    await db.notes.insert_one(note)
    label = 'logged an email for' if body.note_type == 'email_log' else 'added a note on'
    await log_activity(user, body.note_type, f"{label} {c['name']}", candidate_id=candidate_id)
    return clean(note)


@router.get('/{candidate_id}/timeline')
async def timeline(candidate_id: str, user: dict = Depends(get_current_user)):
    if user['role'] == 'interviewer':
        allowed = await interviewer_candidate_ids(user['id'])
        if candidate_id not in allowed:
            raise HTTPException(status_code=403, detail='Not authorized')
    notes = await db.notes.find({'candidate_id': candidate_id}, {'_id': 0}).to_list(500)
    acts = await db.activities.find({'candidate_id': candidate_id}, {'_id': 0}).to_list(500)
    events = [{'kind': 'note', **n} for n in notes] + [{'kind': 'activity', **a} for a in acts]
    events.sort(key=lambda e: e.get('created_at', ''), reverse=True)
    return events
