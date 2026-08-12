import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import {
  Ban, Bell, CalendarClock, CalendarX2, CheckCircle2, Copy, ExternalLink,
  FileClock, History, Link2, Loader2, MailPlus, RefreshCw, RotateCcw, Search, Send,
  Trash2, XCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { api, errMsg } from '@/lib/api';
import { formatInTz, getBrowserTz } from '@/lib/timezones';

const STATUS_META = {
  draft: { label: 'Draft', className: 'bg-secondary text-muted-foreground' },
  awaiting_candidate: { label: 'Awaiting Candidate', className: 'bg-amber-100 text-amber-800' },
  reschedule_requested: { label: 'Reschedule Requested', className: 'bg-amber-100 text-amber-800' },
  booking: { label: 'Booking…', className: 'bg-sky-100 text-sky-800' },
  scheduled: { label: 'Scheduled', className: 'bg-emerald-100 text-emerald-800' },
  cancelled: { label: 'Cancelled', className: 'bg-rose-100 text-rose-800' },
  link_disabled: { label: 'Link Disabled', className: 'bg-secondary text-muted-foreground' },
  expired: { label: 'Expired', className: 'bg-orange-100 text-orange-800' },
};

const TYPE_LABEL = {
  phone_screen: 'Phone Screen', technical: 'Technical', panel: 'Panel', onsite: 'Onsite',
};

const FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'awaiting_candidate', label: 'Awaiting Candidate' },
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'draft', label: 'Draft' },
  { value: 'expired', label: 'Expired' },
  { value: 'cancelled', label: 'Cancelled' },
];

const AUDIT_META = {
  'scheduling.request_created': { icon: CalendarClock, label: 'Request created' },
  'scheduling.link_generated': { icon: Link2, label: 'Link generated' },
  'scheduling.link_sent': { icon: Send, label: 'Link sent to candidate' },
  'scheduling.candidate_opened': { icon: ExternalLink, label: 'Candidate opened the link' },
  'scheduling.candidate_booked': { icon: CheckCircle2, label: 'Candidate booked a slot' },
  'scheduling.rescheduled': { icon: RotateCcw, label: 'Rescheduled' },
  'scheduling.cancelled': { icon: XCircle, label: 'Cancelled' },
  'scheduling.calendar_event_created': { icon: CalendarClock, label: 'Calendar event created' },
  'scheduling.calendar_event_updated': { icon: CalendarClock, label: 'Calendar event updated' },
  'scheduling.link_disabled': { icon: Ban, label: 'Link disabled' },
  'scheduling.link_regenerated': { icon: RefreshCw, label: 'Link regenerated' },
  'scheduling.reminder_sent': { icon: Bell, label: 'Reminder sent' },
};

const timeStr = (iso) => (iso ? formatInTz(new Date(iso), getBrowserTz(), 'MMM d, yyyy · p') : '—');

