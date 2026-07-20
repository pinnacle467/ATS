"""Career-portal email templates: seed defaults, render, and dispatch via the admin's Gmail.

The applicant "Application received" auto-reply is sent from the connected Gmail
of the job's recruiter (if they've connected Google), else the first admin who
has connected Google. If nobody has connected Google, we silently skip — the
application is still saved.
"""
import re
from typing import Optional

from database import db
from gmail_sender import send_gmail
from google_calendar import get_credentials_for_user
from utils import new_id, now_iso

# key → default template. `enabled=True` means the template is active and (for
# `application_received`) will be auto-fired from the apply endpoint.
DEFAULT_TEMPLATES = {
    'application_received': {
        'key': 'application_received',
        'name': 'Application Received (auto-reply)',
        'description': "Sent to the applicant automatically the moment they submit an application on your careers site.",
        'enabled': True,
        'auto_send': True,
        'subject': 'Thanks for applying to {{job_title}} at {{company_name}}',
        'html_body': (
            "<div style=\"font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#0f172a;\">"
            "<h2 style=\"color:{{primary_color}};margin:0 0 12px;\">We got your application!</h2>"
            "<p>Hi {{candidate_first_name}},</p>"
            "<p>Thanks for applying to <strong>{{job_title}}</strong> at <strong>{{company_name}}</strong>. "
            "Our team will review your profile shortly and reach out with next steps.</p>"
            "<p style=\"color:#64748b;font-size:13px;margin-top:24px;\">— The {{company_name}} team</p>"
            "</div>"
        ),
    },
    'application_shortlisted': {
        'key': 'application_shortlisted',
        'name': 'Application Shortlisted',
        'description': "Sent when a candidate is moved to the 'Screening' or 'Interview' stage. Manual send from the candidate profile.",
        'enabled': True,
        'auto_send': False,
        'subject': "Good news — you've been shortlisted for {{job_title}}",
        'html_body': (
            "<div style=\"font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#0f172a;\">"
            "<h2 style=\"color:{{primary_color}};margin:0 0 12px;\">You've been shortlisted!</h2>"
            "<p>Hi {{candidate_first_name}},</p>"
            "<p>Good news — you've been shortlisted for the <strong>{{job_title}}</strong> role at <strong>{{company_name}}</strong>. "
            "We'll be in touch soon to schedule the next step.</p>"
            "<p style=\"color:#64748b;font-size:13px;margin-top:24px;\">— The {{company_name}} team</p>"
            "</div>"
        ),
    },
    'application_rejected': {
        'key': 'application_rejected',
        'name': 'Application Not Moving Forward',
        'description': "Polite rejection template. Manual send from the candidate profile.",
        'enabled': True,
        'auto_send': False,
        'subject': 'Update on your application for {{job_title}}',
        'html_body': (
            "<div style=\"font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#0f172a;\">"
            "<h2 style=\"color:{{primary_color}};margin:0 0 12px;\">Thank you for your interest</h2>"
            "<p>Hi {{candidate_first_name}},</p>"
            "<p>Thank you for applying to <strong>{{job_title}}</strong> at <strong>{{company_name}}</strong>. "
            "After careful review, we've decided to move forward with other candidates for this role. "
            "We're grateful for the time you invested and encourage you to apply for future openings.</p>"
            "<p style=\"color:#64748b;font-size:13px;margin-top:24px;\">— The {{company_name}} team</p>"
            "</div>"
        ),
    },
    'interview_scheduled': {
        'key': 'interview_scheduled',
        'name': 'Interview Scheduled',
        'description': "Sent to a candidate when an interview is scheduled. Manual send from the interview scheduler.",
        'enabled': True,
        'auto_send': False,
        'subject': 'Interview scheduled — {{job_title}} at {{company_name}}',
        'html_body': (
            "<div style=\"font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#0f172a;\">"
            "<h2 style=\"color:{{primary_color}};margin:0 0 12px;\">Your interview is scheduled</h2>"
            "<p>Hi {{candidate_first_name}},</p>"
            "<p>Your interview for the <strong>{{job_title}}</strong> role at <strong>{{company_name}}</strong> is confirmed. "
            "You'll receive a calendar invite with the meeting link shortly.</p>"
            "<p style=\"color:#64748b;font-size:13px;margin-top:24px;\">— The {{company_name}} team</p>"
            "</div>"
        ),
    },
}

