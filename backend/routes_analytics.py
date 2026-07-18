"""Career Portal — Phase 3 analytics.

Public visitors POST events to /api/career/public/track (no auth). Admin/recruiter
UIs read aggregated stats from /api/career/analytics/*.

Design notes:
- Events stored in `analytics_events` collection with a UUID `id`.
- No PII is captured on the public track call. `ip_hash` is a 16-char SHA-256
  fingerprint used only for unique-visitor counting; the raw IP is never stored.
- `session_id` comes from the client (localStorage-persisted UUID) so we can
  compute conversion (a session that viewed a job AND submitted an application).
- Aggregation uses simple MongoDB aggregation pipelines. For an MVP dataset of
  <100k events this is comfortable; if the collection grows we'd move to a
  daily rollup collection.
"""
import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import require_roles
from database import db
from utils import new_id, now_iso

router = APIRouter(prefix='/career', tags=['career-analytics'])

APP_BASE_URL = os.environ.get('APP_BASE_URL', '')

VALID_EVENT_TYPES = {'page_view', 'job_view', 'apply_start', 'apply_submit'}
# Simple heuristic to classify a referrer host into a friendly source label
# used by the "Traffic Sources" chart. Extend as we learn about incoming traffic.
SOURCE_PATTERNS = [
    (re.compile(r'google\.'), 'Google'),
    (re.compile(r'linkedin\.'), 'LinkedIn'),
    (re.compile(r'indeed\.'), 'Indeed'),
    (re.compile(r'facebook\.'), 'Facebook'),
    (re.compile(r'twitter\.|t\.co|x\.com'), 'Twitter / X'),
    (re.compile(r'bing\.'), 'Bing'),
    (re.compile(r'duckduckgo\.'), 'DuckDuckGo'),
    (re.compile(r'reddit\.'), 'Reddit'),
    (re.compile(r'ycombinator\.|hackernews'), 'Hacker News'),
]


def _classify_referrer(referrer: Optional[str], utm_source: Optional[str]) -> str:
    """Return a friendly traffic source label for a raw referrer + utm_source."""
    if utm_source:
        return utm_source.strip()[:40].title()
    if not referrer:
        return 'Direct'
    try:
        host = re.sub(r'^https?://', '', referrer).split('/')[0].lower()
    except Exception:
        return 'Direct'
    for pattern, label in SOURCE_PATTERNS:
        if pattern.search(host):
            return label
    return host or 'Direct'


class TrackEvent(BaseModel):
    event_type: str
    session_id: str
    path: Optional[str] = None
    job_id: Optional[str] = None
    referrer: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    screen_w: Optional[int] = None
    screen_h: Optional[int] = None


@router.post('/public/track')
async def public_track(evt: TrackEvent, request: Request):
    """Public no-auth analytics beacon. Silently drops unknown event types so
    older clients don't break future rollouts."""
    if evt.event_type not in VALID_EVENT_TYPES:
        return {'ok': True}  # unknown types are silently dropped
    # Portal must be enabled for tracking to matter — but we still accept and
    # store the event so analysts can see traffic on a paused portal.
    ip = (request.headers.get('x-forwarded-for') or request.client.host if request.client else '') or ''
    ip = ip.split(',')[0].strip()
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16] if ip else ''
    ua = (request.headers.get('user-agent') or '')[:200]

    source = _classify_referrer(evt.referrer, evt.utm_source)
    doc = {
        'id': new_id(),
        'event_type': evt.event_type,
        'session_id': evt.session_id,
        'path': (evt.path or '')[:400],
        'job_id': evt.job_id,
        'referrer': (evt.referrer or '')[:400],
        'utm_source': (evt.utm_source or '')[:80],
        'utm_medium': (evt.utm_medium or '')[:80],
        'utm_campaign': (evt.utm_campaign or '')[:120],
        'source': source,
        'ip_hash': ip_hash,
        'user_agent': ua,
        'created_at': now_iso(),
    }
    await db.analytics_events.insert_one(doc)
    return {'ok': True}


