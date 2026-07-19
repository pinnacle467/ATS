import { format } from 'date-fns';

// Common IANA timezone presets grouped for the picker
export const TZ_PRESETS = [
  { value: 'America/Los_Angeles', label: 'Los Angeles (PT)' },
  { value: 'America/Denver', label: 'Denver (MT)' },
  { value: 'America/Chicago', label: 'Chicago (CT)' },
  { value: 'America/New_York', label: 'New York (ET)' },
  { value: 'America/Toronto', label: 'Toronto' },
  { value: 'America/Sao_Paulo', label: 'São Paulo' },
  { value: 'Europe/London', label: 'London (GMT/BST)' },
  { value: 'Europe/Berlin', label: 'Berlin' },
  { value: 'Europe/Paris', label: 'Paris' },
  { value: 'Europe/Amsterdam', label: 'Amsterdam' },
  { value: 'Europe/Zurich', label: 'Zurich' },
  { value: 'Africa/Johannesburg', label: 'Johannesburg' },
  { value: 'Asia/Dubai', label: 'Dubai' },
  { value: 'Asia/Kolkata', label: 'Mumbai / Delhi (IST)' },
  { value: 'Asia/Singapore', label: 'Singapore' },
  { value: 'Asia/Shanghai', label: 'Shanghai' },
  { value: 'Asia/Hong_Kong', label: 'Hong Kong' },
  { value: 'Asia/Tokyo', label: 'Tokyo' },
  { value: 'Australia/Sydney', label: 'Sydney' },
  { value: 'Pacific/Auckland', label: 'Auckland' },
  { value: 'UTC', label: 'UTC' },
];

export function getBrowserTz() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

// Best-effort short abbreviation for a tz at a given instant. e.g. "EDT", "IST", "GMT+5:30"
export function tzAbbr(tz, date = new Date()) {
  try {
    const fmt = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'short' });
    const part = fmt.formatToParts(date).find((p) => p.type === 'timeZoneName');
    return part?.value || tz;
  } catch {
    return tz;
  }
}

// Return {year, month, day, hour, minute, second, weekday} in the given tz for a Date.
export function partsInTz(date, tz) {
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    weekday: 'short',
  });
  const parts = Object.fromEntries(fmt.formatToParts(date).map((p) => [p.type, p.value]));
  return {
    year: +parts.year,
    month: +parts.month,
    day: +parts.day,
    hour: (+parts.hour) % 24, // Intl sometimes yields "24"
    minute: +parts.minute,
    second: +parts.second,
    weekday: parts.weekday,
  };
}

// Return a Date pinned to the wall-clock of `date` interpreted in `tz` (i.e. the
// same year/month/day/hour/minute the user sees in `tz`, but expressed as a UTC
// Date so date-fns' format() / getDay() etc read the desired numbers.
export function asWallClockDate(date, tz) {
  const p = partsInTz(date, tz);
  return new Date(Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second));
}

// Format an instant `date` as if it were in `tz`, using date-fns tokens.
export function formatInTz(date, tz, fmtStr) {
  return format(asWallClockDate(date, tz), fmtStr);
}

// Return the "wall clock hours" a given instant lands on in a tz (as a float).
// e.g. 14:30 in tz -> 14.5.
export function tzHours(date, tz) {
  const p = partsInTz(date, tz);
  return p.hour + p.minute / 60;
}

// Return a Date at the start of the given day (00:00) in `tz`, expressed as UTC.
export function startOfDayInTz(date, tz) {
  const p = partsInTz(date, tz);
  return wallClockUtc(p.year, p.month, p.day, 0, 0, tz);
}

// Return a Date for the wall-clock (year, month, day, hour, minute) in `tz` as UTC.
export function wallClockUtc(year, month, day, hour, minute, tz) {
  const asUtc = Date.UTC(year, month - 1, day, hour, minute, 0);
  const p = partsInTz(new Date(asUtc), tz);
  const asTz = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  return new Date(asUtc - (asTz - asUtc));
}

// Are two Date instants on the same wall-clock day in `tz`?
export function isSameDayInTz(a, b, tz) {
  const pa = partsInTz(a, tz);
  const pb = partsInTz(b, tz);
  return pa.year === pb.year && pa.month === pb.month && pa.day === pb.day;
}