export default function SchedulingDashboardPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('all');
  const [search, setSearch] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [timelineFor, setTimelineFor] = useState(null); // request object
  const [timeline, setTimeline] = useState([]);
  const [timelineLoading, setTimelineLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api.get('/scheduling/requests')
      .then((r) => setItems(r.data || []))
      .catch((e) => toast.error(errMsg(e, 'Could not load scheduling requests')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const stats = useMemo(() => ({
    total: items.length,
    awaiting_candidate: items.filter((i) => i.display_status === 'awaiting_candidate' || i.display_status === 'reschedule_requested').length,
    scheduled: items.filter((i) => i.display_status === 'scheduled').length,
    cancelled: items.filter((i) => i.display_status === 'cancelled').length,
  }), [items]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((i) => {
      if (status !== 'all' && i.display_status !== status) return false;
      if (!q) return true;
      return (i.candidate_name || '').toLowerCase().includes(q) || (i.job_title || '').toLowerCase().includes(q);
    });
  }, [items, status, search]);

  const withBusy = async (id, fn) => {
    setBusyId(id);
    try { await fn(); load(); } catch (e) { toast.error(errMsg(e)); } finally { setBusyId(null); }
  };

  const copyLink = (link) => { navigator.clipboard.writeText(link); toast.success('Link copied'); };
  const sendLink = (req) => withBusy(req.id, async () => {
    await api.post(`/scheduling/requests/${req.id}/send-link`);
    toast.success(req.scheduling_link_sent_at ? 'Link re-sent (queued)' : 'Link sent (queued)');
  });
  const disableLink = (req) => withBusy(req.id, async () => {
    await api.post(`/scheduling/requests/${req.id}/disable-link`);
    toast.success('Link disabled');
  });
  const regenerateLink = (req) => withBusy(req.id, async () => {
    const r = await api.post(`/scheduling/requests/${req.id}/regenerate-link`);
    copyLink(r.data.scheduling_link);
    toast.success('New link generated & copied');
  });
  const deleteRequest = (req) => {
    if (!window.confirm(`Delete the scheduling link for ${req.candidate_name || 'this candidate'}? This cannot be undone.`)) return;
    withBusy(req.id, async () => {
      await api.delete(`/scheduling/requests/${req.id}`);
      toast.success('Scheduling request deleted');
    });
  };

  const openTimeline = (req) => {
    setTimelineFor(req);
    setTimelineLoading(true);
    api.get(`/scheduling/requests/${req.id}/timeline`)
      .then((r) => setTimeline(r.data.entries || []))
      .catch((e) => toast.error(errMsg(e)))
      .finally(() => setTimelineLoading(false));
  };

  return (
    <div className="space-y-4" data-testid="scheduling-dashboard-page">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Scheduling</h1>
          <p className="text-sm text-muted-foreground">Candidate self-scheduling links, status &amp; audit trail</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} data-testid="scheduling-refresh-button">
          <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { key: 'total', label: 'Total Requests', value: stats.total },
          { key: 'awaiting_candidate', label: 'Awaiting Candidate', value: stats.awaiting_candidate, cls: 'text-amber-700' },
          { key: 'scheduled', label: 'Scheduled', value: stats.scheduled, cls: 'text-emerald-700' },
          { key: 'cancelled', label: 'Cancelled', value: stats.cancelled, cls: 'text-rose-700' },
        ].map((s) => (
          <Card key={s.key} className="shadow-none">
            <CardContent className="py-3">
              <p className={`text-2xl font-display font-semibold ${s.cls || ''}`} data-testid={`scheduling-stat-${s.key}`}>{s.value}</p>
              <p className="text-[11px] text-muted-foreground uppercase tracking-wide mt-0.5">{s.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg border border-border overflow-hidden bg-card">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatus(f.value)}
              className={`px-3 py-1.5 text-xs font-medium transition-colors whitespace-nowrap ${status === f.value ? 'bg-primary text-primary-foreground' : 'hover:bg-secondary'}`}
              data-testid={`scheduling-filter-${f.value}`}
            >{f.label}</button>
          ))}
        </div>
        <div className="relative w-full sm:w-64 ml-auto">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search candidate or job…"
            className="pl-9 h-9 bg-card"
            data-testid="scheduling-search-input"
          />
        </div>
      </div>

      <Card className="shadow-none">
        <CardContent className="p-0">
          {loading ? (
            <div className="py-14 text-center text-muted-foreground text-sm"><Loader2 className="h-5 w-5 animate-spin inline mr-2" /> Loading…</div>
          ) : visible.length === 0 ? (
            <div className="py-14 text-center text-muted-foreground text-sm" data-testid="scheduling-empty-state">No scheduling requests match your filters.</div>
          ) : (
            <Table data-testid="scheduling-requests-table">
              <TableHeader>
                <TableRow>
                  <TableHead>Candidate</TableHead>
                  <TableHead>Job / Stage</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Link sent</TableHead>
                  <TableHead>Opened</TableHead>
                  <TableHead>Scheduled for</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visible.map((req) => {
                  const meta = STATUS_META[req.display_status] || STATUS_META.draft;
                  const busy = busyId === req.id;
                  const canSend = !['scheduled', 'cancelled', 'booking'].includes(req.display_status);
                  const canDisable = !req.link_disabled && !['cancelled', 'booking'].includes(req.display_status);
                  const canRegenerate = !['booking'].includes(req.display_status);
                  return (
                    <TableRow key={req.id} data-testid={`scheduling-row-${req.id}`}>
                      <TableCell>
                        <Link to={`/candidates/${req.candidate_id}`} className="font-medium hover:underline flex items-center gap-1">
                          {req.candidate_name} <ExternalLink className="h-3 w-3 text-muted-foreground" />
                        </Link>
                        <p className="text-xs text-muted-foreground">{req.candidate_email}</p>
                      </TableCell>
                      <TableCell>
                        <p className="text-sm">{req.job_title || '—'}</p>
                        <p className="text-xs text-muted-foreground">{req.stage || ''}</p>
                      </TableCell>
                      <TableCell><span className="text-xs">{TYPE_LABEL[req.type] || req.type}</span></TableCell>
                      <TableCell><Badge className={`${meta.className} font-medium`} data-testid={`scheduling-status-${req.id}`}>{meta.label}</Badge></TableCell>
                      <TableCell className="text-xs text-muted-foreground">{timeStr(req.scheduling_link_sent_at)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{timeStr(req.link_opened_at)}</TableCell>
                      <TableCell className="text-xs">
                        {req.scheduled_at ? formatInTz(new Date(req.scheduled_at), getBrowserTz(), 'MMM d, p') : '—'}
                      </TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button size="sm" variant="outline" disabled={busy} data-testid={`scheduling-actions-${req.id}`}>
                              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Actions'}
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {req.scheduling_link && (
                              <DropdownMenuItem onClick={() => copyLink(req.scheduling_link)} data-testid={`scheduling-copy-link-${req.id}`}>
                                <Copy className="h-3.5 w-3.5 mr-2" /> Copy link
                              </DropdownMenuItem>
                            )}
                            {canSend && (
                              <DropdownMenuItem onClick={() => sendLink(req)} data-testid={`scheduling-send-link-${req.id}`}>
                                <MailPlus className="h-3.5 w-3.5 mr-2" /> {req.scheduling_link_sent_at ? 'Resend link' : 'Send link'}
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuItem onClick={() => openTimeline(req)} data-testid={`scheduling-view-timeline-${req.id}`}>
                              <History className="h-3.5 w-3.5 mr-2" /> View timeline
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            {canDisable && (
                              <DropdownMenuItem onClick={() => disableLink(req)} className="text-destructive" data-testid={`scheduling-disable-link-${req.id}`}>
                                <Ban className="h-3.5 w-3.5 mr-2" /> Disable link
                              </DropdownMenuItem>
                            )}
                            {canRegenerate && (
                              <DropdownMenuItem onClick={() => regenerateLink(req)} data-testid={`scheduling-regenerate-link-${req.id}`}>
                                <RefreshCw className="h-3.5 w-3.5 mr-2" /> Regenerate link
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onClick={() => deleteRequest(req)} className="text-destructive" data-testid={`scheduling-delete-${req.id}`}>
                              <Trash2 className="h-3.5 w-3.5 mr-2" /> Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Sheet open={!!timelineFor} onOpenChange={(o) => !o && setTimelineFor(null)}>
        <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto" data-testid="scheduling-timeline-sheet">
          <SheetHeader className="border-b border-border pb-4">
            <SheetTitle>Timeline — {timelineFor?.candidate_name}</SheetTitle>
            <p className="text-xs text-muted-foreground">{timelineFor?.job_title}{timelineFor?.stage ? ` · ${timelineFor.stage}` : ''}</p>
          </SheetHeader>
          <div className="py-4">
            {timelineLoading ? (
              <div className="py-10 text-center text-muted-foreground text-sm"><Loader2 className="h-4 w-4 animate-spin inline mr-2" /> Loading…</div>
            ) : timeline.length === 0 ? (
              <div className="py-10 text-center text-muted-foreground text-sm flex flex-col items-center gap-2">
                <FileClock className="h-6 w-6" /> No activity recorded yet.
              </div>
            ) : (
              <ol className="relative border-l border-border ml-2 space-y-5" data-testid="scheduling-timeline-list">
                {timeline.map((e) => {
                  const m = AUDIT_META[e.action] || { icon: CalendarX2, label: e.action };
                  const Icon = m.icon;
                  return (
                    <li key={e.id} className="ml-4">
                      <span className="absolute -left-[9px] flex h-4 w-4 items-center justify-center rounded-full bg-primary/10 border border-primary/30">
                        <Icon className="h-2.5 w-2.5 text-primary" />
                      </span>
                      <p className="text-sm font-medium">{m.label}</p>
                      {e.details && <p className="text-xs text-muted-foreground mt-0.5">{e.details}</p>}
                      <p className="text-[11px] text-muted-foreground mt-0.5">{format(new Date(e.created_at), 'MMM d, yyyy · p')} · {e.actor_name || 'System'}</p>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