def _days_ago_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@router.get('/analytics/overview')
async def analytics_overview(days: int = 30, user: dict = Depends(require_roles('admin', 'recruiter'))):
    """Aggregate view for the analytics dashboard.
    Query param `days` clamps to 1..365."""
    days = max(1, min(365, days))
    since = _days_ago_iso(days)
    base_query = {'created_at': {'$gte': since}}

    # Simple counts — one round trip per number keeps this MVP.
    views = await db.analytics_events.count_documents({**base_query, 'event_type': {'$in': ['page_view', 'job_view']}})
    job_views = await db.analytics_events.count_documents({**base_query, 'event_type': 'job_view'})
    apply_starts = await db.analytics_events.count_documents({**base_query, 'event_type': 'apply_start'})
    apply_submits = await db.analytics_events.count_documents({**base_query, 'event_type': 'apply_submit'})
    # Applications from real career_site records is more reliable than event count,
    # since a client can lose the apply_submit beacon on redirect. We keep both.
    applications = await db.applications.count_documents({
        'source': 'career_site', 'created_at': {'$gte': since},
    })
    unique_visitors = len(await db.analytics_events.distinct('session_id', {**base_query, 'session_id': {'$ne': ''}}))
    conversion_rate = round((applications / job_views * 100), 1) if job_views else 0.0

    # Time-series: bucket by date string (YYYY-MM-DD) for the last `days` days.
    pipeline = [
        {'$match': base_query},
        {'$project': {'day': {'$substr': ['$created_at', 0, 10]}, 'event_type': 1}},
        {'$group': {
            '_id': {'day': '$day', 'event_type': '$event_type'},
            'count': {'$sum': 1},
        }},
    ]
    raw = await db.analytics_events.aggregate(pipeline).to_list(1000)
    day_map: dict = {}
    for r in raw:
        d = r['_id']['day']
        entry = day_map.setdefault(d, {'date': d, 'views': 0, 'applications': 0})
        if r['_id']['event_type'] in ('page_view', 'job_view'):
            entry['views'] += r['count']
        elif r['_id']['event_type'] == 'apply_submit':
            entry['applications'] += r['count']
    # Include days with zero activity so the chart doesn't collapse.
    now = datetime.now(timezone.utc).date()
    timeseries = []
    for i in range(days - 1, -1, -1):
        d = (now - timedelta(days=i)).isoformat()
        timeseries.append(day_map.get(d, {'date': d, 'views': 0, 'applications': 0}))

    # Traffic sources — group page_view + job_view by classified source label.
    source_pipe = [
        {'$match': {**base_query, 'event_type': {'$in': ['page_view', 'job_view']}}},
        {'$group': {'_id': '$source', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 10},
    ]
    sources = [{'name': r['_id'] or 'Direct', 'count': r['count']}
               for r in await db.analytics_events.aggregate(source_pipe).to_list(20)]

    # Top jobs — join event counts with real application counts + job titles.
    top_pipe = [
        {'$match': {**base_query, 'event_type': 'job_view', 'job_id': {'$ne': None}}},
        {'$group': {'_id': '$job_id', 'views': {'$sum': 1}}},
        {'$sort': {'views': -1}},
        {'$limit': 10},
    ]
    top_raw = await db.analytics_events.aggregate(top_pipe).to_list(20)
    job_ids = [r['_id'] for r in top_raw]
    jobs = {j['id']: j for j in await db.jobs.find({'id': {'$in': job_ids}}, {'_id': 0, 'id': 1, 'title': 1, 'department': 1, 'slug': 1}).to_list(50)}
    # Application counts per job in the window
    app_counts_pipe = [
        {'$match': {'source': 'career_site', 'created_at': {'$gte': since}, 'job_id': {'$in': job_ids}}},
        {'$group': {'_id': '$job_id', 'count': {'$sum': 1}}},
    ]
    app_counts = {r['_id']: r['count'] for r in await db.applications.aggregate(app_counts_pipe).to_list(50)}
    top_jobs = []
    for r in top_raw:
        jid = r['_id']
        job = jobs.get(jid) or {}
        v = r['views']
        a = app_counts.get(jid, 0)
        top_jobs.append({
            'job_id': jid,
            'title': job.get('title') or 'Unknown role',
            'department': job.get('department'),
            'slug': job.get('slug'),
            'views': v,
            'applications': a,
            'conversion': round((a / v * 100), 1) if v else 0.0,
        })

    return {
        'window_days': days,
        'views': views,
        'job_views': job_views,
        'apply_starts': apply_starts,
        'apply_submits': apply_submits,
        'applications': applications,
        'unique_visitors': unique_visitors,
        'conversion_rate': conversion_rate,
        'timeseries': timeseries,
        'sources': sources,
        'top_jobs': top_jobs,
    }


@router.get('/analytics/events')
async def analytics_events(limit: int = 100, user: dict = Depends(require_roles('admin', 'recruiter'))):
    """Raw event feed for debugging. Limited to 500 rows to avoid heavy payloads."""
    limit = max(1, min(500, limit))
    rows = await db.analytics_events.find({}, {'_id': 0}).sort('created_at', -1).to_list(limit)
    return rows
