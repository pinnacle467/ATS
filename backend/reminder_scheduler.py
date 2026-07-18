"""Background loop: sends feedback reminder emails at fixed hour intervals after an interview completes."""
import asyncio
import logging
from datetime import datetime, timezone

from database import db
from feedback_emails import REMINDER_INTERVALS_HOURS, send_scorecard_request

logger = logging.getLogger(__name__)


async def _check_once():
    ivs = await db.interviews.find({'status': 'feedback_pending', 'completed_at': {'$ne': None}}).to_list(500)
    now = datetime.now(timezone.utc)
    for iv in ivs:
        try:
            completed_at = datetime.fromisoformat(iv['completed_at'].replace('Z', '+00:00'))
        except (ValueError, TypeError, KeyError):
            continue
        elapsed_hours = (now - completed_at).total_seconds() / 3600
        submitted = set(await db.scorecards.distinct('interviewer_id', {'interview_id': iv['id']}))
        pending = [i for i in iv.get('interviewer_ids', []) if i not in submitted]
        if not pending:
            continue
        reminders_sent = iv.get('reminders_sent') or {}
        for threshold in REMINDER_INTERVALS_HOURS:
            if elapsed_hours < threshold:
                continue
            due = [i for i in pending if threshold not in (reminders_sent.get(i) or [])]
            if not due:
                continue
            try:
                await send_scorecard_request({**iv, 'interviewer_ids': due}, is_reminder=True)
            except Exception:
                logger.exception('Failed sending feedback reminder for interview %s', iv['id'])
                continue
            for i in due:
                reminders_sent.setdefault(i, []).append(threshold)
        if reminders_sent != (iv.get('reminders_sent') or {}):
            await db.interviews.update_one({'id': iv['id']}, {'$set': {'reminders_sent': reminders_sent}})


async def reminder_loop():
    while True:
        try:
            await _check_once()
        except Exception:
            logger.exception('Feedback reminder loop error')
        await asyncio.sleep(600)
