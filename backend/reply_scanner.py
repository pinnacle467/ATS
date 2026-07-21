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

# ---------------------------------------------------------------------------
# Shared write-back helper — used by BOTH the background loop below AND the
# on-demand /candidates/{id}/scan-replies endpoint AND the bulk endpoint. Keeping
# a single implementation means provenance metadata (source, confidence, snippet,
# thread link, timestamps) + history rotation stay consistent across all three
# trigger paths.
# ---------------------------------------------------------------------------

MAX_HISTORY_ENTRIES = 3


def _gmail_thread_url(thread_id: str | None) -> str | None:
    """Deep-link a Gmail thread ID to the connected user's web Gmail. Using
    `/mail/u/0/#all/` means the link opens the thread regardless of whether
    it's currently in Inbox / Archive / a label — safer than `#inbox/`."""
    if not thread_id:
        return None
    return f'https://mail.google.com/mail/u/0/#all/{thread_id}'


def _pick_best_extraction(replies: list[dict], parsed_by_reply: dict[str, dict]) -> dict:
    """From a set of (reply, parsed_json) pairs, choose the FINAL / most-recent
    explicit statement of each field. `replies` should already be sorted with
    the most recent first (Gmail's default) — we iterate in that order and take
    the first non-null value we see. Also returns the source reply metadata so
    the caller can persist provenance."""
    best_notice, best_notice_meta = None, None
    best_comp, best_comp_meta = None, None
    for reply in replies:
        rid = reply.get('id')
        parsed = parsed_by_reply.get(rid) or {}
        snippet_bag = parsed.get('source_snippet') or {}
        conf_bag = parsed.get('confidence') or {}
        if best_notice is None and parsed.get('notice_period'):
            best_notice = parsed['notice_period']
            best_notice_meta = {
                'value': best_notice,
                'confidence': bucket_confidence_lazy(conf_bag.get('notice_period')),
                'confidence_raw': _safe_float(conf_bag.get('notice_period')),
                'snippet': snippet_bag.get('notice_period') or None,
                'source_message_id': rid,
                'source_thread_id': reply.get('thread_id'),
                'source_thread_url': _gmail_thread_url(reply.get('thread_id')),
                'source_subject': reply.get('subject') or None,
                'model': 'gpt-5.4-mini',
            }
        if best_comp is None and parsed.get('expected_compensation'):
            best_comp = parsed['expected_compensation']
            best_comp_meta = {
                'value': best_comp,
                'confidence': bucket_confidence_lazy(conf_bag.get('expected_compensation')),
                'confidence_raw': _safe_float(conf_bag.get('expected_compensation')),
                'snippet': snippet_bag.get('expected_compensation') or None,
                'source_message_id': rid,
                'source_thread_id': reply.get('thread_id'),
                'source_thread_url': _gmail_thread_url(reply.get('thread_id')),
                'source_subject': reply.get('subject') or None,
                'model': 'gpt-5.4-mini',
            }
        if best_notice and best_comp:
            break
    return {'notice_period': best_notice_meta, 'expected_compensation': best_comp_meta}


def bucket_confidence_lazy(x):
    """Local re-export so this module doesn't need a hard import of reply_parser
    at module load (they cross-import each other otherwise)."""
    from reply_parser import bucket_confidence
    return bucket_confidence(x)


def _safe_float(x):
    try:
        return round(float(x), 3)
    except (TypeError, ValueError):
        return None


