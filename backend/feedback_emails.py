"""Interview feedback scorecard emails: sent on completion + reminders at fixed intervals."""
import os

from database import db
from gmail_sender import send_gmail
from google_calendar import get_credentials_for_user

APP_BASE_URL = os.environ['APP_BASE_URL']
# Feedback reminders are sent AT MOST once per interviewer per threshold:
# 12h and 24h after the interview is marked complete. The scheduler will send
# only ONE reminder per interviewer per pass (never spam multiple thresholds
# in the same tick), and it guards each send with an atomic `$addToSet` update
# so a second concurrent pass cannot re-send the same threshold.
REMINDER_INTERVALS_HOURS = [12, 24]


def _email_html(interviewer_name: str, candidate_name: str, job_title: str, interview_id: str, is_reminder: bool) -> str:
    link = f'{APP_BASE_URL}/interviews?scorecard={interview_id}'
    heading = 'Reminder: feedback still needed' if is_reminder else 'Feedback needed'
    role_line = f' for the <strong>{job_title}</strong> role' if job_title else ''
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;padding:24px;">
      <h2 style="color:#1a5c47;margin:0 0 16px;">{heading}</h2>
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

    Idempotency: for the initial (non-reminder) email we look at the
    `scorecard_email_sent_to` array on the interview and skip any interviewer
    already recorded there. This prevents duplicates when
    /interviews/{id}/complete is retried or if the interview transitions back
    to feedback_pending. Reminder emails are deduplicated by the scheduler
    via the `reminders_sent` map — this function does not need to check
    again for reminders.
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
    already_emailed_initial = set(iv.get('scorecard_email_sent_to') or []) if not is_reminder else set()
    sent_any = False
    for iid in iv.get('interviewer_ids', []):
        if iid in submitted:
            continue
        if iid in already_emailed_initial:
            # Initial email was already delivered to this interviewer — the
            # scheduler will handle reminders separately.
            continue
        interviewer = await db.users.find_one({'id': iid}, {'_id': 0})
        if not interviewer or not interviewer.get('email'):
            continue
        cand_name = cand['name'] if cand else 'the candidate'
        html = _email_html(interviewer['name'], cand_name, job['title'] if job else None, iv['id'], is_reminder)
        subject = ('Reminder: ' if is_reminder else '') + f'Feedback needed — interview with {cand_name}'
        try:
            send_gmail(creds, interviewer['email'], subject, html)
            sent_any = True
            if not is_reminder:
                # Record delivery so a retried /complete call won't re-send.
                await db.interviews.update_one(
                    {'id': iv['id']},
                    {'$addToSet': {'scorecard_email_sent_to': iid}},
                )
        except Exception:
            continue
    return sent_any
