"""Candidate-scheduling emails.

Per the current project decision these are QUEUED/LOGGED only (no live delivery)
until an email channel key is provided. Everything is rendered and written to
`db.email_log` with status='queued' so the recruiter dashboard + audit trail
show exactly what would be sent, and flipping to real delivery later is a
one-line change (call email_templates.send_custom instead of _queue).

Company name / branding come from career_settings (never hardcoded).
Timestamps stored UTC; human strings are rendered in the recipient timezone.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from database import db
from email_templates import render
from utils import new_id, now_iso


async def _company_name() -> str:
    s = await db.career_settings.find_one({'key': 'singleton'}, {'_id': 0, 'company_name': 1})
    return (s or {}).get('company_name') or 'Our Company'


def human_time(start_iso: str | None, duration_min: int, tz: str) -> str:
    if not start_iso:
        return 'TBD'
    try:
        s = datetime.fromisoformat(start_iso.replace('Z', '+00:00')).astimezone(ZoneInfo(tz or 'UTC'))
    except Exception:  # noqa: BLE001
        return start_iso
    return s.strftime('%A, %B %d, %Y · %I:%M %p ') + tz


TEMPLATES = {
    'scheduling_invite': {
        'subject': 'Please schedule your interview – {{company_name}}',
        'html_body': (
            '<p>Hi {{candidate_name}},</p>'
            '<p>You\'re invited to schedule your <strong>{{interview_stage}}</strong> interview for the '
            '<strong>{{job_title}}</strong> role at {{company_name}}.</p>'
            '<p>Duration: {{duration}} minutes.</p>'
            '<p>{{instructions}}</p>'
            '<p><a href="{{scheduling_link}}">Pick a time that works for you →</a></p>'
            '<p>Thanks,<br/>{{company_name}} Talent Team</p>'
        ),
    },
    'interview_confirmation_candidate': {
        'subject': 'Interview confirmed – {{job_title}} at {{company_name}}',
        'html_body': (
            '<p>Hi {{candidate_name}},</p>'
            '<p>Your interview is confirmed.</p>'
            '<ul>'
            '<li><strong>Role:</strong> {{job_title}}</li>'
            '<li><strong>Stage:</strong> {{interview_stage}}</li>'
            '<li><strong>When:</strong> {{when}}</li>'
            '<li><strong>Google Meet:</strong> <a href="{{meet_link}}">{{meet_link}}</a></li>'
            '</ul>'
            '<p>Need to change it? <a href="{{scheduling_link}}">Reschedule or cancel here</a>.</p>'
            '<p>See you then,<br/>{{company_name}} Talent Team</p>'
        ),
    },
    'interview_confirmation_interviewer': {
        'subject': 'Interview booked: {{candidate_name}} – {{job_title}}',
        'html_body': (
            '<p>Hi {{interviewer_name}},</p>'
            '<p>{{candidate_name}} booked a <strong>{{interview_stage}}</strong> interview for {{job_title}}.</p>'
            '<ul>'
            '<li><strong>When:</strong> {{when}}</li>'
            '<li><strong>Google Meet:</strong> <a href="{{meet_link}}">{{meet_link}}</a></li>'
            '<li><strong>Candidate profile:</strong> <a href="{{candidate_link}}">{{candidate_link}}</a></li>'
            '<li><strong>Scorecard:</strong> <a href="{{scorecard_link}}">{{scorecard_link}}</a></li>'
            '</ul>'
        ),
    },
    'interview_reschedule': {
        'subject': 'Interview rescheduled – {{job_title}}',
        'html_body': (
            '<p>Hi {{recipient_name}},</p>'
            '<p>The {{interview_stage}} interview for {{job_title}} has been moved.</p>'
            '<p><strong>New time:</strong> {{when}}</p>'
            '<p><strong>Google Meet:</strong> <a href="{{meet_link}}">{{meet_link}}</a></p>'
        ),
    },
    'interview_cancel': {
        'subject': 'Interview cancelled – {{job_title}}',
        'html_body': (
            '<p>Hi {{recipient_name}},</p>'
            '<p>The {{interview_stage}} interview for {{job_title}} scheduled for {{when}} has been cancelled.</p>'
            '<p>{{cancel_reason}}</p>'
        ),
    },
    'interview_reminder': {
        'subject': 'Reminder: {{interview_stage}} interview – {{job_title}}',
        'html_body': (
            '<p>Hi {{recipient_name}},</p>'
            '<p>This is a reminder for your {{interview_stage}} interview for {{job_title}}.</p>'
            '<p><strong>When:</strong> {{when}}</p>'
            '<p><strong>Google Meet:</strong> <a href="{{meet_link}}">{{meet_link}}</a></p>'
        ),
    },
}


async def queue_scheduling_email(kind: str, to_email: str, context: dict, meta: dict | None = None) -> dict:
    """Render a scheduling template and record it as a QUEUED email in
    email_log (no live send yet)."""
    tpl = TEMPLATES.get(kind)
    if not tpl or not to_email:
        return {'queued': False, 'reason': 'no_template_or_recipient'}
    ctx = {'company_name': await _company_name(), **context}
    subject = render(tpl['subject'], ctx)
    html = render(tpl['html_body'], ctx)
    doc = {
        'id': new_id(),
        'template_key': kind,
        'to_email': to_email,
        'subject': subject,
        'html_body': html,
        'status': 'queued',  # flip to 'sent' once a live channel is wired
        'channel': 'queued_no_channel',
        'created_at': now_iso(),
        **(meta or {}),
    }
    await db.email_log.insert_one(doc)
    return {'queued': True, 'email_log_id': doc['id'], 'subject': subject}
