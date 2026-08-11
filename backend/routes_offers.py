"""Offer letter + sequential approval workflow (Lever-style).

Flow: an admin/recruiter creates an offer for a candidate and picks an ordered
list of approvers (any user, any role). Approvers act one at a time — the next
approver is only notified once the previous one approves. Once every approver
has signed off, the offer is "approved" and the recruiter can send a rendered
offer letter to the candidate via a shareable, no-login link where the
candidate can Accept or Decline.
"""
import os
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import get_current_user, require_roles
from database import db, raw_db
from tenant_context import set_tenant_id
from email_templates import render, send_custom
from permissions import is_admin_or_higher
from rate_limiter import enforce as rate_limit
from utils import clean, log_activity, log_audit, new_id, notify, now_iso

router = APIRouter(prefix='/offers', tags=['offers'])

APP_BASE_URL = os.environ['APP_BASE_URL']

DEFAULT_TEMPLATE = {
    'subject': 'Your Offer from {{company_name}} — {{job_title}}',
    'html_body': (
        '<div style="font-family:Georgia,serif;max-width:560px;margin:0 auto;padding:8px;color:#1e293b;line-height:1.65;">'
        '<h1 style="font-size:21px;margin:0 0 4px;">{{company_name}}</h1>'
        '<p style="color:#64748b;font-size:12px;letter-spacing:0.06em;text-transform:uppercase;margin:0 0 24px;">Offer of Employment</p>'
        '<p>Dear {{candidate_name}},</p>'
        '<p>We are delighted to offer you the position of <strong>{{job_title}}</strong> at {{company_name}}. '
        "We were impressed by your background and are excited about the possibility of you joining our team. "
        'Below are the key details of your offer:</p>'
        '<table style="width:100%;border-collapse:collapse;margin:20px 0;font-size:14px;">'
        '<tr><td style="padding:7px 0;color:#64748b;width:45%;">Position</td><td style="padding:7px 0;font-weight:600;">{{job_title}}</td></tr>'
        '<tr><td style="padding:7px 0;color:#64748b;">Start Date</td><td style="padding:7px 0;font-weight:600;">{{start_date}}</td></tr>'
        '<tr><td style="padding:7px 0;color:#64748b;">Base Salary</td><td style="padding:7px 0;font-weight:600;">{{base_salary}}</td></tr>'
        '<tr><td style="padding:7px 0;color:#64748b;">Bonus</td><td style="padding:7px 0;font-weight:600;">{{bonus}}</td></tr>'
        '<tr><td style="padding:7px 0;color:#64748b;">Equity</td><td style="padding:7px 0;font-weight:600;">{{equity}}</td></tr>'
        '<tr><td style="padding:7px 0;color:#64748b;">Reporting Manager</td><td style="padding:7px 0;font-weight:600;">{{reporting_manager}}</td></tr>'
        '<tr><td style="padding:7px 0;color:#64748b;">Offer Expires</td><td style="padding:7px 0;font-weight:600;">{{offer_expiry_date}}</td></tr>'
        '</table>'
        '<p>{{custom_notes}}</p>'
        '<p>We are excited about the prospect of you joining us and look forward to your response.</p>'
        '<p style="margin-top:28px;">Warm regards,<br/><strong>{{recruiter_name}}</strong><br/>{{company_name}}</p>'
        '</div>'
    ),
}


async def _get_template() -> dict:
    tpl = await db.settings.find_one({'key': 'offer_letter_template'}, {'_id': 0})
    if not tpl:
        tpl = {'key': 'offer_letter_template', **DEFAULT_TEMPLATE, 'created_at': now_iso(), 'updated_at': now_iso()}
        await db.settings.insert_one(dict(tpl))
    return tpl


