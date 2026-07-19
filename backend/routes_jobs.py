import base64
import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from auth import get_current_user, require_roles
from database import db
from fit_scorer import recompute_job_candidates_fit
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
    jobs = await db.jobs.find(q, {'_id': 0}).sort('created_at', -1).to_list(500)
    # attach candidate counts
    for j in jobs:
        j['candidate_count'] = await db.candidates.count_documents({'job_id': j['id'], 'status': 'active'})
        j['has_jd'] = bool(j.get('jd_text'))
        j['public_url'] = f"{APP_BASE_URL}/careers/jobs/{j['slug']}" if j.get('slug') else None
    return jobs


@router.get('/{job_id}')
async def get_job(job_id: str, user: dict = Depends(get_current_user)):
    job = await db.jobs.find_one({'id': job_id}, {'_id': 0})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    job['has_jd'] = bool(job.get('jd_text'))
    job['public_url'] = f"{APP_BASE_URL}/careers/jobs/{job['slug']}" if job.get('slug') else None
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
    updates['updated_at'] = now_iso()
    await db.jobs.update_one({'id': job_id}, {'$set': updates})
    await log_audit(user, 'job_updated', 'job', job_id, ', '.join(updates.keys()))
    if 'status' in updates:
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
