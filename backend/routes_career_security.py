"""Career Portal — Phase 5: custom domain + DNS/SSL, email templates, cookie banner,
reCAPTCHA v3, rate limiting, and career-scoped audit log."""
import os
import re
import secrets
from typing import Optional

import dns.resolver
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import require_roles
from database import db
from email_templates import (
    DEFAULT_TEMPLATES,
    VARIABLE_HELP,
    build_context_from_candidate,
    render,
    send_template,
)
from utils import clean, log_audit, new_id, now_iso

router = APIRouter(prefix='/career', tags=['career-security'])

APP_BASE_URL = os.environ['APP_BASE_URL']

# CNAME target the customer's custom domain should point to. Derived from APP_BASE_URL host.
_APP_HOST = APP_BASE_URL.replace('https://', '').replace('http://', '').rstrip('/')

_DOMAIN_RE = re.compile(r'^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(\.(?!-)[a-zA-Z0-9-]{1,63}(?<!-))+$')


# ---------------- Custom Domain ----------------

class CustomDomainSet(BaseModel):
    domain: str


async def _get_settings():
    return await db.career_settings.find_one({'key': 'singleton'}, {'_id': 0}) or {}


@router.get('/settings/custom-domain')
async def get_custom_domain(user: dict = Depends(require_roles('admin', 'recruiter'))):
    s = await _get_settings()
    domain = s.get('custom_domain')
    return {
        'domain': domain,
        'status': s.get('custom_domain_status') or ('none' if not domain else 'pending'),
        'verification_token': s.get('custom_domain_verification_token'),
        'verified_at': s.get('custom_domain_verified_at'),
        'cname_target': _APP_HOST,
        'txt_record_host': f'_ats-verify.{domain}' if domain else None,
        'app_base_url': APP_BASE_URL,
    }


@router.put('/settings/custom-domain')
async def set_custom_domain(body: CustomDomainSet, user: dict = Depends(require_roles('admin'))):
    domain = body.domain.strip().lower().replace('https://', '').replace('http://', '').rstrip('/')
    if not _DOMAIN_RE.match(domain):
        raise HTTPException(status_code=422, detail='Enter a valid domain, e.g. careers.acme.com')
    token = f'ats-verify-{secrets.token_urlsafe(16)}'
    updates = {
        'custom_domain': domain,
        'custom_domain_status': 'pending',
        'custom_domain_verification_token': token,
        'custom_domain_verified_at': None,
        'updated_at': now_iso(),
    }
    await db.career_settings.update_one({'key': 'singleton'}, {'$set': updates}, upsert=True)
    await log_audit(user, 'career.custom_domain.set', 'career_portal', 'singleton', f'Set custom domain to {domain}')
    return {'domain': domain, 'status': 'pending', 'verification_token': token,
            'cname_target': _APP_HOST, 'txt_record_host': f'_ats-verify.{domain}'}


@router.post('/settings/custom-domain/verify')
async def verify_custom_domain(user: dict = Depends(require_roles('admin'))):
    s = await _get_settings()
    domain = s.get('custom_domain')
    token = s.get('custom_domain_verification_token')
    if not domain or not token:
        raise HTTPException(status_code=400, detail='No custom domain set. Configure one first.')

    checks = {'txt': {'ok': False, 'found': [], 'expected': token},
              'cname': {'ok': False, 'found': [], 'expected': _APP_HOST}}
    # TXT check
    try:
        answers = dns.resolver.resolve(f'_ats-verify.{domain}', 'TXT', lifetime=5)
        for r in answers:
            val = b''.join(r.strings).decode('utf-8', errors='ignore') if hasattr(r, 'strings') else str(r).strip('"')
            checks['txt']['found'].append(val)
            if val == token:
                checks['txt']['ok'] = True
    except Exception as e:
        checks['txt']['error'] = str(e)[:200]
    # CNAME check
    try:
        answers = dns.resolver.resolve(domain, 'CNAME', lifetime=5)
        for r in answers:
            target = str(r.target).rstrip('.')
            checks['cname']['found'].append(target)
            if target == _APP_HOST:
                checks['cname']['ok'] = True
    except Exception as e:
        checks['cname']['error'] = str(e)[:200]

    verified = checks['txt']['ok'] and checks['cname']['ok']
    new_status = 'verified' if verified else 'failed'
    upd = {'custom_domain_status': new_status, 'updated_at': now_iso()}
    if verified:
        upd['custom_domain_verified_at'] = now_iso()
    await db.career_settings.update_one({'key': 'singleton'}, {'$set': upd})
    if verified:
        await log_audit(user, 'career.custom_domain.verified', 'career_portal', 'singleton', f'Verified {domain}')
    return {'domain': domain, 'status': new_status, 'checks': checks}