def build_writeback_update(cand: dict, best: dict, overwrite: bool = False) -> dict:
    """Given a candidate document and the winning extraction (`best` from
    `_pick_best_extraction`), compute the Mongo $set payload — respecting the
    "never silently overwrite a manual edit" rule unless `overwrite=True`.

    A field is considered "manually set" when:
      - candidate has a non-empty value for it AND
      - its sidecar {field}_meta.source is 'manual' OR the sidecar is missing
        (legacy pre-provenance record — treat as manual to be safe).
    """
    from utils import now_iso as _now_iso
    updates: dict = {}
    now = _now_iso()

    for field, meta_field, hist_field in [
        ('notice_period', 'notice_period_meta', 'notice_period_history'),
        ('expected_compensation', 'expected_compensation_meta', 'expected_compensation_history'),
    ]:
        winner = best.get(field)
        if not winner or not winner.get('value'):
            continue
        cur_val = cand.get(field)
        cur_meta = cand.get(meta_field) or {}
        cur_source = cur_meta.get('source')  # 'auto' | 'manual' | None
        has_manual = bool(cur_val) and cur_source != 'auto'

        if has_manual and not overwrite:
            # Manual value wins; don't touch the top-level value or the sidecar.
            # But we still append to history so the recruiter can SEE what the
            # extractor found (they just have to click Overwrite to accept it).
            hist = list(cand.get(hist_field) or [])
            hist.insert(0, {**winner, 'source': 'auto', 'extracted_at': now, 'accepted': False})
            updates[hist_field] = hist[:MAX_HISTORY_ENTRIES]
            continue

        # Write it. Populate both the top-level scalar (for backwards compat
        # with everywhere in the app that reads candidate.notice_period) and
        # the sidecar meta for the badge UI.
        updates[field] = winner['value']
        updates[meta_field] = {**winner, 'source': 'auto', 'extracted_at': now, 'accepted': True}
        hist = list(cand.get(hist_field) or [])
        hist.insert(0, {**winner, 'source': 'auto', 'extracted_at': now, 'accepted': True})
        updates[hist_field] = hist[:MAX_HISTORY_ENTRIES]

    if updates:
        updates['last_email_sync_at'] = now
        updates['updated_at'] = now
    else:
        # Even if we didn't write any value, record that we scanned — so the UI
        # can show "Last checked X ago" and know the extractor found nothing.
        updates['last_email_sync_at'] = now

    return updates



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

        # LLM-parse each reply (respecting the seen-set so recurring passes are cheap).
        parsed_by_reply: dict[str, dict] = {}
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
            parsed_by_reply[reply['id']] = parsed

        best = _pick_best_extraction(replies, parsed_by_reply)
        write = build_writeback_update(cand, best, overwrite=False)

        # The build_writeback_update helper always writes last_email_sync_at,
        # even when nothing was extracted — but for the background loop we only
        # want to count as "updated" when a real field changed. Strip the
        # syncmarker-only case here to preserve existing metrics semantics.
        real_change = any(k in write for k in ('notice_period', 'expected_compensation', 'notice_period_history', 'expected_compensation_history'))

        if write:
            await db.candidates.update_one({'id': cand['id']}, {'$set': write})
            if real_change:
                updated += 1
                summary_bits = []
                if write.get('notice_period'):
                    summary_bits.append(f"notice period → {write['notice_period']}")
                if write.get('expected_compensation'):
                    summary_bits.append(f"expected compensation → {write['expected_compensation']}")
                if summary_bits:
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


# ---------------------------------------------------------------------------
# scan_single_candidate — the "worker function" behind both the on-demand
# /candidates/{id}/scan-replies endpoint and the new bulk endpoint. Encapsulates
# the full pipeline: load fresh user creds → check scope → Gmail search →
# LLM parse each reply → pick best → apply writeback with provenance.
# ---------------------------------------------------------------------------

