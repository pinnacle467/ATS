"""Job Boards module — integration management, job publishing/sync, and
application ingestion (webhook + generic XML feed).

Reuses the existing candidate model, resume parser, fit scorer, RBAC helpers
and audit log — see job_board_ingestion.py for the shared ingestion pipeline
and job_boards/ for the provider adapter architecture.
"""
import base64
import hashlib
import hmac
import json
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from auth import get_current_user, require_roles
from crypto_utils import decrypt_dict, decrypt_str, encrypt_dict, encrypt_str
from database import db
from job_board_ingestion import NormalizedApplication, ingest_application
from job_boards.base import ATS_JOB_FIELDS
from job_boards.mapping import map_job_to_board_fields, populated_field_names
from job_boards.registry import get_provider_class, provider_catalog
from permissions import is_admin_or_higher, visible_job_ids_for_user
from rate_limiter import enforce as rate_limit
from tenant_context import get_tenant_id, tenant_scope
from tenants import get_tenant, get_tenant_by_slug
from utils import log_audit, new_id, now_iso

router = APIRouter(prefix='/job-boards', tags=['job-boards'])
public_router = APIRouter(tags=['job-boards-public'])

APP_BASE_URL = os.environ['APP_BASE_URL']
MAX_RESUME_SIZE = 10 * 1024 * 1024


# ==================== Shared helpers ====================

async def _current_slug() -> str:
    t = await get_tenant(get_tenant_id())
    return (t or {}).get('slug', '')


async def _company_name() -> str:
    settings = await db.career_settings.find_one({'key': 'singleton'}, {'_id': 0, 'company_name': 1})
    if settings and settings.get('company_name'):
        return settings['company_name']
    t = await get_tenant(get_tenant_id())
    return (t or {}).get('name') or 'Our Company'


async def _get_job_or_404(job_id: str, user: Optional[dict] = None) -> dict:
    job = await db.jobs.find_one({'id': job_id}, {'_id': 0})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    if user and not is_admin_or_higher(user):
        team = job.get('team_members') or []
        if not any(m.get('user_id') == user.get('id') for m in team):
            raise HTTPException(status_code=403, detail='You do not have access to this job')
    return job


async def _log_sync(actor, provider, action, status, message, job_id=None, publication_id=None, integration_id=None):
    await db.job_board_sync_logs.insert_one({
        'id': new_id(), 'provider': provider, 'integration_id': integration_id, 'job_id': job_id,
        'publication_id': publication_id, 'action': action, 'status': status, 'message': message,
        'actor_id': (actor or {}).get('id'), 'actor_name': (actor or {}).get('name') or 'System',
        'created_at': now_iso(),
    })
    await log_audit(actor, f'job_board_{action}', 'job_board_integration', publication_id or integration_id or job_id or provider, message)


# ==================== Integration management (admin/recruiter only) ====================

@router.get('/integrations')
async def list_integrations(user: dict = Depends(require_roles('admin', 'recruiter'))):
    catalog = provider_catalog()
    docs = await db.job_board_integrations.find({}, {'_id': 0, 'credentials_encrypted': 0, 'webhook_secret_encrypted': 0}).to_list(50)
    by_key = {d['provider']: d for d in docs}
    slug = await _current_slug()
    out = []
    for meta in catalog:
        doc = by_key.get(meta['key']) or {}
        active_jobs = await db.job_board_publications.count_documents({'provider': meta['key'], 'status': {'$in': ['published', 'updated']}})
        applications = await db.applications.count_documents({'provider': meta['key']})
        item = {
            **meta,
            'status': doc.get('status', 'not_connected'),
            'connected': doc.get('status') == 'connected',
            'account_label': doc.get('account_label'),
            'integration_id': doc.get('id'),
            'active_job_count': active_jobs,
            'applications_received': applications,
            'last_synced_at': doc.get('last_synced_at'),
            'last_error': doc.get('last_error'),
            'webhook_auth_mode': doc.get('webhook_auth_mode'),
        }
        if meta['key'] == 'generic_webhook' and doc.get('id'):
            item['webhook_url'] = f"{APP_BASE_URL}/api/integrations/job-boards/applications?tenant={slug}&webhook_id={doc['id']}"
        if meta['key'] == 'generic_xml':
            item['feed_url'] = f"{APP_BASE_URL}/api/job-feeds/{slug}/jobs.xml"
        out.append(item)
    return out


