import { useEffect, useMemo, useState } from 'react';
import { CalendarCheck, Clock, Globe, Loader2, MapPin, Sparkles, Users, Video, X } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { api, errMsg } from '@/lib/api';
import { formatInTz, getBrowserTz, tzAbbr, TZ_PRESETS } from '@/lib/timezones';

const TYPES = [
  { value: 'phone_screen', label: 'Phone Screen', color: 'bg-sky-100 text-sky-800' },
  { value: 'technical', label: 'Technical Interview', color: 'bg-purple-100 text-purple-800' },
  { value: 'panel', label: 'Panel Interview', color: 'bg-amber-100 text-amber-800' },
  { value: 'onsite', label: 'Onsite Interview', color: 'bg-emerald-100 text-emerald-800' },
];

const DURATIONS = [15, 30, 45, 60, 75, 90, 120];

const initials = (name) => (name || '?').split(' ').slice(0, 2).map((n) => n[0]).join('').toUpperCase();

// Convert local wall-clock date+time in `tz` to a UTC ISO string.
// e.g. 2026-07-22 14:00 in America/New_York (EDT = UTC-4) -> 2026-07-22T18:00:00.000Z
function wallClockInTzToUtcIso(dateStr, timeStr, tz) {
  if (!dateStr || !timeStr) return null;
  // Build a Date from the local wall clock as if it were UTC, then figure out the offset in `tz`.
  const [y, m, d] = dateStr.split('-').map(Number);
  const [hh, mm] = timeStr.split(':').map(Number);
  const asUtc = Date.UTC(y, m - 1, d, hh, mm, 0);
  // What time would `asUtc` show as in `tz`? Diff tells us the offset to apply.
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
  const parts = Object.fromEntries(fmt.formatToParts(new Date(asUtc)).map((p) => [p.type, p.value]));
  const asTz = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour % 24, +parts.minute, +parts.second);
  const offset = asTz - asUtc; // ms the tz is ahead of UTC for this instant
  return new Date(asUtc - offset).toISOString();
}