@router.delete('/settings/custom-domain')
async def remove_custom_domain(user: dict = Depends(require_roles('admin'))):
    s = await _get_settings()
    old = s.get('custom_domain')
    await db.career_settings.update_one({'key': 'singleton'}, {'$unset': {
        'custom_domain': '', 'custom_domain_status': '',
        'custom_domain_verification_token': '', 'custom_domain_verified_at': '',
    }})
    if old:
        await log_audit(user, 'career.custom_domain.removed', 'career_portal', 'singleton', f'Removed {old}')
    return {'ok': True}


# ---------------- Email Templates ----------------

class TemplateUpdate(BaseModel):
    subject: Optional[str] = None
    html_body: Optional[str] = None
    enabled: Optional[bool] = None
    auto_send: Optional[bool] = None


class TemplateTest(BaseModel):
    to_email: str


@router.get('/email-templates')
async def list_templates(user: dict = Depends(require_roles('admin', 'recruiter'))):
    docs = await db.email_templates.find({}, {'_id': 0}).sort('key', 1).to_list(50)
    return {'templates': docs, 'variables': VARIABLE_HELP}


@router.get('/email-templates/{key}')
async def get_template(key: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    doc = await db.email_templates.find_one({'key': key}, {'_id': 0})
    if not doc:
        raise HTTPException(status_code=404, detail='Template not found')
    return {'template': doc, 'variables': VARIABLE_HELP}


@router.put('/email-templates/{key}')
async def update_template(key: str, body: TemplateUpdate,
                          user: dict = Depends(require_roles('admin', 'recruiter'))):
    existing = await db.email_templates.find_one({'key': key})
    if not existing:
        raise HTTPException(status_code=404, detail='Template not found')
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates['updated_at'] = now_iso()
    await db.email_templates.update_one({'key': key}, {'$set': updates})
    await log_audit(user, 'career.email_template.updated', 'email_template', key, f'Updated template "{key}"')
    doc = await db.email_templates.find_one({'key': key}, {'_id': 0})
    return doc


@router.post('/email-templates/{key}/reset')
async def reset_template(key: str, user: dict = Depends(require_roles('admin'))):
    default = DEFAULT_TEMPLATES.get(key)
    if not default:
        raise HTTPException(status_code=404, detail='No default for this template')
    await db.email_templates.update_one(
        {'key': key},
        {'$set': {**default, 'updated_at': now_iso()}},
        upsert=True,
    )
    await log_audit(user, 'career.email_template.reset', 'email_template', key, f'Reset "{key}" to default')
    doc = await db.email_templates.find_one({'key': key}, {'_id': 0})
    return doc


@router.post('/email-templates/{key}/test')
async def test_template(key: str, body: TemplateTest, user: dict = Depends(require_roles('admin', 'recruiter'))):
    tpl = await db.email_templates.find_one({'key': key}, {'_id': 0})
    if not tpl:
        raise HTTPException(status_code=404, detail='Template not found')
    settings = await _get_settings()
    fake_candidate = {'name': user.get('name'), 'email': body.to_email, 'stage': 'Applied'}
    fake_job = {'title': 'Sample Role'}
    ctx = build_context_from_candidate(fake_candidate, fake_job, settings)
    subject = f'[TEST] {render(tpl["subject"], ctx)}'
    html = render(tpl['html_body'], ctx)
    result = await send_template(
        template_key=key,
        to_email=body.to_email,
        context=ctx,
        recruiter_id=user.get('id'),
    )
    # Override subject with test prefix in the log to make it obvious
    if result.get('sent'):
        return {'sent': True, 'preview_subject': subject, 'preview_html': html, 'sender': result.get('sender')}
    return {'sent': False, 'reason': result.get('reason'), 'error': result.get('error'),
            'preview_subject': subject, 'preview_html': html}


@router.get('/email-templates/{key}/preview')
async def preview_template(key: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    tpl = await db.email_templates.find_one({'key': key}, {'_id': 0})
    if not tpl:
        raise HTTPException(status_code=404, detail='Template not found')
    settings = await _get_settings()
    fake_candidate = {'name': 'Jane Doe', 'email': 'jane@example.com', 'stage': 'Screening'}
    fake_job = {'title': 'Senior Product Designer'}
    ctx = build_context_from_candidate(fake_candidate, fake_job, settings)
    return {'subject': render(tpl['subject'], ctx), 'html': render(tpl['html_body'], ctx)}


# ---------------- Manual send (used from candidate profile in future / test in UI) ----------------

class ManualSendBody(BaseModel):
    template_key: str
    candidate_id: str


@router.post('/email-templates/send-to-candidate')
async def send_to_candidate(body: ManualSendBody, user: dict = Depends(require_roles('admin', 'recruiter'))):
    cand = await db.candidates.find_one({'id': body.candidate_id}, {'_id': 0})
    if not cand:
        raise HTTPException(status_code=404, detail='Candidate not found')
    job = await db.jobs.find_one({'id': cand.get('job_id')}, {'_id': 0}) if cand.get('job_id') else None
    settings = await _get_settings()
    ctx = build_context_from_candidate(cand, job or {}, settings)
    result = await send_template(
        template_key=body.template_key,
        to_email=cand.get('email'),
        context=ctx,
        recruiter_id=cand.get('recruiter_id') or user.get('id'),
    )
    if result.get('sent'):
        await log_audit(user, 'career.email.sent', 'candidate', cand['id'],
                        f"Sent '{body.template_key}' to {cand.get('email')}")
    return result


# ---------------- Cookie / Privacy / reCAPTCHA / Rate limit settings ----------------

class SecuritySettingsUpdate(BaseModel):
    # Cookie banner
    cookie_banner_enabled: Optional[bool] = None
    cookie_banner_text: Optional[str] = None
    privacy_policy_url: Optional[str] = None
    terms_url: Optional[str] = None
    # reCAPTCHA v3
    recaptcha_enabled: Optional[bool] = None
    recaptcha_site_key: Optional[str] = None
    recaptcha_secret_key: Optional[str] = None
    recaptcha_min_score: Optional[float] = None
    # Rate limiting (per-IP sliding window)
    rate_limit_apply_per_hour: Optional[int] = None
    rate_limit_public_per_minute: Optional[int] = None


@router.get('/settings/security')
async def get_security_settings(user: dict = Depends(require_roles('admin', 'recruiter'))):
    s = await _get_settings()
    # Never leak the reCAPTCHA secret key to the client — return a masked hint only
    secret = s.get('recaptcha_secret_key') or ''
    return {
        'cookie_banner_enabled': s.get('cookie_banner_enabled', False),
        'cookie_banner_text': s.get('cookie_banner_text',
            'We use essential cookies to make our careers site work. By continuing, you agree to our privacy policy.'),
        'privacy_policy_url': s.get('privacy_policy_url'),
        'terms_url': s.get('terms_url'),
        'recaptcha_enabled': s.get('recaptcha_enabled', False),
        'recaptcha_site_key': s.get('recaptcha_site_key'),
        'recaptcha_secret_key_set': bool(secret),
        'recaptcha_secret_key_hint': (secret[:4] + '…' + secret[-4:]) if len(secret) >= 8 else None,
        'recaptcha_min_score': s.get('recaptcha_min_score', 0.5),
        'rate_limit_apply_per_hour': s.get('rate_limit_apply_per_hour', 5),
        'rate_limit_public_per_minute': s.get('rate_limit_public_per_minute', 60),
    }


@router.put('/settings/security')
async def update_security_settings(body: SecuritySettingsUpdate,
                                   user: dict = Depends(require_roles('admin'))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=422, detail='Nothing to update')
    # Clamp values
    if 'recaptcha_min_score' in updates:
        updates['recaptcha_min_score'] = max(0.0, min(1.0, float(updates['recaptcha_min_score'])))
    if 'rate_limit_apply_per_hour' in updates:
        updates['rate_limit_apply_per_hour'] = max(0, min(1000, int(updates['rate_limit_apply_per_hour'])))
    if 'rate_limit_public_per_minute' in updates:
        updates['rate_limit_public_per_minute'] = max(0, min(10000, int(updates['rate_limit_public_per_minute'])))
    updates['updated_at'] = now_iso()
    await db.career_settings.update_one({'key': 'singleton'}, {'$set': updates}, upsert=True)
    # Mask secret in audit log
    audit_details_updates = dict(updates)
    if 'recaptcha_secret_key' in audit_details_updates:
        audit_details_updates['recaptcha_secret_key'] = '***'
    await log_audit(user, 'career.security.updated', 'career_portal', 'singleton',
                    f'Updated security settings: {", ".join(k for k in audit_details_updates if k != "updated_at")}')
    return await get_security_settings(user)


async def verify_recaptcha_token(token: Optional[str], settings: dict) -> tuple[bool, str]:
    """Verify a reCAPTCHA v3 token server-side. Returns (ok, reason_if_failed)."""
    if not settings.get('recaptcha_enabled'):
        return True, ''
    secret = settings.get('recaptcha_secret_key')
    if not secret:
        # reCAPTCHA enabled but not configured — fail closed to avoid silent spam.
        return False, 'reCAPTCHA is required but the secret key is not configured. Contact the site admin.'
    if not token:
        return False, 'reCAPTCHA token missing. Please refresh the page and try again.'
    min_score = float(settings.get('recaptcha_min_score', 0.5))
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post('https://www.google.com/recaptcha/api/siteverify',
                             data={'secret': secret, 'response': token})
            data = r.json()
    except Exception as e:
        return False, f'Could not reach reCAPTCHA (verification failed: {str(e)[:80]}).'
    if not data.get('success'):
        return False, 'reCAPTCHA verification failed. Please try again.'
    if data.get('score') is not None and float(data['score']) < min_score:
        return False, f'reCAPTCHA score too low ({data["score"]:.2f} < {min_score:.2f}). Try again.'
    return True, ''


# ---------------- Career-scoped audit log ----------------

@router.get('/audit-log')
async def career_audit_log(limit: int = 100, user: dict = Depends(require_roles('admin', 'recruiter'))):
    """All audit entries whose action is prefixed 'career.' — the Phase 5 scope."""
    q = {'action': {'$regex': '^career\\.'}}
    docs = await db.audit_log.find(q, {'_id': 0}).sort('created_at', -1).to_list(min(limit, 500))
    return clean(docs)


# ---------------- Public config (no auth) for the frontend to know if reCAPTCHA / cookie banner is on ----------------

@router.get('/public/security-config')
async def public_security_config():
    s = await _get_settings()
    if not s.get('portal_enabled'):
        raise HTTPException(status_code=404, detail='Career portal is not available')
    return {
        'cookie_banner_enabled': s.get('cookie_banner_enabled', False),
        'cookie_banner_text': s.get('cookie_banner_text',
            'We use essential cookies to make our careers site work. By continuing, you agree to our privacy policy.'),
        'privacy_policy_url': s.get('privacy_policy_url'),
        'terms_url': s.get('terms_url'),
        'recaptcha_enabled': s.get('recaptcha_enabled', False),
        'recaptcha_site_key': s.get('recaptcha_site_key') if s.get('recaptcha_enabled') else None,
    }
