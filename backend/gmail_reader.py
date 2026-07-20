"""Gmail inbox reader — fetch replies from candidates to messages sent by a user.

Uses the same OAuth credentials as `gmail_sender.send_gmail` (scope
`gmail.readonly` was added to google_calendar.SCOPES). Non-blocking wrappers are
async but the underlying googleapiclient calls are sync and CPU-light so we call
them via `asyncio.to_thread` from the reply_scanner background loop."""
from __future__ import annotations

import base64
import email
from email import policy
from typing import Optional

from googleapiclient.discovery import build


def _service(creds):
    return build('gmail', 'v1', credentials=creds, cache_discovery=False)


def _rfc3339_to_epoch(iso: str) -> int:
    """Gmail 'after:' query expects seconds since epoch."""
    from datetime import datetime
    # Accept 'YYYY-MM-DDTHH:MM:SS[.ffffff][+00:00]' or 'YYYY-MM-DDTHH:MM:SSZ'
    s = (iso or '').replace('Z', '+00:00')
    try:
        return int(datetime.fromisoformat(s).timestamp())
    except Exception:
        return 0


def search_replies_from(creds, from_email: str, after_iso: Optional[str] = None,
                        max_results: int = 20) -> tuple[list[dict], Optional[str]]:
    """Search the connected user's mailbox for messages sent from `from_email`
    (optionally after a given timestamp).

    Returns `(messages, error)` — `messages` is a list of dicts with keys
    `id, thread_id, snippet, internal_date, subject, body_text`. `error` is
    `None` on success, or a short human-readable error string (e.g.
    'insufficient_scope', 'invalid_token', 'network_error') on failure so the
    caller can surface a helpful message instead of "no replies found".

    Search behavior:
      - Uses `q="from:{email} after:{epoch}"`; also adds `in:anywhere` so
        Gmail includes Spam / Trash in the scan (candidate replies sometimes
        get misfiled).
      - `max_results` messages are fetched at most; each body is decoded to
        plain text (or naive HTML->text) and truncated to 20 000 chars.
    """
    if not from_email:
        return [], 'no_from_email'
    q_parts = [f'from:{from_email}', 'in:anywhere']
    if after_iso:
        epoch = _rfc3339_to_epoch(after_iso)
        if epoch > 0:
            q_parts.append(f'after:{epoch}')
    query = ' '.join(q_parts)
    try:
        svc = _service(creds)
        resp = svc.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
    except Exception as e:
        err = _classify_gmail_error(e)
        return [], err
    msgs = resp.get('messages', []) or []
    out: list[dict] = []
    for m in msgs:
        try:
            full = svc.users().messages().get(userId='me', id=m['id'], format='raw').execute()
        except Exception:
            continue
        raw = full.get('raw')
        if not raw:
            continue
        try:
            mime_bytes = base64.urlsafe_b64decode(raw.encode('utf-8'))
            parsed = email.message_from_bytes(mime_bytes, policy=policy.default)
            body_text = _extract_text(parsed)[:20000]
            subject = parsed.get('Subject', '') or ''
        except Exception:
            body_text = ''
            subject = ''
        out.append({
            'id': m['id'],
            'thread_id': full.get('threadId'),
            'snippet': full.get('snippet') or '',
            'internal_date': full.get('internalDate'),
            'subject': subject,
            'body_text': body_text,
        })
    return out, None


def _classify_gmail_error(e: Exception) -> str:
    """Turn a googleapiclient exception into a short reason string."""
    msg = str(e).lower()
    if 'insufficient' in msg or 'scope' in msg or '403' in msg or 'permission' in msg:
        return 'insufficient_scope'
    if 'invalid_grant' in msg or 'invalid_token' in msg or '401' in msg or 'unauthorized' in msg:
        return 'invalid_token'
    if 'quota' in msg or 'rate' in msg:
        return 'rate_limited'
    if 'network' in msg or 'timeout' in msg or 'connection' in msg:
        return 'network_error'
    return 'gmail_api_error'


def _extract_text(msg) -> str:
    """Prefer text/plain part; fall back to a naive HTML strip on text/html."""
    if msg.is_multipart():
        # Try text/plain first
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == 'text/plain':
                try:
                    return part.get_content()
                except Exception:
                    continue
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                try:
                    return _strip_html(part.get_content())
                except Exception:
                    continue
        return ''
    ctype = msg.get_content_type()
    try:
        content = msg.get_content()
    except Exception:
        return ''
    if ctype == 'text/html':
        return _strip_html(content)
    return content or ''


def _strip_html(html: str) -> str:
    """Minimal HTML->text (avoids adding a beautifulsoup dep just for scanning)."""
    import re
    if not html:
        return ''
    # Drop scripts / styles / quoted-reply blocks entirely
    html = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    # Convert <br> and </p> to newlines
    html = re.sub(r'<\s*br\s*/?>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</\s*p\s*>', '\n', html, flags=re.IGNORECASE)
    # Strip remaining tags
    html = re.sub(r'<[^>]+>', ' ', html)
    # Decode common entities
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
    # Collapse whitespace
    html = re.sub(r'[ \t]+', ' ', html)
    html = re.sub(r'\n\s*\n+', '\n\n', html)
    return html.strip()
