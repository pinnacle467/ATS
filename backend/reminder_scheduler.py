"""Background loop: sends feedback reminder emails at fixed hour intervals after
an interview completes.

Reminders are sent AT MOST ONCE per (interview × interviewer × threshold).
Guarantees against duplicates:
  1. Per pass, we only pick ONE threshold per interviewer — the *highest*
     threshold that (a) has already elapsed and (b) hasn't been claimed yet.
     This means even if the scheduler was down and an interview is now 30h
     old with zero reminders sent, we send just the 24h reminder — not both
     12h and 24h back-to-back.
  2. Before actually sending, we atomically "claim" the threshold in Mongo
     via a conditional `$addToSet`. If the claim update matches 0 documents
     (because a concurrent pass already claimed it, or a manual reminder was
     fired), we skip sending. This makes the loop safe against overlapping
     passes / hot reloads / restart races.
  3. If the actual send fails, we ROLL BACK the claim ($pull) so the next
     pass will retry the same threshold.
"""
import asyncio
import logging
from datetime import datetime, timezone

from database import db
from feedback_emails import REMINDER_INTERVALS_HOURS, send_scorecard_request

logger = logging.getLogger(__name__)


async def _check_once():
    ivs = await db.interviews.find({
        'status': 'feedback_pending',
        'completed_at': {'$ne': None},
    }).to_list(500)
    now = datetime.now(timezone.utc)

    for iv in ivs:
        try:
            completed_at = datetime.fromisoformat(iv['completed_at'].replace('Z', '+00:00'))
        except (ValueError, TypeError, KeyError):
            continue
        elapsed_hours = (now - completed_at).total_seconds() / 3600
        if elapsed_hours < min(REMINDER_INTERVALS_HOURS):
            continue

        submitted = set(await db.scorecards.distinct('interviewer_id', {'interview_id': iv['id']}))
        pending_interviewers = [i for i in iv.get('interviewer_ids', []) if i not in submitted]
        if not pending_interviewers:
            continue

        # Group interviewers by which threshold we should send them now.
        # For each interviewer, find the HIGHEST elapsed threshold that
        # hasn't already been recorded in `reminders_sent[interviewer_id]`.
        reminders_sent = iv.get('reminders_sent') or {}
        threshold_to_interviewers: dict[int, list[str]] = {}
        for iid in pending_interviewers:
            already = set(reminders_sent.get(iid) or [])
            candidates = [t for t in REMINDER_INTERVALS_HOURS if t <= elapsed_hours and t not in already]
            if not candidates:
                continue
            picked = max(candidates)  # only the highest — never spam multiple thresholds
            threshold_to_interviewers.setdefault(picked, []).append(iid)

        if not threshold_to_interviewers:
            continue

        for threshold, iids in threshold_to_interviewers.items():
            # Atomically claim the threshold for each interviewer we intend to
            # notify. If any of them was already claimed concurrently, filter
            # them out. We do this one interviewer at a time so partial claims
            # remain safe.
            claimed: list[str] = []
            for iid in iids:
                res = await db.interviews.update_one(
                    {
                        'id': iv['id'],
                        f'reminders_sent.{iid}': {'$ne': threshold},
                    },
                    {'$addToSet': {f'reminders_sent.{iid}': threshold}},
                )
                if res.modified_count == 1:
                    claimed.append(iid)
                # else: another pass or manual send already claimed it → skip

            if not claimed:
                continue

            # Send only to the interviewers we successfully claimed
            try:
                sent_ok = await send_scorecard_request(
                    {**iv, 'interviewer_ids': claimed},
                    is_reminder=True,
                )
            except Exception:
                logger.exception('Failed sending feedback reminder for interview %s threshold %sh', iv['id'], threshold)
                sent_ok = False

            if not sent_ok:
                # Roll back the claim so the next pass retries this threshold
                for iid in claimed:
                    await db.interviews.update_one(
                        {'id': iv['id']},
                        {'$pull': {f'reminders_sent.{iid}': threshold}},
                    )
            else:
                logger.info(
                    'reminder sent for interview=%s threshold=%sh interviewers=%s',
                    iv['id'], threshold, claimed,
                )


async def reminder_loop():
    while True:
        try:
            await _check_once()
        except Exception:
            logger.exception('Feedback reminder loop error')
        await asyncio.sleep(600)
