"""Career Portal — Phase 1: settings/dashboard (admin) + public jobs & apply flow (no auth)."""
import base64
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from auth import require_roles
from database import db
from fit_scorer import recompute_candidate_fit
from resume_parser import extract_text_from_bytes, parse_resume_text
from routes_resumes import _store_file
from utils import log_activity, new_id, next_candidate_code, notify, now_iso

router = APIRouter(prefix='/career', tags=['career'])

APP_BASE_URL = os.environ['APP_BASE_URL']
MAX_RESUME_SIZE = 10 * 1024 * 1024

DEFAULT_SETTINGS = {
    'key': 'singleton',
    'portal_enabled': False,
    'company_name': 'Our Company',
    'tagline': 'Join our team',
    'headline': "We're hiring",
    'subheadline': 'Explore open roles and help us build something great.',
    'logo_file_id': None,
    'hero_image_url': None,
    'primary_color': '#1a5c47',
    'about_text': '',
    'benefits': [],
}


async def _get_settings() -> dict:
    s = await db.career_settings.find_one({'key': 'singleton'}, {'_id': 0})
    if not s:
        s = {**DEFAULT_SETTINGS, 'created_at': now_iso(), 'updated_at': now_iso()}
        await db.career_settings.insert_one(dict(s))
    return s


def _norm_phone(p: Optional[str]) -> Optional[str]:
    if not p:
        return None
    digits = re.sub(r'\D', '', p)
    return digits[-10:] if len(digits) >= 10 else (digits or None)


def _public_job(job: dict) -> dict:
    return {
        'id': job['id'], 'slug': job.get('slug'), 'title': job['title'], 'department': job.get('department'),
        'location': job.get('location'), 'employment_type': job.get('employment_type'),
        'experience_level': job.get('experience_level'), 'remote_type': job.get('remote_type'),
        'description': job.get('description'), 'jd_text': job.get('jd_text'),
        'created_at': job.get('created_at'),
    }


# ---------------- Admin-side (authenticated) ----------------

@router.get('/settings')
async def get_settings(user: dict = Depends(require_roles('admin', 'recruiter'))):
    s = await _get_settings()
    s['portal_url'] = f'{APP_BASE_URL}/careers'
    return s


class SettingsUpdate(BaseModel):
    portal_enabled: Optional[bool] = None
    company_name: Optional[str] = None
    tagline: Optional[str] = None
    headline: Optional[str] = None
    subheadline: Optional[str] = None
    hero_image_url: Optional[str] = None
    primary_color: Optional[str] = None
    about_text: Optional[str] = None
    benefits: Optional[list[str]] = None


@router.put('/settings')
async def update_settings(body: SettingsUpdate, user: dict = Depends(require_roles('admin', 'recruiter'))):
    await _get_settings()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates['updated_at'] = now_iso()
    await db.career_settings.update_one({'key': 'singleton'}, {'$set': updates}, upsert=True)
    s = await db.career_settings.find_one({'key': 'singleton'}, {'_id': 0})
    s['portal_url'] = f'{APP_BASE_URL}/careers'
    return s


@router.post('/settings/logo')
async def upload_logo(file: UploadFile = File(...), user: dict = Depends(require_roles('admin', 'recruiter'))):
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=422, detail='Logo must be under 5MB')
    fid = new_id()
    await db.files.insert_one({
        'id': fid, 'filename': file.filename, 'content_type': file.content_type or 'image/png',
        'size': len(data), 'data_b64': base64.b64encode(data).decode(), 'uploaded_by': user['id'], 'created_at': now_iso(),
    })
    await db.career_settings.update_one({'key': 'singleton'}, {'$set': {'logo_file_id': fid, 'updated_at': now_iso()}}, upsert=True)
    return {'logo_file_id': fid}