class ConnectBody(BaseModel):
    credentials: dict = {}
    webhook_auth_mode: Optional[str] = None  # 'hmac_sha256' | 'bearer_token' — generic_webhook only


@router.post('/integrations/{provider}/connect')
async def connect_integration(provider: str, body: ConnectBody, user: dict = Depends(require_roles('admin', 'recruiter'))):
    cls = get_provider_class(provider)
    if not cls:
        raise HTTPException(status_code=404, detail='Unknown provider')
    existing = await db.job_board_integrations.find_one({'provider': provider})
    integration_id = (existing or {}).get('id') or new_id()
    slug = await _current_slug()
    doc = {
        'id': integration_id, 'provider': provider, 'display_name': cls.display_name, 'company_slug': slug,
        'credentials_encrypted': encrypt_dict(body.credentials),
        'created_by': (existing or {}).get('created_by') or user['id'],
        'created_at': (existing or {}).get('created_at') or now_iso(), 'updated_at': now_iso(),
    }
    webhook_secret = None
    if provider == 'generic_webhook':
        import secrets as _secrets
        webhook_secret = _secrets.token_urlsafe(32)
        doc['webhook_secret_encrypted'] = encrypt_str(webhook_secret)
        doc['webhook_auth_mode'] = body.webhook_auth_mode or 'bearer_token'
    creds = decrypt_dict(doc['credentials_encrypted'])
    result = await cls(doc, creds).test_connection()
    doc['status'] = result.status
    doc['account_label'] = result.account_label
    doc['last_error'] = result.error
    if result.ok:
        doc['last_synced_at'] = now_iso()
    await db.job_board_integrations.update_one({'provider': provider}, {'$set': doc}, upsert=True)
    await _log_sync(user, provider, 'connect', 'success' if result.ok else 'error',
                     result.error or f'{cls.display_name} connected', integration_id=integration_id)
    out = await db.job_board_integrations.find_one({'provider': provider}, {'_id': 0, 'credentials_encrypted': 0, 'webhook_secret_encrypted': 0})
    if webhook_secret:
        out['webhook_secret'] = webhook_secret  # shown once, right after (re)generation — never persisted in plaintext
        out['webhook_url'] = f"{APP_BASE_URL}/api/integrations/job-boards/applications?tenant={slug}&webhook_id={integration_id}"
    return out


