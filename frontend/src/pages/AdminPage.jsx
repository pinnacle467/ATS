import { useCallback, useEffect, useState } from 'react';
import { ArrowDown, ArrowUp, BookOpen, Plus, Trash2, UserPlus } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { useAuth } from '@/context/AuthContext';
import { api, errMsg } from '@/lib/api';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// New 4-role model. Keep legacy names as fallback labels.
const ROLE_OPTIONS = [
  { value: 'super_admin', label: 'Super Admin', desc: 'Full unrestricted access' },
  { value: 'admin', label: 'Admin', desc: 'Manages jobs, candidates, users (except Super Admins)' },
  { value: 'interview_panel', label: 'Interview Panel', desc: 'Job-limited access; no salary/budget' },
  { value: 'vendor', label: 'Agency / Vendor', desc: 'Job-limited access; own submissions only' },
];
const ROLE_LABELS = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  interview_panel: 'Interview Panel',
  vendor: 'Agency / Vendor',
  // legacy
  recruiter: 'Admin (legacy)',
  interviewer: 'Interview Panel (legacy)',
};

function assignableRolesForActor(actorRole) {
  // Super Admin can assign any role; Admin can assign anything except super_admin
  if (actorRole === 'super_admin') return ROLE_OPTIONS;
  return ROLE_OPTIONS.filter((r) => r.value !== 'super_admin');
}

