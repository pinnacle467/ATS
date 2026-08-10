import { useEffect, useMemo, useState } from 'react';
import { CalendarRange, CheckCircle2, Clock, Copy, Link2, Loader2, Search, Send, Users } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { api, errMsg } from '@/lib/api';
import { useCachedUsers } from '@/lib/referenceCache';
import { getBrowserTz, TZ_PRESETS } from '@/lib/timezones';

const TYPES = [
  { value: 'phone_screen', label: 'Phone Screen' },
  { value: 'technical', label: 'Technical Interview' },
  { value: 'panel', label: 'Panel Interview' },
  { value: 'onsite', label: 'Onsite Interview' },
];
const DURATIONS = [30, 45, 60];
const todayStr = () => new Date().toISOString().slice(0, 10);
const addDaysStr = (n) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);

/**
 * Recruiter dialog: configure an interview scheduling request, preview
 * interviewer availability, then generate + send a candidate scheduling link.
 */
export default function ScheduleRequestDialog({ open, onOpenChange, candidate, onCreated }) {
  const [rawUsers] = useCachedUsers();
  const users = useMemo(() => rawUsers.filter((u) => u.active !== false), [rawUsers]);
  const [form, setForm] = useState(null);
  const [customDuration, setCustomDuration] = useState(false);
  const [ivStatus, setIvStatus] = useState([]);
  const [slotPreview, setSlotPreview] = useState(null);
  const [checking, setChecking] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // {scheduling_link}
  const [attendeeInput, setAttendeeInput] = useState('');

  useEffect(() => {
    if (open) {
      setForm({
        stage: candidate?.stage || 'Technical Round',
        title: '',
        type: 'technical',
        duration_min: 60,
        interviewer_ids: [],
        attendee_emails: [],
        date_range_start: todayStr(),
        date_range_end: addDaysStr(7),
        timezone: getBrowserTz(),
        instructions: '',
      });
      setResult(null); setSlotPreview(null); setIvStatus([]); setCustomDuration(false); setAttendeeInput('');
    }
  }, [open, candidate]);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  // Fetch interviewer google/working-hours status when selection changes.
  useEffect(() => {
    if (!form?.interviewer_ids?.length) { setIvStatus([]); return; }
    api.get('/scheduling/interviewer-status', { params: { ids: form.interviewer_ids.join(',') } })
      .then((r) => setIvStatus(r.data.interviewers || []))
      .catch(() => setIvStatus([]));
  }, [form?.interviewer_ids]);

  if (!form) return null;

  const toggleInterviewer = (id) => {
    const has = form.interviewer_ids.includes(id);
    set({ interviewer_ids: has ? form.interviewer_ids.filter((x) => x !== id) : [...form.interviewer_ids, id] });
    setSlotPreview(null);
  };

  const addAttendee = () => {
    const e = attendeeInput.trim();
    if (e && /.+@.+\..+/.test(e) && !form.attendee_emails.includes(e)) {
      set({ attendee_emails: [...form.attendee_emails, e] });
    }
    setAttendeeInput('');
  };

  const createPayload = () => ({
    candidate_id: candidate.id,
    job_id: candidate.job_id,
    stage: form.stage || null,
    title: form.title || `${TYPES.find((t) => t.value === form.type)?.label || 'Interview'}`,
    type: form.type,
    duration_min: Number(form.duration_min) || 60,
    interviewer_ids: form.interviewer_ids,
    attendee_emails: form.attendee_emails,
    date_range_start: form.date_range_start,
    date_range_end: form.date_range_end,
    timezone: form.timezone,
    instructions: form.instructions || null,
  });

  const findAvailability = async () => {
    if (!form.interviewer_ids.length) { toast.error('Select at least one interviewer'); return; }
    setChecking(true); setSlotPreview(null);
    try {
      // Create a draft request, then preview its slots (keeps engine logic server-side).
      const r = await api.post('/scheduling/requests', createPayload());
      const req = r.data;
      const s = await api.get(`/scheduling/requests/${req.id}/slots`);
      setSlotPreview({ req_id: req.id, count: (s.data.slots || []).length, calendar_error: s.data.calendar_error, link: req.scheduling_link });
    } catch (e) {
      toast.error(errMsg(e, 'Could not check availability'));
    } finally { setChecking(false); }
  };

  const createAndSend = async () => {
    if (!form.interviewer_ids.length) { toast.error('Select at least one interviewer'); return; }
    setSubmitting(true);
    try {
      let reqId = slotPreview?.req_id;
      let link = slotPreview?.link;
      if (!reqId) {
        const r = await api.post('/scheduling/requests', createPayload());
        reqId = r.data.id; link = r.data.scheduling_link;
      }
      const sr = await api.post(`/scheduling/requests/${reqId}/send-link`);
      setResult({ scheduling_link: sr.data.scheduling_link || link, queued: sr.data.email?.queued });
      toast.success('Scheduling link generated & queued to candidate');
      onCreated?.();
    } catch (e) {
      toast.error(errMsg(e, 'Could not create scheduling request'));
    } finally { setSubmitting(false); }
  };

  const copyLink = () => { navigator.clipboard.writeText(result.scheduling_link); toast.success('Link copied'); };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="schedule-request-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><CalendarRange className="h-5 w-5 text-emerald-600" /> Schedule Interview — {candidate?.name}</DialogTitle>
        </DialogHeader>

        {result ? (
          <div className="py-4">
            <div className="flex items-center gap-2 text-emerald-600 mb-3"><CheckCircle2 className="h-5 w-5" /><span className="font-medium">Scheduling link ready</span></div>
            <p className="text-sm text-slate-500 mb-2">Share this link with the candidate. {result.queued ? 'An invite email has been queued.' : ''}</p>
            <div className="flex items-center gap-2 bg-slate-50 border rounded-lg p-2">
              <Link2 className="h-4 w-4 text-slate-400 shrink-0" />
              <span className="text-sm text-slate-700 truncate flex-1" data-testid="schedule-generated-link">{result.scheduling_link}</span>
              <Button size="sm" variant="outline" onClick={copyLink} data-testid="schedule-copy-link"><Copy className="h-3.5 w-3.5 mr-1" /> Copy</Button>
            </div>
            <DialogFooter className="mt-5"><Button onClick={() => onOpenChange(false)}>Done</Button></DialogFooter>
          </div>
        ) : (
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Interview title</Label><Input value={form.title} onChange={(e) => set({ title: e.target.value })} placeholder="e.g. Technical Round" data-testid="schedule-title" /></div>
              <div><Label>Stage</Label><Input value={form.stage} onChange={(e) => set({ stage: e.target.value })} data-testid="schedule-stage" /></div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Type</Label>
                <Select value={form.type} onValueChange={(v) => set({ type: v })}>
                  <SelectTrigger data-testid="schedule-type"><SelectValue /></SelectTrigger>
                  <SelectContent>{TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label>Duration</Label>
                <div className="flex gap-1.5 items-center">
                  {DURATIONS.map((d) => (
                    <button key={d} onClick={() => { setCustomDuration(false); set({ duration_min: d }); }}
                      className={`px-2.5 py-1.5 rounded-md border text-sm ${!customDuration && form.duration_min === d ? 'border-emerald-500 bg-emerald-50 text-emerald-700' : 'border-slate-200'}`}>{d}m</button>
                  ))}
                  <button onClick={() => setCustomDuration(true)} className={`px-2.5 py-1.5 rounded-md border text-sm ${customDuration ? 'border-emerald-500 bg-emerald-50 text-emerald-700' : 'border-slate-200'}`}>Custom</button>
                  {customDuration && <Input type="number" min="10" className="w-20 h-8" value={form.duration_min} onChange={(e) => set({ duration_min: e.target.value })} data-testid="schedule-custom-duration" />}
                </div>
              </div>
            </div>

            <div>
              <Label className="flex items-center gap-1.5"><Users className="h-3.5 w-3.5" /> Interviewers</Label>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {users.map((u) => {
                  const sel = form.interviewer_ids.includes(u.id);
                  return (
                    <button key={u.id} onClick={() => toggleInterviewer(u.id)} data-testid="schedule-interviewer-chip"
                      className={`px-2.5 py-1 rounded-full border text-xs ${sel ? 'border-emerald-500 bg-emerald-600 text-white' : 'border-slate-200 text-slate-600 hover:border-emerald-400'}`}>
                      {u.name}
                    </button>
                  );
                })}
              </div>
              {ivStatus.some((s) => !s.google_calendar_connected) && (
                <div className="mt-2 text-xs text-amber-700 bg-amber-50 rounded-md px-2.5 py-1.5">
                  {ivStatus.filter((s) => !s.google_calendar_connected).map((s) => s.name).join(', ')} {ivStatus.filter((s) => !s.google_calendar_connected).length > 1 ? 'have' : 'has'} not connected Google Calendar — availability falls back to working hours.
                </div>
              )}
            </div>

            <div>
              <Label>Additional attendees (optional)</Label>
              <div className="flex gap-2">
                <Input value={attendeeInput} onChange={(e) => setAttendeeInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addAttendee(); } }} placeholder="email@company.com" data-testid="schedule-attendee-input" />
                <Button type="button" variant="outline" onClick={addAttendee}>Add</Button>
              </div>
              {form.attendee_emails.length > 0 && <div className="flex flex-wrap gap-1.5 mt-1.5">{form.attendee_emails.map((e) => <Badge key={e} variant="secondary" className="cursor-pointer" onClick={() => set({ attendee_emails: form.attendee_emails.filter((x) => x !== e) })}>{e} ✕</Badge>)}</div>}
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div><Label>From date</Label><Input type="date" value={form.date_range_start} onChange={(e) => { set({ date_range_start: e.target.value }); setSlotPreview(null); }} data-testid="schedule-from-date" /></div>
              <div><Label>To date</Label><Input type="date" value={form.date_range_end} onChange={(e) => { set({ date_range_end: e.target.value }); setSlotPreview(null); }} data-testid="schedule-to-date" /></div>
              <div>
                <Label>Timezone</Label>
                <Select value={form.timezone} onValueChange={(v) => set({ timezone: v })}>
                  <SelectTrigger data-testid="schedule-timezone"><SelectValue /></SelectTrigger>
                  <SelectContent className="max-h-64">{TZ_PRESETS.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>

            <div><Label>Instructions for candidate (optional)</Label><Textarea rows={2} value={form.instructions} onChange={(e) => set({ instructions: e.target.value })} placeholder="Anything the candidate should know…" data-testid="schedule-instructions" /></div>

            {slotPreview && (
              <div className={`text-sm rounded-md px-3 py-2 ${slotPreview.calendar_error ? 'bg-amber-50 text-amber-700' : slotPreview.count > 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-50 text-slate-600'}`} data-testid="schedule-slot-preview">
                {slotPreview.calendar_error ? 'Some interviewer calendars could not be read — reconnect Google Calendar.' : slotPreview.count > 0 ? `${slotPreview.count} available slots found in this window.` : 'No common availability in this window. Try a wider date range or fewer interviewers.'}
              </div>
            )}

            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={findAvailability} disabled={checking} data-testid="schedule-find-availability">
                {checking ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <Search className="h-4 w-4 mr-1.5" />} Find Availability
              </Button>
              <Button onClick={createAndSend} disabled={submitting} className="bg-emerald-600 hover:bg-emerald-700" data-testid="schedule-send-link">
                {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <Send className="h-4 w-4 mr-1.5" />} Generate & Send Link
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
