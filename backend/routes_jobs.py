import base64
import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from auth import get_current_user, require_roles
from database import db
from fit_scorer import recompute_job_candidates_fit
from permissions import (
    is_admin_or_higher,
    is_interview_panel,
    is_super_admin,
    is_vendor,
    strip_job_sensitive,
)
from resume_parser import extract_text_from_bytes
from utils import clean, log_activity, log_audit, new_id, next_job_code, now_iso, slugify

router = APIRouter(prefix='/jobs', tags=['jobs'])

DEFAULT_STAGES = ['Applied', 'Screening', 'Interview', 'Offer', 'Hired', 'Rejected']
APP_BASE_URL = os.environ['APP_BASE_URL']


class JobCreate(BaseModel):
    title: str
    department: str
    location: Optional[str] = None
    description: Optional[str] = None
    stages: Optional[list[str]] = None
    recruiter_id: Optional[str] = None
    status: str = 'open'
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    remote_type: Optional[str] = None
    salary_range: Optional[str] = None
    budget: Optional[str] = None


class JobUpdate(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    stages: Optional[list[str]] = None
    recruiter_id: Optional[str] = None
    status: Optional[str] = None
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    remote_type: Optional[str] = None
    salary_range: Optional[str] = None
    budget: Optional[str] = None


def _apply_job_visibility(job: dict, user: dict) -> dict:
    """Strip sensitive fields from a job dict based on the caller's role and their
    team_members entry on this job. Called on every list/detail response."""
    if is_admin_or_higher(user):
        return job
    # For interview_panel/vendor: check if they have salary_visible on this job's team
    team = job.get('team_members') or []
    my_entry = next((m for m in team if m.get('user_id') == user.get('id')), None)
    salary_visible = bool(my_entry and my_entry.get('salary_visible'))
    if not salary_visible:
        strip_job_sensitive(job)
    return job


async def _unique_slug(title: str) -> str:
    base = slugify(title)
    slug = base
    i = 2
    while await db.jobs.find_one({'slug': slug}):
        slug = f'{base}-{i}'
        i += 1
    return slug


@router.get('')
async def list_jobs(status: Optional[str] = None, department: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {}
    if status:
        q['status'] = status
    if department:
        q['department'] = department
    # Visibility filter: interview_panel/vendor see only jobs they're on the team of
    if not is_admin_or_higher(user):
        q['team_members.user_id'] = user['id']
    jobs = await db.jobs.find(q, {'_id': 0}).sort('created_at', -1).to_list(500)
    # attach candidate counts + strip sensitive fields for non-admins
    for j in jobs:
        j['candidate_count'] = await db.candidates.count_documents({'job_id': j['id'], 'status': 'active'})
        j['has_jd'] = bool(j.get('jd_text'))
        j['public_url'] = f"{APP_BASE_URL}/careers/jobs/{j['slug']}" if j.get('slug') else None
        _apply_job_visibility(j, user)
    return jobs


@router.get('/{job_id}')
async def get_job(job_id: str, user: dict = Depends(get_current_user)):
    job = await db.jobs.find_one({'id': job_id}, {'_id': 0})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    # Non-admin caller must be on the team of this job
    if not is_admin_or_higher(user):
        team = job.get('team_members') or []
        if not any(m.get('user_id') == user.get('id') for m in team):
            raise HTTPException(status_code=403, detail='You do not have access to this job')
    job['has_jd'] = bool(job.get('jd_text'))
    job['public_url'] = f"{APP_BASE_URL}/careers/jobs/{job['slug']}" if job.get('slug') else None
    _apply_job_visibility(job, user)
    return job


@router.post('')
async def create_job(body: JobCreate, user: dict = Depends(require_roles('admin', 'recruiter'))):
    settings = await db.settings.find_one({'key': 'pipeline_stages'})
    default_stages = [s['name'] for s in settings['stages']] if settings else DEFAULT_STAGES
    job = {
        'id': new_id(),
        'job_code': await next_job_code(),
        'slug': await _unique_slug(body.title),
        'title': body.title,
        'department': body.department,
        'location': body.location,
        'description': body.description,
        'stages': body.stages or default_stages,
        'recruiter_id': body.recruiter_id or user['id'],
        'status': body.status,
        'employment_type': body.employment_type,
        'experience_level': body.experience_level,
        'remote_type': body.remote_type,
        'salary_range': body.salary_range,
        'budget': body.budget,
        'team_members': [],
        'published': False,
        'created_at': now_iso(),
        'updated_at': now_iso(),
    }
    await db.jobs.insert_one(job)
    await log_activity(user, 'job_created', f"created job \"{body.title}\"", job_id=job['id'])
    await log_audit(user, 'job_created', 'job', job['id'], body.title)
    return clean(job)


@router.put('/{job_id}')
async def update_job(job_id: str, body: JobUpdate, user: dict = Depends(require_roles('admin', 'recruiter'))):
    job = await db.jobs.find_one({'id': job_id})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    # Field-level diff for the change log
    change_details = []
    for k, v in updates.items():
        old_v = job.get(k)
        if old_v != v:
            def _repr(x):
                if x is None:
                    return '(empty)'
                s = str(x)
                return s if len(s) <= 60 else s[:57] + '...'
            change_details.append(f'{k}: {_repr(old_v)} → {_repr(v)}')
    updates['updated_at'] = now_iso()
    await db.jobs.update_one({'id': job_id}, {'$set': updates})
    if change_details:
        await log_audit(user, 'job_updated', 'job', job_id, '; '.join(change_details))
    if 'status' in updates and updates['status'] != job.get('status'):
        await log_activity(user, 'job_status', f"marked job \"{job['title']}\" as {updates['status']}", job_id=job_id)
    return clean(await db.jobs.find_one({'id': job_id}, {'_id': 0}))


@router.delete('/{job_id}')
async def delete_job(job_id: str, user: dict = Depends(require_roles('admin'))):
    job = await db.jobs.find_one({'id': job_id})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    await db.jobs.delete_one({'id': job_id})
    await log_audit(user, 'job_deleted', 'job', job_id, job.get('title', ''))
    return {'ok': True}


@router.post('/{job_id}/jd')
async def upload_jd(
    job_id: str,
    background_tasks: BackgroundTasks,
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    user: dict = Depends(require_roles('admin', 'recruiter')),
):
    job = await db.jobs.find_one({'id': job_id})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')

    jd_file_id = None
    jd_filename = None
    if file is not None and file.filename:
        data = await file.read()
        try:
            jd_text = extract_text_from_bytes(data, file.filename)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        if len(jd_text) < 20:
            raise HTTPException(status_code=422, detail='Could not extract readable text from this file')
        jd_file_id = new_id()
        await db.files.insert_one({
            'id': jd_file_id, 'filename': file.filename, 'content_type': file.content_type or 'application/octet-stream',
            'size': len(data), 'data_b64': base64.b64encode(data).decode(), 'uploaded_by': user['id'], 'created_at': now_iso(),
        })
        jd_filename = file.filename
    elif text and text.strip():
        jd_text = text.strip()
    else:
        raise HTTPException(status_code=422, detail='Provide either JD text or a file')

    await db.jobs.update_one({'id': job_id}, {'$set': {
        'jd_text': jd_text, 'jd_file_id': jd_file_id, 'jd_filename': jd_filename, 'jd_updated_at': now_iso(),
    }})
    await log_audit(user, 'jd_updated', 'job', job_id, job['title'])
    background_tasks.add_task(recompute_job_candidates_fit, job_id)
    updated = await db.jobs.find_one({'id': job_id}, {'_id': 0})
    updated['has_jd'] = True
    return clean(updated)


@router.delete('/{job_id}/jd')
async def delete_jd(job_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    job = await db.jobs.find_one({'id': job_id})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    await db.jobs.update_one({'id': job_id}, {'$set': {'jd_text': None, 'jd_file_id': None, 'jd_filename': None, 'jd_updated_at': None}})
    await db.candidates.update_many({'job_id': job_id}, {'$set': {'fit_score': None, 'fit_score_summary': None, 'fit_score_computed_at': None}})
    await log_audit(user, 'jd_removed', 'job', job_id, job['title'])
    return {'ok': True}


@router.post('/{job_id}/publish')
async def publish_job(job_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    job = await db.jobs.find_one({'id': job_id})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    if job.get('status') != 'open':
        raise HTTPException(status_code=400, detail='Job must be Open to publish it to the career portal')
    if not job.get('slug'):
        await db.jobs.update_one({'id': job_id}, {'$set': {'slug': await _unique_slug(job['title'])}})
    await db.jobs.update_one({'id': job_id}, {'$set': {'published': True, 'updated_at': now_iso()}})
    await log_audit(user, 'job_published', 'job', job_id, job['title'])
    updated = await db.jobs.find_one({'id': job_id}, {'_id': 0})
    updated['public_url'] = f"{APP_BASE_URL}/careers/jobs/{updated['slug']}"
    return clean(updated)


@router.post('/{job_id}/unpublish')
async def unpublish_job(job_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    job = await db.jobs.find_one({'id': job_id})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    await db.jobs.update_one({'id': job_id}, {'$set': {'published': False, 'updated_at': now_iso()}})
    await log_audit(user, 'job_unpublished', 'job', job_id, job['title'])
    return clean(await db.jobs.find_one({'id': job_id}, {'_id': 0}))


# ==================== Team Management ====================
# Admin+ can add/remove users to a specific job. Interview-panel users see the
# job only if they're on the team; vendors see the job only if they're on the
# team AND their candidates are filtered to those they submitted.

class TeamAdd(BaseModel):
    user_id: str
    role_on_job: str  # 'interview_panel' | 'vendor'
    salary_visible: bool = False


class TeamPatch(BaseModel):
    salary_visible: Optional[bool] = None
    role_on_job: Optional[str] = None


@router.get('/{job_id}/team')
async def list_job_team(job_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    job = await db.jobs.find_one({'id': job_id}, {'_id': 0, 'team_members': 1, 'title': 1})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    members = job.get('team_members') or []
    # Enrich with user info
    if members:
        user_ids = [m['user_id'] for m in members]
        users = await db.users.find({'id': {'$in': user_ids}}, {'_id': 0, 'password_hash': 0}).to_list(len(user_ids))
        by_id = {u['id']: u for u in users}
        for m in members:
            u = by_id.get(m['user_id'])
            if u:
                m['user_name'] = u.get('name')
                m['user_email'] = u.get('email')
                m['user_role'] = u.get('role')
                m['user_active'] = u.get('active', True)
    return {'job_id': job_id, 'members': members}


@router.post('/{job_id}/team')
async def add_job_team_member(job_id: str, body: TeamAdd, user: dict = Depends(require_roles('admin', 'recruiter'))):
    if body.role_on_job not in ('interview_panel', 'vendor'):
        raise HTTPException(status_code=422, detail='role_on_job must be interview_panel or vendor')
    job = await db.jobs.find_one({'id': job_id})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    target = await db.users.find_one({'id': body.user_id}, {'_id': 0, 'password_hash': 0})
    if not target:
        raise HTTPException(status_code=404, detail='User not found')
    # Sanity: the target user's global role should match what we're granting them
    # (a super_admin doesn't need job assignment, they already see everything)
    if target.get('role') in ('super_admin', 'admin', 'recruiter'):
        raise HTTPException(status_code=422, detail=f'{target["email"]} is an {target["role"]} — they already have global access; no need to add them to a job team')
    # Prevent duplicates
    existing = [m for m in (job.get('team_members') or []) if m.get('user_id') == body.user_id]
    if existing:
        raise HTTPException(status_code=409, detail='User is already on this job team')
    member = {
        'user_id': body.user_id,
        'role_on_job': body.role_on_job,
        'salary_visible': bool(body.salary_visible),
        'added_by': user['id'],
        'added_by_name': user.get('name'),
        'added_at': now_iso(),
    }
    await db.jobs.update_one({'id': job_id}, {'$push': {'team_members': member}, '$set': {'updated_at': now_iso()}})
    await log_audit(user, 'job_team_added', 'job', job_id,
                    f'{target.get("email")} as {body.role_on_job} (salary_visible={body.salary_visible})')
    return {'ok': True, 'member': {**member, 'user_name': target.get('name'), 'user_email': target.get('email'), 'user_role': target.get('role')}}


@router.patch('/{job_id}/team/{user_id}')
async def patch_job_team_member(job_id: str, user_id: str, body: TeamPatch, user: dict = Depends(require_roles('admin', 'recruiter'))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=422, detail='Nothing to update')
    if 'role_on_job' in updates and updates['role_on_job'] not in ('interview_panel', 'vendor'):
        raise HTTPException(status_code=422, detail='role_on_job must be interview_panel or vendor')
    set_updates = {f'team_members.$.{k}': v for k, v in updates.items()}
    r = await db.jobs.update_one(
        {'id': job_id, 'team_members.user_id': user_id},
        {'$set': {**set_updates, 'updated_at': now_iso()}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail='Job team member not found')
    target = await db.users.find_one({'id': user_id}, {'_id': 0, 'email': 1})
    await log_audit(user, 'job_team_updated', 'job', job_id,
                    f'{(target or {}).get("email", user_id)}: {", ".join(f"{k}={v}" for k, v in updates.items())}')
    return {'ok': True}


@router.delete('/{job_id}/team/{user_id}')
async def remove_job_team_member(job_id: str, user_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    r = await db.jobs.update_one(
        {'id': job_id},
        {'$pull': {'team_members': {'user_id': user_id}}, '$set': {'updated_at': now_iso()}},
    )
    if r.modified_count == 0:
        raise HTTPException(status_code=404, detail='Job team member not found')
    target = await db.users.find_one({'id': user_id}, {'_id': 0, 'email': 1})
    await log_audit(user, 'job_team_removed', 'job', job_id, (target or {}).get('email', user_id))
    return {'ok': True}
