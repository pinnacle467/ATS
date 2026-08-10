import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { CalendarClock, CheckCircle2, Clock, Globe, Loader2, MapPin, Video, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { api, errMsg } from '@/lib/api';
import { formatInTz, getBrowserTz, tzAbbr, TZ_PRESETS } from '@/lib/timezones';

/**
 * PUBLIC candidate self-scheduling page (`/schedule/interview/:token`).
 * No login required. Left: company + interview info. Right: date + time slots
 * with a timezone selector. On confirm → book → confirmation view.
 */
export default function SchedulePage() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [slots, setSlots] = useState([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [calError, setCalError] = useState(false);
  const [tz, setTz] = useState(getBrowserTz());
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [booking, setBooking] = useState(false);
  const [mode, setMode] = useState('book'); // book | reschedule

  const loadInfo = () => {
    api.get(`/schedule/${token}`)
      .then((r) => {
        if (r.data.error) { setError(r.data.error); setInfo(r.data); }
        else setInfo(r.data);
      })
      .catch((e) => setError(errMsg(e, 'This scheduling link is invalid or has expired')));
  };
  useEffect(() => { loadInfo(); /* eslint-disable-next-line */ }, [token]);

  const loadSlots = () => {
    setSlotsLoading(true);
    api.get(`/schedule/${token}/slots`, { params: { tz } })
      .then((r) => { setSlots(r.data.slots || []); setCalError(!!r.data.calendar_error); })
      .catch((e) => { setSlots([]); toast.error(errMsg(e, 'Could not load available times')); })
      .finally(() => setSlotsLoading(false));
  };
  useEffect(() => {
    if (info && !info.error && (mode === 'reschedule' || info.status !== 'scheduled')) loadSlots();
    // eslint-disable-next-line
  }, [info, mode]);

  // Group slots by local date in the selected timezone.
  const grouped = useMemo(() => {
    const g = {};
    for (const s of slots) {
      const d = new Date(s.start_utc);
      const key = formatInTz(d, tz, 'yyyy-MM-dd');
      (g[key] = g[key] || []).push(s);
    }
    return g;
  }, [slots, tz]);

  const dateKeys = useMemo(() => Object.keys(grouped).sort(), [grouped]);
  useEffect(() => {
    if (dateKeys.length && (!selectedDate || !grouped[selectedDate])) setSelectedDate(dateKeys[0]);
    // eslint-disable-next-line
  }, [dateKeys]);

  const doBook = async () => {
    if (!selectedSlot) return;
    setBooking(true);
    try {
      const endpoint = mode === 'reschedule' ? 'reschedule' : 'book';
      const r = await api.post(`/schedule/${token}/${endpoint}`, { slot_start_utc: selectedSlot.start_utc, timezone: tz });
      setInfo(r.data);
      setMode('book');
      setSelectedSlot(null);
      toast.success(mode === 'reschedule' ? 'Interview rescheduled' : 'Interview confirmed!');
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail === 'slot_taken' || e?.response?.status === 409) {
        toast.error('Sorry, this time slot was just booked. Please pick another.');
        setSelectedSlot(null);
        loadSlots();
      } else if (detail === 'calendar_error') {
        toast.error('Unable to confirm right now — please try again.');
      } else {
        toast.error(errMsg(e, 'Could not book this slot'));
      }
    } finally {
      setBooking(false);
    }
  };

  const doCancel = async () => {
    if (!window.confirm('Cancel this interview? This will release the time slot.')) return;
    try {
      const r = await api.post(`/schedule/${token}/cancel`, { reason: 'Cancelled by candidate' });
      setInfo(r.data);
      toast.success('Interview cancelled');
    } catch (e) { toast.error(errMsg(e, 'Could not cancel')); }
  };

  // ---- error / invalid link
  if (error) {
    return (
      <Shell logo={info?.logo_url} company={info?.company_name}>
        <div className="text-center py-10">
          <XCircle className="h-12 w-12 text-red-400 mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-slate-800">
            {error === 'link_expired' ? 'This scheduling link has expired' : error === 'link_disabled' ? 'This scheduling link is no longer active' : 'Link not available'}
          </h2>
          <p className="text-sm text-slate-500 mt-1">Please contact the recruiter for a new link.</p>
        </div>
      </Shell>
    );
  }
  if (!info) {
    return <div className="min-h-screen flex items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;
  }

  const booked = info.status === 'scheduled';
  const cancelled = info.status === 'cancelled';

  return (
    <Shell logo={info.logo_url} company={info.company_name}>
      <div className="grid md:grid-cols-[340px_1fr] gap-0 md:gap-8">
        {/* LEFT — interview info */}
        <div className="md:border-r md:pr-8 border-slate-100">
          <div className="text-xs font-medium uppercase tracking-wide text-emerald-600">{info.company_name}</div>
          <h1 className="text-2xl font-bold text-slate-900 mt-1 leading-tight">{info.title}</h1>
          <p className="text-slate-500 mt-1">{info.job_title}{info.stage ? ` · ${info.stage}` : ''}</p>
          <div className="mt-5 space-y-3 text-sm text-slate-600">
            <div className="flex items-center gap-2"><Clock className="h-4 w-4 text-slate-400" /> {info.duration_min} minutes</div>
            <div className="flex items-center gap-2"><Video className="h-4 w-4 text-slate-400" /> Google Meet (link shared on confirmation)</div>
            {info.candidate_name && <div className="flex items-center gap-2"><MapPin className="h-4 w-4 text-slate-400" /> {info.candidate_name}</div>}
          </div>
          {info.instructions && (
            <div className="mt-5 text-sm bg-slate-50 rounded-lg p-3 text-slate-600 whitespace-pre-wrap">{info.instructions}</div>
          )}
        </div>

        {/* RIGHT — booked confirmation OR slot picker */}
        <div className="pt-6 md:pt-0">
          {cancelled ? (
            <div className="text-center py-10">
              <XCircle className="h-10 w-10 text-slate-300 mx-auto mb-3" />
              <h2 className="text-lg font-semibold text-slate-800">This interview was cancelled</h2>
            </div>
          ) : booked && mode !== 'reschedule' ? (
            <Confirmation info={info} tz={tz} onReschedule={() => { setMode('reschedule'); }} onCancel={doCancel} />
          ) : (
            <SlotPicker
              info={info}
              tz={tz} setTz={setTz}
              grouped={grouped} dateKeys={dateKeys}
              selectedDate={selectedDate} setSelectedDate={setSelectedDate}
              selectedSlot={selectedSlot} setSelectedSlot={setSelectedSlot}
              loading={slotsLoading} calError={calError}
              booking={booking} onConfirm={doBook}
              mode={mode}
              onCancelReschedule={() => { setMode('book'); setSelectedSlot(null); }}
            />
          )}
        </div>
      </div>
    </Shell>
  );
}

function Shell({ children, logo, company }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-emerald-50/40 to-white flex items-start justify-center py-8 px-4">
      <div className="w-full max-w-4xl bg-white rounded-2xl shadow-sm border border-slate-100 p-6 md:p-8">
        <div className="flex items-center gap-2 mb-6">
          {logo ? <img src={logo} alt={company || 'Company'} className="h-8 w-auto" onError={(e) => { e.currentTarget.style.display = 'none'; }} /> : null}
          <span className="font-semibold text-slate-700">{company || 'Interview Scheduling'}</span>
        </div>
        {children}
      </div>
    </div>
  );
}