@router.post('/integrations/{provider}/test')
async def test_integration(provider: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    integration = await db.job_board_integrations.find_one({'provider': provider})
    if not integration:
        raise HTTPException(status_code=404, detail='Not connected yet')
    cls = get_provider_class(provider)
    creds = decrypt_dict(integration.get('credentials_encrypted') or {})
    result = await cls(integration, creds).test_connection()
    await db.job_board_integrations.update_one({'provider': provider}, {'$set': {
        'status': result.status, 'account_label': result.account_label or integration.get('account_label'),
        'last_error': result.error, 'last_synced_at': now_iso() if result.ok else integration.get('last_synced_at'),
    }})
    await _log_sync(user, provider, 'test_connection', 'success' if result.ok else 'error',
                     result.error or 'Connection OK', integration_id=integration['id'])
    return {'ok': result.ok, 'status': result.status, 'error': result.error}


@router.post('/integrations/{provider}/disconnect')
async def disconnect_integration(provider: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    integration = await db.job_board_integrations.find_one({'provider': provider})
    if not integration:
        raise HTTPException(status_code=404, detail='Not connected')
    await db.job_board_integrations.delete_one({'provider': provider})
    await _log_sync(user, provider, 'disconnect', 'success', f'{integration.get("display_name", provider)} disconnected',
                     integration_id=integration['id'])
    return {'ok': True}


# ==================== Job publishing ====================

class PublishBody(BaseModel):
    providers: list[str]


@router.post('/jobs/{job_id}/publish-preview')
async def publish_preview(job_id: str, body: PublishBody, user: dict = Depends(require_roles('admin', 'recruiter'))):
    job = await _get_job_or_404(job_id, user)
    mapped = map_job_to_board_fields(job, await _company_name())
    populated = populated_field_names(job)
    docs = await db.job_board_integrations.find({'provider': {'$in': body.providers}}, {'_id': 0, 'credentials_encrypted': 0, 'webhook_secret_encrypted': 0}).to_list(20)
    by_key = {d['provider']: d for d in docs}
    out = []
    for key in body.providers:
        cls = get_provider_class(key)
        if not cls:
            continue
        warnings = sorted(populated & (ATS_JOB_FIELDS - cls.supported_fields))
        doc = by_key.get(key)
        out.append({
            'provider': key, 'display_name': cls.display_name,
            'connected': bool(doc and doc.get('status') == 'connected'),
            'requires_partner_approval': cls.requires_partner_approval,
            'mapped_fields': mapped, 'unsupported_field_warnings': warnings,
        })
    return out


@router.post('/jobs/{job_id}/publish')
async def publish_job_to_boards(job_id: str, body: PublishBody, user: dict = Depends(require_roles('admin', 'recruiter'))):
    job = await _get_job_or_404(job_id, user)
    mapped = map_job_to_board_fields(job, await _company_name())
    results = []
    for provider in body.providers:
        cls = get_provider_class(provider)
        if not cls:
            results.append({'provider': provider, 'ok': False, 'error': 'Unknown provider'})
            continue
        integration = await db.job_board_integrations.find_one({'provider': provider})
        existing_pub = await db.job_board_publications.find_one({'job_id': job_id, 'provider': provider})
        pub_id = (existing_pub or {}).get('id') or new_id()
        if not integration:
            await db.job_board_publications.update_one(
                {'job_id': job_id, 'provider': provider},
                {'$set': {'id': pub_id, 'job_id': job_id, 'provider': provider, 'status': 'failed',
                          'error': f'{cls.display_name} is not connected — connect it first from Job Boards settings.',
                          'updated_at': now_iso()},
                 '$setOnInsert': {'created_at': now_iso(), 'published_by': user['id']}},
                upsert=True,
            )
            results.append({'provider': provider, 'ok': False, 'status': 'failed', 'error': 'Not connected'})
            continue
        creds = decrypt_dict(integration.get('credentials_encrypted') or {})
        result = await cls(integration, creds).publish_job(mapped)
        update = {
            'id': pub_id, 'job_id': job_id, 'provider': provider, 'integration_id': integration['id'],
            'status': result.status, 'external_job_id': result.external_job_id,
            'external_posting_id': result.external_posting_id, 'external_url': result.external_url,
            'error': result.error, 'updated_at': now_iso(), 'published_by': user['id'],
        }
        if result.ok:
            update['published_at'] = (existing_pub or {}).get('published_at') or now_iso()
        await db.job_board_publications.update_one({'job_id': job_id, 'provider': provider},
                                                     {'$set': update, '$setOnInsert': {'created_at': now_iso()}}, upsert=True)
        await _log_sync(user, provider, 'publish', 'success' if result.ok else 'error',
                         result.error or f'Published "{job["title"]}"', job_id=job_id, publication_id=pub_id,
                         integration_id=integration['id'])
        results.append({'provider': provider, 'ok': result.ok, 'status': result.status,
                         'error': result.error, 'external_url': result.external_url})
    return {'results': results}


async def _act_on_publication(pub_id: str, user: dict, action: str):
    pub = await db.job_board_publications.find_one({'id': pub_id})
    if not pub:
        raise HTTPException(status_code=404, detail='Publication not found')
    job = await _get_job_or_404(pub['job_id'], user)
    cls = get_provider_class(pub['provider'])
    integration = await db.job_board_integrations.find_one({'provider': pub['provider']})
    if not integration:
        raise HTTPException(status_code=400, detail=f'{pub["provider"]} is not connected')
    creds = decrypt_dict(integration.get('credentials_encrypted') or {})
    instance = cls(integration, creds)
    if action == 'update':
        mapped = map_job_to_board_fields(job, await _company_name())
        result = await instance.update_job(mapped, pub)
    elif action == 'close':
        result = await instance.expire_job(pub)
    elif action == 'retry':
        mapped = map_job_to_board_fields(job, await _company_name())
        result = await instance.publish_job(mapped)
    else:
        raise HTTPException(status_code=422, detail='Unknown action')
    update = {'status': result.status, 'error': result.error, 'updated_at': now_iso()}
    if result.external_job_id:
        update['external_job_id'] = result.external_job_id
    if result.external_posting_id:
        update['external_posting_id'] = result.external_posting_id
    if result.external_url:
        update['external_url'] = result.external_url
    await db.job_board_publications.update_one({'id': pub_id}, {'$set': update})
    await _log_sync(user, pub['provider'], action, 'success' if result.ok else 'error',
                     result.error or f'{action} OK', job_id=pub['job_id'], publication_id=pub_id,
                     integration_id=integration['id'])
    return {'ok': result.ok, 'status': result.status, 'error': result.error}


@router.put('/publications/{pub_id}')
async def update_publication(pub_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    return await _act_on_publication(pub_id, user, 'update')


@router.post('/publications/{pub_id}/close')
async def close_publication(pub_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    return await _act_on_publication(pub_id, user, 'close')


@router.post('/publications/{pub_id}/retry')
async def retry_publication(pub_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    return await _act_on_publication(pub_id, user, 'retry')


@router.delete('/publications/{pub_id}')
async def remove_publication(pub_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    pub = await db.job_board_publications.find_one({'id': pub_id})
    if not pub:
        raise HTTPException(status_code=404, detail='Publication not found')
    await _get_job_or_404(pub['job_id'], user)
    await db.job_board_publications.delete_one({'id': pub_id})
    await _log_sync(user, pub['provider'], 'remove', 'success', 'Distribution row removed', job_id=pub['job_id'], publication_id=pub_id)
    return {'ok': True}


@router.get('/jobs/{job_id}/publications')
async def list_job_publications(job_id: str, user: dict = Depends(get_current_user)):
    job = await _get_job_or_404(job_id, user)
    pubs = await db.job_board_publications.find({'job_id': job_id}, {'_id': 0}).to_list(20)
    for p in pubs:
        cls = get_provider_class(p['provider'])
        p['display_name'] = cls.display_name if cls else p['provider']
        p['applications_received'] = await db.applications.count_documents({'job_id': job_id, 'provider': p['provider']})
    career_row = {
        'provider': 'career_portal', 'display_name': 'Career Portal', 'is_virtual': True,
        'status': 'published' if job.get('published') else 'draft',
        'external_url': job.get('public_url'),
        'published_at': job.get('updated_at') if job.get('published') else None,
        'applications_received': await db.applications.count_documents({'job_id': job_id, 'source': 'career_site'}),
    }
    return [career_row] + pubs


# ==================== Applications (review + dedup) ====================

@router.get('/applications')
async def list_job_board_applications(job_id: Optional[str] = None, provider: Optional[str] = None,
                                       status: Optional[str] = None, user: dict = Depends(get_current_user)):
    q: dict = {'source_type': 'job_board'}
    if provider:
        q['provider'] = provider
    if status:
        q['status'] = status
    if not is_admin_or_higher(user):
        job_ids = await visible_job_ids_for_user(db, user)
        if job_id and job_id not in job_ids:
            return []
        q['job_id'] = job_id if job_id else {'$in': job_ids or ['__none__']}
    elif job_id:
        q['job_id'] = job_id
    apps = await db.applications.find(q, {'_id': 0}).sort('created_at', -1).to_list(500)
    cand_ids = list({a['candidate_id'] for a in apps if a.get('candidate_id')})
    job_ids_ = list({a['job_id'] for a in apps})
    cands = {c['id']: c for c in await db.candidates.find({'id': {'$in': cand_ids}}, {'_id': 0, 'id': 1, 'name': 1, 'email': 1, 'candidate_code': 1}).to_list(len(cand_ids) or 1)}
    jobs = {j['id']: j for j in await db.jobs.find({'id': {'$in': job_ids_}}, {'_id': 0, 'id': 1, 'title': 1}).to_list(len(job_ids_) or 1)}
    for a in apps:
        c = cands.get(a.get('candidate_id'), {})
        a['candidate_name'] = c.get('name')
        a['candidate_email'] = c.get('email')
        a['candidate_code'] = c.get('candidate_code')
        a['job_title'] = jobs.get(a['job_id'], {}).get('title')
        a.pop('raw_payload', None)
    return apps


@router.get('/applications/{application_id}')
async def get_job_board_application(application_id: str, user: dict = Depends(get_current_user)):
    app_doc = await db.applications.find_one({'id': application_id}, {'_id': 0})
    if not app_doc:
        raise HTTPException(status_code=404, detail='Application not found')
    await _get_job_or_404(app_doc['job_id'], user)
    return app_doc


class ResolveBody(BaseModel):
    action: str  # add_to_pipeline | create_new_candidate | ignore


@router.post('/applications/{application_id}/resolve')
async def resolve_application(application_id: str, body: ResolveBody, user: dict = Depends(require_roles('admin', 'recruiter'))):
    app_doc = await db.applications.find_one({'id': application_id})
    if not app_doc:
        raise HTTPException(status_code=404, detail='Application not found')
    if app_doc.get('status') != 'duplicate_review':
        raise HTTPException(status_code=400, detail='This application is not pending duplicate review')
    job = await db.jobs.find_one({'id': app_doc['job_id']})
    if body.action == 'add_to_pipeline':
        stage = (job.get('stages') or ['Applied'])[0]
        await db.candidates.update_one({'id': app_doc['candidate_id']}, {'$set': {
            'job_id': app_doc['job_id'], 'stage': stage, 'status': 'active', 'updated_at': now_iso(),
        }})
        await db.applications.update_one({'id': application_id}, {'$set': {'status': 'linked', 'updated_at': now_iso()}})
        await log_audit(user, 'job_board_duplicate_resolved', 'application', application_id, 'Added to pipeline for this job')
    elif body.action == 'create_new_candidate':
        from utils import next_candidate_code
        old_cand = await db.candidates.find_one({'id': app_doc['candidate_id']}, {'_id': 0})
        new_cand_id = new_id()
        stage = (job.get('stages') or ['Applied'])[0]
        cand = {**(old_cand or {}), 'id': new_cand_id, 'candidate_code': await next_candidate_code(),
                'job_id': app_doc['job_id'], 'stage': stage, 'status': 'active',
                'created_at': now_iso(), 'updated_at': now_iso()}
        await db.candidates.insert_one(cand)
        await db.applications.update_one({'id': application_id}, {'$set': {
            'candidate_id': new_cand_id, 'status': 'linked', 'updated_at': now_iso(),
        }})
        await log_audit(user, 'job_board_duplicate_resolved', 'application', application_id,
                         f'Created new candidate {new_cand_id} (treated as a different person)')
    elif body.action == 'ignore':
        await db.applications.update_one({'id': application_id}, {'$set': {'status': 'rejected_invalid', 'updated_at': now_iso()}})
        await log_audit(user, 'job_board_duplicate_resolved', 'application', application_id, 'Ignored')
    else:
        raise HTTPException(status_code=422, detail='action must be add_to_pipeline, create_new_candidate, or ignore')
    return {'ok': True}


# ==================== Analytics ====================

@router.get('/analytics/{job_id}')
async def job_board_analytics(job_id: str, user: dict = Depends(get_current_user)):
    await _get_job_or_404(job_id, user)
    cands = await db.candidates.find({'job_id': job_id}, {'_id': 0, 'source': 1, 'stage': 1, 'status': 1}).to_list(5000)
    by_source: dict = {}
    for c in cands:
        src = c.get('source') or 'other'
        b = by_source.setdefault(src, {'candidates': 0, 'interviews': 0, 'shortlisted': 0, 'rejected': 0, 'hired': 0})
        b['candidates'] += 1
        if c.get('stage') == 'Interview':
            b['interviews'] += 1
        if c.get('stage') in ('Offer', 'Hired'):
            b['shortlisted'] += 1
        if c.get('stage') == 'Rejected':
            b['rejected'] += 1
        if c.get('stage') == 'Hired':
            b['hired'] += 1
    out = []
    for src, stats in by_source.items():
        conv_interview = round(stats['interviews'] / stats['candidates'] * 100, 1) if stats['candidates'] else 0.0
        conv_hire = round(stats['hired'] / stats['candidates'] * 100, 1) if stats['candidates'] else 0.0
        out.append({'source': src, **stats, 'conversion_to_interview_pct': conv_interview, 'conversion_to_hire_pct': conv_hire})
    out.sort(key=lambda r: -r['candidates'])
    return out


@router.get('/sync-logs')
async def list_sync_logs(provider: Optional[str] = None, user: dict = Depends(require_roles('admin', 'recruiter'))):
    q = {'provider': provider} if provider else {}
    return await db.job_board_sync_logs.find(q, {'_id': 0}).sort('created_at', -1).to_list(200)


# ==================== Sandbox helper (QA the full pipeline with zero setup) ====================

class SimulateBody(BaseModel):
    job_id: str
    name: str = 'Test Candidate'
    email: Optional[str] = None
    phone: Optional[str] = None


@router.post('/integrations/mock/simulate-application')
async def simulate_mock_application(body: SimulateBody, user: dict = Depends(require_roles('admin', 'recruiter'))):
    pub = await db.job_board_publications.find_one({'job_id': body.job_id, 'provider': 'mock'})
    if not pub or pub.get('status') not in ('published', 'updated'):
        raise HTTPException(status_code=400, detail='Publish this job to the Sandbox provider first')
    app = NormalizedApplication(
        provider='mock', external_application_id=new_id(), external_candidate_id=new_id(),
        external_job_id=pub['external_job_id'], job_id=body.job_id, name=body.name,
        email=body.email or f'{body.name.lower().replace(" ", ".")}.{new_id()[:6]}@example.com',
        phone=body.phone, applied_at=now_iso(), raw_payload={'simulated': True, 'triggered_by': user['id']},
    )
    result = await ingest_application('mock', app, actor=user)
    await _log_sync(user, 'mock', 'simulate_application', 'success' if result.get('ok') else 'error',
                     result.get('error') or f"Simulated application from {body.name}", job_id=body.job_id,
                     publication_id=pub['id'])
    return result


# ==================== Public: Generic Application Webhook ====================

def _verify_webhook_auth(integration: dict, headers, body_bytes: bytes):
    secret = decrypt_str(integration.get('webhook_secret_encrypted'))
    if not secret:
        return False, 'Webhook not properly configured (missing secret)'
    mode = integration.get('webhook_auth_mode', 'bearer_token')
    if mode == 'hmac_sha256':
        raw_sig = headers.get('x-webhook-signature', '')
        sig = raw_sig.split('=', 1)[-1] if '=' in raw_sig else raw_sig
        expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        if not sig or not hmac.compare_digest(sig, expected):
            return False, 'Invalid webhook signature'
        return True, ''
    auth = headers.get('authorization', '')
    token = auth.split(' ', 1)[-1] if auth.lower().startswith('bearer ') else auth
    if not token or not hmac.compare_digest(token, secret):
        return False, 'Invalid or missing webhook token'
    return True, ''


async def _extract_resume(payload: dict):
    if payload.get('resume_base64'):
        try:
            data = base64.b64decode(payload['resume_base64'])
        except Exception:
            return None, None
        if len(data) > MAX_RESUME_SIZE:
            return None, None
        return data, payload.get('resume_filename') or 'resume.pdf'
    if payload.get('resume_url'):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(payload['resume_url'])
            if r.status_code == 200 and len(r.content) <= MAX_RESUME_SIZE:
                filename = payload.get('resume_filename') or payload['resume_url'].split('/')[-1].split('?')[0] or 'resume.pdf'
                return r.content, filename
        except Exception:
            return None, None
    return None, None


@public_router.post('/integrations/job-boards/applications')
async def receive_generic_webhook_application(request: Request, tenant: str = Query(...), webhook_id: str = Query(...)):
    body_bytes = await request.body()
    integration = await db.job_board_integrations.find_one({'id': webhook_id, 'provider': 'generic_webhook'})
    if not integration:
        raise HTTPException(status_code=404, detail='Unknown webhook endpoint')

    rate_limit(request, scope='job_board_webhook', limit=120, window_seconds=60, extra_key=webhook_id)

    ok, reason = _verify_webhook_auth(integration, request.headers, body_bytes)
    if not ok:
        await _log_sync(None, 'generic_webhook', 'webhook_auth_failed', 'error', reason, integration_id=webhook_id)
        raise HTTPException(status_code=401, detail=reason)

    try:
        payload = json.loads(body_bytes or b'{}')
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail='Invalid JSON payload')
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail='Payload must be a JSON object')

    idempotency_key = str(payload.get('external_application_id') or hashlib.sha256(body_bytes).hexdigest())
    dup = await db.job_board_webhook_events.find_one({'webhook_id': webhook_id, 'idempotency_key': idempotency_key})
    if dup:
        return {'ok': True, 'status': 'duplicate_delivery', 'application_id': dup.get('application_id')}

    resume_bytes, resume_filename = await _extract_resume(payload)
    app = NormalizedApplication(
        provider='generic_webhook',
        external_application_id=payload.get('external_application_id'),
        external_candidate_id=payload.get('external_candidate_id'),
        external_job_id=payload.get('external_job_id'), job_id=payload.get('job_id'),
        name=payload.get('name'), first_name=payload.get('first_name'), last_name=payload.get('last_name'),
        email=payload.get('email'), phone=payload.get('phone'), location=payload.get('location'),
        linkedin_url=payload.get('linkedin_url'), portfolio_url=payload.get('portfolio_url'),
        cover_letter=payload.get('cover_letter'), screening_answers=payload.get('screening_answers') or [],
        applied_at=payload.get('applied_at'), resume_bytes=resume_bytes, resume_filename=resume_filename,
        raw_payload=payload,
    )
    result = await ingest_application('generic_webhook', app)
    await db.job_board_webhook_events.insert_one({
        'id': new_id(), 'webhook_id': webhook_id, 'idempotency_key': idempotency_key,
        'application_id': result.get('application_id'), 'ok': result.get('ok'), 'received_at': now_iso(),
    })
    if not result.get('ok'):
        await _log_sync(None, 'generic_webhook', 'webhook_received', 'error', result.get('error'), integration_id=webhook_id)
        raise HTTPException(status_code=422, detail=result.get('error'))
    await _log_sync(None, 'generic_webhook', 'webhook_received', 'success',
                     f"Application ingested ({result['status']})", integration_id=webhook_id)
    return {'ok': True, **result}


# ==================== Public: Generic XML Job Feed ====================

def _xml_escape(s) -> str:
    return (str(s) if s is not None else '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _job_xml_item(job: dict, pub: dict, company_name: str) -> str:
    url = f"{APP_BASE_URL}/careers/jobs/{job['slug']}" if job.get('slug') else ''
    return (
        '  <job>\n'
        f'    <id>{_xml_escape(job["id"])}</id>\n'
        f'    <title>{_xml_escape(job.get("title"))}</title>\n'
        f'    <description><![CDATA[{job.get("jd_text") or job.get("description") or ""}]]></description>\n'
        f'    <company>{_xml_escape(company_name)}</company>\n'
        f'    <location>{_xml_escape(job.get("location"))}</location>\n'
        f'    <employment_type>{_xml_escape(job.get("employment_type"))}</employment_type>\n'
        f'    <salary>{_xml_escape(job.get("salary_range"))}</salary>\n'
        f'    <url>{_xml_escape(url)}</url>\n'
        f'    <date_posted>{_xml_escape(job.get("created_at"))}</date_posted>\n'
        f'    <date_updated>{_xml_escape(pub.get("updated_at") or job.get("updated_at"))}</date_updated>\n'
        f'    <expiration_date>{_xml_escape(pub.get("expires_at"))}</expiration_date>\n'
        f'    <remote>{_xml_escape(job.get("remote_type"))}</remote>\n'
        '  </job>'
    )


@public_router.get('/job-feeds/{company_slug}/jobs.xml')
async def public_job_feed_xml(company_slug: str):
    t = await get_tenant_by_slug(company_slug)
    if not t:
        raise HTTPException(status_code=404, detail='Unknown company')
    with tenant_scope(t['id']):
        pubs = await db.job_board_publications.find(
            {'provider': 'generic_xml', 'status': {'$in': ['published', 'updated']}}, {'_id': 0},
        ).to_list(1000)
        job_ids = [p['job_id'] for p in pubs]
        items = []
        if job_ids:
            jobs = await db.jobs.find({'id': {'$in': job_ids}, 'status': 'open'}, {'_id': 0}).to_list(1000)
            settings = await db.career_settings.find_one({'key': 'singleton'}, {'_id': 0, 'company_name': 1})
            company_name = (settings or {}).get('company_name') or t.get('name') or company_slug
            pub_by_job = {p['job_id']: p for p in pubs}
            items = [_job_xml_item(j, pub_by_job.get(j['id'], {}), company_name) for j in jobs]
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<source>\n' + '\n'.join(items) + '\n</source>\n'
    return Response(content=body, media_type='application/xml')
