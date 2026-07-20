"""Career Portal — Phase 1: settings/dashboard (admin) + public jobs & apply flow (no auth)."""
import base64
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from auth import require_roles
from database import db
from email_templates import build_context_from_candidate, send_template
from fit_scorer import recompute_candidate_fit
from rate_limiter import enforce as rate_limit
from resume_parser import extract_text_from_bytes, parse_resume_text
from routes_career_security import verify_recaptcha_token
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
    'hero_image_file_id': None,
    'hero_image_url': None,
    'primary_color': '#1a5c47',
    'secondary_color': '#f4b942',
    'heading_font_family': None,
    'heading_font_url': None,
    'body_font_family': None,
    'body_font_url': None,
    'meta_description': None,
    'meta_keywords': None,
    'og_image_file_id': None,
    'jobposting_seo_enabled': True,
    'about_text': '',
    'benefits': [],
    # ---- Phase 5: Custom domain ----
    'custom_domain': None,
    'custom_domain_status': None,  # none | pending | verified | failed
    'custom_domain_verification_token': None,
    'custom_domain_verified_at': None,
    # ---- Phase 5: Cookie banner / privacy links ----
    'cookie_banner_enabled': False,
    'cookie_banner_text': 'We use essential cookies to make our careers site work. By continuing, you agree to our privacy policy.',
    'privacy_policy_url': None,
    'terms_url': None,
    # ---- Phase 5: reCAPTCHA v3 ----
    'recaptcha_enabled': False,
    'recaptcha_site_key': None,
    'recaptcha_secret_key': None,
    'recaptcha_min_score': 0.5,
    # ---- Phase 5: Rate limiting ----
    'rate_limit_apply_per_hour': 5,
    'rate_limit_public_per_minute': 60,
}

# Static content pages exposed under /careers/{key}. Kept as a fixed catalogue so
# the admin UI knows what to show and the public router knows what routes exist.
CONTENT_PAGE_KEYS = ['about', 'benefits', 'life', 'testimonials']
CONTENT_PAGE_TITLES = {
    'about': 'About Us',
    'benefits': 'Benefits & Perks',
    'life': 'Life at Company',
    'testimonials': 'What Our Team Says',
}


def _default_page(key: str) -> dict:
    return {
        'key': key,
        'hero_heading': CONTENT_PAGE_TITLES.get(key, key.title()),
        'hero_subheading': '',
        'hero_image_file_id': None,
        'body_markdown': '',
        'published': False,
        'meta_description': None,
        'created_at': now_iso(),
        'updated_at': now_iso(),
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
        'id': job['id'], 'job_code': job.get('job_code'), 'slug': job.get('slug'), 'title': job['title'], 'department': job.get('department'),
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
    secondary_color: Optional[str] = None
    heading_font_family: Optional[str] = None
    heading_font_url: Optional[str] = None
    body_font_family: Optional[str] = None
    body_font_url: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    jobposting_seo_enabled: Optional[bool] = None
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


async def _upload_branding_image(file: UploadFile, user: dict, field: str, max_mb: int = 8) -> str:
    data = await file.read()
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=422, detail=f'Image must be under {max_mb}MB')
    if not (file.content_type or '').startswith('image/'):
        raise HTTPException(status_code=422, detail='File must be an image')
    fid = new_id()
    await db.files.insert_one({
        'id': fid, 'filename': file.filename, 'content_type': file.content_type or 'image/jpeg',
        'size': len(data), 'data_b64': base64.b64encode(data).decode(), 'uploaded_by': user['id'], 'created_at': now_iso(),
    })
    await db.career_settings.update_one({'key': 'singleton'}, {'$set': {field: fid, 'updated_at': now_iso()}}, upsert=True)
    return fid


@router.post('/settings/hero')
async def upload_hero(file: UploadFile = File(...), user: dict = Depends(require_roles('admin', 'recruiter'))):
    fid = await _upload_branding_image(file, user, 'hero_image_file_id', max_mb=8)
    return {'hero_image_file_id': fid}