async def _build_context(offer: dict, candidate: dict, job: Optional[dict]) -> dict:
    settings = await db.career_settings.find_one({'key': 'singleton'}, {'_id': 0}) or {}
    salary_str = 'TBD'
    if offer.get('base_salary') is not None:
        try:
            salary_str = f"{offer.get('salary_currency', 'USD')} {float(offer['base_salary']):,.0f}"
        except (TypeError, ValueError):
            salary_str = str(offer['base_salary'])
    return {
        'candidate_name': candidate.get('name', ''),
        'candidate_first_name': (candidate.get('name') or '').split(' ')[0],
        'candidate_email': candidate.get('email', ''),
        'job_title': (job.get('title') if job else offer.get('job_title')) or '',
        'company_name': settings.get('company_name') or 'Our Company',
        'start_date': offer.get('start_date') or 'TBD',
        'base_salary': salary_str,
        'bonus': offer.get('bonus') or '—',
        'equity': offer.get('equity') or '—',
        'reporting_manager': offer.get('reporting_manager') or '—',
        'offer_expiry_date': offer.get('offer_expiry_date') or '—',
        'custom_notes': offer.get('custom_notes') or '',
        'recruiter_name': offer.get('created_by_name') or '',
    }


def _visible_offer_query(user: dict) -> dict:
    if is_admin_or_higher(user):
        return {}
    return {'$or': [{'created_by': user['id']}, {'approvers.user_id': user['id']}]}


def _assert_can_view(offer: dict, user: dict):
    if is_admin_or_higher(user):
        return
    allowed = offer.get('created_by') == user['id'] or any(a['user_id'] == user['id'] for a in offer.get('approvers', []))
    if not allowed:
        raise HTTPException(status_code=403, detail='Not authorized to view this offer')


class ApproverIn(BaseModel):
    user_id: str


class OfferCreate(BaseModel):
    candidate_id: str
    start_date: Optional[str] = None
    base_salary: Optional[float] = None
    salary_currency: str = 'USD'
    bonus: Optional[str] = None
    equity: Optional[str] = None
    reporting_manager: Optional[str] = None
    offer_expiry_date: Optional[str] = None
    custom_notes: Optional[str] = None
    approvers: list[ApproverIn] = Field(default_factory=list)


@router.post('')
async def create_offer(body: OfferCreate, user: dict = Depends(require_roles('admin', 'recruiter'))):
    candidate = await db.candidates.find_one({'id': body.candidate_id}, {'_id': 0})
    if not candidate:
        raise HTTPException(status_code=404, detail='Candidate not found')
    if not body.approvers:
        raise HTTPException(status_code=422, detail='At least one approver is required')
    job = await db.jobs.find_one({'id': candidate.get('job_id')}, {'_id': 0}) if candidate.get('job_id') else None

    approver_ids = [a.user_id for a in body.approvers]
    approver_users = await db.users.find({'id': {'$in': approver_ids}}, {'_id': 0, 'password_hash': 0}).to_list(len(approver_ids))
    by_id = {u['id']: u for u in approver_users}
    approvers = []
    for i, a in enumerate(body.approvers):
        u = by_id.get(a.user_id)
        if not u:
            raise HTTPException(status_code=404, detail=f'Approver user not found: {a.user_id}')
        approvers.append({
            'step': i + 1, 'user_id': a.user_id, 'user_name': u.get('name'), 'user_email': u.get('email'),
            'status': 'pending', 'comment': None, 'acted_at': None,
        })

    offer = {
        'id': new_id(),
        'candidate_id': body.candidate_id,
        'candidate_name': candidate.get('name'),
        'job_id': candidate.get('job_id'),
        'job_title': job.get('title') if job else None,
        'created_by': user['id'],
        'created_by_name': user.get('name'),
        'created_at': now_iso(),
        'updated_at': now_iso(),
        'status': 'pending_approval',
        'start_date': body.start_date,
        'base_salary': body.base_salary,
        'salary_currency': body.salary_currency or 'USD',
        'bonus': body.bonus,
        'equity': body.equity,
        'reporting_manager': body.reporting_manager,
        'offer_expiry_date': body.offer_expiry_date,
        'custom_notes': body.custom_notes,
        'approvers': approvers,
        'current_step': 1,
        'public_token': None,
        'sent_at': None,
        'sent_by': None,
        'email_sent': False,
        'response_status': None,
        'response_comment': None,
        'responded_at': None,
    }
    await db.offers.insert_one(dict(offer))
    await log_activity(user, 'offer_created', f"Created an offer for {candidate.get('name')}", candidate_id=body.candidate_id, job_id=candidate.get('job_id'))
    await log_audit(user, 'offer_created', 'offer', offer['id'], f"Offer for {candidate.get('name')}")
    await notify(approvers[0]['user_id'], 'offer_approval',
                 f"{candidate.get('name')}'s offer needs your approval (step 1 of {len(approvers)})",
                 f"/candidates/{body.candidate_id}")
    return clean(offer)


