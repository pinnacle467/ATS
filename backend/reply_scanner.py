"""Background loop that scans connected users' Gmail inboxes for candidate
replies to previously sent ATS emails and auto-updates notice_period +
expected_compensation on the matching candidate via an LLM extractor.

Runs every REPLY_SCAN_INTERVAL_SEC. Fire-and-forget task launched from
server.py's startup handler.

Design:
- Enumerate all `email_log` rows with status='sent' from the last 30 days that
  have a linked candidate email and a valid `sender_user_id`.
- Skip rows where the candidate already has BOTH notice_period AND
  expected_compensation populated (nothing to fill).
- For each unique (sender_user_id, candidate.email) pair, load the user's
  Gmail credentials and search their inbox for messages `from:{candidate_email}`
  received after the email_log's `created_at` (and after any previous
  `last_reply_scanned_at` if we've scanned this row before).
- For each new reply, LLM-parse the body and, if the extractor returned any
  non-null value AND the candidate's corresponding DB field is still null,
  update it + log an `activity` + `audit_log` entry (actor is the sender user).
- Mark the email_log row with `last_reply_scanned_at` and the count of replies
  processed so we don't reparse them.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

REPLY_SCAN_INTERVAL_SEC = int(os.environ.get('REPLY_SCAN_INTERVAL_SEC', '300'))  # 5 min
REPLY_LOOKBACK_DAYS = int(os.environ.get('REPLY_LOOKBACK_DAYS', '30'))


async def _scan_once():
    """One pass over recent email_log rows. Kept lazy so a boot-time import
    error in gmail_reader/reply_parser doesn't crash the whole server."""
    from database import db
    from google_calendar import get_credentials_for_user
    from gmail_reader import search_replies_from
    from reply_parser import parse_candidate_reply
    from utils import log_activity, log_audit, now_iso

    cutoff = (datetime.now(timezone.utc) - timedelta(days=REPLY_LOOKBACK_DAYS)).isoformat()

    rows = await db.email_log.find({
        'status': 'sent',
        'sender_user_id': {'$ne': None, '$exists': True},
        'to_email': {'$ne': None, '$exists': True},
        'created_at': {'$gte': cutoff},
    }, {'_id': 0}).sort('created_at', -1).to_list(500)

    if not rows:
        return {'checked': 0, 'updated': 0}

    # Cache creds per user_id per pass so we don't refresh tokens on every row
    creds_cache: dict[str, object] = {}
    user_cache: dict[str, dict] = {}

    checked, updated = 0, 0
    processed_reply_ids: set[str] = set()

    for row in rows:
        sender_id = row.get('sender_user_id')
        to_email = (row.get('to_email') or '').strip().lower()
        if not sender_id or not to_email:
            continue

        # Look up the candidate by email (case-insensitive) — a log row may
        # not carry candidate_id (older sends), so match on email.
        cand_query: dict = {'email': {'$regex': f'^{__escape_regex(to_email)}$', '$options': 'i'}}
        cand = await db.candidates.find_one(cand_query, {'_id': 0})
        if not cand:
            # If the log_meta included candidate_id, try that as fallback
            if row.get('candidate_id'):
                cand = await db.candidates.find_one({'id': row['candidate_id']}, {'_id': 0})
            if not cand:
                continue

        has_notice = bool((cand.get('notice_period') or '').strip()) if isinstance(cand.get('notice_period'), str) else bool(cand.get('notice_period'))
        has_comp = bool((cand.get('expected_compensation') or '').strip()) if isinstance(cand.get('expected_compensation'), str) else bool(cand.get('expected_compensation'))
        if has_notice and has_comp:
            continue

        # Only scan replies received after the LATER of (email sent time,
        # last time we scanned this row).
        after_iso = row.get('last_reply_scanned_at') or row.get('created_at')

        # Load creds for this sender_user_id (cache within this pass)
        if sender_id not in creds_cache:
            u = await db.users.find_one({'id': sender_id}, {'_id': 0})
            user_cache[sender_id] = u or {}
            creds_cache[sender_id] = await get_credentials_for_user(u) if u else None
        creds = creds_cache.get(sender_id)
        actor = user_cache.get(sender_id) or {'id': sender_id, 'name': 'System', 'role': 'admin'}
        if not creds:
            continue

        try:
            replies, gmail_error = await asyncio.to_thread(search_replies_from, creds, to_email, after_iso, 10)
        except Exception:
            logger.exception('gmail search failed for sender=%s to=%s', sender_id, to_email)
            continue
        if gmail_error:
            # Common: user has old tokens without gmail.readonly; log once and skip.
            logger.info('reply_scan gmail error for sender=%s to=%s: %s', sender_id, to_email, gmail_error)
            continue
        checked += 1
        if not replies:
            await db.email_log.update_one({'id': row['id']}, {'$set': {'last_reply_scanned_at': now_iso()}})
            continue

        best_notice = None
        best_comp = None
        for reply in replies:
            if reply['id'] in processed_reply_ids:
                continue
            processed_reply_ids.add(reply['id'])
            body = reply.get('body_text') or reply.get('snippet') or ''
            if not body.strip():
                continue
            try:
                parsed = await parse_candidate_reply(body, session_label=f'{sender_id}-{reply["id"]}')
            except Exception:
                logger.exception('reply parse failed for reply=%s', reply['id'])
                continue
            if parsed.get('notice_period') and not best_notice:
                best_notice = parsed['notice_period']
            if parsed.get('expected_compensation') and not best_comp:
                best_comp = parsed['expected_compensation']
            if best_notice and best_comp:
                break

        # Only write fields the candidate currently lacks
        write: dict = {}
        if best_notice and not has_notice:
            write['notice_period'] = best_notice
        if best_comp and not has_comp:
            write['expected_compensation'] = best_comp

        if write:
            write['updated_at'] = now_iso()
            await db.candidates.update_one({'id': cand['id']}, {'$set': write})
            updated += 1
            summary_bits = []
            if 'notice_period' in write:
                summary_bits.append(f"notice period → {write['notice_period']}")
            if 'expected_compensation' in write:
                summary_bits.append(f"expected compensation → {write['expected_compensation']}")
            summary = 'Auto-extracted from candidate reply: ' + '; '.join(summary_bits)
            try:
                await log_activity(actor, 'reply_extracted', summary, candidate_id=cand['id'])
                await log_audit(actor, 'reply_extracted', 'candidate', cand['id'], summary)
            except Exception:
                pass

        await db.email_log.update_one({'id': row['id']}, {'$set': {
            'last_reply_scanned_at': now_iso(),
            'last_replies_seen': len(replies),
        }})

    return {'checked': checked, 'updated': updated}


def __escape_regex(s: str) -> str:
    import re
    return re.escape(s)


async def reply_scan_loop():
    # Delay start a bit so seed / other startup tasks settle
    await asyncio.sleep(45)
    while True:
        try:
            result = await _scan_once()
            if result and (result.get('checked') or result.get('updated')):
                logger.info('reply_scan pass done: %s', result)
        except Exception:
            logger.exception('reply_scan loop iteration failed')
        await asyncio.sleep(REPLY_SCAN_INTERVAL_SEC)