@router.post('/settings/og-image')
async def upload_og_image(file: UploadFile = File(...), user: dict = Depends(require_roles('admin', 'recruiter'))):
    fid = await _upload_branding_image(file, user, 'og_image_file_id', max_mb=5)
    return {'og_image_file_id': fid}


# ---------------- Static content pages (admin) ----------------

class PageUpdate(BaseModel):
    hero_heading: Optional[str] = None
    hero_subheading: Optional[str] = None
    body_markdown: Optional[str] = None
    meta_description: Optional[str] = None
    published: Optional[bool] = None


@router.get('/pages')
async def list_pages(user: dict = Depends(require_roles('admin', 'recruiter'))):
    out = []
    for key in CONTENT_PAGE_KEYS:
        page = await db.career_pages.find_one({'key': key}, {'_id': 0})
        if not page:
            page = _default_page(key)
            await db.career_pages.insert_one(dict(page))
        page['title'] = CONTENT_PAGE_TITLES[key]
        out.append(page)
    return out


@router.get('/pages/{key}')
async def get_page(key: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    if key not in CONTENT_PAGE_KEYS:
        raise HTTPException(status_code=404, detail='Unknown page')
    page = await db.career_pages.find_one({'key': key}, {'_id': 0})
    if not page:
        page = _default_page(key)
        await db.career_pages.insert_one(dict(page))
    page['title'] = CONTENT_PAGE_TITLES[key]
    return page


@router.put('/pages/{key}')
async def update_page(key: str, body: PageUpdate, user: dict = Depends(require_roles('admin', 'recruiter'))):
    if key not in CONTENT_PAGE_KEYS:
        raise HTTPException(status_code=404, detail='Unknown page')
    await db.career_pages.update_one({'key': key}, {'$setOnInsert': _default_page(key)}, upsert=True)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates['updated_at'] = now_iso()
    await db.career_pages.update_one({'key': key}, {'$set': updates})
    page = await db.career_pages.find_one({'key': key}, {'_id': 0})
    page['title'] = CONTENT_PAGE_TITLES[key]
    return page


@router.post('/pages/{key}/hero')
async def upload_page_hero(key: str, file: UploadFile = File(...), user: dict = Depends(require_roles('admin', 'recruiter'))):
    if key not in CONTENT_PAGE_KEYS:
        raise HTTPException(status_code=404, detail='Unknown page')
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=422, detail='Image must be under 8MB')
    if not (file.content_type or '').startswith('image/'):
        raise HTTPException(status_code=422, detail='File must be an image')
    fid = new_id()
    await db.files.insert_one({
        'id': fid, 'filename': file.filename, 'content_type': file.content_type or 'image/jpeg',
        'size': len(data), 'data_b64': base64.b64encode(data).decode(), 'uploaded_by': user['id'], 'created_at': now_iso(),
    })
    await db.career_pages.update_one({'key': key}, {'$setOnInsert': _default_page(key)}, upsert=True)
    await db.career_pages.update_one({'key': key}, {'$set': {'hero_image_file_id': fid, 'updated_at': now_iso()}})
    return {'hero_image_file_id': fid}


# ---------------- Media Library (admin) ----------------

class MediaTagsUpdate(BaseModel):
    tags: list[str]


@router.get('/media')
async def list_media(q: Optional[str] = None, tag: Optional[str] = None,
                     user: dict = Depends(require_roles('admin', 'recruiter'))):
    query: dict = {}
    if tag and tag != 'all':
        query['tags'] = tag
    if q:
        query['filename'] = {'$regex': re.escape(q), '$options': 'i'}
    items = await db.media_library.find(query, {'_id': 0, 'data_b64': 0}).sort('created_at', -1).to_list(500)
    return items


