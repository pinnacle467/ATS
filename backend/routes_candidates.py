import csv
import io
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import get_current_user, interviewer_candidate_ids, require_roles
from database import db
from fit_scorer import recompute_candidate_fit
from permissions import (
    is_admin_or_higher,
    is_interview_panel,
    is_vendor,
    strip_candidate_sensitive,
    visible_job_ids_for_user,
)
from utils import clean, log_activity, log_audit, new_id, next_candidate_code, notify, now_iso

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
    notice_period: Optional[str] = None
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
    notice_period: Optional[str] = None


class StageMove(BaseModel):
    stage: str
    reason: Optional[str] = None


class NoteCreate(BaseModel):
    text: str
    note_type: str = 'note'  # note | email_log


class BulkAction(BaseModel):
    candidate_ids: list[str]
    action: str  # move_stage | reject | tag | assign | change_source | delete
    stage: Optional[str] = None
    reason: Optional[str] = None
    tag: Optional[str] = None
    recruiter_id: Optional[str] = None
    source: Optional[str] = None


async def _visible_query(user: dict) -> dict:
    """Restrict candidate visibility based on the caller's role.
      - super_admin/admin: no restriction
      - interview_panel: only candidates on jobs they are on the team of
      - vendor: only candidates they submitted (candidate.submitted_by == user.id)
                AND on a job they are on the team of
      - legacy 'interviewer' (pre-migration): only candidates from their assigned interviews
    """
    if is_admin_or_higher(user):
        return {}
    role = user.get('role')
    if role == 'interviewer':
        # Legacy interviewer: keep old behaviour (assigned interviews)
        ids = await interviewer_candidate_ids(user['id'])
        return {'id': {'$in': ids}}
    if is_interview_panel(user):
        job_ids = await visible_job_ids_for_user(db, user)
        return {'job_id': {'$in': job_ids}} if job_ids else {'id': {'$in': []}}
    if is_vendor(user):
        job_ids = await visible_job_ids_for_user(db, user)
        if not job_ids:
            return {'id': {'$in': []}}
        # Vendors only see their own submitted candidates
        return {'job_id': {'$in': job_ids}, 'submitted_by': user['id']}
    # Unknown role — deny everything
    return {'id': {'$in': []}}