@router.get('/dashboard')
async def career_dashboard(user: dict = Depends(require_roles('admin', 'recruiter'))):
    s = await _get_settings()
    published_jobs = await db.jobs.count_documents({'published': True, 'status': 'open'})
    total_applications = await db.applications.count_documents({})
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_start = (now - timedelta(days=7)).isoformat()
    apps_today = await db.applications.count_documents({'created_at': {'$gte': today_start}})
    apps_week = await db.applications.count_documents({'created_at': {'$gte': week_start}})
    latest = await db.applications.find({}, {'_id': 0}).sort('created_at', -1).to_list(10)
    cand_ids = [a['candidate_id'] for a in latest]
    job_ids = [a['job_id'] for a in latest]
    cands = {c['id']: c for c in await db.candidates.find({'id': {'$in': cand_ids}}, {'_id': 0, 'id': 1, 'name': 1, 'candidate_code': 1}).to_list(50)}
    jobs = {j['id']: j for j in await db.jobs.find({'id': {'$in': job_ids}}, {'_id': 0, 'id': 1, 'title': 1}).to_list(50)}
    for a in latest:
        a['candidate_name'] = cands.get(a['candidate_id'], {}).get('name')
        a['candidate_code'] = cands.get(a['candidate_id'], {}).get('candidate_code')
        a['job_title'] = jobs.get(a['job_id'], {}).get('title')
    return {
        'portal_enabled': s.get('portal_enabled', False),
        'portal_url': f'{APP_BASE_URL}/careers',
        'published_jobs': published_jobs,
        'total_applications': total_applications,
        'applications_today': apps_today,
        'applications_this_week': apps_week,
        'latest_applications': latest,
    }


# ---------------- Public (no auth) ----------------

@router.get('/public/logo')
async def public_logo():
    s = await _get_settings()
    if not s.get('logo_file_id'):
        raise HTTPException(status_code=404, detail='No logo set')
    doc = await db.files.find_one({'id': s['logo_file_id']})
    if not doc:
        raise HTTPException(status_code=404, detail='No logo set')
    return Response(content=base64.b64decode(doc['data_b64']), media_type=doc.get('content_type', 'image/png'))


@router.get('/public/settings')
async def public_settings():
    s = await _get_settings()
    if not s.get('portal_enabled'):
        raise HTTPException(status_code=404, detail='Career portal is not available')
    s.pop('key', None)
    return s


@router.get('/public/jobs')
async def public_jobs(q: Optional[str] = None, department: Optional[str] = None, location: Optional[str] = None,
                       employment_type: Optional[str] = None, remote_type: Optional[str] = None):
    s = await _get_settings()
    if not s.get('portal_enabled'):
        raise HTTPException(status_code=404, detail='Career portal is not available')
    query = {'published': True, 'status': 'open'}
    if department and department != 'all':
        query['department'] = department
    if location and location != 'all':
        query['location'] = {'$regex': re.escape(location), '$options': 'i'}
    if employment_type and employment_type != 'all':
        query['employment_type'] = employment_type
    if remote_type and remote_type != 'all':
        query['remote_type'] = remote_type
    if q:
        query['$or'] = [
            {'title': {'$regex': re.escape(q), '$options': 'i'}},
            {'department': {'$regex': re.escape(q), '$options': 'i'}},
            {'location': {'$regex': re.escape(q), '$options': 'i'}},
        ]
    jobs = await db.jobs.find(query, {'_id': 0}).sort('created_at', -1).to_list(200)
    return [_public_job(j) for j in jobs]


@router.get('/public/jobs/{slug}')
async def public_job_detail(slug: str):
    s = await _get_settings()
    if not s.get('portal_enabled'):
        raise HTTPException(status_code=404, detail='Career portal is not available')
    job = await db.jobs.find_one({'slug': slug, 'published': True, 'status': 'open'}, {'_id': 0})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found or no longer open')
    return _public_job(job)


