import { useEffect, useState } from 'react';
import { CalendarCheck, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { api, errMsg } from '@/lib/api';

const TYPES = [
  { value: 'phone_screen', label: 'Phone Screen' },
  { value: 'technical', label: 'Technical' },
  { value: 'panel', label: 'Panel' },
  { value: 'onsite', label: 'Onsite' },
];

export default function ScheduleInterviewDialog({ open, onOpenChange, onScheduled, presetCandidateId }) {
  const [candidates, setCandidates] = useState([]);
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({
    candidate_id: presetCandidateId || '',
    type: 'phone_screen',
    interviewer_ids: [],
    date: '',
    time: '10:00',
    duration_min: 60,
    location: '',
    video_link: '',
  });
  const [availability, setAvailability] = useState(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    Promise.all([api.get('/candidates', { params: { status: 'active', limit: 500 } }), api.get('/users')])
      .then(([c, u]) => {
        setCandidates(c.data.items);
        setUsers(u.data.filter((x) => x.active !== false));
      })
      .catch(() => {});
    setForm((f) => ({ ...f, candidate_id: presetCandidateId || f.candidate_id }));
    setAvailability(null);
  }, [open, presetCandidateId]);

  const scheduledAtIso = () => {
    if (!form.date || !form.time) return null;
    return new Date(`${form.date}T${form.time}:00`).toISOString();
  };

  const checkAvailability = async () => {
    const at = scheduledAtIso();
    if (!at || form.interviewer_ids.length === 0) {
      toast.error('Pick interviewers, date and time first');
      return;
    }
    setChecking(true);
    try {
      const r = await api.get('/interviews-availability-check', {
        params: { interviewer_ids: form.interviewer_ids.join(','), scheduled_at: at, duration_min: form.duration_min },
      });
      setAvailability(r.data.results);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setChecking(false);
    }
  };

  const submit = async () => {
    const at = scheduledAtIso();
    if (!form.candidate_id) return toast.error('Select a candidate');
    if (form.interviewer_ids.length === 0) return toast.error('Select at least one interviewer');
    if (!at) return toast.error('Pick a date and time');
    setSaving(true);
    try {
      await api.post('/interviews', {
        candidate_id: form.candidate_id,
        type: form.type,
        interviewer_ids: form.interviewer_ids,
        scheduled_at: at,
        duration_min: Number(form.duration_min) || 60,
        location: form.location || null,
        video_link: form.video_link || null,
      });
      toast.success('Interview scheduled — interviewers notified');
      onOpenChange(false);
      setForm({ candidate_id: '', type: 'phone_screen', interviewer_ids: [], date: '', time: '10:00', duration_min: 60, location: '', video_link: '' });
      setAvailability(null);
      onScheduled?.();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto" data-testid="schedule-interview-dialog">
        <DialogHeader><DialogTitle>Schedule Interview</DialogTitle></DialogHeader>
        <div className="space-y-4">
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

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Interview type</Label>
              <Select value={form.type} onValueChange={(v) => setForm((f) => ({ ...f, type: v }))}>
                <SelectTrigger data-testid="schedule-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>{TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Duration (minutes)</Label>
              <Input type="number" min="15" step="15" value={form.duration_min} onChange={(e) => setForm((f) => ({ ...f, duration_min: e.target.value }))} data-testid="schedule-duration-input" />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Interviewers</Label>
            <div className="border border-border rounded-lg p-2 space-y-1 max-h-36 overflow-y-auto">
              {users.map((u) => (
                <label key={u.id} className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-secondary cursor-pointer">
                  <Checkbox
                    checked={form.interviewer_ids.includes(u.id)}
                    onCheckedChange={(ck) =>
                      setForm((f) => ({
                        ...f,
                        interviewer_ids: ck ? [...f.interviewer_ids, u.id] : f.interviewer_ids.filter((x) => x !== u.id),
                      }))
                    }
                    data-testid={`schedule-interviewer-checkbox-${u.id}`}
                  />
                  <span className="text-sm">{u.name}</span>
                  <span className="text-xs text-muted-foreground capitalize ml-auto">{u.role}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Date</Label>
              <Input type="date" value={form.date} onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))} data-testid="schedule-date-input" />
            </div>
            <div className="space-y-1.5">
              <Label>Time</Label>
              <Input type="time" value={form.time} onChange={(e) => setForm((f) => ({ ...f, time: e.target.value }))} data-testid="schedule-time-input" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Location (optional)</Label>
              <Input value={form.location} onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))} placeholder="HQ Conference Room B" data-testid="schedule-location-input" />
            </div>
            <div className="space-y-1.5">
              <Label>Video link (optional)</Label>
              <Input value={form.video_link} onChange={(e) => setForm((f) => ({ ...f, video_link: e.target.value }))} placeholder="https://meet..." data-testid="schedule-video-input" />
            </div>
          </div>

          <div>
            <Button type="button" variant="outline" size="sm" onClick={checkAvailability} disabled={checking} data-testid="schedule-check-availability-button">
              {checking ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <CalendarCheck className="h-4 w-4 mr-1" />}
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
                    {a.google_calendar_connected && (
                      <span className="text-muted-foreground"> · Google Calendar checked</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={saving} data-testid="schedule-submit-button">
            {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null} Schedule
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
