"""Background loop: sends 24h/1h interview reminders to the candidate and
interviewers for BOOKED self-scheduled interviews.

Reminders are queued the same way as every other scheduling email
(scheduling_emails.queue_scheduling_email) — no live delivery until an email
channel key is provided. Flipping to real delivery later is a one-line change
inside that helper.

Duplicate-send guarantees mirror reminder_scheduler.py's feedback loop:
  1. `scheduling_reminders_sent` (a plain list of ints, distinct from the
     feedback loop's per-interviewer `reminders_sent` dict) records which
     hour-thresholds have already fired for this interview.
  2. Only the single most-urgent (smallest) unsent threshold is claimed per
     pass, so a scheduler outage spanning both the 24h and 1h windows never
     fires two reminders back-to-back in the same tick. Once a smaller
     threshold has been sent, any larger (now-stale) threshold is permanently
     skipped — we never follow a "1h" reminder with a late "24h" one.
  3. The claim is an atomic `$addToSet`; a failed send rolls the claim back
     with `$pull` so the next pass retries it.
"""
import asyncio
import logging
from datetime import datetime, timezone

from database import db
from scheduling_emails import human_time, queue_scheduling_email
from scheduling_engine import get_scheduling_settings
from tenant_context import set_tenant_id
from utils import log_activity, log_audit, notify

logger = logging.getLogger(__name__)


async def _send_reminder(iv: dict, threshold_hours: int):
    cand = await db.candidates.find_one({'id': iv['candidate_id']}, {'_id': 0}) or {}
    job = await db.jobs.find_one({'id': iv.get('job_id')}, {'_id': 0, 'title': 1}) or {}
    interviewers = await db.users.find({'id': {'$in': iv.get('interviewer_ids', [])}}, {'_id': 0, 'id': 1, 'name': 1, 'email': 1}).to_list(50)
    tz = iv.get('candidate_timezone') or iv.get('timezone') or 'UTC'
    when = human_time(iv.get('scheduled_at'), iv.get('duration_min', 60), tz)
    meet = iv.get('video_link') or 'To be shared'
    label = f"{threshold_hours}h" if threshold_hours != 1 else '1 hour'

    await queue_scheduling_email('interview_reminder', cand.get('email'), {
        'recipient_name': cand.get('name', 'there'),
        'job_title': job.get('title', 'the role'),
        'interview_stage': iv.get('stage') or 'interview',
        'when': when, 'meet_link': meet,
    }, meta={'interview_id': iv['id'], 'candidate_id': iv['candidate_id'], 'reminder_offset_hours': threshold_hours})

    for it in interviewers:
        await queue_scheduling_email('interview_reminder', it.get('email'), {
            'recipient_name': it.get('name', 'there'),
            'job_title': job.get('title', ''),
            'interview_stage': iv.get('stage') or 'interview',
            'when': when, 'meet_link': meet,
        }, meta={'interview_id': iv['id'], 'reminder_offset_hours': threshold_hours})
        await notify(it['id'], 'interview', f"Reminder: {cand.get('name', 'candidate')} interview in {label}", '/interviews')

    actor = await db.users.find_one({'id': iv.get('created_by')}, {'_id': 0}) or {}
    await log_audit(actor, 'scheduling.reminder_sent', 'interview', iv['id'], f"{label} reminder — {when}")
    await log_activity(
        actor, 'interview_reminder_sent',
        f"{label} reminder sent for {cand.get('name', 'candidate')}'s interview",
        candidate_id=iv['candidate_id'], job_id=iv.get('job_id'),
    )


async def _check_once():
    settings = await get_scheduling_settings()
    offsets = sorted({int(o) for o in (settings.get('reminder_offsets_hours') or [24, 1]) if o})
    if not offsets:
        return
    now = datetime.now(timezone.utc)
    ivs = await db.interviews.find({
        'self_scheduled': True,
        'scheduling_status': 'scheduled',
        'scheduled_at': {'$ne': None},
    }, {'_id': 0}).to_list(1000)

    for iv in ivs:
        set_tenant_id(iv.get('tenant_id'))
        try:
            start = datetime.fromisoformat(iv['scheduled_at'].replace('Z', '+00:00'))
        except (ValueError, TypeError, KeyError):
            continue
        hours_until = (start - now).total_seconds() / 3600
        if hours_until <= 0:
            continue  # already started/passed — nothing to remind about

        already = set(iv.get('scheduling_reminders_sent') or [])
        # A threshold is due if it's been crossed, hasn't been sent yet, AND no
        # smaller/more-urgent threshold has already been sent (once the 1h
        # reminder went out, a stale "24h" reminder must never follow it).
        due = [
            o for o in offsets
            if hours_until <= o and o not in already and not any(sent < o for sent in already)
        ]
        if not due:
            continue
        threshold = min(due)  # most urgent unsent reminder — never send more than one per pass

        claim = await db.interviews.update_one(
            {'id': iv['id'], 'scheduling_reminders_sent': {'$ne': threshold}},
            {'$addToSet': {'scheduling_reminders_sent': threshold}},
        )
        if claim.modified_count != 1:
            continue  # concurrent pass already claimed it

        try:
            await _send_reminder(iv, threshold)
            logger.info('scheduling reminder sent for interview=%s threshold=%sh', iv['id'], threshold)
        except Exception:
            logger.exception('Failed sending scheduling reminder for interview %s threshold %sh', iv['id'], threshold)
            await db.interviews.update_one({'id': iv['id']}, {'$pull': {'scheduling_reminders_sent': threshold}})


async def scheduling_reminder_loop():
    while True:
        try:
            await _check_once()
        except Exception:
            logger.exception('Scheduling reminder loop error')
        await asyncio.sleep(300)
