/**
 * Lightweight client-side tracking helper for the public Career Portal.
 *
 * - `sessionId()` returns a stable UUID stored in localStorage so we can
 *   compute per-session conversion (viewed a job + submitted an application).
 * - `track(event_type, extras)` sends a fire-and-forget POST to the public
 *   `/api/career/public/track` endpoint. Never awaited, never blocks the UI.
 * - `utmParams()` reads utm_source/medium/campaign from the current URL so
 *   the first pageview correctly attributes the visitor's traffic source.
 */
import { api } from '@/lib/api';

const SESSION_KEY = 'career_session_id';

function uuid() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  // Fallback for older browsers — RFC4122 v4-ish
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function sessionId() {
  try {
    let sid = localStorage.getItem(SESSION_KEY);
    if (!sid) {
      sid = uuid();
      localStorage.setItem(SESSION_KEY, sid);
    }
    return sid;
  } catch {
    // localStorage blocked (e.g. Safari private mode). Fall back to a
    // per-page-load UUID so we still get *some* aggregation.
    return uuid();
  }
}

export function utmParams() {
  try {
    const p = new URLSearchParams(window.location.search);
    return {
      utm_source: p.get('utm_source') || undefined,
      utm_medium: p.get('utm_medium') || undefined,
      utm_campaign: p.get('utm_campaign') || undefined,
    };
  } catch {
    return {};
  }
}

export function track(event_type, extras = {}) {
  try {
    const payload = {
      event_type,
      session_id: sessionId(),
      path: window.location.pathname + window.location.search,
      referrer: document.referrer || undefined,
      screen_w: window.innerWidth,
      screen_h: window.innerHeight,
      ...utmParams(),
      ...extras,
    };
    // Fire-and-forget: never await, never surface errors — this is telemetry.
    api.post('/career/public/track', payload).catch(() => {});
  } catch {
    /* swallow */
  }
}