function UsersTab() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'admin', title: '' });

  const assignable = assignableRolesForActor(me?.role);

  const load = useCallback(() => {
    api.get('/users').then((r) => setUsers(r.data)).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const invite = async () => {
    if (!form.name.trim()) return toast.error('Name is required');
    if (!EMAIL_RE.test(form.email)) return toast.error('Valid email is required');
    if (form.password.length < 6) return toast.error('Password must be at least 6 characters');
    try {
      await api.post('/users', form);
      toast.success(`${form.name} invited as ${ROLE_LABELS[form.role] || form.role}`);
      setInviteOpen(false);
      setForm({ name: '', email: '', password: '', role: 'admin', title: '' });
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const setRole = async (u, role) => {
    try {
      await api.put(`/users/${u.id}`, { role });
      toast.success(`${u.name} is now ${ROLE_LABELS[role] || role}`);
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const setActive = async (u, active) => {
    try {
      await api.put(`/users/${u.id}`, { active });
      toast.success(`${u.name} ${active ? 'activated' : 'deactivated'}`);
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const remove = async (u) => {
    if (!window.confirm(`Remove ${u.name}? This cannot be undone.`)) return;
    try {
      await api.delete(`/users/${u.id}`);
      toast.success('User removed');
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button onClick={() => setInviteOpen(true)} data-testid="admin-invite-user-button"><UserPlus className="h-4 w-4 mr-1" /> Invite User</Button>
      </div>
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <Table data-testid="admin-users-table">
          <TableHeader>
            <TableRow className="bg-secondary/50 hover:bg-secondary/50">
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Role</TableHead>
              <TableHead className="hidden md:table-cell">Last Login</TableHead>
              <TableHead>Active</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((u) => (
              <TableRow key={u.id} data-testid={`admin-user-row-${u.id}`}>
                <TableCell>
                  <div className="font-medium">{u.name}</div>
                  <div className="text-xs text-muted-foreground">{u.title || ''}</div>
                </TableCell>
                <TableCell className="text-sm">{u.email}</TableCell>
                <TableCell>
                  <Select
                    value={u.role}
                    onValueChange={(v) => setRole(u, v)}
                    disabled={u.id === me?.id || (u.role === 'super_admin' && me?.role !== 'super_admin')}
                  >
                    <SelectTrigger className="w-[170px] h-8" data-testid={`admin-user-role-${u.id}`}>
                      <SelectValue>{ROLE_LABELS[u.role] || u.role}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {assignable.map((r) => (
                        <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell className="hidden md:table-cell text-xs font-mono text-muted-foreground">
                  {u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}
                </TableCell>
                <TableCell>
                  <Switch checked={u.active !== false} onCheckedChange={(v) => setActive(u, v)} disabled={u.id === me?.id} data-testid={`admin-user-active-${u.id}`} aria-label={`Toggle ${u.name} active`} />
                </TableCell>
                <TableCell>
                  {u.id !== me?.id && (
                    <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => remove(u)} aria-label={`Remove ${u.name}`} data-testid={`admin-user-delete-${u.id}`}>
                      <Trash2 className="h-4 w-4 text-muted-foreground" />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Invite User</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5"><Label>Name *</Label><Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} data-testid="invite-name-input" /></div>
            <div className="space-y-1.5"><Label>Email *</Label><Input type="email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} data-testid="invite-email-input" /></div>
            <div className="space-y-1.5"><Label>Temporary password *</Label><Input type="text" value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} data-testid="invite-password-input" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Role</Label>
                <Select value={form.role} onValueChange={(v) => setForm((f) => ({ ...f, role: v }))}>
                  <SelectTrigger data-testid="invite-role-select"><SelectValue>{ROLE_LABELS[form.role] || form.role}</SelectValue></SelectTrigger>
                  <SelectContent>
                    {assignable.map((r) => (
                      <SelectItem key={r.value} value={r.value}>
                        <div className="flex flex-col">
                          <span>{r.label}</span>
                          <span className="text-[10px] text-muted-foreground">{r.desc}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Title</Label><Input value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="Recruiter" /></div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setInviteOpen(false)}>Cancel</Button>
            <Button onClick={invite} data-testid="invite-submit-button">Send Invite</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PipelineTab() {
  const [stages, setStages] = useState([]);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    api.get('/settings/pipeline').then((r) => setStages(r.data.stages || [])).catch(() => {});
  }, []);

  const move = (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= stages.length) return;
    const x = [...stages];
    [x[i], x[j]] = [x[j], x[i]];
    setStages(x);
    setDirty(true);
  };

  const save = async () => {
    if (stages.some((s) => !s.name.trim())) return toast.error('Stage names cannot be empty');
    try {
      await api.put('/settings/pipeline', { stages });
      toast.success('Pipeline stages saved');
      setDirty(false);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <Card className="shadow-none">
      <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
        <CardTitle className="text-sm font-semibold">Global Pipeline Stages</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => { setStages((s) => [...s, { name: 'New Stage', scorecard_attributes: [] }]); setDirty(true); }} data-testid="pipeline-add-stage-button">
            <Plus className="h-4 w-4 mr-1" /> Add Stage
          </Button>
          <Button size="sm" onClick={save} disabled={!dirty} data-testid="pipeline-save-button">Save Changes</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-xs text-muted-foreground">Stage order defines the pipeline. Scorecard attributes per stage drive the feedback form. New jobs inherit these stages; per-job stages can be customized on the job itself.</p>
        {stages.map((s, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 border border-border rounded-lg p-2.5" data-testid={`pipeline-stage-row-${i}`}>
            <div className="flex flex-col gap-0.5">
              <button onClick={() => move(i, -1)} disabled={i === 0} className="disabled:opacity-30" aria-label="Move up"><ArrowUp className="h-3.5 w-3.5" /></button>
              <button onClick={() => move(i, 1)} disabled={i === stages.length - 1} className="disabled:opacity-30" aria-label="Move down"><ArrowDown className="h-3.5 w-3.5" /></button>
            </div>
            <Input
              className="h-8 w-40"
              value={s.name}
              onChange={(e) => { const x = [...stages]; x[i] = { ...x[i], name: e.target.value }; setStages(x); setDirty(true); }}
              data-testid={`pipeline-stage-name-${i}`}
            />
            <Input
              className="h-8 flex-1 min-w-[200px]"
              placeholder="Scorecard attributes (comma-separated)"
              value={(s.scorecard_attributes || []).join(', ')}
              onChange={(e) => { const x = [...stages]; x[i] = { ...x[i], scorecard_attributes: e.target.value.split(',').map((a) => a.trim()).filter(Boolean) }; setStages(x); setDirty(true); }}
            />
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => { setStages(stages.filter((_, j) => j !== i)); setDirty(true); }} aria-label="Remove stage">
              <Trash2 className="h-4 w-4 text-muted-foreground" />
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function DepartmentsTagsTab() {
  const [departments, setDepartments] = useState([]);
  const [tags, setTags] = useState([]);
  const [newDep, setNewDep] = useState('');
  const [newTag, setNewTag] = useState('');

  const load = useCallback(() => {
    api.get('/departments').then((r) => setDepartments(r.data)).catch(() => {});
    api.get('/tags').then((r) => setTags(r.data)).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card className="shadow-none">
        <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Departments</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div className="flex gap-2">
            <Input value={newDep} onChange={(e) => setNewDep(e.target.value)} placeholder="New department" className="h-9" data-testid="admin-new-department-input" />
            <Button
              size="sm"
              className="h-9"
              data-testid="admin-add-department-button"
              onClick={async () => {
                if (!newDep.trim()) return;
                try {
                  await api.post('/departments', { name: newDep.trim() });
                  setNewDep('');
                  toast.success('Department added');
                  load();
                } catch (e) { toast.error(errMsg(e)); }
              }}
            >Add</Button>
          </div>
          {departments.map((d) => (
            <div key={d.id} className="flex items-center justify-between border border-border rounded-lg px-3 py-2">
              <span className="text-sm">{d.name}</span>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={async () => { await api.delete(`/departments/${d.id}`); load(); }} aria-label={`Delete ${d.name}`}>
                <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>
      <Card className="shadow-none">
        <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Tags</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div className="flex gap-2">
            <Input value={newTag} onChange={(e) => setNewTag(e.target.value)} placeholder="New tag" className="h-9" data-testid="admin-new-tag-input" />
            <Button
              size="sm"
              className="h-9"
              data-testid="admin-add-tag-button"
              onClick={async () => {
                if (!newTag.trim()) return;
                try {
                  await api.post('/tags', { name: newTag.trim() });
                  setNewTag('');
                  toast.success('Tag added');
                  load();
                } catch (e) { toast.error(errMsg(e)); }
              }}
            >Add</Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {tags.map((t) => (
              <Badge key={t.id} variant="secondary" className="gap-1.5 py-1">
                {t.name}
                <button onClick={async () => { await api.delete(`/tags/${t.id}`); load(); }} aria-label={`Delete tag ${t.name}`} className="hover:text-destructive">×</button>
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function KitsTab() {
  const [kits, setKits] = useState([]);
  const [stages, setStages] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ stage: '', title: '', questions: '', guidelines: '' });

  const load = useCallback(() => {
    api.get('/interview-kits').then((r) => setKits(r.data)).catch(() => {});
    api.get('/settings/pipeline').then((r) => setStages((r.data.stages || []).map((s) => s.name))).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!form.stage || !form.title.trim()) return toast.error('Stage and title are required');
    const body = { stage: form.stage, title: form.title, questions: form.questions.split('\n').map((q) => q.trim()).filter(Boolean), guidelines: form.guidelines || null };
    try {
      if (editing) await api.put(`/interview-kits/${editing.id}`, body);
      else await api.post('/interview-kits', body);
      toast.success('Interview kit saved');
      setOpen(false);
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button onClick={() => { setEditing(null); setForm({ stage: '', title: '', questions: '', guidelines: '' }); setOpen(true); }} data-testid="admin-add-kit-button">
          <BookOpen className="h-4 w-4 mr-1" /> New Kit
        </Button>
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        {kits.length === 0 && <p className="text-sm text-muted-foreground md:col-span-2 text-center py-6">No interview kits yet.</p>}
        {kits.map((k) => (
          <Card key={k.id} className="shadow-none">
            <CardContent className="pt-5 space-y-2">
              <div className="flex items-center justify-between">
                <div className="font-medium text-sm">{k.title}</div>
                <Badge variant="secondary">{k.stage}</Badge>
              </div>
              {k.guidelines && <p className="text-xs text-muted-foreground">{k.guidelines}</p>}
              <ul className="text-xs space-y-1 list-disc list-inside text-muted-foreground">
                {(k.questions || []).slice(0, 3).map((q, i) => <li key={i}>{q}</li>)}
                {(k.questions || []).length > 3 && <li>+{k.questions.length - 3} more</li>}
              </ul>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => { setEditing(k); setForm({ stage: k.stage, title: k.title, questions: (k.questions || []).join('\n'), guidelines: k.guidelines || '' }); setOpen(true); }}>Edit</Button>
                <Button size="sm" variant="ghost" onClick={async () => { await api.delete(`/interview-kits/${k.id}`); load(); }}>Delete</Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>{editing ? 'Edit Kit' : 'New Interview Kit'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Stage *</Label>
                <Select value={form.stage} onValueChange={(v) => setForm((f) => ({ ...f, stage: v }))}>
                  <SelectTrigger data-testid="kit-stage-select"><SelectValue placeholder="Select stage" /></SelectTrigger>
                  <SelectContent>{stages.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5"><Label>Title *</Label><Input value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} data-testid="kit-title-input" /></div>
            </div>
            <div className="space-y-1.5"><Label>Questions (one per line)</Label><Textarea rows={5} value={form.questions} onChange={(e) => setForm((f) => ({ ...f, questions: e.target.value }))} data-testid="kit-questions-textarea" /></div>
            <div className="space-y-1.5"><Label>Guidelines</Label><Textarea rows={2} value={form.guidelines} onChange={(e) => setForm((f) => ({ ...f, guidelines: e.target.value }))} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save} data-testid="kit-save-button">Save Kit</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AuditTab() {
  const [logs, setLogs] = useState([]);
  const [action, setAction] = useState('all');

  useEffect(() => {
    const params = action !== 'all' ? { action } : {};
    api.get('/audit-log', { params }).then((r) => setLogs(r.data)).catch(() => {});
  }, [action]);

  const actions = ['login', 'stage_change', 'user_created', 'role_changed', 'user_deactivated', 'user_deleted', 'candidate_deleted', 'job_created', 'job_updated', 'pipeline_updated', 'candidates_exported'];

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Select value={action} onValueChange={setAction}>
          <SelectTrigger className="w-[200px] h-9 bg-card" data-testid="audit-filter-action"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All actions</SelectItem>
            {actions.map((a) => <SelectItem key={a} value={a}>{a.replace(/_/g, ' ')}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <Table data-testid="admin-audit-log-table">
          <TableHeader>
            <TableRow className="bg-secondary/50 hover:bg-secondary/50">
              <TableHead>Time</TableHead>
              <TableHead>Actor</TableHead>
              <TableHead>Action</TableHead>
              <TableHead className="hidden md:table-cell">Entity</TableHead>
              <TableHead className="hidden md:table-cell">Details</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {logs.length === 0 && <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground text-sm">No audit entries.</TableCell></TableRow>}
            {logs.map((l) => (
              <TableRow key={l.id}>
                <TableCell className="text-xs font-mono text-muted-foreground whitespace-nowrap">{new Date(l.created_at).toLocaleString()}</TableCell>
                <TableCell className="text-sm">{l.actor_name}</TableCell>
                <TableCell><Badge variant="secondary" className="text-xs">{l.action.replace(/_/g, ' ')}</Badge></TableCell>
                <TableCell className="hidden md:table-cell text-xs text-muted-foreground">{l.entity_type}</TableCell>
                <TableCell className="hidden md:table-cell text-xs">{l.details}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function IndustryBackfillTab() {
  const [task, setTask] = useState(null);
  const [force, setForce] = useState(false);

  const poll = useCallback(async () => {
    try {
      const r = await api.get('/candidates/backfill-industry/status');
      setTask(r.data);
      return r.data;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => { poll(); }, [poll]);

  useEffect(() => {
    if (task?.status !== 'running') return undefined;
    const t = setInterval(async () => {
      const s = await poll();
      if (!s || s.status !== 'running') {
        clearInterval(t);
        if (s?.status === 'done') {
          toast.success(`Backfill complete — updated ${s.updated} of ${s.processed} candidates`);
        } else if (s?.status === 'error') {
          toast.error('Industry backfill failed — check server logs');
        }
      }
    }, 2000);
    return () => clearInterval(t);
  }, [task?.status, poll]);

  const start = async () => {
    try {
      const r = await api.post('/candidates/backfill-industry', null, { params: { force } });
      setTask(r.data);
      if (r.data?.already_running) toast.message('A backfill is already running');
      else toast.info(force ? 'Backfill started — recomputing industry for all non-manual candidates' : 'Backfill started — filling in candidates with no industry yet');
    } catch (e) {
      toast.error(errMsg(e, 'Could not start backfill'));
    }
  };

  const running = task?.status === 'running';

  return (
    <div className="space-y-4 max-w-2xl">
      <Card className="shadow-none">
        <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Backfill Candidate Industries</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Uses AI to classify each candidate&apos;s industry (FinTech, Healthcare, SaaS, etc.) from their resume/work history.
            Candidates whose industry was manually corrected are never overwritten.
          </p>
          <label className="flex items-start gap-2 text-xs cursor-pointer">
            <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} className="mt-0.5" data-testid="backfill-force-checkbox" />
            <span>Recompute for ALL candidates without a manual correction (not just ones with no industry yet)</span>
          </label>
          <Button onClick={start} disabled={running} data-testid="backfill-industry-start-button">
            {running ? `Running ${task?.processed || 0}/${task?.total || '…'}...` : 'Run Backfill'}
          </Button>
          {task && task.status !== 'idle' && (
            <div className="text-xs text-muted-foreground space-y-0.5 pt-2 border-t border-border" data-testid="backfill-industry-status">
              <p>Status: <span className="font-medium text-foreground">{task.status}</span></p>
              <p>Processed: {task.processed || 0} / {task.total || 0}</p>
              <p>Updated: {task.updated || 0} · No evidence found: {task.skipped_no_evidence || 0} · Errors: {(task.errors || []).length}</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function AdminPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Admin Panel</h1>
        <p className="text-sm text-muted-foreground">Users, pipeline configuration, org settings, and audit trail.</p>
      </div>
      <Tabs defaultValue="users" data-testid="admin-tabs">
        <TabsList>
          <TabsTrigger value="users" data-testid="admin-tab-users">Users</TabsTrigger>
          <TabsTrigger value="pipeline" data-testid="admin-tab-pipeline">Pipeline Stages</TabsTrigger>
          <TabsTrigger value="org" data-testid="admin-tab-org">Departments & Tags</TabsTrigger>
          <TabsTrigger value="kits" data-testid="admin-tab-kits">Interview Kits</TabsTrigger>
          <TabsTrigger value="audit" data-testid="admin-tab-audit">Audit Log</TabsTrigger>
          <TabsTrigger value="data" data-testid="admin-tab-data">Data Tools</TabsTrigger>
        </TabsList>
        <TabsContent value="users" className="mt-4"><UsersTab /></TabsContent>
        <TabsContent value="pipeline" className="mt-4"><PipelineTab /></TabsContent>
        <TabsContent value="org" className="mt-4"><DepartmentsTagsTab /></TabsContent>
        <TabsContent value="kits" className="mt-4"><KitsTab /></TabsContent>
        <TabsContent value="audit" className="mt-4"><AuditTab /></TabsContent>
        <TabsContent value="data" className="mt-4"><IndustryBackfillTab /></TabsContent>
      </Tabs>
    </div>
  );
}
