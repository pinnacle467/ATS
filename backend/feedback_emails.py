"""Interview feedback scorecard emails: sent ONCE, 12 hours after the interview is marked complete."""
import os

from database import db
from gmail_sender import send_gmail
from google_calendar import get_credentials_for_user

APP_BASE_URL = os.environ['APP_BASE_URL']
# ONE feedback request email per interviewer per interview, sent 12h after
# `/complete`. The scheduler treats each threshold in this list as a claim-once
# opportunity via an atomic `$addToSet` on `reminders_sent`, so even if the
# scheduler restarts / doubles up it can never send twice for the same threshold.
REMINDER_INTERVALS_HOURS = [12]


def _email_html(interviewer_name: str, candidate_name: str, job_title: str, interview_id: str, is_reminder: bool) -> str:
    link = f'{APP_BASE_URL}/interviews?scorecard={interview_id}'
    role_line = f' for the <strong>{job_title}</strong> role' if job_title else ''
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;padding:24px;">
      <h2 style="color:#1a5c47;margin:0 0 16px;">Feedback needed</h2>
      <p>Hi {interviewer_name},</p>
      <p>Please submit your feedback scorecard for the interview with <strong>{candidate_name}</strong>{role_line}.</p>
      <p style="margin:24px 0;">
        <a href="{link}" style="background:#1a5c47;color:#ffffff;padding:12px 22px;border-radius:8px;text-decoration:none;display:inline-block;">Fill Scorecard</a>
      </p>
      <p style="color:#94a3b8;font-size:12px;margin-top:32px;">Pinnacle ATS</p>
    </div>
    """


async def send_scorecard_request(iv: dict, is_reminder: bool = False) -> bool:
    """Best-effort: emails every interviewer on `iv` who hasn't submitted a
    scorecard yet.

    Only ONE email per (interview × interviewer) is ever sent — the scheduler
    claims each interviewer atomically via `reminders_sent` before calling
    this function, and we also record deliveries in `scorecard_email_sent_to`
    as a second guardrail.
    """
    creator = await db.users.find_one({'id': iv.get('created_by')})
    if not creator:
        return False
    creds = await get_credentials_for_user(creator)
    if not creds:
        return False
    cand = await db.candidates.find_one({'id': iv['candidate_id']}, {'_id': 0})
    job = await db.jobs.find_one({'id': iv['job_id']}, {'_id': 0}) if iv.get('job_id') else None
    submitted = set(await db.scorecards.distinct('interviewer_id', {'interview_id': iv['id']}))
    already_emailed = set(iv.get('scorecard_email_sent_to') or [])
    sent_any = False
    for iid in iv.get('interviewer_ids', []):
        if iid in submitted:
            continue
        if iid in already_emailed:
            # This interviewer already got the one-and-only email — never send again
            continue
        interviewer = await db.users.find_one({'id': iid}, {'_id': 0})
        if not interviewer or not interviewer.get('email'):
            continue
        cand_name = cand['name'] if cand else 'the candidate'
        html = _email_html(interviewer['name'], cand_name, job['title'] if job else None, iv['id'], is_reminder)
        subject = f'Feedback needed — interview with {cand_name}'
        try:
            send_gmail(creds, interviewer['email'], subject, html)
            sent_any = True
            # Record delivery so nothing can re-send later — belt AND suspenders
            await db.interviews.update_one(
                {'id': iv['id']},
                {'$addToSet': {'scorecard_email_sent_to': iid}},
            )
        except Exception:
            continue
    return sent_any