VARIABLE_HELP = {
    '{{candidate_name}}': 'Full applicant name',
    '{{candidate_first_name}}': 'Applicant first name',
    '{{candidate_email}}': 'Applicant email',
    '{{job_title}}': 'Job title being applied for',
    '{{company_name}}': 'Company name (from career settings)',
    '{{stage}}': 'Current pipeline stage',
    '{{primary_color}}': 'Brand primary color (from career settings)',
}


def render(template_str: str, context: dict) -> str:
    """Render `{{var}}` placeholders. Unknown vars are left in place (visible to
    the admin so they notice typos), but missing values fall back to empty string."""
    def _sub(m):
        var = m.group(1).strip()
        return str(context.get(var, m.group(0)))
    return re.sub(r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}', _sub, template_str)


async def _pick_sender_creds(sender_user_id: Optional[str], allow_admin_fallback: bool = False):
    """Return the specified user's Gmail creds. When `allow_admin_fallback` is
    True (only used for system-triggered auto-emails like career-portal
    auto-replies where there is no logged-in user), fall back to the first
    admin/super_admin with connected Google. Otherwise strict: caller MUST
    handle `no_gmail_connected` by prompting the user to connect.
    """
    if sender_user_id:
        u = await db.users.find_one({'id': sender_user_id})
        if u:
            c = await get_credentials_for_user(u)
            if c:
                return c, u
    if not allow_admin_fallback:
        return None, None
    admins = await db.users.find({'role': {'$in': ['admin', 'super_admin']}, 'active': True}).to_list(20)
    for u in admins:
        c = await get_credentials_for_user(u)
        if c:
            return c, u
    return None, None


async def send_template(
    template_key: str,
    to_email: str,
    context: dict,
    sender_user_id: Optional[str] = None,
    # Deprecated alias — old callers used `recruiter_id`. Kept only for backwards
    # compatibility if anything external still passes it.
    recruiter_id: Optional[str] = None,
    allow_admin_fallback: bool = False,
    dedup_window_seconds: Optional[int] = None,
) -> dict:
    """Render + send a template. Returns {sent: bool, reason: str, ...}.

    If `dedup_window_seconds` is provided, we consult `email_log` and skip
    the send if we already dispatched this exact `(template_key, to_email)`
    pair within that window (used by automated / system-triggered sends like
    the career-portal `application_received` auto-reply so a double-submit
    doesn't produce a duplicate confirmation email).
    """
    tpl = await db.email_templates.find_one({'key': template_key}, {'_id': 0})
    if not tpl:
        return {'sent': False, 'reason': 'template_not_found'}
    if not tpl.get('enabled', True):
        return {'sent': False, 'reason': 'template_disabled'}
    if not to_email:
        return {'sent': False, 'reason': 'no_recipient'}

    # Dedup guard (opt-in) — protects automated senders from duplicate delivery
    if dedup_window_seconds and dedup_window_seconds > 0:
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=dedup_window_seconds)).isoformat()
        recent = await db.email_log.find_one({
            'template_key': template_key,
            'to_email': to_email,
            'status': 'sent',
            'created_at': {'$gte': cutoff},
        })
        if recent:
            return {'sent': False, 'reason': 'duplicate_recent_send', 'dedup_of': recent.get('id')}

    creds, sender = await _pick_sender_creds(sender_user_id or recruiter_id, allow_admin_fallback=allow_admin_fallback)
    if not creds:
        return {'sent': False, 'reason': 'no_gmail_connected'}

    subject = render(tpl['subject'], context)
    html = render(tpl['html_body'], context)
    try:
        result = send_gmail(creds, to_email, subject, html)
        await db.email_log.insert_one({
            'id': new_id(),
            'template_key': template_key,
            'to_email': to_email,
            'subject': subject,
            'sender_user_id': sender['id'] if sender else None,
            'gmail_message_id': result.get('id'),
            'status': 'sent',
            'created_at': now_iso(),
        })
        return {'sent': True, 'gmail_id': result.get('id'), 'sender': sender['email'] if sender else None}
    except Exception as e:
        await db.email_log.insert_one({
            'id': new_id(),
            'template_key': template_key,
            'to_email': to_email,
            'subject': subject,
            'sender_user_id': sender['id'] if sender else None,
            'status': 'failed',
            'error': str(e)[:500],
            'created_at': now_iso(),
        })
        return {'sent': False, 'reason': 'send_failed', 'error': str(e)[:200]}