async def scan_single_candidate(user: dict, candidate: dict, overwrite: bool = False,
                                 lookback_days: int = 90, max_replies: int = 5) -> dict:
    """Run the full extract pipeline for ONE candidate against ONE user's Gmail.

    Returns a rich structured result:
        {
          "ok": bool,
          "reason": str,                # e.g. 'no_email_on_candidate', 'no_gmail_connected',
                                        # 'missing_readonly_scope', 'insufficient_scope',
                                        # 'no_replies_found', 'ok'
          "message": str,               # human-readable
          "replies_scanned": int,
          "updated": bool,              # did we write any field on the candidate?
          "extracted": {                # meta the UI badge needs
            "notice_period": {...} | None,
            "expected_compensation": {...} | None,
          },
          "candidate_had": {            # values BEFORE the scan
            "notice_period": str | None,
            "expected_compensation": str | None,
          },
          "overwrite": bool,
        }
    """
    from datetime import datetime, timedelta, timezone as _tz

    from database import db
    from google_calendar import get_credentials_for_user
    from gmail_reader import search_replies_from
    from reply_parser import parse_candidate_reply
    from utils import log_activity, log_audit

    result = {
        'ok': False,
        'reason': '',
        'message': '',
        'replies_scanned': 0,
        'updated': False,
        'extracted': {'notice_period': None, 'expected_compensation': None},
        'candidate_had': {
            'notice_period': candidate.get('notice_period'),
            'expected_compensation': candidate.get('expected_compensation'),
        },
        'overwrite': overwrite,
    }

    if not candidate.get('email'):
        result['reason'] = 'no_email_on_candidate'
        result['message'] = 'Candidate has no email address on file.'
        return result

    fresh_user = await db.users.find_one({'id': user['id']}, {'_id': 0})
    creds = await get_credentials_for_user(fresh_user or {})
    if not creds:
        result['reason'] = 'no_gmail_connected'
        result['message'] = 'You have not connected Gmail to your account.'
        return result

    granted_scopes = ((fresh_user or {}).get('google_tokens', {}).get('scope') or '').split(' ')
    if 'https://www.googleapis.com/auth/gmail.readonly' not in granted_scopes:
        result['reason'] = 'missing_readonly_scope'
        result['message'] = 'Reconnect your Gmail to grant inbox-read permission.'
        return result

    after_iso = (datetime.now(_tz.utc) - timedelta(days=lookback_days)).isoformat()
    replies, gmail_error = await asyncio.to_thread(
        search_replies_from, creds, candidate['email'], after_iso, max_replies,
    )
    if gmail_error:
        result['reason'] = gmail_error
        result['message'] = (
            'Reconnect your Gmail to grant inbox-read permission.'
            if gmail_error in ('insufficient_scope', 'invalid_token')
            else f'Gmail API error: {gmail_error}'
        )
        return result

    result['replies_scanned'] = len(replies)

    if not replies:
        # No candidate replies in the window — still update last_email_sync_at so
        # the UI can show "checked N minutes ago, no reply found yet".
        from utils import now_iso as _now
        await db.candidates.update_one({'id': candidate['id']}, {'$set': {'last_email_sync_at': _now()}})
        result['ok'] = True
        result['reason'] = 'no_replies_found'
        result['message'] = f'Searched {lookback_days} days of your Gmail; no replies from {candidate["email"]} found.'
        return result

    parsed_by_reply: dict[str, dict] = {}
    for reply in replies:
        body = reply.get('body_text') or reply.get('snippet') or ''
        if not body.strip():
            continue
        try:
            parsed = await parse_candidate_reply(body, session_label=f'candid-{candidate["id"]}-{reply["id"]}')
        except Exception:
            logger.exception('reply parse failed for candidate=%s reply=%s', candidate['id'], reply.get('id'))
            continue
        parsed_by_reply[reply['id']] = parsed

    best = _pick_best_extraction(replies, parsed_by_reply)
    write = build_writeback_update(candidate, best, overwrite=overwrite)

    if write:
        await db.candidates.update_one({'id': candidate['id']}, {'$set': write})
        real_change = any(k in write for k in ('notice_period', 'expected_compensation', 'notice_period_history', 'expected_compensation_history'))
        if real_change:
            result['updated'] = 'notice_period' in write or 'expected_compensation' in write
            summary_bits = []
            if write.get('notice_period'):
                summary_bits.append(f"notice period → {write['notice_period']}")
            if write.get('expected_compensation'):
                summary_bits.append(f"expected compensation → {write['expected_compensation']}")
            if summary_bits:
                summary = ('Overwrite-extracted' if overwrite else 'Auto-extracted') + \
                          ' from candidate reply: ' + '; '.join(summary_bits)
                try:
                    await log_activity(user, 'reply_extracted', summary, candidate_id=candidate['id'])
                    await log_audit(user, 'reply_extracted', 'candidate', candidate['id'], summary)
                except Exception:
                    pass

    # Return the meta blobs (with snippet, thread link etc) so the UI badge
    # can render right away without a follow-up GET.
    result['ok'] = True
    result['reason'] = 'ok'
    result['message'] = 'Scan complete.'
    result['extracted'] = {
        'notice_period': best.get('notice_period'),
        'expected_compensation': best.get('expected_compensation'),
    }
    return result
