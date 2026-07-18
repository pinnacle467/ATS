import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Briefcase, FileText, MapPin, Pencil, Plus, Trash2, Users } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useAuth } from '@/context/AuthContext';
import { api, errMsg } from '@/lib/api';

export function JdIndicator({ hasJd }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            data-testid="job-jd-indicator"
            data-has-jd={hasJd ? 'true' : 'false'}
            className={`inline-flex items-center justify-center h-5 w-5 rounded-full shrink-0 ${hasJd ? 'text-primary bg-primary/10' : 'text-muted-foreground/50 bg-secondary'}`}
          >
            <FileText className="h-3 w-3" />
          </span>
        </TooltipTrigger>
        <TooltipContent>{hasJd ? 'Job description attached' : 'No job description attached'}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

const STATUS_STYLE = {
  open: 'bg-green-100 text-green-800',
  on_hold: 'bg-amber-100 text-amber-800',
  closed: 'bg-secondary text-muted-foreground',
};

const emptyForm = { title: '', department: '', location: '', description: '', status: 'open', stages: '' };

export default function JobsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [jobs, setJobs] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || 'all');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    const params = statusFilter !== 'all' ? { status: statusFilter } : {};
    api.get('/jobs', { params }).then((r) => setJobs(r.data)).catch((e) => toast.error(errMsg(e)));
  }, [statusFilter]);

  useEffect(() => {
    load();
    api.get('/departments').then((r) => setDepartments(r.data)).catch(() => {});
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setDialogOpen(true);
  };

  const openEdit = (job) => {
    setEditing(job);
    setForm({
      title: job.title,
      department: job.department,
      location: job.location || '',
      description: job.description || '',
      status: job.status,
      stages: (job.stages || []).join(', '),
    });
    setDialogOpen(true);
  };

  const save = async () => {
    if (!form.title.trim()) return toast.error('Job title is required');
    if (!form.department) return toast.error('Department is required');
    setSaving(true);
    const body = {
      title: form.title,
      department: form.department,
      location: form.location || null,
      description: form.description || null,
      status: form.status,
    };
    if (form.stages.trim()) body.stages = form.stages.split(',').map((s) => s.trim()).filter(Boolean);
    try {
      if (editing) {
        await api.put(`/jobs/${editing.id}`, body);
        toast.success('Job updated');
      } else {
        await api.post('/jobs', body);
        toast.success('Job created');
      }
      setDialogOpen(false);
      load();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  const setStatus = async (job, status) => {
    try {
      await api.put(`/jobs/${job.id}`, { status });
      toast.success(`Job marked ${status.replace('_', ' ')}`);
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const deleteJob = async (job) => {
    const msg = job.candidate_count > 0
      ? `Delete "${job.title}"? It has ${job.candidate_count} active candidate${job.candidate_count === 1 ? '' : 's'} — they will remain in the system but lose their job link. This cannot be undone.`
      : `Delete "${job.title}"? This cannot be undone.`;
    if (!window.confirm(msg)) return;
    try {
      await api.delete(`/jobs/${job.id}`);
      toast.success('Job deleted');
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not delete job'));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Jobs</h1>
          <p className="text-sm text-muted-foreground">Manage job requisitions and their pipelines.</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[140px] h-9 bg-card" data-testid="jobs-filter-status"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="open">Open</SelectItem>
              <SelectItem value="on_hold">On Hold</SelectItem>
              <SelectItem value="closed">Closed</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={openCreate} data-testid="jobs-create-button"><Plus className="h-4 w-4 mr-1" /> New Job</Button>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {jobs.length === 0 && (
          <Card className="shadow-none sm:col-span-2 lg:col-span-3"><CardContent className="py-10 text-center text-sm text-muted-foreground">No jobs found.</CardContent></Card>
        )}
        {jobs.map((j) => (
          <Card
            key={j.id}
            className="shadow-none hover:shadow-sm hover:border-primary/40 transition-all cursor-pointer"
            data-testid={`job-card-${j.id}`}
            onClick={() => navigate(`/jobs/${j.id}`)}
          >
            <CardContent className="pt-5 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-1.5">
                  <div>
                    <div className="font-display font-semibold">{j.title}</div>
                    <div className="text-xs text-muted-foreground">{j.department}</div>
                  </div>
                  <JdIndicator hasJd={j.has_jd} />
                </div>
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${STATUS_STYLE[j.status]}`}>{j.status.replace('_', ' ')}</span>
              </div>
              {j.location && <div className="text-xs text-muted-foreground flex items-center gap-1"><MapPin className="h-3 w-3" /> {j.location}</div>}
              <div className="flex items-center gap-3 text-sm">
                <button
                  className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors"
                  onClick={(e) => { e.stopPropagation(); navigate(`/jobs/${j.id}`); }}
                  data-testid={`job-view-pipeline-${j.id}`}
                >
                  <Users className="h-4 w-4" /> <span className="tabular-nums font-medium text-foreground">{j.candidate_count ?? 0}</span> active · View pipeline
                </button>
              </div>
              <div className="flex flex-wrap gap-1">
                {(j.stages || []).map((s) => <Badge key={s} variant="outline" className="text-[10px]">{s}</Badge>)}
              </div>
              <div className="flex gap-2 pt-1" onClick={(e) => e.stopPropagation()}>
                <Button size="sm" variant="outline" onClick={() => openEdit(j)} data-testid={`job-edit-${j.id}`}><Pencil className="h-3.5 w-3.5 mr-1" /> Edit</Button>
                {j.status === 'open' && <Button size="sm" variant="ghost" onClick={() => setStatus(j, 'on_hold')}>Hold</Button>}
                {j.status !== 'closed' && <Button size="sm" variant="ghost" onClick={() => setStatus(j, 'closed')}>Close</Button>}
                {j.status !== 'open' && <Button size="sm" variant="ghost" onClick={() => setStatus(j, 'open')}>Reopen</Button>}
                {user?.role === 'admin' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive ml-auto"
                    onClick={() => deleteJob(j)}
                    aria-label={`Delete ${j.title}`}
                    data-testid={`job-delete-${j.id}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>{editing ? 'Edit Job' : 'Create Job'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>Title *</Label>
              <Input value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="Senior Backend Engineer" data-testid="job-form-title" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Department *</Label>
                <Select value={form.department} onValueChange={(v) => setForm((f) => ({ ...f, department: v }))}>
                  <SelectTrigger data-testid="job-form-department"><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>{departments.map((d) => <SelectItem key={d.id} value={d.name}>{d.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Status</Label>
                <Select value={form.status} onValueChange={(v) => setForm((f) => ({ ...f, status: v }))}>
                  <SelectTrigger data-testid="job-form-status"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="open">Open</SelectItem>
                    <SelectItem value="on_hold">On Hold</SelectItem>
                    <SelectItem value="closed">Closed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>Location</Label>
              <Input value={form.location} onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))} placeholder="Remote (US)" data-testid="job-form-location" />
            </div>
            <div className="space-y-1.5">
              <Label>Description</Label>
              <Textarea rows={3} value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} data-testid="job-form-description" />
            </div>
            <div className="space-y-1.5">
              <Label>Pipeline stages (comma-separated, leave blank for default)</Label>
              <Input value={form.stages} onChange={(e) => setForm((f) => ({ ...f, stages: e.target.value }))} placeholder="Applied, Screening, Interview, Offer, Hired, Rejected" data-testid="job-form-stages" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={save} disabled={saving} data-testid="job-form-save">{editing ? 'Save Changes' : 'Create Job'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