function Confirmation({ info, tz, onReschedule, onCancel }) {
  const when = info.scheduled_at ? formatInTz(new Date(info.scheduled_at), tz, "EEEE, MMMM d, yyyy · p") : 'TBD';
  const gcalUrl = buildGoogleCalUrl(info);
  return (
    <div>
      <div className="flex items-center gap-2 text-emerald-600 mb-3">
        <CheckCircle2 className="h-6 w-6" /> <span className="font-semibold text-lg">Interview Confirmed</span>
      </div>
      <div className="rounded-xl border border-slate-100 p-4 space-y-3">
        <div className="flex items-start gap-2"><CalendarClock className="h-4 w-4 text-slate-400 mt-0.5" />
          <div><div className="font-medium text-slate-800">{when}</div><div className="text-xs text-slate-500">{tzAbbr(tz)} · {tz}</div></div>
        </div>
        {info.interviewer_names?.length > 0 && (
          <div className="text-sm text-slate-600">Interviewers: {info.interviewer_names.join(', ')}</div>
        )}
        {info.video_link ? (
          <a href={info.video_link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-emerald-700 text-sm font-medium hover:underline">
            <Video className="h-4 w-4" /> Join Google Meet
          </a>
        ) : (
          <div className="text-xs text-slate-400">A Google Meet link will be shared before the interview.</div>
        )}
      </div>
      <div className="flex flex-wrap gap-2 mt-5">
        {gcalUrl && <a href={gcalUrl} target="_blank" rel="noreferrer"><Button variant="outline" size="sm">Add to Google Calendar</Button></a>}
        <Button variant="outline" size="sm" onClick={onReschedule} data-testid="schedule-reschedule-button">Reschedule</Button>
        <Button variant="ghost" size="sm" className="text-red-600 hover:text-red-700" onClick={onCancel} data-testid="schedule-cancel-button">Cancel Interview</Button>
      </div>
    </div>
  );
}

function SlotPicker({ info, tz, setTz, grouped, dateKeys, selectedDate, setSelectedDate, selectedSlot, setSelectedSlot, loading, calError, booking, onConfirm, mode, onCancelReschedule }) {
  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-4">
        <h2 className="font-semibold text-slate-800">{mode === 'reschedule' ? 'Pick a new time' : 'Select a time'}</h2>
        <div className="flex items-center gap-1.5">
          <Globe className="h-4 w-4 text-slate-400" />
          <Select value={tz} onValueChange={setTz}>
            <SelectTrigger className="w-[190px] h-8 text-xs" data-testid="schedule-tz-select"><SelectValue /></SelectTrigger>
            <SelectContent className="max-h-72">
              {TZ_PRESETS.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading ? (
        <div className="py-12 text-center text-slate-400"><Loader2 className="h-5 w-5 animate-spin mx-auto mb-2" />Checking interviewer availability…</div>
      ) : calError ? (
        <div className="py-10 text-center text-sm text-amber-700 bg-amber-50 rounded-lg px-4">Unable to check calendar availability right now. Please try again shortly or contact the recruiter.</div>
      ) : dateKeys.length === 0 ? (
        <div className="py-10 text-center text-sm text-slate-500">No common availability found for the selected window. Please contact the recruiter for other options.</div>
      ) : (
        <>
          {/* date chips */}
          <div className="flex gap-2 overflow-x-auto pb-2 mb-3">
            {dateKeys.map((k) => {
              const d = new Date(grouped[k][0].start_utc);
              const active = k === selectedDate;
              return (
                <button
                  key={k}
                  onClick={() => { setSelectedDate(k); setSelectedSlot(null); }}
                  className={`shrink-0 px-3 py-2 rounded-lg border text-sm ${active ? 'border-emerald-500 bg-emerald-50 text-emerald-700 font-medium' : 'border-slate-200 text-slate-600 hover:border-slate-300'}`}
                  data-testid="schedule-date-chip"
                >
                  <div className="text-[10px] uppercase tracking-wide">{formatInTz(d, tz, 'EEE')}</div>
                  <div>{formatInTz(d, tz, 'MMM d')}</div>
                </button>
              );
            })}
          </div>
          {/* times */}
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 max-h-72 overflow-y-auto">
            {(grouped[selectedDate] || []).map((s) => {
              const active = selectedSlot?.start_utc === s.start_utc;
              return (
                <button
                  key={s.start_utc}
                  onClick={() => setSelectedSlot(s)}
                  className={`px-2 py-2 rounded-lg border text-sm ${active ? 'border-emerald-500 bg-emerald-600 text-white' : 'border-slate-200 text-slate-700 hover:border-emerald-400'}`}
                  data-testid="schedule-slot-button"
                >
                  {formatInTz(new Date(s.start_utc), tz, 'p')}
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-2 mt-5">
            <Button onClick={onConfirm} disabled={!selectedSlot || booking} className="bg-emerald-600 hover:bg-emerald-700" data-testid="schedule-confirm-button">
              {booking ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : null}
              {mode === 'reschedule' ? 'Confirm New Time' : 'Confirm Interview'}
            </Button>
            {mode === 'reschedule' && <Button variant="ghost" size="sm" onClick={onCancelReschedule}>Back</Button>}
            {selectedSlot && <span className="text-xs text-slate-500">{formatInTz(new Date(selectedSlot.start_utc), tz, "EEE, MMM d · p")} ({tzAbbr(tz)})</span>}
          </div>
        </>
      )}
    </div>
  );
}

function buildGoogleCalUrl(info) {
  if (!info.scheduled_at || !info.duration_min) return null;
  const start = new Date(info.scheduled_at);
  const end = new Date(start.getTime() + info.duration_min * 60000);
  const fmt = (d) => d.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: info.title || 'Interview',
    dates: `${fmt(start)}/${fmt(end)}`,
    details: `${info.job_title || ''}${info.video_link ? `\nGoogle Meet: ${info.video_link}` : ''}`,
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}
