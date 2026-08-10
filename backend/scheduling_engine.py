"""Reusable interview-availability engine for candidate self-scheduling.

Generates bookable interview slots by intersecting, for EVERY required
interviewer:
  * company (or interviewer-specific) working hours,
  * existing ATS interview bookings (non-cancelled, already-booked),
  * the interviewer's Google Calendar free/busy (only when their Google
    account is connected).

All timestamps are handled in UTC internally. Slot generation walks the
working-hours window expressed in the company's IANA timezone (DST-correct via
zoneinfo) and returns UTC instants; the candidate-facing UI converts those to
whatever timezone the candidate selects for display.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo

from database import db
from google_calendar import free_busy, get_credentials_for_user

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    'key': 'scheduling',
    'working_days': [0, 1, 2, 3, 4],       # 0=Mon .. 6=Sun
    'start_time': '09:00',
    'end_time': '18:00',
    'timezone': 'Asia/Kolkata',
    'min_notice_hours': 12,
    'max_horizon_days': 14,
    'slot_interval_min': 30,
    'reminder_offsets_hours': [24, 1],
}


async def get_scheduling_settings() -> dict:
    doc = await db.settings.find_one({'key': 'scheduling'}, {'_id': 0})
    if not doc:
        doc = dict(DEFAULT_SETTINGS)
        await db.settings.update_one({'key': 'scheduling'}, {'$set': doc}, upsert=True)
        return doc
    # Backfill any missing keys with defaults so older docs stay valid.
    merged = {**DEFAULT_SETTINGS, **doc}
    return merged


def _parse_hhmm(s: str) -> time:
    h, m = (s or '09:00').split(':')
    return time(int(h), int(m))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


async def _ats_busy_for(interviewer_id: str, win_start: datetime, win_end: datetime,
                        exclude_interview_id: str | None = None) -> list[tuple[datetime, datetime]]:
    """Booked, non-cancelled ATS interviews for this interviewer in the window."""
    q = {
        'interviewer_ids': interviewer_id,
        'status': {'$nin': ['cancelled']},
        'scheduled_at': {'$ne': None},
    }
    busy: list[tuple[datetime, datetime]] = []
    docs = await db.interviews.find(q, {'_id': 0, 'id': 1, 'scheduled_at': 1, 'duration_min': 1}).to_list(2000)
    for iv in docs:
        if exclude_interview_id and iv.get('id') == exclude_interview_id:
            continue
        sa = iv.get('scheduled_at')
        if not sa:
            continue
        try:
            s = datetime.fromisoformat(sa.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            continue
        e = s + timedelta(minutes=iv.get('duration_min', 60))
        if _overlaps(s, e, win_start, win_end):
            busy.append((s, e))
    return busy


async def _google_busy_for(user_doc: dict, win_start: datetime, win_end: datetime) -> tuple[list[tuple[datetime, datetime]], bool]:
    """Returns (busy_intervals, ok). ok=False means the calendar could not be
    read (token expired / API error) — caller should treat availability as
    unknown rather than "free"."""
    if not user_doc.get('google_tokens'):
        return [], True  # no calendar connected → nothing to subtract, ok
    try:
        creds = await get_credentials_for_user(user_doc)
        if not creds:
            return [], False
        raw = await asyncio.to_thread(free_busy, creds, _iso(win_start), _iso(win_end))
        out = []
        for b in raw:
            try:
                s = datetime.fromisoformat(b['start'].replace('Z', '+00:00'))
                e = datetime.fromisoformat(b['end'].replace('Z', '+00:00'))
                out.append((s, e))
            except (ValueError, KeyError, AttributeError):
                continue
        return out, True
    except Exception as e:  # noqa: BLE001
        logger.warning('free/busy read failed for user %s: %s', user_doc.get('id'), e)
        return [], False


async def _availability_windows(interviewer_id: str) -> dict[int, list[tuple[time, time]]]:
    """Per-weekday working windows defined explicitly by the interviewer (the
    `availability` collection). Empty dict → no personal rules (use company)."""
    rows = await db.availability.find({'user_id': interviewer_id}, {'_id': 0}).to_list(50)
    out: dict[int, list[tuple[time, time]]] = {}
    for r in rows:
        try:
            out.setdefault(int(r['day_of_week']), []).append((_parse_hhmm(r['start_time']), _parse_hhmm(r['end_time'])))
        except (KeyError, ValueError):
            continue
    return out


async def build_interviewer_context(interviewer_ids: list[str], win_start: datetime, win_end: datetime,
                                    exclude_interview_id: str | None = None) -> dict:
    """Pre-compute per-interviewer busy intervals + personal windows over the
    whole scheduling window (one Google call per interviewer)."""
    users = {u['id']: u for u in await db.users.find({'id': {'$in': interviewer_ids}}).to_list(100)}
    ctx = {}
    for iid in interviewer_ids:
        u = users.get(iid, {'id': iid})
        ats = await _ats_busy_for(iid, win_start, win_end, exclude_interview_id)
        g_busy, g_ok = await _google_busy_for(u, win_start, win_end)
        windows = await _availability_windows(iid)
        ctx[iid] = {
            'user': u,
            'busy': ats + g_busy,
            'google_connected': bool(u.get('google_tokens')),
            'calendar_ok': g_ok,
            'windows': windows,
            'name': u.get('name', '?'),
        }
    return ctx


def _within_personal_window(windows: dict, weekday: int, local_start: datetime, local_end: datetime) -> bool:
    """If the interviewer defined personal windows for this weekday, the slot
    must fall entirely inside one of them. No rules for the day → True."""
    day_windows = windows.get(weekday)
    if not day_windows:
        return True
    for (ws, we) in day_windows:
        w_start = local_start.replace(hour=ws.hour, minute=ws.minute, second=0, microsecond=0)
        w_end = local_start.replace(hour=we.hour, minute=we.minute, second=0, microsecond=0)
        if w_start <= local_start and local_end <= w_end:
            return True
    return False


def _slot_free_for_all(ctx: dict, slot_start_utc: datetime, slot_end_utc: datetime, zone: ZoneInfo) -> bool:
    local_start = slot_start_utc.astimezone(zone)
    local_end = slot_end_utc.astimezone(zone)
    weekday = local_start.weekday()
    for iid, c in ctx.items():
        if not c['calendar_ok']:
            return False  # unknown availability → never offer
        if not _within_personal_window(c['windows'], weekday, local_start, local_end):
            return False
        for (bs, be) in c['busy']:
            if _overlaps(slot_start_utc, slot_end_utc, bs, be):
                return False
    return True


async def generate_slots(interviewer_ids: list[str], duration_min: int,
                         date_from: str, date_to: str, settings: dict,
                         exclude_interview_id: str | None = None,
                         now_utc: datetime | None = None) -> dict:
    """Return {slots:[{start_utc,end_utc}], generation_timezone, interviewers:[...],
    calendar_error:bool}. Slots are only returned when EVERY interviewer is free
    for the entire duration."""
    zone = ZoneInfo(settings.get('timezone') or 'UTC')
    now_utc = now_utc or datetime.now(timezone.utc)
    min_start = now_utc + timedelta(hours=int(settings.get('min_notice_hours', 12)))
    max_end = now_utc + timedelta(days=int(settings.get('max_horizon_days', 14)))
    interval = int(settings.get('slot_interval_min', 30)) or 30
    working_days = set(settings.get('working_days') or [0, 1, 2, 3, 4])
    day_start_t = _parse_hhmm(settings.get('start_time', '09:00'))
    day_end_t = _parse_hhmm(settings.get('end_time', '18:00'))

    d0 = date.fromisoformat(date_from)
    d1 = date.fromisoformat(date_to)
    if d1 < d0:
        d0, d1 = d1, d0

    # Window in UTC covering the requested date range (in company tz).
    win_start = max(min_start, datetime.combine(d0, time(0, 0), tzinfo=zone).astimezone(timezone.utc))
    win_end = min(max_end, datetime.combine(d1, time(23, 59), tzinfo=zone).astimezone(timezone.utc))

    ctx = await build_interviewer_context(interviewer_ids, win_start - timedelta(hours=6),
                                          win_end + timedelta(hours=6), exclude_interview_id)
    calendar_error = any(not c['calendar_ok'] for c in ctx.values())

    slots = []
    cur = d0
    while cur <= d1:
        if cur.weekday() in working_days:
            local_day_start = datetime.combine(cur, day_start_t, tzinfo=zone)
            local_day_end = datetime.combine(cur, day_end_t, tzinfo=zone)
            cursor = local_day_start
            step = timedelta(minutes=interval)
            dur = timedelta(minutes=duration_min)
            while cursor + dur <= local_day_end:
                s_utc = cursor.astimezone(timezone.utc)
                e_utc = s_utc + dur
                if s_utc >= min_start and e_utc <= max_end and s_utc >= now_utc:
                    if _slot_free_for_all(ctx, s_utc, e_utc, zone):
                        slots.append({'start_utc': s_utc.isoformat(), 'end_utc': e_utc.isoformat()})
                cursor += step
        cur += timedelta(days=1)

    interviewers = [{
        'id': iid,
        'name': c['name'],
        'google_calendar_connected': c['google_connected'],
        'calendar_readable': c['calendar_ok'],
        'has_working_hours': bool(c['windows']),
    } for iid, c in ctx.items()]

    return {
        'slots': slots,
        'generation_timezone': settings.get('timezone') or 'UTC',
        'slot_interval_min': interval,
        'interviewers': interviewers,
        'calendar_error': calendar_error,
    }


async def is_slot_free(interviewer_ids: list[str], start_utc: datetime, duration_min: int,
                       exclude_interview_id: str | None = None) -> tuple[bool, str, dict]:
    """Immediate re-validation used right before booking. Returns
    (free, reason, ctx). reason ∈ {'ok','slot_taken','calendar_error'}."""
    end_utc = start_utc + timedelta(minutes=duration_min)
    ctx = await build_interviewer_context(interviewer_ids, start_utc - timedelta(minutes=1),
                                          end_utc + timedelta(minutes=1), exclude_interview_id)
    for c in ctx.values():
        if not c['calendar_ok']:
            return False, 'calendar_error', ctx
    zone = ZoneInfo('UTC')
    if _slot_free_for_all(ctx, start_utc, end_utc, zone):
        return True, 'ok', ctx
    return False, 'slot_taken', ctx