@router.get('')
async def list_offers(candidate_id: Optional[str] = None, job_id: Optional[str] = None, status: Optional[str] = None,
                       pending_my_approval: bool = False, user: dict = Depends(get_current_user)):
    q = _visible_offer_query(user)
    if candidate_id:
        q = {**q, 'candidate_id': candidate_id} if q else {'candidate_id': candidate_id}
    if job_id:
        q = {**q, 'job_id': job_id} if q else {'job_id': job_id}
    if status:
        q = {**q, 'status': status} if q else {'status': status}
    offers = await db.offers.find(q, {'_id': 0}).sort('created_at', -1).to_list(500)
    if pending_my_approval:
        offers = [
            o for o in offers
            if o.get('status') == 'pending_approval' and o.get('approvers')
            and 0 < o.get('current_step', 0) <= len(o['approvers'])
            and o['approvers'][o['current_step'] - 1]['user_id'] == user['id']
        ]
    return offers


@router.get('/settings/template')
async def get_offer_template(user: dict = Depends(require_roles('admin'))):
    return await _get_template()


class TemplateUpdate(BaseModel):
    subject: str
    html_body: str


@router.put('/settings/template')
async def update_offer_template(body: TemplateUpdate, user: dict = Depends(require_roles('admin'))):
    await _get_template()
    await db.settings.update_one({'key': 'offer_letter_template'},
                                  {'$set': {'subject': body.subject, 'html_body': body.html_body, 'updated_at': now_iso()}})
    return await _get_template()


@router.get('/{offer_id}')
async def get_offer(offer_id: str, user: dict = Depends(get_current_user)):
    offer = await db.offers.find_one({'id': offer_id}, {'_id': 0})
    if not offer:
        raise HTTPException(status_code=404, detail='Offer not found')
    _assert_can_view(offer, user)
    return offer


class ApproveBody(BaseModel):
    comment: Optional[str] = None


class RejectBody(BaseModel):
    comment: str


@router.post('/{offer_id}/approve')
async def approve_offer(offer_id: str, body: ApproveBody, user: dict = Depends(get_current_user)):
    offer = await db.offers.find_one({'id': offer_id})
    if not offer:
        raise HTTPException(status_code=404, detail='Offer not found')
    if offer['status'] != 'pending_approval':
        raise HTTPException(status_code=422, detail='This offer is not awaiting approval')
    approvers = offer['approvers']
    step = offer['current_step']
    current = approvers[step - 1]
    if current['user_id'] != user['id']:
        raise HTTPException(status_code=403, detail='It is not your turn to approve this offer')
    current['status'] = 'approved'
    current['comment'] = body.comment
    current['acted_at'] = now_iso()
    is_last = step == len(approvers)
    updates = {'approvers': approvers, 'updated_at': now_iso()}
    if is_last:
        updates['status'] = 'approved'
    else:
        updates['current_step'] = step + 1
    await db.offers.update_one({'id': offer_id}, {'$set': updates})
    await log_audit(user, 'offer_approved', 'offer', offer_id, f"Step {step} approved" + (f': {body.comment}' if body.comment else ''))
    await log_activity(user, 'offer_approved', f"Approved offer for {offer.get('candidate_name')} (step {step})",
                        candidate_id=offer['candidate_id'], job_id=offer.get('job_id'))
    if offer['created_by'] != user['id']:
        msg = f"{user.get('name')} approved {offer.get('candidate_name')}'s offer"
        if is_last:
            msg += ' — fully approved!'
        await notify(offer['created_by'], 'offer_approval', msg, f"/candidates/{offer['candidate_id']}")
    if not is_last:
        nxt = approvers[step]
        await notify(nxt['user_id'], 'offer_approval',
                     f"{offer.get('candidate_name')}'s offer needs your approval (step {step + 1} of {len(approvers)})",
                     f"/candidates/{offer['candidate_id']}")
    return clean(await db.offers.find_one({'id': offer_id}, {'_id': 0}))