@router.post('/media')
async def upload_media(files: list[UploadFile] = File(...), tags: Optional[str] = Form(None),
                      user: dict = Depends(require_roles('admin', 'recruiter'))):
    if len(files) > 20:
        raise HTTPException(status_code=422, detail='Maximum 20 files per upload')
    tag_list = [t.strip() for t in (tags or '').split(',') if t.strip()]
    created = []
    for f in files:
        data = await f.read()
        if not (f.content_type or '').startswith('image/'):
            continue  # silently skip non-images in bulk
        if len(data) > 10 * 1024 * 1024:
            continue
        item = {
            'id': new_id(), 'filename': f.filename, 'content_type': f.content_type or 'image/jpeg',
            'size': len(data), 'data_b64': base64.b64encode(data).decode(),
            'tags': tag_list, 'uploaded_by': user['id'], 'created_at': now_iso(),
        }
        await db.media_library.insert_one(item)
        # motor mutates `item` in place adding `_id` — strip both `_id` and `data_b64`
        # before returning so responses stay JSON-serializable and lightweight.
        item.pop('data_b64', None)
        item.pop('_id', None)
        created.append(item)
    return {'created': created, 'skipped': len(files) - len(created)}


@router.put('/media/{media_id}/tags')
async def update_media_tags(media_id: str, body: MediaTagsUpdate,
                            user: dict = Depends(require_roles('admin', 'recruiter'))):
    result = await db.media_library.update_one({'id': media_id}, {'$set': {'tags': body.tags}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail='Media not found')
    item = await db.media_library.find_one({'id': media_id}, {'_id': 0, 'data_b64': 0})
    return item


@router.delete('/media/{media_id}')
async def delete_media(media_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    result = await db.media_library.delete_one({'id': media_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail='Media not found')
    return {'ok': True}


@router.get('/media/{media_id}/raw')
async def media_raw(media_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    doc = await db.media_library.find_one({'id': media_id})
    if not doc:
        raise HTTPException(status_code=404, detail='Media not found')
    return Response(content=base64.b64decode(doc['data_b64']), media_type=doc.get('content_type', 'image/jpeg'))


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


@router.get('/public/hero')
async def public_hero():
    s = await _get_settings()
    if not s.get('hero_image_file_id'):
        raise HTTPException(status_code=404, detail='No hero image set')
    doc = await db.files.find_one({'id': s['hero_image_file_id']})
    if not doc:
        raise HTTPException(status_code=404, detail='No hero image set')
    return Response(content=base64.b64decode(doc['data_b64']), media_type=doc.get('content_type', 'image/jpeg'))


@router.get('/public/og-image')
async def public_og_image():
    s = await _get_settings()
    fid = s.get('og_image_file_id') or s.get('hero_image_file_id') or s.get('logo_file_id')
    if not fid:
        raise HTTPException(status_code=404, detail='No OG image set')
    doc = await db.files.find_one({'id': fid})
    if not doc:
        raise HTTPException(status_code=404, detail='No OG image set')
    return Response(content=base64.b64decode(doc['data_b64']), media_type=doc.get('content_type', 'image/jpeg'))


@router.get('/public/pages')
async def public_pages_list():
    s = await _get_settings()
    if not s.get('portal_enabled'):
        raise HTTPException(status_code=404, detail='Career portal is not available')
    pages = await db.career_pages.find({'published': True}, {'_id': 0, 'body_markdown': 0}).to_list(20)
    for p in pages:
        p['title'] = CONTENT_PAGE_TITLES.get(p.get('key'), p.get('key', '').title())
    return pages


@router.get('/public/pages/{key}')
async def public_page(key: str):
    s = await _get_settings()
    if not s.get('portal_enabled'):
        raise HTTPException(status_code=404, detail='Career portal is not available')
    if key not in CONTENT_PAGE_KEYS:
        raise HTTPException(status_code=404, detail='Page not found')
    page = await db.career_pages.find_one({'key': key, 'published': True}, {'_id': 0})
    if not page:
        raise HTTPException(status_code=404, detail='This page has not been published yet')
    page['title'] = CONTENT_PAGE_TITLES[key]
    return page


@router.get('/public/pages/{key}/hero')
async def public_page_hero(key: str):
    if key not in CONTENT_PAGE_KEYS:
        raise HTTPException(status_code=404, detail='Unknown page')
    page = await db.career_pages.find_one({'key': key})
    if not page or not page.get('hero_image_file_id'):
        raise HTTPException(status_code=404, detail='No hero image')
    doc = await db.files.find_one({'id': page['hero_image_file_id']})
    if not doc:
        raise HTTPException(status_code=404, detail='No hero image')
    return Response(content=base64.b64decode(doc['data_b64']), media_type=doc.get('content_type', 'image/jpeg'))


@router.get('/public/media/{media_id}')
async def public_media(media_id: str):
    doc = await db.media_library.find_one({'id': media_id})
    if not doc:
        raise HTTPException(status_code=404, detail='Media not found')
    return Response(content=base64.b64decode(doc['data_b64']), media_type=doc.get('content_type', 'image/jpeg'))


# ---------------- SEO endpoints (public) ----------------

@router.get('/seo/robots.txt')
async def robots_txt():
    s = await _get_settings()
    lines = ['User-agent: *']
    if s.get('portal_enabled'):
        lines.append('Allow: /careers')
        lines.append('Disallow: /login')
        lines.append('Disallow: /candidates')
        lines.append('Disallow: /jobs')
        lines.append('Disallow: /interviews')
        lines.append('Disallow: /admin')
        lines.append('Disallow: /career-portal')
        lines.append(f'Sitemap: {APP_BASE_URL}/api/career/seo/sitemap.xml')
    else:
        lines.append('Disallow: /')
    return Response(content='\n'.join(lines) + '\n', media_type='text/plain')


@router.get('/seo/sitemap.xml')
async def sitemap_xml():
    s = await _get_settings()
    urls: list[dict] = []
    if s.get('portal_enabled'):
        urls.append({'loc': f'{APP_BASE_URL}/careers', 'priority': '1.0', 'changefreq': 'daily'})
        urls.append({'loc': f'{APP_BASE_URL}/careers/jobs', 'priority': '0.9', 'changefreq': 'daily'})
        pages = await db.career_pages.find({'published': True}, {'_id': 0, 'key': 1, 'updated_at': 1}).to_list(20)
        for p in pages:
            urls.append({'loc': f'{APP_BASE_URL}/careers/{p["key"]}', 'priority': '0.6',
                         'changefreq': 'weekly', 'lastmod': (p.get('updated_at') or '')[:10]})
        jobs = await db.jobs.find({'published': True, 'status': 'open'},
                                  {'_id': 0, 'slug': 1, 'updated_at': 1, 'created_at': 1}).to_list(500)
        for j in jobs:
            if not j.get('slug'):
                continue
            urls.append({'loc': f'{APP_BASE_URL}/careers/jobs/{j["slug"]}', 'priority': '0.8',
                         'changefreq': 'weekly', 'lastmod': (j.get('updated_at') or j.get('created_at') or '')[:10]})
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        body.append('  <url>')
        body.append(f'    <loc>{u["loc"]}</loc>')
        if u.get('lastmod'):
            body.append(f'    <lastmod>{u["lastmod"]}</lastmod>')
        body.append(f'    <changefreq>{u.get("changefreq", "weekly")}</changefreq>')
        body.append(f'    <priority>{u.get("priority", "0.5")}</priority>')
        body.append('  </url>')
    body.append('</urlset>')
    return Response(content='\n'.join(body), media_type='application/xml')


@router.get('/public/jobs/{slug}/jobposting.json')
async def jobposting_jsonld(slug: str):
    """Google JobPosting structured data for a single open role (SEO)."""
    s = await _get_settings()
    if not s.get('portal_enabled') or not s.get('jobposting_seo_enabled', True):
        raise HTTPException(status_code=404, detail='Not available')
    job = await db.jobs.find_one({'slug': slug, 'published': True, 'status': 'open'}, {'_id': 0})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    desc = (job.get('jd_text') or job.get('description') or '').strip()
    if not desc:
        desc = f'{job["title"]} at {s.get("company_name")}'
    location_str = job.get('location') or ''
    remote_type = (job.get('remote_type') or '').lower()
    posted = (job.get('created_at') or now_iso())[:10]
    payload: dict = {
        '@context': 'https://schema.org',
        '@type': 'JobPosting',
        'title': job['title'],
        'description': desc,
        'datePosted': posted,
        'employmentType': (job.get('employment_type') or 'FULL_TIME').upper().replace('-', '_'),
        'hiringOrganization': {
            '@type': 'Organization',
            'name': s.get('company_name'),
            'sameAs': APP_BASE_URL,
        },
        'directApply': True,
        'url': f'{APP_BASE_URL}/careers/jobs/{slug}',
    }
    if location_str:
        payload['jobLocation'] = {
            '@type': 'Place',
            'address': {'@type': 'PostalAddress', 'addressLocality': location_str},
        }
    if remote_type in ('remote', 'fully_remote'):
        payload['jobLocationType'] = 'TELECOMMUTE'
        payload.setdefault('applicantLocationRequirements', {
            '@type': 'Country', 'name': 'Worldwide',
        })
    if job.get('salary_min') or job.get('salary_max'):
        payload['baseSalary'] = {
            '@type': 'MonetaryAmount',
            'currency': job.get('salary_currency', 'USD'),
            'value': {
                '@type': 'QuantitativeValue',
                'minValue': job.get('salary_min'),
                'maxValue': job.get('salary_max'),
                'unitText': (job.get('salary_period') or 'YEAR').upper(),
            },
        }
    return payload


@router.get('/public/settings')
async def public_settings():
    s = await _get_settings()
    if not s.get('portal_enabled'):
        raise HTTPException(status_code=404, detail='Career portal is not available')
    s.pop('key', None)
    return s


@router.get('/public/jobs')
async def public_jobs(request: Request, q: Optional[str] = None, department: Optional[str] = None, location: Optional[str] = None,
                       employment_type: Optional[str] = None, remote_type: Optional[str] = None):
    s = await _get_settings()
    if not s.get('portal_enabled'):
        raise HTTPException(status_code=404, detail='Career portal is not available')
    rate_limit(request, scope='career_public', limit=int(s.get('rate_limit_public_per_minute', 60) or 0), window_seconds=60)
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
async def public_job_detail(request: Request, slug: str):
    s = await _get_settings()
    if not s.get('portal_enabled'):
        raise HTTPException(status_code=404, detail='Career portal is not available')
    rate_limit(request, scope='career_public', limit=int(s.get('rate_limit_public_per_minute', 60) or 0), window_seconds=60)
    job = await db.jobs.find_one({'slug': slug, 'published': True, 'status': 'open'}, {'_id': 0})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found or no longer open')
    return _public_job(job)


@router.post('/public/apply')
async def apply_to_job(
    request: Request,
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
    recaptcha_token: Optional[str] = Form(None),
    resume: UploadFile = File(...),
):
    s = await _get_settings()
    if not s.get('portal_enabled'):
        raise HTTPException(status_code=404, detail='Career portal is not available')

    # Rate limit: per-IP + per-job so a single IP can't spam applications.
    apply_limit = int(s.get('rate_limit_apply_per_hour', 5) or 0)
    rate_limit(request, scope='career_apply', limit=apply_limit, window_seconds=3600, extra_key=job_id)

    # reCAPTCHA v3 verification (only if enabled in settings)
    ok, reason = await verify_recaptcha_token(recaptcha_token, s)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

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

    # Fire "Application received" auto-reply from admin's Gmail (silent no-op if
    # nobody has connected Google or the template is disabled).
    try:
        cand_doc = await db.candidates.find_one({'id': candidate_id}, {'_id': 0})
        ctx = build_context_from_candidate(cand_doc or {}, job, s)
        await send_template(
            template_key='application_received',
            to_email=email_norm,
            context=ctx,
            sender_user_id=job.get('recruiter_id'),
            allow_admin_fallback=True,
            # Prevent duplicate auto-replies if the same candidate submits the
            # apply form twice in quick succession (or if the client retries).
            dedup_window_seconds=24 * 3600,
        )
    except Exception:
        pass  # never fail the application because email failed

    return {'ok': True, 'message': 'Application submitted successfully', 'candidate_id': candidate_id}
