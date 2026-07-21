import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { addDays, format, startOfWeek } from 'date-fns';
import {
  BookOpen, CalendarCheck2, CalendarPlus, CheckCircle2, ChevronLeft, ChevronRight,
  ClipboardList, Clock, ExternalLink, Globe, Link2Off, Loader2, MapPin, RefreshCw, User, Users, Video, XCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import ScheduleInterviewDialog from '@/components/ScheduleInterviewDialog';
import ScorecardDialog from '@/components/ScorecardDialog';
import { useAuth } from '@/context/AuthContext';
import { api, errMsg } from '@/lib/api';
import {
  asWallClockDate, formatInTz, getBrowserTz, isSameDayInTz, TZ_PRESETS, tzAbbr, tzHours,
} from '@/lib/timezones';

const STATUS_STYLE = {
  scheduled: { bg: 'bg-sky-50', border: 'border-l-sky-500', pill: 'bg-sky-100 text-sky-800', text: 'text-sky-900' },
  feedback_pending: { bg: 'bg-amber-50', border: 'border-l-amber-500', pill: 'bg-amber-100 text-amber-800', text: 'text-amber-900' },
  feedback_submitted: { bg: 'bg-emerald-50', border: 'border-l-emerald-500', pill: 'bg-emerald-100 text-emerald-800', text: 'text-emerald-900' },
  cancelled: { bg: 'bg-secondary', border: 'border-l-muted-foreground', pill: 'bg-secondary text-muted-foreground', text: 'text-muted-foreground' },
};
const STATUS_LABEL = {
  scheduled: 'Scheduled',
  feedback_pending: 'Feedback Pending',
  feedback_submitted: 'Feedback In',
  cancelled: 'Cancelled',
};
const TYPE_LABEL = {
  phone_screen: 'Phone Screen',
  technical: 'Technical',
  panel: 'Panel',
  onsite: 'Onsite',
};
const TYPE_COLOR = {
  phone_screen: 'bg-sky-100 text-sky-800',
  technical: 'bg-purple-100 text-purple-800',
  panel: 'bg-amber-100 text-amber-800',
  onsite: 'bg-emerald-100 text-emerald-800',
};

const initials = (name) => (name || '?').split(' ').slice(0, 2).map((n) => n[0]).join('').toUpperCase();

// Config for the day/week grid
const GRID_START_HOUR = 7;
const GRID_END_HOUR = 21; // 9 PM
const HOUR_ROW_PX = 56;

export default function InterviewsPage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [interviews, setInterviews] = useState([]);
  const [users, setUsers] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [kits, setKits] = useState([]);
  const [filters, setFilters] = useState({ interviewer_id: 'all', job_id: 'all', status: 'all', type: 'all' });
  const [view, setView] = useState('week');
  const [displayTz, setDisplayTz] = useState(() => localStorage.getItem('interviews_display_tz') || getBrowserTz());
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }));
  const [dayFocus, setDayFocus] = useState(() => new Date());
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scorecardIv, setScorecardIv] = useState(null);
  const [detailIv, setDetailIv] = useState(null);
  const [detailScores, setDetailScores] = useState([]);
  const [kitOpen, setKitOpen] = useState(null);
  const [calStatus, setCalStatus] = useState(null);
  const [calBusy, setCalBusy] = useState(false);
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [externalEvents, setExternalEvents] = useState([]); // read-only overlay from Google Calendar

  const isRecruiter = ['super_admin', 'admin', 'recruiter'].includes(user?.role);

  useEffect(() => { localStorage.setItem('interviews_display_tz', displayTz); }, [displayTz]);

  const loadCalStatus = useCallback(() => {
    api.get('/calendar/status').then((r) => setCalStatus(r.data)).catch(() => {});
  }, []);

  useEffect(() => { loadCalStatus(); }, [loadCalStatus]);

  useEffect(() => {
    const cal = searchParams.get('calendar');
    if (cal === 'connected') {
      toast.success('Google Calendar connected — new interviews will sync automatically');
      loadCalStatus();
      searchParams.delete('calendar'); setSearchParams(searchParams, { replace: true });
    } else if (cal === 'error') {
      toast.error('Could not connect Google Calendar. Please try again.');
      searchParams.delete('calendar'); setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams, loadCalStatus]);

  useEffect(() => {
    const scId = searchParams.get('scorecard');
    if (!scId || interviews.length === 0) return;
    const iv = interviews.find((i) => i.id === scId);
    if (iv) setScorecardIv(iv);
    searchParams.delete('scorecard');
    setSearchParams(searchParams, { replace: true });
  }, [searchParams, setSearchParams, interviews]);

  const load = useCallback(() => {
    const params = {};
    if (filters.interviewer_id !== 'all') params.interviewer_id = filters.interviewer_id;
    if (filters.job_id !== 'all') params.job_id = filters.job_id;
    if (filters.status !== 'all') params.status = filters.status;
    api.get('/interviews', { params }).then((r) => setInterviews(r.data)).catch((e) => toast.error(errMsg(e)));
  }, [filters]);

  useEffect(() => {
    load();
    Promise.all([api.get('/users'), api.get('/jobs'), api.get('/interview-kits')])
      .then(([u, j, k]) => { setUsers(u.data); setJobs(j.data); setKits(k.data); })
      .catch(() => {});
  }, [load]);

  // Read-only overlay of Google Calendar events on the week/day grid. We keep
  // the fetch narrow (only the visible window ± 1 day) so nothing extra is
  // pulled if the user is stuck on List view or hasn't connected calendar.
  useEffect(() => {
    if (!calStatus?.connected) { setExternalEvents([]); return; }
    if (view !== 'week' && view !== 'day') { setExternalEvents([]); return; }
    let cancelled = false;
    const from = view === 'week' ? addDays(weekStart, -1) : addDays(dayFocus, -1);
    const to = view === 'week' ? addDays(weekStart, 8) : addDays(dayFocus, 2);
    api.get('/calendar/external-events', {
      params: { time_min: from.toISOString(), time_max: to.toISOString() },
    })
      .then((r) => { if (!cancelled) setExternalEvents(r.data?.events || []); })
      .catch(() => { if (!cancelled) setExternalEvents([]); });
    return () => { cancelled = true; };
  }, [calStatus?.connected, view, weekStart, dayFocus]);

  const openDetail = async (iv) => {
    setDetailIv(iv);
    if (iv.scorecards_submitted > 0) {
      try {
        const r = await api.get(`/interviews/${iv.id}/scorecards`);
        setDetailScores(r.data || []);
      } catch { setDetailScores([]); }
    } else {
      setDetailScores([]);
    }
  };

  const complete = async (iv) => {
    try {
      await api.post(`/interviews/${iv.id}/complete`);
      toast.success('Marked complete — feedback now pending');
      load();
      if (detailIv?.id === iv.id) setDetailIv({ ...iv, status: 'feedback_pending' });
    } catch (e) { toast.error(errMsg(e)); }
  };

  const cancel = async (iv) => {
    if (!window.confirm(`Cancel interview with ${iv.candidate_name}?`)) return;
    try {
      await api.put(`/interviews/${iv.id}`, { status: 'cancelled' });
      toast.success('Interview cancelled');
      load();
      setDetailIv(null);
    } catch (e) { toast.error(errMsg(e)); }
  };

  const connectCalendar = async () => {
    setCalBusy(true);
    try {
      const r = await api.get('/oauth/google/login');
      window.location.href = r.data.authorization_url;
    } catch (e) { toast.error(errMsg(e)); setCalBusy(false); }
  };

  const disconnectCalendar = async () => {
    if (!window.confirm('Disconnect Google Calendar? Future interviews will no longer sync automatically.')) return;
    setCalBusy(true);
    try { await api.post('/calendar/disconnect'); toast.success('Google Calendar disconnected'); loadCalStatus(); }
    catch (e) { toast.error(errMsg(e)); }
    finally { setCalBusy(false); }
  };

  // Pull events from the connected user's Google Calendar and create ATS
  // interview records for any event whose attendees include a known candidate
  // email. Idempotent — reruns are safe.
  const syncInterviewsFromCalendar = async () => {
    setSyncBusy(true);
    setSyncResult(null);
    try {
      const r = await api.post('/calendar/sync-interviews', null, { params: { days_back: 14, days_forward: 30 } });
      setSyncResult(r.data);
      const n = (r.data?.imported || []).length;
      if (n > 0) {
        toast.success(`Imported ${n} interview${n === 1 ? '' : 's'} from Google Calendar`);
        // Refresh the calendar view so the new interviews show up.
        load();
      } else {
        toast.info('No new interviews found in your Google Calendar');
      }
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSyncBusy(false);
    }
  };

  // -------- Filtering --------
  const visibleInterviews = useMemo(() => {
    return interviews.filter((iv) => {
      if (filters.type !== 'all' && iv.type !== filters.type) return false;
      if (filters.status === 'all' && iv.status === 'cancelled') return false;
      return true;
    });
  }, [interviews, filters]);

  // -------- Header time helpers --------
  const rangeLabel = useMemo(() => {
    if (view === 'week') {
      const end = addDays(weekStart, 6);
      return `${format(weekStart, 'MMM d')} – ${format(end, 'MMM d, yyyy')}`;
    }
    return format(dayFocus, 'EEEE, MMM d, yyyy');
  }, [view, weekStart, dayFocus]);

  const goPrev = () => view === 'week' ? setWeekStart((w) => addDays(w, -7)) : setDayFocus((d) => addDays(d, -1));
  const goNext = () => view === 'week' ? setWeekStart((w) => addDays(w, 7)) : setDayFocus((d) => addDays(d, 1));
  const goToday = () => {
    if (view === 'week') setWeekStart(startOfWeek(new Date(), { weekStartsOn: 1 }));
    else setDayFocus(new Date());
  };

  // -------- Sidebar upcoming list --------
  const upcoming = useMemo(() => {
    const now = new Date();
    return visibleInterviews
      .filter((iv) => iv.status !== 'cancelled' && new Date(iv.scheduled_at) >= now)
      .sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at))
      .slice(0, 8);
  }, [visibleInterviews]);

  const kpi = useMemo(() => {
    const now = new Date();
    const weekEnd = addDays(weekStart, 7);
    const inThisWeek = visibleInterviews.filter((iv) => {
      const d = new Date(iv.scheduled_at);
      return d >= weekStart && d < weekEnd && iv.status !== 'cancelled';
    });
    return {
      thisWeek: inThisWeek.length,
      pending: visibleInterviews.filter((iv) => iv.status === 'feedback_pending').length,
      todayUpcoming: visibleInterviews.filter((iv) => {
        const d = new Date(iv.scheduled_at);
        return isSameDayInTz(d, now, displayTz) && iv.status !== 'cancelled' && d >= now;
      }).length,
    };
  }, [visibleInterviews, weekStart, displayTz]);

  // -------- Sidebar (upcoming list) --------
  const UpcomingSidebar = () => (
    <div className="space-y-3">
      <Card className="shadow-none">
        <CardContent className="py-3 space-y-2">
          <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">This week</p>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="bg-secondary/60 rounded-lg py-2">
              <p className="text-lg font-display font-semibold" data-testid="kpi-this-week">{kpi.thisWeek}</p>
              <p className="text-[10px] text-muted-foreground uppercase">Scheduled</p>
            </div>
            <div className="bg-secondary/60 rounded-lg py-2">
              <p className="text-lg font-display font-semibold text-amber-700" data-testid="kpi-pending">{kpi.pending}</p>
              <p className="text-[10px] text-muted-foreground uppercase">Feedback pending</p>
            </div>
            <div className="bg-secondary/60 rounded-lg py-2">
              <p className="text-lg font-display font-semibold text-sky-700" data-testid="kpi-today">{kpi.todayUpcoming}</p>
              <p className="text-[10px] text-muted-foreground uppercase">Today</p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="shadow-none">
        <CardContent className="py-3">
          <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium mb-2">Upcoming</p>
          <div className="space-y-1.5 max-h-[65vh] overflow-y-auto -mx-1 px-1" data-testid="interviews-upcoming-list">
            {upcoming.length === 0 && <p className="text-xs text-muted-foreground text-center py-6">Nothing coming up.</p>}
            {upcoming.map((iv) => {
              const st = STATUS_STYLE[iv.status];
              return (
                <button
                  key={iv.id}
                  onClick={() => openDetail(iv)}
                  className={`w-full text-left border-l-2 ${st.border} bg-card border border-border rounded-lg px-2 py-2 hover:bg-secondary/60 transition-colors`}
                  data-testid={`interview-upcoming-${iv.id}`}
                >
                  <div className="flex items-center justify-between gap-1">
                    <p className="text-sm font-medium truncate">{iv.candidate_name}</p>
                    {iv.calendar_synced && <CalendarCheck2 className="h-3 w-3 text-primary shrink-0" />}
                  </div>
                  <p className="text-[11px] text-muted-foreground truncate">{iv.job_title || TYPE_LABEL[iv.type]}</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5 flex items-center gap-1">
                    <Clock className="h-2.5 w-2.5" />
                    {formatInTz(new Date(iv.scheduled_at), displayTz, 'EEE, MMM d · p')}
                  </p>
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );

  // -------- Time grid (week / day) --------
  const WeekGrid = () => {
    const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
    const hours = Array.from({ length: GRID_END_HOUR - GRID_START_HOUR + 1 }, (_, i) => GRID_START_HOUR + i);
    const nowWall = asWallClockDate(new Date(), displayTz);
    const showNowLine = days.some((d) => format(d, 'yyyy-MM-dd') === format(nowWall, 'yyyy-MM-dd'));

    return (
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="grid grid-cols-[60px_repeat(7,minmax(0,1fr))] border-b border-border bg-secondary/40 sticky top-0 z-10">
          <div className="px-2 py-2 text-[11px] text-muted-foreground font-medium">{tzAbbr(displayTz)}</div>
          {days.map((d) => {
            const isToday = isSameDayInTz(new Date(), d, displayTz);
            return (
              <div key={d.toISOString()} className={`px-2 py-2 text-center border-l border-border ${isToday ? 'bg-primary/5' : ''}`}>
                <p className="text-[10px] text-muted-foreground uppercase font-medium">{format(d, 'EEE')}</p>
                <p className={`text-lg font-display leading-none mt-0.5 ${isToday ? 'text-primary font-semibold' : ''}`}>{format(d, 'd')}</p>
              </div>
            );
          })}
        </div>
        <div className="grid grid-cols-[60px_repeat(7,minmax(0,1fr))] relative">
          {/* Hour column */}
          <div className="border-r border-border">
            {hours.map((h) => (
              <div key={h} className="text-[10px] text-muted-foreground text-right pr-1.5" style={{ height: HOUR_ROW_PX }}>
                <span className="-translate-y-1/2 inline-block">{format(new Date(2020, 0, 1, h), 'h a')}</span>
              </div>
            ))}
          </div>
          {days.map((d) => (
            <DayColumn key={d.toISOString()} day={d} showNowLine={showNowLine} />
          ))}
        </div>
      </div>
    );

    function DayColumn({ day }) {
      const isToday = isSameDayInTz(new Date(), day, displayTz);
      const dayIvs = visibleInterviews.filter((iv) => isSameDayInTz(new Date(iv.scheduled_at), day, displayTz));
      const dayExts = externalEvents.filter((ev) => !ev.all_day && isSameDayInTz(new Date(ev.start), day, displayTz));
      // Now line
      const nowHours = tzHours(new Date(), displayTz);
      const nowTop = (nowHours - GRID_START_HOUR) * HOUR_ROW_PX;

      return (
        <div className={`border-l border-border relative ${isToday ? 'bg-primary/5' : ''}`}>
          {hours.map((h) => (
            <div key={h} className="border-t border-border/60" style={{ height: HOUR_ROW_PX }} />
          ))}
          {isToday && nowHours >= GRID_START_HOUR && nowHours <= GRID_END_HOUR && (
            <div className="absolute left-0 right-0 pointer-events-none z-20" style={{ top: nowTop }}>
              <div className="h-px bg-rose-500 relative"><span className="absolute -left-1 -top-1 w-2 h-2 rounded-full bg-rose-500" /></div>
            </div>
          )}
          {/* External Google Calendar events render UNDER interview pills (lower z) so ATS interviews always win the visual layer */}
          {dayExts.map((ev) => <ExtEventBlock key={`ext-${ev.id}`} ev={ev} />)}
          {dayIvs.map((iv) => <IvBlock key={iv.id} iv={iv} />)}
        </div>
      );
    }
  };

  const DayGrid = () => {
    const hours = Array.from({ length: GRID_END_HOUR - GRID_START_HOUR + 1 }, (_, i) => GRID_START_HOUR + i);
    const dayIvs = visibleInterviews.filter((iv) => isSameDayInTz(new Date(iv.scheduled_at), dayFocus, displayTz));
    const dayExts = externalEvents.filter((ev) => !ev.all_day && isSameDayInTz(new Date(ev.start), dayFocus, displayTz));
    const nowHours = tzHours(new Date(), displayTz);
    const isToday = isSameDayInTz(new Date(), dayFocus, displayTz);
    const nowTop = (nowHours - GRID_START_HOUR) * HOUR_ROW_PX;

    return (
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="grid grid-cols-[60px_1fr] border-b border-border bg-secondary/40">
          <div className="px-2 py-2 text-[11px] text-muted-foreground font-medium">{tzAbbr(displayTz)}</div>
          <div className={`px-3 py-2 border-l border-border ${isToday ? 'bg-primary/5' : ''}`}>
            <p className="text-[10px] text-muted-foreground uppercase font-medium">{format(dayFocus, 'EEEE')}</p>
            <p className={`text-lg font-display font-semibold leading-none mt-0.5 ${isToday ? 'text-primary' : ''}`}>{format(dayFocus, 'MMM d')}</p>
          </div>
        </div>
        <div className="grid grid-cols-[60px_1fr]">
          <div className="border-r border-border">
            {hours.map((h) => (
              <div key={h} className="text-[10px] text-muted-foreground text-right pr-1.5" style={{ height: HOUR_ROW_PX }}>
                <span className="-translate-y-1/2 inline-block">{format(new Date(2020, 0, 1, h), 'h a')}</span>
              </div>
            ))}
          </div>
          <div className={`relative ${isToday ? 'bg-primary/5' : ''}`}>
            {hours.map((h) => (
              <div key={h} className="border-t border-border/60" style={{ height: HOUR_ROW_PX }} />
            ))}
            {isToday && nowHours >= GRID_START_HOUR && nowHours <= GRID_END_HOUR && (
              <div className="absolute left-0 right-0 pointer-events-none z-20" style={{ top: nowTop }}>
                <div className="h-px bg-rose-500 relative"><span className="absolute -left-1 -top-1 w-2 h-2 rounded-full bg-rose-500" /></div>
              </div>
            )}
            {dayExts.map((ev) => <ExtEventBlock key={`ext-${ev.id}`} ev={ev} />)}
            {dayIvs.map((iv) => <IvBlock key={iv.id} iv={iv} wide />)}
          </div>
        </div>
      </div>
    );
  };

  // Grey read-only pill for events pulled from the user's Google Calendar
  // that aren't ATS interviews (1:1s, standups, holds, etc.). Rendered next
  // to IvBlock inside the same day column so the user has a single-glance
  // view of their true availability. Clicking opens the event in Google Calendar.
  const ExtEventBlock = ({ ev }) => {
    // Skip all-day events on the timed grid — they'd swallow the whole column.
    if (ev.all_day) return null;
    const startDate = new Date(ev.start);
    const endDate = new Date(ev.end);
    const start = tzHours(startDate, displayTz);
    if (start < GRID_START_HOUR || start > GRID_END_HOUR) return null;
    const durationMin = Math.max(15, (endDate - startDate) / 60000);
    const top = Math.max(0, (start - GRID_START_HOUR) * HOUR_ROW_PX);
    const height = Math.max(24, (durationMin / 60) * HOUR_ROW_PX - 2);
    // Tentative / declined events dim further to reduce visual noise.
    const dim = ev.status_response === 'declined' || ev.status_response === 'tentative';
    const soloStyle = ev.is_solo
      ? 'bg-slate-100/70 border-slate-300 text-slate-600'
      : 'bg-slate-200/70 border-slate-400 text-slate-700';
    return (
      <a
        href={ev.html_link || '#'}
        target="_blank"
        rel="noopener noreferrer"
        className={`absolute left-0.5 right-0.5 rounded-md border border-dashed ${soloStyle} ${dim ? 'opacity-50 line-through' : ''} px-1.5 py-1 text-left overflow-hidden hover:opacity-100 hover:shadow-md hover:z-10 transition-all block`}
        style={{ top, height }}
        title={`${ev.summary} — ${formatInTz(startDate, displayTz, 'p')} to ${formatInTz(endDate, displayTz, 'p')}${ev.attendee_count > 0 ? ` · ${ev.attendee_count} attendee${ev.attendee_count === 1 ? '' : 's'}` : ' · solo'} (external — click to open in Google Calendar)`}
        data-testid={`external-event-${ev.id}`}
      >
        <div className="flex items-center gap-1 min-w-0">
          <span className="text-[8px] px-1 py-px rounded font-medium shrink-0 bg-slate-300/60 text-slate-700 uppercase tracking-wide">Ext</span>
        </div>
        <p className="text-[11px] font-medium truncate mt-0.5">{ev.summary}</p>
        <p className="text-[10px] opacity-70 truncate">{formatInTz(startDate, displayTz, 'p')}{ev.attendee_count > 0 ? ` · ${ev.attendee_count}` : ''}</p>
      </a>
    );
  };

  const IvBlock = ({ iv, wide }) => {
    const start = tzHours(new Date(iv.scheduled_at), displayTz);
    const top = Math.max(0, (start - GRID_START_HOUR) * HOUR_ROW_PX);
    const height = Math.max(28, (iv.duration_min / 60) * HOUR_ROW_PX - 2);
    const st = STATUS_STYLE[iv.status];
    return (
      <button
        onClick={() => openDetail(iv)}
        className={`absolute left-0.5 right-0.5 rounded-md ${st.bg} border-l-2 ${st.border} border border-border/50 px-1.5 py-1 text-left overflow-hidden hover:shadow-md hover:z-10 transition-all`}
        style={{ top, height }}
        data-testid={`interview-block-${iv.id}`}
      >
        <div className="flex items-center gap-1 min-w-0">
          <span className={`text-[9px] px-1 py-px rounded font-medium shrink-0 ${TYPE_COLOR[iv.type]}`}>{TYPE_LABEL[iv.type]}</span>
          {iv.calendar_synced && <CalendarCheck2 className="h-2.5 w-2.5 text-primary shrink-0" />}
        </div>
        <p className={`text-[11px] font-medium truncate mt-0.5 ${st.text}`}>{iv.candidate_name}</p>
        {wide && iv.job_title && <p className="text-[10px] text-muted-foreground truncate">{iv.job_title}</p>}
        <p className="text-[10px] text-muted-foreground truncate">{formatInTz(new Date(iv.scheduled_at), displayTz, 'p')}</p>
        {height >= 60 && iv.interviewer_names?.length > 0 && (
          <div className="flex -space-x-1 mt-1">
            {iv.interviewers?.slice(0, 3).map((i) => (
              <span key={i.id} className="inline-flex h-4 w-4 rounded-full bg-secondary border border-card items-center justify-center text-[8px] font-semibold" title={i.name}>
                {initials(i.name)}
              </span>
            ))}
            {iv.interviewers?.length > 3 && (
              <span className="inline-flex h-4 w-4 rounded-full bg-secondary border border-card items-center justify-center text-[8px] font-medium">+{iv.interviewers.length - 3}</span>
            )}
          </div>
        )}
      </button>
    );
  };

  // -------- List view --------
  const ListView = () => {
    const now = new Date();
    const items = visibleInterviews
      .filter((iv) => filters.status !== 'all' || iv.status !== 'cancelled' || filters.status === 'cancelled')
      .sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));
    if (items.length === 0) {
      return <Card className="shadow-none"><CardContent className="py-14 text-center text-muted-foreground text-sm">No interviews match your filters.</CardContent></Card>;
    }
    // Group by day-in-tz
    const groups = [];
    let curKey = null;
    items.forEach((iv) => {
      const d = new Date(iv.scheduled_at);
      const key = formatInTz(d, displayTz, 'yyyy-MM-dd');
      if (key !== curKey) { groups.push({ key, label: formatInTz(d, displayTz, 'EEEE, MMM d, yyyy'), isToday: isSameDayInTz(d, now, displayTz), items: [] }); curKey = key; }
      groups[groups.length - 1].items.push(iv);
    });
    return (
      <div className="space-y-4" data-testid="interviews-list">
        {groups.map((g) => (
          <div key={g.key}>
            <div className="flex items-center gap-2 mb-2">
              <p className={`text-sm font-medium ${g.isToday ? 'text-primary' : ''}`}>{g.label}</p>
              {g.isToday && <Badge variant="outline" className="text-primary border-primary/40">Today</Badge>}
              <span className="text-xs text-muted-foreground">· {g.items.length} interview{g.items.length !== 1 ? 's' : ''}</span>
            </div>
            <div className="space-y-2">
              {g.items.map((iv) => <ListRow key={iv.id} iv={iv} />)}
            </div>
          </div>
        ))}
      </div>
    );
  };

  const ListRow = ({ iv }) => {
    const st = STATUS_STYLE[iv.status];
    const start = new Date(iv.scheduled_at);
    const end = new Date(start.getTime() + iv.duration_min * 60000);
    const kit = kits.find((k) => k.stage === iv.stage);
    const mySubmitPending = iv.interviewer_ids?.includes(user?.id) && iv.status !== 'cancelled' && iv.status !== 'feedback_submitted';
    return (
      <div
        className={`bg-card border border-border rounded-xl border-l-4 ${st.border} hover:shadow-sm transition-shadow`}
        data-testid={`interview-card-${iv.id}`}
      >
        <div className="p-3 flex items-start gap-4 flex-wrap md:flex-nowrap">
          <button onClick={() => openDetail(iv)} className="flex-1 min-w-0 text-left">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${TYPE_COLOR[iv.type]}`}>{TYPE_LABEL[iv.type]}</span>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${st.pill}`}>{STATUS_LABEL[iv.status]}</span>
              {iv.calendar_synced && (
                <span title="Synced to Google Calendar" className="text-primary"><CalendarCheck2 className="h-3.5 w-3.5" /></span>
              )}
            </div>
            <p className="text-base font-medium mt-1 truncate">{iv.candidate_name}</p>
            {(iv.candidate_title || iv.job_title) && (
              <p className="text-xs text-muted-foreground truncate">{iv.candidate_title}{iv.candidate_title && iv.job_title ? ' · ' : ''}{iv.job_title && `for ${iv.job_title}`}</p>
            )}
            <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground flex-wrap">
              <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {formatInTz(start, displayTz, 'p')} – {formatInTz(end, displayTz, 'p')} <span className="text-[10px] uppercase">({tzAbbr(displayTz)})</span></span>
              {iv.location && <span className="flex items-center gap-1"><MapPin className="h-3 w-3" /> {iv.location}</span>}
              {iv.video_link && (
                <a href={iv.video_link} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-primary hover:underline" onClick={(e) => e.stopPropagation()}>
                  <Video className="h-3 w-3" /> Join
                </a>
              )}
            </div>
            {iv.interviewers?.length > 0 && (
              <div className="flex items-center gap-1 mt-2">
                <Users className="h-3 w-3 text-muted-foreground" />
                <div className="flex -space-x-1.5">
                  {iv.interviewers.slice(0, 4).map((i) => (
                    <span key={i.id} className="inline-flex h-6 w-6 rounded-full bg-secondary border-2 border-card items-center justify-center text-[10px] font-semibold" title={i.name}>{initials(i.name)}</span>
                  ))}
                  {iv.interviewers.length > 4 && (
                    <span className="inline-flex h-6 w-6 rounded-full bg-secondary border-2 border-card items-center justify-center text-[10px] font-medium">+{iv.interviewers.length - 4}</span>
                  )}
                </div>
                <span className="text-xs text-muted-foreground ml-1 truncate">{iv.interviewers.map((i) => i.name).join(', ')}</span>
              </div>
            )}
          </button>
          <div className="flex flex-wrap gap-1.5 shrink-0">
            {iv.status === 'scheduled' && (
              <Button size="sm" variant="outline" onClick={() => complete(iv)} data-testid={`interview-complete-${iv.id}`}>
                <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Complete
              </Button>
            )}
            {mySubmitPending && (
              <Button size="sm" onClick={() => setScorecardIv(iv)} data-testid={`interview-scorecard-${iv.id}`}>
                <ClipboardList className="h-3.5 w-3.5 mr-1" /> Scorecard
              </Button>
            )}
            {kit && (
              <Button size="sm" variant="ghost" onClick={() => setKitOpen(kit)} data-testid={`interview-kit-${iv.id}`}>
                <BookOpen className="h-3.5 w-3.5 mr-1" /> Kit
              </Button>
            )}
            {isRecruiter && iv.status === 'scheduled' && (
              <Button size="sm" variant="ghost" onClick={() => cancel(iv)} className="text-destructive hover:text-destructive" data-testid={`interview-cancel-${iv.id}`}>
                <XCircle className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  };

  // -------- Detail sheet --------
  const DetailSheet = () => {
    if (!detailIv) return null;
    const iv = detailIv;
    const st = STATUS_STYLE[iv.status];
    const start = new Date(iv.scheduled_at);
    const end = new Date(start.getTime() + iv.duration_min * 60000);
    const kit = kits.find((k) => k.stage === iv.stage);
    const mySubmitPending = iv.interviewer_ids?.includes(user?.id) && iv.status !== 'cancelled' && iv.status !== 'feedback_submitted';
    const originTz = iv.timezone && iv.timezone !== 'UTC' ? iv.timezone : null;
    const showOrigin = originTz && originTz !== displayTz;
    return (
      <Sheet open={!!detailIv} onOpenChange={(o) => !o && setDetailIv(null)}>
        <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto" data-testid="interview-detail-sheet">
          <SheetHeader className="border-b border-border pb-4">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${TYPE_COLOR[iv.type]}`}>{TYPE_LABEL[iv.type]}</span>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${st.pill}`}>{STATUS_LABEL[iv.status]}</span>
              {iv.calendar_synced && (
                <span className="ml-auto text-xs text-primary inline-flex items-center gap-1" title="Synced to Google Calendar">
                  <CalendarCheck2 className="h-3.5 w-3.5" /> Synced
                </span>
              )}
            </div>
            <SheetTitle className="text-xl">
              <Link to={`/candidates/${iv.candidate_id}`} className="hover:underline flex items-center gap-1">
                {iv.candidate_name} <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            </SheetTitle>
            {(iv.candidate_title || iv.job_title) && (
              <p className="text-sm text-muted-foreground">{iv.candidate_title}{iv.candidate_title && iv.job_title ? ' · ' : ''}{iv.job_title && `for ${iv.job_title}`}</p>
            )}
          </SheetHeader>

          <div className="py-4 space-y-4">
            <div className="grid grid-cols-[120px_1fr] gap-2 text-sm">
              <span className="text-muted-foreground flex items-center gap-1"><Clock className="h-3.5 w-3.5" /> When</span>
              <div>
                <p>{formatInTz(start, displayTz, 'EEE, MMM d, yyyy')}</p>
                <p className="font-medium">{formatInTz(start, displayTz, 'p')} – {formatInTz(end, displayTz, 'p')} <span className="text-xs text-muted-foreground">({tzAbbr(displayTz)})</span></p>
                {showOrigin && (
                  <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
                    <Globe className="h-3 w-3" /> Scheduled in: {formatInTz(start, originTz, 'p')} – {formatInTz(end, originTz, 'p')} ({tzAbbr(originTz)})
                  </p>
                )}
                <p className="text-xs text-muted-foreground">{iv.duration_min} minutes</p>
              </div>

              {iv.location && (<>
                <span className="text-muted-foreground flex items-center gap-1"><MapPin className="h-3.5 w-3.5" /> Location</span>
                <span>{iv.location}</span>
              </>)}

              {iv.video_link && (<>
                <span className="text-muted-foreground flex items-center gap-1"><Video className="h-3.5 w-3.5" /> Video</span>
                <a href={iv.video_link} target="_blank" rel="noreferrer" className="text-primary hover:underline truncate">{iv.video_link}</a>
              </>)}

              <span className="text-muted-foreground flex items-center gap-1"><Users className="h-3.5 w-3.5" /> Interviewers</span>
              <div className="flex flex-wrap gap-1.5">
                {iv.interviewers?.map((i) => (
                  <Badge key={i.id} variant="secondary" className="gap-1 pl-1">
                    <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-semibold text-primary-foreground">{initials(i.name)}</span>
                    {i.name}
                  </Badge>
                ))}
              </div>

              {iv.stage && (<>
                <span className="text-muted-foreground flex items-center gap-1"><User className="h-3.5 w-3.5" /> Stage</span>
                <span>{iv.stage}</span>
              </>)}
            </div>

            {iv.notes && (
              <div>
                <p className="text-xs text-muted-foreground uppercase font-medium mb-1">Notes for interviewers</p>
                <p className="text-sm bg-secondary/40 rounded-lg p-3 whitespace-pre-wrap">{iv.notes}</p>
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-wrap gap-2 pt-2 border-t border-border">
              {iv.video_link && (
                <a href={iv.video_link} target="_blank" rel="noreferrer">
                  <Button size="sm"><Video className="h-3.5 w-3.5 mr-1" /> Join call</Button>
                </a>
              )}
              {iv.status === 'scheduled' && (
                <Button size="sm" variant="outline" onClick={() => complete(iv)}><CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Complete</Button>
              )}
              {mySubmitPending && (
                <Button size="sm" onClick={() => { setScorecardIv(iv); setDetailIv(null); }}><ClipboardList className="h-3.5 w-3.5 mr-1" /> Fill Scorecard</Button>
              )}
              {kit && (
                <Button size="sm" variant="ghost" onClick={() => setKitOpen(kit)}><BookOpen className="h-3.5 w-3.5 mr-1" /> Interview Kit</Button>
              )}
              {isRecruiter && iv.status === 'scheduled' && (
                <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive ml-auto" onClick={() => cancel(iv)}>
                  <XCircle className="h-3.5 w-3.5 mr-1" /> Cancel
                </Button>
              )}
            </div>

            {/* Feedback */}
            {detailScores.length > 0 && (
              <div className="pt-2">
                <p className="text-xs text-muted-foreground uppercase font-medium mb-2">Feedback ({detailScores.length})</p>
                <div className="space-y-2">
                  {detailScores.map((sc) => (
                    <div key={sc.id} className="border border-border rounded-lg p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">{sc.interviewer_name}</span>
                        <Badge variant="secondary" className="capitalize">{sc.recommendation?.replace('_', ' ')}</Badge>
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1.5 text-xs text-muted-foreground">
                        {Object.entries(sc.ratings || {}).map(([k, v]) => (
                          <span key={k}>{k}: <span className="text-foreground font-medium">{v}/5</span></span>
                        ))}
                        <span>Overall: <span className="text-foreground font-medium">{sc.overall}/5</span></span>
                      </div>
                      {sc.notes && <p className="text-sm mt-2 whitespace-pre-wrap">{sc.notes}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>
    );
  };

  // ---------------- Render ----------------
  return (
    <div className="space-y-4" data-testid="interviews-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Interviews</h1>
          <p className="text-sm text-muted-foreground">{['interview_panel', 'interviewer'].includes(user?.role) ? 'Your assigned interviews' : 'All scheduled interviews'}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Timezone switcher */}
          <Select value={displayTz} onValueChange={setDisplayTz}>
            <SelectTrigger className="h-9 w-[180px] bg-card" data-testid="interviews-tz-select">
              <SelectValue><span className="inline-flex items-center gap-1.5 text-xs"><Globe className="h-3.5 w-3.5" /> {tzAbbr(displayTz)}</span></SelectValue>
            </SelectTrigger>
            <SelectContent className="max-h-72">
              {TZ_PRESETS.map((tz) => <SelectItem key={tz.value} value={tz.value}>{tz.label} ({tzAbbr(tz.value)})</SelectItem>)}
            </SelectContent>
          </Select>
          {/* View toggle */}
          <div className="flex rounded-lg border border-border overflow-hidden bg-card">
            {['day', 'week', 'list'].map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`px-3 py-1.5 text-sm capitalize transition-colors ${view === v ? 'bg-primary text-primary-foreground' : 'hover:bg-secondary'}`}
                data-testid={`interviews-view-toggle-${v}`}
              >{v}</button>
            ))}
          </div>
          {isRecruiter && (
            <Button onClick={() => setScheduleOpen(true)} data-testid="schedule-interview-button">
              <CalendarPlus className="h-4 w-4 mr-1" /> Schedule
            </Button>
          )}
        </div>
      </div>

      {/* Google Calendar banner */}
      {calStatus && (
        <Card className="shadow-none" data-testid="google-calendar-card">
          <CardContent className="py-3 flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2 text-sm">
              <CalendarCheck2 className={`h-4 w-4 ${calStatus.connected ? 'text-primary' : 'text-muted-foreground'}`} />
              {calStatus.connected ? (
                <span data-testid="google-calendar-connected-label">
                  Google Calendar connected as <span className="font-medium">{calStatus.email}</span>
                  {isRecruiter ? ' — interviews you schedule sync automatically, and your other calendar events show as grey blocks on the grid.' : ' — recruiters can see your real availability, and your other calendar events show as grey blocks on the grid.'}
                </span>
              ) : (
                <span className="text-muted-foreground">
                  {isRecruiter
                    ? 'Connect Google Calendar to auto-create events with Meet links when you schedule interviews.'
                    : 'Connect your Google Calendar so recruiters can see your real availability when scheduling interviews.'}
                </span>
              )}
            </div>
            {calStatus.connected ? (
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={syncInterviewsFromCalendar}
                  disabled={syncBusy}
                  data-testid="google-calendar-sync-button"
                  title="Import interviews you scheduled directly in Google Calendar (last 14 days + next 30)"
                >
                  {syncBusy
                    ? <><Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> Syncing…</>
                    : <><RefreshCw className="h-3.5 w-3.5 mr-1" /> Sync interviews</>}
                </Button>
                <Button size="sm" variant="outline" onClick={disconnectCalendar} disabled={calBusy} data-testid="google-calendar-disconnect-button">
                  <Link2Off className="h-3.5 w-3.5 mr-1" /> Disconnect
                </Button>
              </div>
            ) : (
              <Button size="sm" onClick={connectCalendar} disabled={calBusy} data-testid="google-calendar-connect-button">
                <CalendarCheck2 className="h-3.5 w-3.5 mr-1" /> Connect Google Calendar
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {/* Sync-from-Google-Calendar result dialog */}
      <Dialog open={!!syncResult} onOpenChange={(o) => { if (!o) setSyncResult(null); }}>
        <DialogContent className="max-w-lg" data-testid="calendar-sync-result-dialog">
          <DialogHeader>
            <DialogTitle>Google Calendar sync</DialogTitle>
          </DialogHeader>
          {syncResult && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-md border p-2">
                  <div className="text-xs text-muted-foreground">Imported</div>
                  <div className="text-lg font-semibold" data-testid="sync-count-imported">{(syncResult.imported || []).length}</div>
                </div>
                <div className="rounded-md border p-2">
                  <div className="text-xs text-muted-foreground">Events scanned</div>
                  <div className="text-lg font-semibold" data-testid="sync-count-scanned">{syncResult.scanned ?? 0}</div>
                </div>
                <div className="rounded-md border p-2">
                  <div className="text-xs text-muted-foreground">Already imported</div>
                  <div className="text-lg font-semibold">{syncResult.skipped_duplicate ?? 0}</div>
                </div>
                <div className="rounded-md border p-2">
                  <div className="text-xs text-muted-foreground">No candidate match</div>
                  <div className="text-lg font-semibold">{syncResult.skipped_no_candidate_match ?? 0}</div>
                </div>
              </div>
              {(syncResult.imported || []).length > 0 ? (
                <div>
                  <div className="mb-1 text-xs font-medium text-muted-foreground">New interviews created</div>
                  <div className="max-h-56 overflow-y-auto divide-y rounded-md border">
                    {syncResult.imported.map((iv) => (
                      <Link
                        key={iv.id}
                        to={`/candidates/${iv.candidate_id}`}
                        className="flex items-center justify-between gap-2 px-3 py-2 hover:bg-secondary"
                      >
                        <div className="min-w-0">
                          <div className="truncate font-medium">{iv.candidate_name || iv.summary}</div>
                          <div className="truncate text-xs text-muted-foreground">{iv.summary}</div>
                        </div>
                        <Badge variant="outline" className="shrink-0">{iv.type?.replace('_', ' ')}</Badge>
                      </Link>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-muted-foreground">
                  Nothing new to import. Interviews are only imported when at least one attendee&apos;s email matches a candidate in your ATS.
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Window scanned: last 14 days + next 30 days. Re-run anytime — already-imported events are skipped automatically.
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Filters + date navigation */}
      <div className="flex flex-wrap items-center gap-2">
        {user?.role !== 'interviewer' && (
          <Select value={filters.interviewer_id} onValueChange={(v) => setFilters((f) => ({ ...f, interviewer_id: v }))}>
            <SelectTrigger className="h-9 w-[170px] bg-card" data-testid="interviews-filter-interviewer"><SelectValue placeholder="All interviewers" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All interviewers</SelectItem>
              {users.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        <Select value={filters.job_id} onValueChange={(v) => setFilters((f) => ({ ...f, job_id: v }))}>
          <SelectTrigger className="h-9 w-[170px] bg-card" data-testid="interviews-filter-job"><SelectValue placeholder="All jobs" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All jobs</SelectItem>
            {jobs.map((j) => <SelectItem key={j.id} value={j.id}>{j.title}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filters.type} onValueChange={(v) => setFilters((f) => ({ ...f, type: v }))}>
          <SelectTrigger className="h-9 w-[150px] bg-card" data-testid="interviews-filter-type"><SelectValue placeholder="All types" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {Object.entries(TYPE_LABEL).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filters.status} onValueChange={(v) => setFilters((f) => ({ ...f, status: v }))}>
          <SelectTrigger className="h-9 w-[160px] bg-card" data-testid="interviews-filter-status"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All (hide cancelled)</SelectItem>
            <SelectItem value="scheduled">Scheduled</SelectItem>
            <SelectItem value="feedback_pending">Feedback Pending</SelectItem>
            <SelectItem value="feedback_submitted">Feedback In</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
          </SelectContent>
        </Select>

        {view !== 'list' && (
          <div className="flex items-center gap-1 ml-auto">
            <Button variant="outline" size="icon" className="h-9 w-9" onClick={goPrev} aria-label={`Previous ${view}`} data-testid="interviews-prev-nav">
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="outline" className="h-9" onClick={goToday}>Today</Button>
            <Button variant="outline" size="icon" className="h-9 w-9" onClick={goNext} aria-label={`Next ${view}`} data-testid="interviews-next-nav">
              <ChevronRight className="h-4 w-4" />
            </Button>
            <span className="text-sm font-medium ml-2">{rangeLabel}</span>
          </div>
        )}
      </div>

      {/* Body: sidebar + main */}
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
        <div className="hidden lg:block">
          <UpcomingSidebar />
        </div>
        <div>
          {view === 'week' && <WeekGrid />}
          {view === 'day' && <DayGrid />}
          {view === 'list' && <ListView />}
        </div>
      </div>

      <ScheduleInterviewDialog open={scheduleOpen} onOpenChange={setScheduleOpen} onScheduled={load} />
      <ScorecardDialog open={!!scorecardIv} onOpenChange={(o) => !o && setScorecardIv(null)} interview={scorecardIv} onSubmitted={load} />
      <DetailSheet />

      {/* Interview kit dialog */}
      <Dialog open={!!kitOpen} onOpenChange={(o) => !o && setKitOpen(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>{kitOpen?.title}</DialogTitle></DialogHeader>
          {kitOpen?.guidelines && <p className="text-sm text-muted-foreground">{kitOpen.guidelines}</p>}
          <ol className="space-y-2 list-decimal list-inside">
            {(kitOpen?.questions || []).map((q, i) => <li key={i} className="text-sm">{q}</li>)}
          </ol>
        </DialogContent>
      </Dialog>
    </div>
  );
}
