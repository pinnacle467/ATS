from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user, require_roles
from database import db
from utils import clean, log_activity, log_audit, new_id, now_iso

router = APIRouter(prefix='/jobs', tags=['jobs'])

DEFAULT_STAGES = ['Applied', 'Screening', 'Interview', 'Offer', 'Hired', 'Rejected']


class JobCreate(BaseModel):
    title: str
    department: str
    location: Optional[str] = None
    description: Optional[str] = None
    stages: Optional[list[str]] = None
    recruiter_id: Optional[str] = None
    status: str = 'open'


class JobUpdate(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    stages: Optional[list[str]] = None
    recruiter_id: Optional[str] = None
    status: Optional[str] = None


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
    return jobs


@router.get('/{job_id}')
async def get_job(job_id: str, user: dict = Depends(get_current_user)):
    job = await db.jobs.find_one({'id': job_id}, {'_id': 0})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    return job


@router.post('')
async def create_job(body: JobCreate, user: dict = Depends(require_roles('admin', 'recruiter'))):
    settings = await db.settings.find_one({'key': 'pipeline_stages'})
    default_stages = [s['name'] for s in settings['stages']] if settings else DEFAULT_STAGES
    job = {
        'id': new_id(),
        'title': body.title,
        'department': body.department,
        'location': body.location,
        'description': body.description,
        'stages': body.stages or default_stages,
        'recruiter_id': body.recruiter_id or user['id'],
        'status': body.status,
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
