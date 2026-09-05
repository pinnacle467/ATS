import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Briefcase, FileText, MapPin, Pencil, Plus, Search, Trash2, UserCheck, Users } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useAuth } from '@/context/AuthContext';
import { api, errMsg } from '@/lib/api';
import { refreshJobs, useCachedDepartments, useCachedJobs } from '@/lib/referenceCache';

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
  const [allJobs] = useCachedJobs();
  const [departments] = useCachedDepartments();
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || 'all');
  const [search, setSearch] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [hiredCount, setHiredCount] = useState(null);

  useEffect(() => {
    api.get('/candidates', { params: { stage: 'Hired', limit: 1 } }).then((r) => setHiredCount(r.data.total)).catch(() => {});
  }, []);

  const jobs = useMemo(() => {
    let list = statusFilter === 'all' ? allJobs : allJobs.filter((j) => j.status === statusFilter);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((j) => j.title.toLowerCase().includes(q) || (j.department || '').toLowerCase().includes(q) || (j.location || '').toLowerCase().includes(q));
    }
    return list;
  }, [allJobs, statusFilter, search]);

  const totalApplicants = useMemo(() => allJobs.reduce((sum, j) => sum + (j.candidate_count || 0), 0), [allJobs]);
  const activeInPipeline = useMemo(() => allJobs.filter((j) => j.status === 'open').reduce((sum, j) => sum + (j.candidate_count || 0), 0), [allJobs]);
  const openCount = useMemo(() => allJobs.filter((j) => j.status === 'open').length, [allJobs]);
  const onHoldCount = useMemo(() => allJobs.filter((j) => j.status === 'on_hold').length, [allJobs]);
  const closedCount = useMemo(() => allJobs.filter((j) => j.status === 'closed').length, [allJobs]);

  const kpis = [
    { label: 'Open Roles', value: openCount, icon: Briefcase, bg: 'bg-blue-100 text-blue-700' },
    { label: 'Total Applicants', value: totalApplicants, icon: Users, bg: 'bg-violet-100 text-violet-700' },
    { label: 'Active in Pipeline', value: activeInPipeline, icon: UserCheck, bg: 'bg-amber-100 text-amber-700' },
    { label: 'Hired', value: hiredCount ?? '—', icon: Briefcase, bg: 'bg-emerald-100 text-emerald-700' },
  ];

  const STATUS_TABS = [
    { value: 'all', label: 'All Jobs', count: allJobs.length },
    { value: 'open', label: 'Open', count: openCount },
    { value: 'on_hold', label: 'On Hold', count: onHoldCount },
    { value: 'closed', label: 'Closed', count: closedCount },
  ];

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
      refreshJobs();
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
      refreshJobs();
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
      refreshJobs();
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
        <Button onClick={openCreate} data-testid="jobs-create-button"><Plus className="h-4 w-4 mr-1" /> New Job</Button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((k) => {
          const Icon = k.icon;
          return (
            <Card key={k.label} className="shadow-none" data-testid={`jobs-kpi-${k.label.toLowerCase().replace(/\s+/g, '-')}`}>
              <CardContent className="pt-5 pb-4">
                <span className={`h-9 w-9 rounded-lg flex items-center justify-center ${k.bg}`}>
                  <Icon className="h-4.5 w-4.5" />
                </span>
                <div className="font-display text-3xl font-semibold tabular-nums mt-3">{k.value}</div>
                <span className="text-xs text-muted-foreground font-medium">{k.label}</span>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Status tabs + search */}
      <div className="flex flex-wrap items-center gap-2">
        {STATUS_TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setStatusFilter(t.value)}
            data-testid={`jobs-status-tab-${t.value}`}
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${statusFilter === t.value ? 'bg-primary text-primary-foreground border-primary' : 'bg-card border-border text-muted-foreground hover:text-foreground'}`}
          >
            {t.label} <span className="tabular-nums opacity-80">{t.count}</span>
          </button>
        ))}
        <div className="relative flex-1 min-w-[200px] ml-auto max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search jobs by title, department..."
            className="pl-9 h-9"
            data-testid="jobs-search-input"
          />
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-secondary/50 hover:bg-secondary/50">
              <TableHead>Job Title</TableHead>
              <TableHead>Department</TableHead>
              <TableHead className="hidden sm:table-cell">Location</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Applicants</TableHead>
              <TableHead className="hidden lg:table-cell">Stages</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.length === 0 && (
              <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">No jobs found.</TableCell></TableRow>
            )}
            {jobs.map((j) => (
              <TableRow key={j.id} className="cursor-pointer" data-testid={`job-row-${j.id}`} onClick={() => navigate(`/jobs/${j.id}`)}>
                <TableCell>
                  <div className="flex items-center gap-1.5">
                    <span className="font-medium">{j.title}</span>
                    {j.job_code && (
                      <span className="text-[10px] font-mono font-normal text-muted-foreground bg-secondary rounded px-1.5 py-0.5" data-testid={`job-code-${j.id}`}>
                        {j.job_code}
                      </span>
                    )}
                    <JdIndicator hasJd={j.has_jd} />
                  </div>
                </TableCell>
                <TableCell className="text-sm">{j.department}</TableCell>
                <TableCell className="hidden sm:table-cell text-sm text-muted-foreground">
                  {j.location ? <span className="flex items-center gap-1"><MapPin className="h-3 w-3" /> {j.location}</span> : '—'}
                </TableCell>
                <TableCell>
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${STATUS_STYLE[j.status]}`}>{j.status.replace('_', ' ')}</span>
                </TableCell>
                <TableCell>
                  <button
                    className="flex items-center gap-1.5 text-muted-foreground hover:text-primary hover:underline transition-colors"
                    onClick={(e) => { e.stopPropagation(); navigate(`/jobs/${j.id}`); }}
                    data-testid={`job-view-pipeline-${j.id}`}
                  >
                    <Users className="h-4 w-4" /> <span className="tabular-nums font-medium text-foreground group-hover:text-primary">{j.candidate_count ?? 0}</span>
                  </button>
                </TableCell>
                <TableCell className="hidden lg:table-cell">
                  <div className="flex flex-wrap gap-1">
                    {(j.stages || []).slice(0, 3).map((s) => <Badge key={s} variant="outline" className="text-[10px]">{s}</Badge>)}
                    {(j.stages || []).length > 3 && <Badge variant="outline" className="text-[10px]">+{j.stages.length - 3}</Badge>}
                  </div>
                </TableCell>
                <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                  <div className="flex justify-end gap-1">
                    <Button size="icon" variant="ghost" onClick={() => openEdit(j)} aria-label={`Edit ${j.title}`} data-testid={`job-edit-${j.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                    {j.status === 'open' && <Button size="sm" variant="ghost" className="text-xs" onClick={() => setStatus(j, 'on_hold')}>Hold</Button>}
                    {j.status !== 'closed' && <Button size="sm" variant="ghost" className="text-xs" onClick={() => setStatus(j, 'closed')}>Close</Button>}
                    {j.status !== 'open' && <Button size="sm" variant="ghost" className="text-xs" onClick={() => setStatus(j, 'open')}>Reopen</Button>}
                    {['super_admin', 'admin'].includes(user?.role) && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="text-destructive hover:text-destructive"
                        onClick={() => deleteJob(j)}
                        aria-label={`Delete ${j.title}`}
                        data-testid={`job-delete-${j.id}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
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
