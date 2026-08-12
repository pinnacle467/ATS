"""Shared application-ingestion pipeline for job-board sourced applications.

Used by the generic webhook endpoint today; designed so the (deferred) email
ingestion channel and any future provider-specific inbound handler can reuse
the exact same logic. Deliberately reuses the EXISTING resume parser
(resume_parser.py) and fit scorer (fit_scorer.py) rather than building new
ones, per the requirement not to duplicate that functionality.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from database import db
from fit_scorer import recompute_candidate_fit
from resume_parser import extract_text_from_bytes, parse_resume_text
from utils import log_activity, log_audit, new_id, next_candidate_code, notify, now_iso

PROVIDER_LABELS = {
    'indeed': 'Indeed', 'ziprecruiter': 'ZipRecruiter', 'linkedin': 'LinkedIn',
    'generic_xml': 'Generic XML Feed', 'generic_webhook': 'Generic Application Webhook',
    'mock': 'Sandbox (Testing)',
}


@dataclass
class NormalizedApplication:
    """The internal normalized application object every inbound channel maps into."""
    provider: str
    external_application_id: Optional[str] = None
    external_candidate_id: Optional[str] = None
    external_job_id: Optional[str] = None
    job_id: Optional[str] = None  # ATS job id, if the sender already knows it
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    cover_letter: Optional[str] = None
    screening_answers: list = field(default_factory=list)
    applied_at: Optional[str] = None
    resume_bytes: Optional[bytes] = None
    resume_filename: Optional[str] = None
    raw_payload: dict = field(default_factory=dict)


def normalize_phone(p: Optional[str]) -> Optional[str]:
    if not p:
        return None
    digits = re.sub(r'\D', '', p)
    return digits[-10:] if len(digits) >= 10 else (digits or None)


async def _resolve_job_id(provider: str, app: NormalizedApplication) -> Optional[str]:
    if app.job_id:
        job = await db.jobs.find_one({'id': app.job_id})
        if job:
            return job['id']
    if app.external_job_id:
        pub = await db.job_board_publications.find_one({'provider': provider, 'external_job_id': app.external_job_id})
        if pub:
            return pub['job_id']
    return None


async def _find_duplicate_candidate(provider: str, app: NormalizedApplication) -> Optional[dict]:
    """Ordered dedup: external_candidate_id+provider -> exact email -> normalized phone."""
    if app.external_candidate_id:
        cand = await db.candidates.find_one({'job_board_refs': {'$elemMatch': {
            'provider': provider, 'external_candidate_id': app.external_candidate_id,
        }}})
        if cand:
            return cand
    email_norm = (app.email or '').strip().lower()
    if email_norm:
        cand = await db.candidates.find_one({'email': {'$regex': f'^{re.escape(email_norm)}$', '$options': 'i'}})
        if cand:
            return cand
    phone_norm = normalize_phone(app.phone)
    if phone_norm:
        with_phone = await db.candidates.find({'phone': {'$ne': None}}, {'_id': 0, 'id': 1, 'phone': 1}).to_list(2000)
        for c in with_phone:
            if normalize_phone(c.get('phone')) == phone_norm:
                return await db.candidates.find_one({'id': c['id']})
    return None


async def ingest_application(provider: str, app: NormalizedApplication, actor: dict = None) -> dict:
    """Runs the full pipeline for one normalized application. Returns a result
    dict describing what happened — never raises for expected/business-level
    outcomes (job not found, duplicate, invalid payload); those come back as
    {'ok': False, 'reason': ...} for the caller to turn into an HTTP response."""
    provider_label = PROVIDER_LABELS.get(provider, provider)

    if not (app.name or app.first_name or app.email or app.phone):
        return {'ok': False, 'reason': 'invalid_payload', 'error': 'Application has no candidate name, email or phone'}

    job_id = await _resolve_job_id(provider, app)
    if not job_id:
        return {'ok': False, 'reason': 'job_not_found',
                'error': 'Could not match this application to a published job posting on this provider'}
    job = await db.jobs.find_one({'id': job_id})

    name = app.name or f'{app.first_name or ""} {app.last_name or ""}'.strip() or 'Unknown Candidate'
    email_norm = (app.email or '').strip().lower() or None
    stage = (job.get('stages') or ['Applied'])[0]

    # Resume storage (reuses the same file/compression pipeline as everywhere else)
    resume_file_id = None
    parsed: dict = {}
    if app.resume_bytes and app.resume_filename:
        try:
            text = extract_text_from_bytes(app.resume_bytes, app.resume_filename)
        except ValueError:
            text = ''
        if len(text) >= 30:
            from routes_resumes import _store_file  # local import avoids a circular import at module load time
            resume_file_id = await _store_file(app.resume_bytes, app.resume_filename, 'application/octet-stream',
                                               (actor or {}).get('id') or 'job_board_ingestion')
            try:
                parsed = await parse_resume_text(text, resume_file_id[:8])
            except Exception:
                parsed = {}

    existing = await _find_duplicate_candidate(provider, app)

    application_doc = {
        'id': new_id(), 'job_id': job_id, 'candidate_id': None,
        'source': provider, 'source_type': 'job_board', 'source_detail': f'{provider_label} application',
        'provider': provider, 'external_candidate_id': app.external_candidate_id,
        'external_application_id': app.external_application_id, 'external_job_id': app.external_job_id,
        'applied_at': app.applied_at or now_iso(), 'cover_letter': app.cover_letter,
        'resume_file_id': resume_file_id, 'raw_payload': app.raw_payload,
        'screening_answers': app.screening_answers, 'status': 'new',
        'potential_duplicate_of': None, 'created_at': now_iso(), 'updated_at': now_iso(),
    }

    if existing:
        application_doc['candidate_id'] = existing['id']
        same_job = existing.get('job_id') == job_id
        if same_job:
            application_doc['status'] = 'linked'
            candidate_id = existing['id']
        else:
            # Different role than the one this person is currently tracked against —
            # do NOT silently move their pipeline; flag for recruiter review.
            application_doc['status'] = 'duplicate_review'
            application_doc['potential_duplicate_of'] = existing['id']
            candidate_id = existing['id']
            if job.get('recruiter_id'):
                await notify(job['recruiter_id'], 'job_board_duplicate',
                             f"{name} (existing candidate) applied to \"{job['title']}\" via {provider_label} — review needed",
                             f'/candidates/{existing["id"]}')
        await db.applications.insert_one(application_doc)
        await log_activity(actor, 'job_board_application', f"{name} applied via {provider_label} to {job['title']}",
                            candidate_id=candidate_id, job_id=job_id)
        await log_audit(actor, 'job_board_application_received', 'application', application_doc['id'],
                         f'{provider_label} -> existing candidate {existing.get("email") or candidate_id} ({"same job" if same_job else "needs duplicate review"})')
        return {'ok': True, 'candidate_id': candidate_id, 'application_id': application_doc['id'],
                'status': application_doc['status'], 'duplicate': not same_job}

    candidate_id = new_id()
    application_doc['candidate_id'] = candidate_id
    cand = {
        'id': candidate_id, 'candidate_code': await next_candidate_code(), 'name': name,
        'email': email_norm, 'phone': app.phone, 'location': app.location,
        'linkedin_url': app.linkedin_url, 'portfolio_url': app.portfolio_url,
        'experience': parsed.get('experience') or [], 'education': parsed.get('education') or [],
        'skills': parsed.get('skills') or [], 'industry': parsed.get('industry') or [],
        'current_title': parsed.get('current_title'), 'current_company': parsed.get('current_company'),
        'job_id': job_id, 'stage': stage, 'source': provider, 'recruiter_id': job.get('recruiter_id'),
        'tags': [], 'resume_file_id': resume_file_id, 'low_confidence_fields': [],
        'notice_period': parsed.get('notice_period'), 'status': 'active', 'rejection_reason': None,
        'fit_score': None, 'fit_score_summary': None, 'fit_score_computed_at': None,
        'applied_at': app.applied_at or now_iso(), 'hired_at': None,
        'created_at': now_iso(), 'updated_at': now_iso(),
        'job_board_refs': [{'provider': provider, 'external_candidate_id': app.external_candidate_id}] if app.external_candidate_id else [],
    }
    await db.candidates.insert_one(cand)
    await db.applications.insert_one(application_doc)
    await log_activity(actor, 'job_board_application', f"{name} applied via {provider_label} to {job['title']}",
                        candidate_id=candidate_id, job_id=job_id)
    await log_audit(actor, 'job_board_application_received', 'application', application_doc['id'],
                     f'{provider_label} -> new candidate {email_norm or name}')
    if job.get('recruiter_id'):
        await notify(job['recruiter_id'], 'application', f"{name} applied to {job['title']} via {provider_label}",
                     f'/candidates/{candidate_id}')
    if job.get('jd_text'):
        await recompute_candidate_fit(candidate_id)
    return {'ok': True, 'candidate_id': candidate_id, 'application_id': application_doc['id'],
            'status': 'new', 'duplicate': False}
