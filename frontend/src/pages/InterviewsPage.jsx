import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { addDays, format, isSameDay, startOfWeek } from 'date-fns';
import { BookOpen, CalendarCheck2, CalendarPlus, CheckCircle2, ChevronLeft, ChevronRight, ClipboardList, Link2Off, MapPin, Video, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import ScheduleInterviewDialog from '@/components/ScheduleInterviewDialog';
import ScorecardDialog from '@/components/ScorecardDialog';
import { useAuth } from '@/context/AuthContext';
import { api, errMsg } from '@/lib/api';

const STATUS_STYLE = {
  scheduled: 'bg-sky-100 text-sky-800',
  feedback_pending: 'bg-amber-100 text-amber-800',
  feedback_submitted: 'bg-green-100 text-green-800',
  cancelled: 'bg-secondary text-muted-foreground',
};
const STATUS_LABEL = {
  scheduled: 'Scheduled',
  feedback_pending: 'Feedback Pending',
  feedback_submitted: 'Feedback Submitted',
  cancelled: 'Cancelled',
};
const TYPE_LABEL = { phone_screen: 'Phone Screen', technical: 'Technical', panel: 'Panel', onsite: 'Onsite' };

export default function InterviewsPage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [interviews, setInterviews] = useState([]);
  const [users, setUsers] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [kits, setKits] = useState([]);
  const [filters, setFilters] = useState({ interviewer_id: 'all', job_id: 'all' });
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }));
  const [view, setView] = useState('week');
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scorecardIv, setScorecardIv] = useState(null);
  const [viewScores, setViewScores] = useState(null);
  const [scores, setScores] = useState([]);
  const [kitOpen, setKitOpen] = useState(null);
  const [calStatus, setCalStatus] = useState(null);
  const [calBusy, setCalBusy] = useState(false);

  const isRecruiter = user?.role === 'admin' || user?.role === 'recruiter';

  const loadCalStatus = useCallback(() => {
    if (!isRecruiter) return;
    api.get('/calendar/status').then((r) => setCalStatus(r.data)).catch(() => {});
  }, [isRecruiter]);

  useEffect(() => {
    loadCalStatus();
  }, [loadCalStatus]);

  useEffect(() => {
    const cal = searchParams.get('calendar');
    if (!cal) return;
    if (cal === 'connected') {
      toast.success('Google Calendar connected — new interviews will sync automatically');
      loadCalStatus();
    } else if (cal === 'error') {
      toast.error('Could not connect Google Calendar. Please try again.');
    }
    searchParams.delete('calendar');
    setSearchParams(searchParams, { replace: true });
  }, [searchParams, setSearchParams, loadCalStatus]);

  const connectCalendar = async () => {
    setCalBusy(true);
    try {
      const r = await api.get('/oauth/google/login');
      window.location.href = r.data.authorization_url;
    } catch (e) {
      toast.error(errMsg(e, 'Could not start Google connection'));
      setCalBusy(false);
    }
  };

  const disconnectCalendar = async () => {
    if (!window.confirm('Disconnect Google Calendar? Future interviews will no longer sync automatically.')) return;
    setCalBusy(true);
    try {
      await api.post('/calendar/disconnect');
      toast.success('Google Calendar disconnected');
      loadCalStatus();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setCalBusy(false);
    }
  };

  const load = useCallback(() => {
    const params = {};
    if (filters.interviewer_id !== 'all') params.interviewer_id = filters.interviewer_id;
    if (filters.job_id !== 'all') params.job_id = filters.job_id;
    api.get('/interviews', { params }).then((r) => setInterviews(r.data)).catch((e) => toast.error(errMsg(e)));
  }, [filters]);

  useEffect(() => {
    load();
    Promise.all([api.get('/users'), api.get('/jobs'), api.get('/interview-kits')])
      .then(([u, j, k]) => {
        setUsers(u.data);
        setJobs(j.data);
        setKits(k.data);
      })
      .catch(() => {});
  }, [load]);

  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)), [weekStart]);

  const complete = async (iv) => {
    try {
      await api.post(`/interviews/${iv.id}/complete`);
      toast.success('Marked complete — feedback now pending');
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const cancel = async (iv) => {
    if (!window.confirm(`Cancel interview with ${iv.candidate_name}?`)) return;
    try {
      await api.put(`/interviews/${iv.id}`, { status: 'cancelled' });
      toast.success('Interview cancelled');
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const openScores = async (iv) => {
    try {
      const r = await api.get(`/interviews/${iv.id}/scorecards`);
      setScores(r.data);
      setViewScores(iv);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const IvCard = ({ iv, compact }) => {
    const mySubmitPending = iv.interviewer_ids?.includes(user?.id) && iv.status !== 'cancelled' && iv.status !== 'feedback_submitted';
    const kit = kits.find((k) => k.stage === iv.stage);
    return (
      <div className="bg-card border border-border rounded-lg p-2.5 space-y-1.5 hover:shadow-sm transition-shadow" data-testid={`interview-card-${iv.id}`}>
        <div className="flex items-start justify-between gap-1">
          <Link to={`/candidates/${iv.candidate_id}`} className="text-sm font-medium hover:underline leading-tight">{iv.candidate_name}</Link>
          <div className="flex items-center gap-1 shrink-0">
            {iv.calendar_synced && (
              <span title="Synced to Google Calendar" data-testid={`interview-calendar-synced-${iv.id}`}>
                <CalendarCheck2 className="h-3 w-3 text-primary" />
              </span>
            )}
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium whitespace-nowrap ${STATUS_STYLE[iv.status]}`}>{STATUS_LABEL[iv.status]}</span>
          </div>
        </div>
        <div className="text-xs text-muted-foreground">
          {format(new Date(iv.scheduled_at), 'p')} · {iv.duration_min}m · {TYPE_LABEL[iv.type] || iv.type}
        </div>
        {!compact && (
          <>
            <div className="text-xs text-muted-foreground">{iv.interviewer_names?.join(', ')}</div>
            {iv.video_link && (
              <a href={iv.video_link} target="_blank" rel="noreferrer" className="text-xs text-primary flex items-center gap-1 hover:underline"><Video className="h-3 w-3" /> Join video</a>
            )}
            {iv.location && <div className="text-xs text-muted-foreground flex items-center gap-1"><MapPin className="h-3 w-3" /> {iv.location}</div>}
          </>
        )}
        <div className="flex flex-wrap gap-1 pt-1">
          {iv.status === 'scheduled' && (
            <Button size="sm" variant="outline" className="h-6 text-[11px] px-2" onClick={() => complete(iv)} data-testid={`interview-complete-${iv.id}`}>
              <CheckCircle2 className="h-3 w-3 mr-1" /> Complete
            </Button>
          )}
          {mySubmitPending && (
            <Button size="sm" className="h-6 text-[11px] px-2" onClick={() => setScorecardIv(iv)} data-testid={`interview-scorecard-${iv.id}`}>
              <ClipboardList className="h-3 w-3 mr-1" /> Scorecard
            </Button>
          )}
          {iv.scorecards_submitted > 0 && (
            <Button size="sm" variant="ghost" className="h-6 text-[11px] px-2" onClick={() => openScores(iv)} data-testid={`interview-view-scores-${iv.id}`}>
              View feedback ({iv.scorecards_submitted})
            </Button>
          )}
          {kit && (
            <Button size="sm" variant="ghost" className="h-6 text-[11px] px-2" onClick={() => setKitOpen(kit)} data-testid={`interview-kit-${iv.id}`}>
              <BookOpen className="h-3 w-3 mr-1" /> Kit
            </Button>
          )}
          {isRecruiter && iv.status === 'scheduled' && (
            <Button size="sm" variant="ghost" className="h-6 text-[11px] px-2 text-destructive hover:text-destructive" onClick={() => cancel(iv)} data-testid={`interview-cancel-${iv.id}`}>
              <XCircle className="h-3 w-3 mr-1" /> Cancel
            </Button>
          )}
        </div>
      </div>
    );
  };

  const upcoming = interviews.filter((iv) => iv.status !== 'cancelled');

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Interviews</h1>
          <p className="text-sm text-muted-foreground">{user?.role === 'interviewer' ? 'Your assigned interviews' : 'All scheduled interviews'}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex rounded-lg border border-border overflow-hidden">
            <button onClick={() => setView('week')} data-testid="interviews-view-toggle-week" className={`px-3 py-1.5 text-sm transition-colors ${view === 'week' ? 'bg-primary text-primary-foreground' : 'bg-card hover:bg-secondary'}`}>Week</button>
            <button onClick={() => setView('list')} data-testid="interviews-view-toggle-day" className={`px-3 py-1.5 text-sm transition-colors ${view === 'list' ? 'bg-primary text-primary-foreground' : 'bg-card hover:bg-secondary'}`}>List</button>
          </div>
          {isRecruiter && (
            <Button onClick={() => setScheduleOpen(true)} data-testid="schedule-interview-button">
              <CalendarPlus className="h-4 w-4 mr-1" /> Schedule Interview
            </Button>
          )}
        </div>
      </div>

      {isRecruiter && calStatus && (
        <Card className="shadow-none" data-testid="google-calendar-card">
          <CardContent className="py-3 flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2 text-sm">
              <CalendarCheck2 className={`h-4 w-4 ${calStatus.connected ? 'text-primary' : 'text-muted-foreground'}`} />
              {calStatus.connected ? (
                <span data-testid="google-calendar-connected-label">Google Calendar connected as <span className="font-medium">{calStatus.email}</span> — interviews you schedule sync automatically.</span>
              ) : (
                <span className="text-muted-foreground">Connect Google Calendar to auto-create events with Meet links when you schedule interviews.</span>
              )}
            </div>
            {calStatus.connected ? (
              <Button size="sm" variant="outline" onClick={disconnectCalendar} disabled={calBusy} data-testid="google-calendar-disconnect-button">
                <Link2Off className="h-3.5 w-3.5 mr-1" /> Disconnect
              </Button>
            ) : (
              <Button size="sm" onClick={connectCalendar} disabled={calBusy} data-testid="google-calendar-connect-button">
                <CalendarCheck2 className="h-3.5 w-3.5 mr-1" /> Connect Google Calendar
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        {user?.role !== 'interviewer' && (
          <Select value={filters.interviewer_id} onValueChange={(v) => setFilters((f) => ({ ...f, interviewer_id: v }))}>
            <SelectTrigger className="w-[180px] h-9 bg-card" data-testid="interviews-filter-interviewer"><SelectValue placeholder="All interviewers" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All interviewers</SelectItem>
              {users.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        <Select value={filters.job_id} onValueChange={(v) => setFilters((f) => ({ ...f, job_id: v }))}>
          <SelectTrigger className="w-[180px] h-9 bg-card" data-testid="interviews-filter-job"><SelectValue placeholder="All jobs" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All jobs</SelectItem>
            {jobs.map((j) => <SelectItem key={j.id} value={j.id}>{j.title}</SelectItem>)}
          </SelectContent>
        </Select>
        {view === 'week' && (
          <div className="flex items-center gap-1 ml-auto">
            <Button variant="outline" size="icon" className="h-9 w-9" onClick={() => setWeekStart((w) => addDays(w, -7))} aria-label="Previous week" data-testid="interviews-prev-week">
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="outline" className="h-9" onClick={() => setWeekStart(startOfWeek(new Date(), { weekStartsOn: 1 }))}>Today</Button>
            <Button variant="outline" size="icon" className="h-9 w-9" onClick={() => setWeekStart((w) => addDays(w, 7))} aria-label="Next week" data-testid="interviews-next-week">
              <ChevronRight className="h-4 w-4" />
            </Button>
            <span className="text-sm font-medium ml-2 font-mono">{format(weekStart, 'MMM d')} – {format(addDays(weekStart, 6), 'MMM d, yyyy')}</span>
          </div>
        )}
      </div>

      {/* Calendar week view */}
      {view === 'week' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-7 gap-3" data-testid="interviews-calendar">
          {days.map((d) => {
            const dayIvs = upcoming.filter((iv) => isSameDay(new Date(iv.scheduled_at), d));
            const isToday = isSameDay(d, new Date());
            return (
              <div key={d.toISOString()} className={`rounded-xl border p-2 min-h-[140px] ${isToday ? 'border-primary bg-accent/50' : 'border-border bg-card'}`}>
                <div className="text-xs font-semibold mb-2 flex items-center justify-between">
                  <span className={isToday ? 'text-primary' : ''}>{format(d, 'EEE d')}</span>
                  {dayIvs.length > 0 && <Badge variant="secondary" className="text-[10px] tabular-nums">{dayIvs.length}</Badge>}
                </div>
                <div className="space-y-2">
                  {dayIvs.map((iv) => <IvCard key={iv.id} iv={iv} compact />)}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="space-y-2" data-testid="interviews-list">
          {upcoming.length === 0 && (
            <Card className="shadow-none"><CardContent className="py-10 text-center text-muted-foreground text-sm">No interviews found.</CardContent></Card>
          )}
          {upcoming.map((iv) => (
            <div key={iv.id} className="flex items-start gap-4 bg-card border border-border rounded-xl p-4">
              <div className="text-center shrink-0 w-14">
                <div className="font-display text-lg font-semibold">{format(new Date(iv.scheduled_at), 'd')}</div>
                <div className="text-xs text-muted-foreground uppercase">{format(new Date(iv.scheduled_at), 'MMM')}</div>
              </div>
              <div className="flex-1"><IvCard iv={iv} /></div>
            </div>
          ))}
        </div>
      )}

      <ScheduleInterviewDialog open={scheduleOpen} onOpenChange={setScheduleOpen} onScheduled={load} />
      <ScorecardDialog open={!!scorecardIv} onOpenChange={(o) => !o && setScorecardIv(null)} interview={scorecardIv} onSubmitted={load} />

      {/* View scorecards dialog */}
      <Dialog open={!!viewScores} onOpenChange={(o) => !o && setViewScores(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Feedback — {viewScores?.candidate_name}</DialogTitle></DialogHeader>
          <div className="space-y-3 max-h-[60vh] overflow-y-auto">
            {scores.map((sc) => (
              <div key={sc.id} className="border border-border rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{sc.interviewer_name}</span>
                  <Badge variant="secondary" className="capitalize">{sc.recommendation?.replace('_', ' ')}</Badge>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5">
                  {Object.entries(sc.ratings || {}).map(([k, v]) => (
                    <span key={k} className="text-xs text-muted-foreground">{k}: <span className="font-medium text-foreground">{v}/5</span></span>
                  ))}
                  <span className="text-xs text-muted-foreground">Overall: <span className="font-medium text-foreground">{sc.overall}/5</span></span>
                </div>
                {sc.notes && <p className="text-sm mt-2">{sc.notes}</p>}
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

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