@router.post('/{offer_id}/reject')
async def reject_offer(offer_id: str, body: RejectBody, user: dict = Depends(get_current_user)):
    offer = await db.offers.find_one({'id': offer_id})
    if not offer:
        raise HTTPException(status_code=404, detail='Offer not found')
    if offer['status'] != 'pending_approval':
        raise HTTPException(status_code=422, detail='This offer is not awaiting approval')
    if not body.comment or not body.comment.strip():
        raise HTTPException(status_code=422, detail='A reason is required to reject an offer')
    approvers = offer['approvers']
    step = offer['current_step']
    current = approvers[step - 1]
    if current['user_id'] != user['id']:
        raise HTTPException(status_code=403, detail='It is not your turn to act on this offer')
    current['status'] = 'rejected'
    current['comment'] = body.comment
    current['acted_at'] = now_iso()
    await db.offers.update_one({'id': offer_id}, {'$set': {'approvers': approvers, 'status': 'rejected', 'updated_at': now_iso()}})
    await log_audit(user, 'offer_rejected', 'offer', offer_id, f'Step {step} rejected: {body.comment}')
    await log_activity(user, 'offer_rejected', f"Rejected offer for {offer.get('candidate_name')}: {body.comment}",
                        candidate_id=offer['candidate_id'], job_id=offer.get('job_id'))
    if offer['created_by'] != user['id']:
        await notify(offer['created_by'], 'offer_approval',
                     f"{user.get('name')} rejected {offer.get('candidate_name')}'s offer: {body.comment}",
                     f"/candidates/{offer['candidate_id']}")
    return clean(await db.offers.find_one({'id': offer_id}, {'_id': 0}))


@router.post('/{offer_id}/cancel')
async def cancel_offer(offer_id: str, user: dict = Depends(get_current_user)):
    offer = await db.offers.find_one({'id': offer_id})
    if not offer:
        raise HTTPException(status_code=404, detail='Offer not found')
    if offer['status'] not in ('pending_approval', 'approved', 'rejected'):
        raise HTTPException(status_code=422, detail='This offer can no longer be cancelled')
    if not (is_admin_or_higher(user) or offer['created_by'] == user['id']):
        raise HTTPException(status_code=403, detail='Only the creator or an admin can cancel this offer')
    await db.offers.update_one({'id': offer_id}, {'$set': {'status': 'cancelled', 'updated_at': now_iso()}})
    await log_audit(user, 'offer_cancelled', 'offer', offer_id, '')
    return {'ok': True}