export default function ScheduleInterviewDialog({ open, onOpenChange, onScheduled, presetCandidateId }) {
  const [candidates, setCandidates] = useState([]);
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(() => ({
    candidate_id: presetCandidateId || '',
    type: 'phone_screen',
    interviewer_ids: [],
    date: '',
    time: '10:00',
    timezone: getBrowserTz(),
    duration_min: 60,
    location: '',
    video_link: '',
    notes: '',
    auto_meet: true,
    enable_gemini_ai: true,
  }));
  const [availability, setAvailability] = useState(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [interviewerSearch, setInterviewerSearch] = useState('');
  const [calStatus, setCalStatus] = useState(null); // { connected, can_create_meet_ai, ... }

  useEffect(() => {
    if (!open) return;
    Promise.all([
      api.get('/candidates', { params: { status: 'active', limit: 500 } }),
      api.get('/users'),
      api.get('/calendar/status').catch(() => ({ data: null })),
    ])
      .then(([c, u, s]) => {
        setCandidates(c.data.items);
        setUsers(u.data.filter((x) => x.active !== false));
        setCalStatus(s.data);
      })
      .catch(() => {});
    setForm((f) => ({ ...f, candidate_id: presetCandidateId || f.candidate_id }));
    setAvailability(null);
    setInterviewerSearch('');
  }, [open, presetCandidateId]);

  const scheduledAtUtc = useMemo(
    () => wallClockInTzToUtcIso(form.date, form.time, form.timezone),
    [form.date, form.time, form.timezone],
  );

  const filteredUsers = useMemo(() => {
    if (!interviewerSearch.trim()) return users;
    const q = interviewerSearch.toLowerCase();
    return users.filter((u) => u.name?.toLowerCase().includes(q) || u.email?.toLowerCase().includes(q));
  }, [users, interviewerSearch]);

  const selectedInterviewers = useMemo(
    () => users.filter((u) => form.interviewer_ids.includes(u.id)),
    [users, form.interviewer_ids],
  );

  const toggleInterviewer = (id) => {
    setForm((f) => ({
      ...f,
      interviewer_ids: f.interviewer_ids.includes(id) ? f.interviewer_ids.filter((x) => x !== id) : [...f.interviewer_ids, id],
    }));
    setAvailability(null);
  };

  const checkAvailability = async () => {
    if (!scheduledAtUtc || form.interviewer_ids.length === 0) {
      toast.error('Pick interviewers, date and time first');
      return;
    }
    setChecking(true);
    try {
      const r = await api.get('/interviews-availability-check', {
        params: {
          interviewer_ids: form.interviewer_ids.join(','),
          scheduled_at: scheduledAtUtc,
          duration_min: form.duration_min,
        },
      });
      setAvailability(r.data.results);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setChecking(false);
    }
  };

  const submit = async () => {
    if (!form.candidate_id) return toast.error('Select a candidate');
    if (form.interviewer_ids.length === 0) return toast.error('Select at least one interviewer');
    if (!scheduledAtUtc) return toast.error('Pick a date and time');
    setSaving(true);
    try {
      await api.post('/interviews', {
        candidate_id: form.candidate_id,
        type: form.type,
        interviewer_ids: form.interviewer_ids,
        scheduled_at: scheduledAtUtc,
        timezone: form.timezone,
        duration_min: Number(form.duration_min) || 60,
        location: form.location || null,
        video_link: form.auto_meet && !form.video_link ? null : (form.video_link || null),
        notes: form.notes || null,
        enable_gemini_ai: form.enable_gemini_ai && !form.video_link,
      });
      toast.success('Interview scheduled — interviewers notified');
      onOpenChange(false);
      setForm({
        candidate_id: '', type: 'phone_screen', interviewer_ids: [],
        date: '', time: '10:00', timezone: getBrowserTz(),
        duration_min: 60, location: '', video_link: '', notes: '',
        auto_meet: true, enable_gemini_ai: true,
      });
      setAvailability(null);
      onScheduled?.();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  const cand = candidates.find((c) => c.id === form.candidate_id);
  const typeMeta = TYPES.find((t) => t.value === form.type);
  const endTimeStr = scheduledAtUtc
    ? formatInTz(new Date(new Date(scheduledAtUtc).getTime() + form.duration_min * 60000), form.timezone, 'p')
    : null;
  const startTimeStr = scheduledAtUtc ? formatInTz(new Date(scheduledAtUtc), form.timezone, 'p') : null;
  const dayStr = scheduledAtUtc ? formatInTz(new Date(scheduledAtUtc), form.timezone, 'EEE, MMM d, yyyy') : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[92vh] overflow-y-auto" data-testid="schedule-interview-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarCheck className="h-5 w-5" /> Schedule Interview
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-5">
          {/* Candidate + Type */}
          <div className="grid grid-cols-1 md:grid-cols-[1fr_220px] gap-3">
            <div className="space-y-1.5">
              <Label>Candidate</Label>
              <Select value={form.candidate_id} onValueChange={(v) => setForm((f) => ({ ...f, candidate_id: v }))}>
                <SelectTrigger data-testid="schedule-candidate-select"><SelectValue placeholder="Select candidate" /></SelectTrigger>
                <SelectContent>
                  {candidates.map((c) => (
                    <SelectItem key={c.id} value={c.id}>{c.name} · {c.stage}{c.job_title ? ` · ${c.job_title}` : ''}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Interview type</Label>
              <Select value={form.type} onValueChange={(v) => setForm((f) => ({ ...f, type: v }))}>
                <SelectTrigger data-testid="schedule-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>{TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>

          {/* Date + Time + Timezone + Duration */}
          <div>
            <Label className="mb-1.5 block">When</Label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <div>
                <Input type="date" value={form.date} onChange={(e) => { setForm((f) => ({ ...f, date: e.target.value })); setAvailability(null); }} data-testid="schedule-date-input" />
              </div>
              <div>
                <Input type="time" value={form.time} onChange={(e) => { setForm((f) => ({ ...f, time: e.target.value })); setAvailability(null); }} data-testid="schedule-time-input" />
              </div>
              <div>
                <Select value={form.timezone} onValueChange={(v) => { setForm((f) => ({ ...f, timezone: v })); setAvailability(null); }}>
                  <SelectTrigger data-testid="schedule-timezone-select"><SelectValue /></SelectTrigger>
                  <SelectContent className="max-h-72">
                    {TZ_PRESETS.map((tz) => (
                      <SelectItem key={tz.value} value={tz.value}>
                        <span className="inline-flex items-center gap-1"><Globe className="h-3 w-3" /> {tz.label}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Select value={String(form.duration_min)} onValueChange={(v) => setForm((f) => ({ ...f, duration_min: Number(v) }))}>
                  <SelectTrigger data-testid="schedule-duration-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {DURATIONS.map((d) => <SelectItem key={d} value={String(d)}>{d} minutes</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {scheduledAtUtc && (
              <div className="mt-2 text-xs text-muted-foreground flex items-center gap-1.5">
                <Clock className="h-3 w-3" /> {dayStr} · <span className="font-medium text-foreground">{startTimeStr} → {endTimeStr}</span> ({tzAbbr(form.timezone)})
              </div>
            )}
          </div>

          {/* Interviewers */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <Label className="flex items-center gap-1.5"><Users className="h-3.5 w-3.5" /> Interviewers ({form.interviewer_ids.length})</Label>
              <Input
                placeholder="Search…"
                value={interviewerSearch}
                onChange={(e) => setInterviewerSearch(e.target.value)}
                className="h-7 w-40 text-xs"
                data-testid="schedule-interviewer-search"
              />
            </div>
            {selectedInterviewers.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {selectedInterviewers.map((u) => (
                  <Badge key={u.id} variant="secondary" className="pl-1 pr-1 h-6 flex items-center gap-1" data-testid={`schedule-selected-chip-${u.id}`}>
                    <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-semibold text-primary-foreground">{initials(u.name)}</span>
                    <span className="text-xs">{u.name}</span>
                    <button onClick={() => toggleInterviewer(u.id)} className="ml-0.5 hover:text-destructive"><X className="h-3 w-3" /></button>
                  </Badge>
                ))}
              </div>
            )}
            <div className="border border-border rounded-lg p-1 max-h-40 overflow-y-auto">
              {filteredUsers.map((u) => (
                <label key={u.id} className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-secondary cursor-pointer">
                  <Checkbox
                    checked={form.interviewer_ids.includes(u.id)}
                    onCheckedChange={() => toggleInterviewer(u.id)}
                    data-testid={`schedule-interviewer-checkbox-${u.id}`}
                  />
                  <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-secondary text-[10px] font-semibold">{initials(u.name)}</span>
                  <span className="text-sm flex-1">{u.name}</span>
                  <span className="text-xs text-muted-foreground capitalize">{u.role}</span>
                </label>
              ))}
              {filteredUsers.length === 0 && <p className="text-xs text-muted-foreground p-3 text-center">No users match your search.</p>}
            </div>
            <div className="mt-2">
              <Button type="button" variant="outline" size="sm" onClick={checkAvailability} disabled={checking} data-testid="schedule-check-availability-button">
                {checking ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <CalendarCheck className="h-3.5 w-3.5 mr-1" />}
                Check availability
              </Button>
              {availability && (
                <div className="mt-2 space-y-1.5" data-testid="availability-results">
                  {availability.map((a) => (
                    <div key={a.interviewer_id} className={`text-xs rounded-lg px-3 py-2 border ${a.available ? 'bg-green-50 border-green-200 text-green-800' : 'bg-red-50 border-red-200 text-red-800'}`}>
                      <span className="font-medium">{a.interviewer_name}:</span>{' '}
                      {a.available
                        ? 'Available'
                        : a.conflicts.length > 0
                          ? `Conflict — ${a.conflicts.length} existing interview${a.conflicts.length === 1 ? '' : 's'} at this time`
                          : a.google_conflicts?.length > 0
                            ? 'Busy on their Google Calendar at this time'
                            : 'Outside working availability'}
                      {a.has_slots_defined === false && <span className="text-muted-foreground"> (no availability slots defined)</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Location + Video */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="flex items-center gap-1.5"><MapPin className="h-3.5 w-3.5" /> Location (optional)</Label>
              <Input value={form.location} onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))} placeholder="HQ Conference Room B" data-testid="schedule-location-input" />
            </div>
            <div className="space-y-1.5">
              <Label className="flex items-center gap-1.5"><Video className="h-3.5 w-3.5" /> Video link</Label>
              <Input value={form.video_link} onChange={(e) => setForm((f) => ({ ...f, video_link: e.target.value, auto_meet: false }))} placeholder="Leave empty to auto-create Google Meet" data-testid="schedule-video-input" />
              {!form.video_link && (
                <p className="text-xs text-muted-foreground">A Google Meet link will be auto-generated when the event syncs.</p>
              )}
            </div>
          </div>

          {/* Gemini AI (auto notes + transcription) — only relevant when a Meet link is being auto-created */}
          {!form.video_link && (
            <div className="rounded-lg border border-border bg-gradient-to-br from-emerald-50/40 to-transparent p-3">
              <div className="flex items-start gap-3">
                <Checkbox
                  id="enable-gemini-ai"
                  checked={form.enable_gemini_ai}
                  onCheckedChange={(v) => setForm((f) => ({ ...f, enable_gemini_ai: !!v }))}
                  data-testid="schedule-gemini-toggle"
                  className="mt-0.5"
                />
                <div className="flex-1 min-w-0">
                  <Label htmlFor="enable-gemini-ai" className="flex items-center gap-1.5 text-sm font-medium cursor-pointer">
                    <Sparkles className="h-3.5 w-3.5 text-emerald-600" />
                    Enable Gemini smart notes &amp; transcription
                  </Label>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Auto-generates AI meeting notes and a live transcript in Google Meet. Requires a Workspace edition with Gemini for Meet.
                  </p>
                  {calStatus && calStatus.connected && !calStatus.can_create_meet_ai && form.enable_gemini_ai && (
                    <div className="mt-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5 flex items-start gap-1.5" data-testid="schedule-gemini-reconnect-hint">
                      <Sparkles className="h-3 w-3 mt-0.5 flex-shrink-0" />
                      <span>Reconnect Google Calendar in <a href="/my-integrations" className="underline font-medium">My Integrations</a> to grant the new Meet AI permissions.</span>
                    </div>
                  )}
                  {calStatus && !calStatus.connected && form.enable_gemini_ai && (
                    <div className="mt-2 text-xs text-muted-foreground bg-muted rounded-md px-2 py-1.5">
                      Connect Google Calendar in <a href="/my-integrations" className="underline font-medium">My Integrations</a> first — Gemini notes won&apos;t apply without a Meet link.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Notes */}
          <div className="space-y-1.5">
            <Label>Notes for interviewers (optional)</Label>
            <Textarea rows={2} value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} placeholder="Focus areas, links to portfolio, etc." data-testid="schedule-notes-input" />
          </div>

          {/* Preview */}
          {scheduledAtUtc && cand && form.interviewer_ids.length > 0 && (
            <div className="rounded-lg border border-border bg-secondary/40 p-3">
              <p className="text-xs font-medium text-muted-foreground mb-1.5">Preview</p>
              <div className="flex items-start gap-3">
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${typeMeta?.color}`}>{typeMeta?.label}</span>
                <div className="flex-1 text-sm">
                  <p className="font-medium">{cand.name} · {form.duration_min}min</p>
                  <p className="text-xs text-muted-foreground">{dayStr} · {startTimeStr} → {endTimeStr} ({tzAbbr(form.timezone)})</p>
                  <p className="text-xs text-muted-foreground mt-1">with {selectedInterviewers.map((u) => u.name).join(', ')}</p>
                </div>
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={saving} data-testid="schedule-submit-button">
            {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null} Schedule Interview
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