@router.post('/public/apply')
async def apply_to_job(
    job_id: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    linkedin_url: Optional[str] = Form(None),
    portfolio_url: Optional[str] = Form(None),
    current_company: Optional[str] = Form(None),
    current_title: Optional[str] = Form(None),
    current_salary: Optional[str] = Form(None),
    expected_salary: Optional[str] = Form(None),
    notice_period: Optional[str] = Form(None),
    years_experience: Optional[str] = Form(None),
    cover_letter: Optional[str] = Form(None),
    resume: UploadFile = File(...),
):
    s = await _get_settings()
    if not s.get('portal_enabled'):
        raise HTTPException(status_code=404, detail='Career portal is not available')
    job = await db.jobs.find_one({'id': job_id, 'published': True, 'status': 'open'})
    if not job:
        raise HTTPException(status_code=404, detail='This role is no longer accepting applications')

    data = await resume.read()
    if len(data) > MAX_RESUME_SIZE:
        raise HTTPException(status_code=422, detail='Resume must be under 10MB')
    try:
        text = extract_text_from_bytes(data, resume.filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if len(text) < 30:
        raise HTTPException(status_code=422, detail='Could not read this resume — please upload a text-based PDF or DOCX')

    file_id = await _store_file(data, resume.filename, resume.content_type, 'career_portal')
    try:
        parsed = await parse_resume_text(text, file_id[:8])
    except Exception:
        parsed = {}

    name = f'{first_name.strip()} {last_name.strip()}'.strip()
    email_norm = email.strip().lower()
    phone_norm = _norm_phone(phone)

    existing = await db.candidates.find_one({'email': {'$regex': f'^{re.escape(email_norm)}$', '$options': 'i'}})
    if not existing and phone_norm:
        with_phone = await db.candidates.find({'phone': {'$ne': None}}, {'_id': 0, 'id': 1, 'phone': 1}).to_list(2000)
        for c in with_phone:
            if _norm_phone(c.get('phone')) == phone_norm:
                existing = await db.candidates.find_one({'id': c['id']})
                break

    stage = (job.get('stages') or ['Applied'])[0]
    application = {
        'id': new_id(), 'job_id': job_id, 'source': 'career_site', 'resume_file_id': file_id,
        'cover_letter': cover_letter, 'created_at': now_iso(),
    }

    if existing:
        candidate_id = existing['id']
        application['candidate_id'] = candidate_id
        already_in_pipeline = existing.get('job_id') == job_id and existing.get('status') == 'active'
        if not already_in_pipeline:
            updates = {
                'job_id': job_id, 'stage': stage, 'status': 'active', 'resume_file_id': file_id,
                'updated_at': now_iso(), 'applied_at': now_iso(),
            }
            for f, v in [('phone', phone), ('location', location), ('current_company', current_company),
                         ('current_title', current_title), ('notice_period', notice_period),
                         ('linkedin_url', linkedin_url), ('portfolio_url', portfolio_url),
                         ('expected_salary', expected_salary), ('current_salary', current_salary),
                         ('years_experience', years_experience)]:
                if v:
                    updates[f] = v
            if parsed.get('skills'):
                updates['skills'] = parsed['skills']
            if parsed.get('experience'):
                updates['experience'] = parsed['experience']
            if parsed.get('education'):
                updates['education'] = parsed['education']
            await db.candidates.update_one({'id': candidate_id}, {'$set': updates})
            await log_activity(None, 'application', f"{name} applied via Career Portal to {job['title']}", candidate_id=candidate_id, job_id=job_id)
            if job.get('recruiter_id'):
                await notify(job['recruiter_id'], 'application', f"{name} applied to {job['title']} via Career Portal", f'/candidates/{candidate_id}')
            if job.get('jd_text'):
                await recompute_candidate_fit(candidate_id)
        await db.applications.insert_one(application)
    else:
        candidate_id = new_id()
        application['candidate_id'] = candidate_id
        cand = {
            'id': candidate_id,
            'candidate_code': await next_candidate_code(),
            'name': name,
            'email': email_norm,
            'phone': phone,
            'current_title': current_title,
            'current_company': current_company,
            'location': location,
            'experience': parsed.get('experience') or [],
            'education': parsed.get('education') or [],
            'skills': parsed.get('skills') or [],
            'job_id': job_id,
            'stage': stage,
            'source': 'career_site',
            'recruiter_id': job.get('recruiter_id'),
            'tags': [],
            'resume_file_id': file_id,
            'low_confidence_fields': [],
            'notice_period': notice_period,
            'status': 'active',
            'rejection_reason': None,
            'fit_score': None, 'fit_score_summary': None, 'fit_score_computed_at': None,
            'applied_at': now_iso(), 'hired_at': None,
            'created_at': now_iso(), 'updated_at': now_iso(),
            'linkedin_url': linkedin_url, 'portfolio_url': portfolio_url,
            'current_salary': current_salary, 'expected_salary': expected_salary, 'years_experience': years_experience,
        }
        await db.candidates.insert_one(cand)
        await db.applications.insert_one(application)
        await log_activity(None, 'application', f"{name} applied via Career Portal to {job['title']}", candidate_id=candidate_id, job_id=job_id)
        if job.get('recruiter_id'):
            await notify(job['recruiter_id'], 'application', f"{name} applied to {job['title']} via Career Portal", f'/candidates/{candidate_id}')
        if job.get('jd_text'):
            await recompute_candidate_fit(candidate_id)

    return {'ok': True, 'message': 'Application submitted successfully', 'candidate_id': candidate_id}