def _apply_candidate_visibility(cand: Optional[dict], user: dict) -> Optional[dict]:
    """Strip sensitive candidate fields for interview_panel users."""
    if not cand:
        return cand
    if is_interview_panel(user) or user.get('role') == 'interviewer':
        strip_candidate_sensitive(cand)
    return cand


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
    # enrich with job title + code + recruiter name
    jobs = {j['id']: j for j in await db.jobs.find({}, {'_id': 0, 'id': 1, 'title': 1, 'job_code': 1}).to_list(500)}
    users = {u['id']: u for u in await db.users.find({}, {'_id': 0, 'id': 1, 'name': 1}).to_list(500)}
    for c in items:
        job = jobs.get(c.get('job_id'), {})
        c['job_title'] = job.get('title')
        c['job_code'] = job.get('job_code')
        c['recruiter_name'] = users.get(c.get('recruiter_id'), {}).get('name')
        _apply_candidate_visibility(c, user)
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
    w.writerow(['Candidate ID', 'Name', 'Email', 'Phone', 'Title', 'Company', 'Location', 'Job', 'Stage', 'Status', 'Source', 'Recruiter', 'Tags', 'Skills', 'Applied At'])
    for c in items:
        w.writerow([
            c.get('candidate_code'), c.get('name'), c.get('email'), c.get('phone'), c.get('current_title'), c.get('current_company'),
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
    if user.get('role') == 'interviewer':
        allowed = await interviewer_candidate_ids(user['id'])
        if candidate_id not in allowed:
            raise HTTPException(status_code=403, detail='Not authorized to view this candidate')
    c = await db.candidates.find_one({'id': candidate_id}, {'_id': 0})
    if not c:
        raise HTTPException(status_code=404, detail='Candidate not found')
    # RBAC: non-admin must have visibility to this candidate
    if not is_admin_or_higher(user):
        vis = await _visible_query(user)
        # Vendors are additionally restricted to candidates they submitted
        if is_vendor(user) and c.get('submitted_by') != user.get('id'):
            raise HTTPException(status_code=403, detail='Not authorized to view this candidate')
        if is_interview_panel(user):
            allowed_job_ids = await visible_job_ids_for_user(db, user)
            if c.get('job_id') not in allowed_job_ids:
                raise HTTPException(status_code=403, detail='Not authorized to view this candidate')
    job = await db.jobs.find_one({'id': c.get('job_id')}, {'_id': 0}) if c.get('job_id') else None
    rec = await db.users.find_one({'id': c.get('recruiter_id')}, {'_id': 0, 'id': 1, 'name': 1}) if c.get('recruiter_id') else None
    c['job'] = job
    c['recruiter'] = rec
    # Strip sensitive fields for interview_panel
    _apply_candidate_visibility(c, user)
    # Also strip job's sensitive fields when embedded
    if job and (is_interview_panel(user) or is_vendor(user)):
        team = (job.get('team_members') or [])
        my_entry = next((m for m in team if m.get('user_id') == user.get('id')), None)
        if not (my_entry and my_entry.get('salary_visible')):
            from permissions import strip_job_sensitive
            strip_job_sensitive(c['job'])
    return c


@router.post('')
async def create_candidate(body: CandidateCreate, background_tasks: BackgroundTasks, user: dict = Depends(require_roles('admin', 'recruiter', 'vendor'))):
    # Vendors can only add candidates to jobs they're on the team of
    if is_vendor(user):
        if not body.job_id:
            raise HTTPException(status_code=422, detail='Vendors must specify a job_id when adding candidates')
        allowed = await visible_job_ids_for_user(db, user)
        if body.job_id not in allowed:
            raise HTTPException(status_code=403, detail='You are not on the team for this job')
    stage = body.stage
    if body.job_id and not stage:
        job = await db.jobs.find_one({'id': body.job_id})
        stage = (job.get('stages') or ['Applied'])[0] if job else 'Applied'
    cand = {
        'id': new_id(),
        'candidate_code': await next_candidate_code(),
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
        'source': 'vendor' if is_vendor(user) else body.source,
        'recruiter_id': body.recruiter_id or user['id'],
        'submitted_by': user['id'],
        'submitted_by_name': user.get('name'),
        'tags': body.tags,
        'resume_file_id': body.resume_file_id,
        'low_confidence_fields': body.low_confidence_fields,
        'notice_period': body.notice_period,
        'status': 'active',
        'rejection_reason': None,
        'fit_score': None,
        'fit_score_summary': None,
        'fit_score_computed_at': None,
        'applied_at': now_iso(),
        'hired_at': None,
        'created_at': now_iso(),
        'updated_at': now_iso(),
    }
    await db.candidates.insert_one(cand)
    await log_activity(user, 'application', f'added candidate {body.name}', candidate_id=cand['id'], job_id=body.job_id)
    await log_audit(user, 'candidate_created', 'candidate', cand['id'], f'{body.name} ({body.email or "no email"})')
    if body.notes:
        await db.notes.insert_one({'id': new_id(), 'candidate_id': cand['id'], 'author_id': user['id'],
                                   'author_name': user['name'], 'text': body.notes, 'note_type': 'note', 'created_at': now_iso()})
    if cand['job_id']:
        background_tasks.add_task(recompute_candidate_fit, cand['id'])
    return clean(cand)


@router.put('/{candidate_id}')
async def update_candidate(candidate_id: str, body: CandidateUpdate, background_tasks: BackgroundTasks, user: dict = Depends(require_roles('admin', 'recruiter'))):
    c = await db.candidates.find_one({'id': candidate_id})
    if not c:
        raise HTTPException(status_code=404, detail='Candidate not found')
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    # Build field-level diff for the audit trail — the change log surfaces this per candidate
    change_details = []
    for k, v in updates.items():
        if k == 'updated_at':
            continue
        old_v = c.get(k)
        if old_v != v:
            def _repr(x):
                if x is None:
                    return '(empty)'
                s = str(x)
                return s if len(s) <= 60 else s[:57] + '...'
            change_details.append(f'{k}: {_repr(old_v)} → {_repr(v)}')
    updates['updated_at'] = now_iso()
    if 'recruiter_id' in updates and updates['recruiter_id'] != c.get('recruiter_id'):
        await notify(updates['recruiter_id'], 'assignment', f"Candidate {c['name']} was assigned to you", f"/candidates/{candidate_id}")
    await db.candidates.update_one({'id': candidate_id}, {'$set': updates})
    if change_details:
        await log_audit(user, 'candidate_updated', 'candidate', candidate_id, '; '.join(change_details))
    if 'job_id' in updates and updates['job_id'] != c.get('job_id'):
        background_tasks.add_task(recompute_candidate_fit, candidate_id)
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
    if body.action == 'delete' and not is_admin_or_higher(user):
        raise HTTPException(status_code=403, detail='Only admins can delete candidates')
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
        elif body.action == 'change_source' and body.source:
            old_source = c.get('source') or '(empty)'
            await db.candidates.update_one({'id': cid}, {'$set': {'source': body.source, 'updated_at': now_iso()}})
            await log_activity(user, 'source_changed', f"changed source of {c['name']} from {old_source} to {body.source}", candidate_id=cid)
            await log_audit(user, 'source_changed', 'candidate', cid, f'source: {old_source} → {body.source}')
        elif body.action == 'delete':
            await db.candidates.delete_one({'id': cid})
            await db.notes.delete_many({'candidate_id': cid})
            await log_activity(user, 'candidate_deleted', f"deleted {c['name']}", candidate_id=cid)
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
    # Legacy interviewer
    if user.get('role') == 'interviewer':
        allowed = await interviewer_candidate_ids(user['id'])
        if candidate_id not in allowed:
            raise HTTPException(status_code=403, detail='Not authorized')
    c = await db.candidates.find_one({'id': candidate_id})
    if not c:
        raise HTTPException(status_code=404, detail='Candidate not found')
    # Interview Panel — must have visibility to this candidate via job team
    if is_interview_panel(user):
        allowed_jobs = await visible_job_ids_for_user(db, user)
        if c.get('job_id') not in allowed_jobs:
            raise HTTPException(status_code=403, detail='Not authorized')
    # Vendor — only their own candidates
    if is_vendor(user):
        if c.get('submitted_by') != user.get('id'):
            raise HTTPException(status_code=403, detail='Not authorized')
    note = {'id': new_id(), 'candidate_id': candidate_id, 'author_id': user['id'], 'author_name': user['name'],
            'text': body.text, 'note_type': body.note_type, 'created_at': now_iso()}
    await db.notes.insert_one(note)
    label = 'logged an email for' if body.note_type == 'email_log' else 'added a note on'
    await log_activity(user, body.note_type, f"{label} {c['name']}", candidate_id=candidate_id)
    return clean(note)


class MergeResume(BaseModel):
    file_id: str
    parsed: dict = {}


@router.post('/{candidate_id}/merge-resume')
async def merge_resume(candidate_id: str, body: MergeResume, background_tasks: BackgroundTasks, user: dict = Depends(require_roles('admin', 'recruiter'))):
    cand = await db.candidates.find_one({'id': candidate_id})
    if not cand:
        raise HTTPException(status_code=404, detail='Candidate not found')
    p = body.parsed or {}
    updates = {'resume_file_id': body.file_id, 'updated_at': now_iso()}
    for f in ['name', 'email', 'phone', 'current_title', 'current_company', 'location', 'notice_period']:
        val = p.get(f)
        if val:
            updates[f] = val
    for f in ['experience', 'education', 'skills']:
        val = p.get(f)
        if val:
            updates[f] = val
    await db.candidates.update_one({'id': candidate_id}, {'$set': updates})
    await log_activity(user, 'resume_merged', f"Matched and merged an uploaded resume into {cand['name']}'s profile", candidate_id=candidate_id)
    await log_audit(user, 'merge_resume', 'candidate', candidate_id, cand['name'])
    if cand.get('job_id'):
        background_tasks.add_task(recompute_candidate_fit, candidate_id)
    updated = await db.candidates.find_one({'id': candidate_id})
    updated.pop('_id', None)
    return updated


@router.get('/{candidate_id}/timeline')
async def timeline(candidate_id: str, user: dict = Depends(get_current_user)):
    # Access check: same as get_candidate
    if user.get('role') == 'interviewer':
        allowed = await interviewer_candidate_ids(user['id'])
        if candidate_id not in allowed:
            raise HTTPException(status_code=403, detail='Not authorized')
    elif is_interview_panel(user):
        # New interview_panel: allowed if candidate's job is in their team
        c = await db.candidates.find_one({'id': candidate_id}, {'_id': 0, 'job_id': 1})
        allowed_jobs = await visible_job_ids_for_user(db, user)
        if not c or c.get('job_id') not in allowed_jobs:
            raise HTTPException(status_code=403, detail='Not authorized')
    elif is_vendor(user):
        c = await db.candidates.find_one({'id': candidate_id}, {'_id': 0, 'submitted_by': 1})
        if not c or c.get('submitted_by') != user.get('id'):
            raise HTTPException(status_code=403, detail='Not authorized')

    notes = await db.notes.find({'candidate_id': candidate_id}, {'_id': 0}).to_list(500)
    acts = await db.activities.find({'candidate_id': candidate_id}, {'_id': 0}).to_list(500)

    # Interview Panel — hide recruiter-internal notes and activities.
    # They can only see: their own notes, and activities that are candidate-lifecycle
    # (application, stage_change, interview_scheduled, feedback_submitted, resume_merged, hired).
    # Anything email/note-related from OTHER users is hidden.
    if is_interview_panel(user) or user.get('role') == 'interviewer':
        my_id = user.get('id')
        notes = [n for n in notes if n.get('author_id') == my_id]
        INTERNAL_ACTIVITY_TYPES = {'note', 'email_log', 'email_sent'}
        acts = [
            a for a in acts
            if a.get('type') not in INTERNAL_ACTIVITY_TYPES or a.get('actor_id') == my_id
        ]
    events = [{'kind': 'note', **n} for n in notes] + [{'kind': 'activity', **a} for a in acts]
    events.sort(key=lambda e: e.get('created_at', ''), reverse=True)
    return events