@router.get('/{offer_id}/letter')
async def preview_letter(offer_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    offer = await db.offers.find_one({'id': offer_id}, {'_id': 0})
    if not offer:
        raise HTTPException(status_code=404, detail='Offer not found')
    candidate = await db.candidates.find_one({'id': offer['candidate_id']}, {'_id': 0}) or {}
    job = await db.jobs.find_one({'id': offer['job_id']}, {'_id': 0}) if offer.get('job_id') else None
    tpl = await _get_template()
    ctx = await _build_context(offer, candidate, job)
    return {'subject': render(tpl['subject'], ctx), 'html': render(tpl['html_body'], ctx)}


@router.post('/{offer_id}/send')
async def send_offer(offer_id: str, user: dict = Depends(require_roles('admin', 'recruiter'))):
    offer = await db.offers.find_one({'id': offer_id})
    if not offer:
        raise HTTPException(status_code=404, detail='Offer not found')
    if offer['status'] != 'approved':
        raise HTTPException(status_code=422, detail='Offer must be fully approved before it can be sent')
    candidate = await db.candidates.find_one({'id': offer['candidate_id']}, {'_id': 0}) or {}
    job = await db.jobs.find_one({'id': offer['job_id']}, {'_id': 0}) if offer.get('job_id') else None
    token = secrets.token_urlsafe(24)
    link = f'{APP_BASE_URL}/offer/{token}'
    tpl = await _get_template()
    ctx = await _build_context(offer, candidate, job)
    ctx['offer_link'] = link
    subject = render(tpl['subject'], ctx)
    html = render(tpl['html_body'], ctx) + (
        f'<div style="margin-top:24px;text-align:center;">'
        f'<a href="{link}" style="display:inline-block;background:#10b981;color:#fff;text-decoration:none;'
        f'font-weight:600;padding:12px 28px;border-radius:8px;">View &amp; Respond to Offer</a></div>'
    )
    email_result = {'sent': False, 'reason': 'no_email_on_candidate'}
    if candidate.get('email'):
        email_result = await send_custom(candidate['email'], subject, html, ctx, sender_user_id=user['id'],
                                          log_meta={'offer_id': offer_id})
    await db.offers.update_one({'id': offer_id}, {'$set': {
        'status': 'sent', 'public_token': token, 'sent_at': now_iso(), 'sent_by': user['id'],
        'email_sent': bool(email_result.get('sent')), 'response_status': 'pending', 'updated_at': now_iso(),
    }})
    await log_audit(user, 'offer_sent', 'offer', offer_id, f"Link generated for {candidate.get('email') or offer.get('candidate_name')}")
    await log_activity(user, 'offer_sent', f"Sent offer letter to {offer.get('candidate_name')}",
                        candidate_id=offer['candidate_id'], job_id=offer.get('job_id'))
    return {'ok': True, 'link': link, 'email_sent': bool(email_result.get('sent')), 'email_reason': email_result.get('reason')}


# ---------------- Public (candidate-facing, no auth) ----------------

@router.get('/public/{token}')
async def public_get_offer(token: str, request: Request):
    rate_limit(request, scope='offer_public', limit=60, window_seconds=60)
    offer = await raw_db.offers.find_one({'public_token': token}, {'_id': 0})
    if not offer or offer['status'] not in ('sent', 'accepted', 'declined'):
        raise HTTPException(status_code=404, detail='This offer link is invalid or no longer available')
    set_tenant_id(offer.get('tenant_id'))
    candidate = await db.candidates.find_one({'id': offer['candidate_id']}, {'_id': 0}) or {}
    job = await db.jobs.find_one({'id': offer['job_id']}, {'_id': 0}) if offer.get('job_id') else None
    tpl = await _get_template()
    ctx = await _build_context(offer, candidate, job)
    return {
        'candidate_name': offer.get('candidate_name'),
        'job_title': offer.get('job_title'),
        'company_name': ctx.get('company_name'),
        'status': offer.get('status'),
        'response_status': offer.get('response_status'),
        'response_comment': offer.get('response_comment'),
        'letter_html': render(tpl['html_body'], ctx),
    }


class RespondBody(BaseModel):
    response: str  # 'accepted' | 'declined'
    comment: Optional[str] = None


@router.post('/public/{token}/respond')
async def public_respond(token: str, body: RespondBody, request: Request):
    rate_limit(request, scope='offer_public_respond', limit=10, window_seconds=60)
    if body.response not in ('accepted', 'declined'):
        raise HTTPException(status_code=422, detail='response must be accepted or declined')
    offer = await raw_db.offers.find_one({'public_token': token})
    if not offer or offer['status'] != 'sent':
        raise HTTPException(status_code=404, detail='This offer has already been responded to or is no longer available')
    set_tenant_id(offer.get('tenant_id'))
    await db.offers.update_one({'id': offer['id']}, {'$set': {
        'status': body.response, 'response_status': body.response, 'response_comment': body.comment,
        'responded_at': now_iso(), 'updated_at': now_iso(),
    }})
    await log_activity(None, f'offer_{body.response}', f"{offer.get('candidate_name')} {body.response} the offer" +
                        (f': {body.comment}' if body.comment else ''), candidate_id=offer['candidate_id'], job_id=offer.get('job_id'))
    if offer.get('created_by'):
        await notify(offer['created_by'], 'offer_approval', f"{offer.get('candidate_name')} {body.response} the offer!",
                     f"/candidates/{offer['candidate_id']}")
    return {'ok': True}