async def send_custom(
    to_email: str,
    subject: str,
    html_body: str,
    context: dict,
    sender_user_id: Optional[str] = None,
    recruiter_id: Optional[str] = None,  # deprecated alias
    log_meta: Optional[dict] = None,
) -> dict:
    """Send a free-form (non-template) email. Subject/body are rendered so that
    `{{candidate_name}}` etc. still work if the recruiter uses variables.
    Returns {sent: bool, reason: str, ...}."""
    if not to_email:
        return {'sent': False, 'reason': 'no_recipient'}
    if not (subject or '').strip():
        return {'sent': False, 'reason': 'no_subject'}
    if not (html_body or '').strip():
        return {'sent': False, 'reason': 'no_body'}

    creds, sender = await _pick_sender_creds(sender_user_id or recruiter_id)
    if not creds:
        return {'sent': False, 'reason': 'no_gmail_connected'}

    rendered_subject = render(subject, context)
    rendered_html = render(html_body, context)
    try:
        result = send_gmail(creds, to_email, rendered_subject, rendered_html)
        await db.email_log.insert_one({
            'id': new_id(),
            'template_key': 'custom',
            'to_email': to_email,
            'subject': rendered_subject,
            'sender_user_id': sender['id'] if sender else None,
            'gmail_message_id': result.get('id'),
            'status': 'sent',
            'created_at': now_iso(),
            **(log_meta or {}),
        })
        return {'sent': True, 'gmail_id': result.get('id'), 'sender': sender['email'] if sender else None}
    except Exception as e:
        await db.email_log.insert_one({
            'id': new_id(),
            'template_key': 'custom',
            'to_email': to_email,
            'subject': rendered_subject,
            'sender_user_id': sender['id'] if sender else None,
            'status': 'failed',
            'error': str(e)[:500],
            'created_at': now_iso(),
            **(log_meta or {}),
        })
        return {'sent': False, 'reason': 'send_failed', 'error': str(e)[:200]}


async def seed_default_templates():
    """Insert any DEFAULT_TEMPLATES not already present in the collection."""
    existing = {t['key'] for t in await db.email_templates.find({}, {'_id': 0, 'key': 1}).to_list(50)}
    to_insert = []
    for key, tpl in DEFAULT_TEMPLATES.items():
        if key not in existing:
            to_insert.append({**tpl, 'created_at': now_iso(), 'updated_at': now_iso()})
    if to_insert:
        await db.email_templates.insert_many(to_insert)
    return len(to_insert)


def build_context_from_candidate(candidate: dict, job: dict, settings: dict) -> dict:
    """Standard variable map used by both auto-sends and preview/test."""
    full = candidate.get('name') or ''
    first = full.split()[0] if full else ''
    return {
        'candidate_name': full,
        'candidate_first_name': first,
        'candidate_email': candidate.get('email') or '',
        'job_title': job.get('title') if job else '',
        'company_name': (settings or {}).get('company_name') or 'our company',
        'stage': candidate.get('stage') or '',
        'primary_color': (settings or {}).get('primary_color') or '#1a5c47',
    }
