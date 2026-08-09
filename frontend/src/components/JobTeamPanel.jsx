import { useCallback, useEffect, useState } from 'react';
import { Plus, Shield, ShieldOff, Trash2, UserPlus, Users } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { useAuth } from '@/context/AuthContext';
import { api, errMsg } from '@/lib/api';
import { useCachedUsers } from '@/lib/referenceCache';
import { isAdminOrHigher, ROLE_LABELS } from '@/lib/roles';

const ROLE_ON_JOB_OPTIONS = [
  { value: 'interview_panel', label: 'Interview Panel', desc: 'Sees job & candidates on this job' },
  { value: 'vendor', label: 'Agency / Vendor', desc: 'Adds candidates; sees only their own' },
];

const ROLE_ON_JOB_LABELS = {
  interview_panel: 'Interview Panel',
  vendor: 'Agency / Vendor',
};

/**
 * JobTeamPanel — Admin+ tool to grant per-job access to interview_panel or
 * vendor users. Shows current team members and lets you add/remove and toggle
 * the salary_visible flag.
 */
export default function JobTeamPanel({ jobId }) {
  const { user: me } = useAuth();
  const [members, setMembers] = useState([]);
  const [allUsers] = useCachedUsers();
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ user_id: '', role_on_job: 'interview_panel', salary_visible: false });

  const canManage = isAdminOrHigher(me);
  // Only interview_panel / vendor role users can be added to a job team
  const candidates = allUsers.filter((u) => u.active !== false && ['interview_panel', 'vendor', 'interviewer'].includes(u.role));

  const load = useCallback(() => {
    if (!jobId || !canManage) {
      setLoading(false);
      return;
    }
    setLoading(true);
    api.get(`/jobs/${jobId}/team`)
      .then((team) => setMembers(team.data.members || []))
      .catch((e) => toast.error(errMsg(e, 'Failed to load team')))
      .finally(() => setLoading(false));
  }, [jobId, canManage]);

  useEffect(() => { load(); }, [load]);

  if (!canManage) return null; // Only Admin+ sees this panel

  const eligibleToAdd = candidates.filter((u) => !members.some((m) => m.user_id === u.id));

  const addMember = async () => {
    if (!form.user_id) return toast.error('Choose a user');
    try {
      await api.post(`/jobs/${jobId}/team`, form);
      toast.success('Team member added');
      setAddOpen(false);
      setForm({ user_id: '', role_on_job: 'interview_panel', salary_visible: false });
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const removeMember = async (m) => {
    if (!confirm(`Remove ${m.user_name || m.user_email} from this job?`)) return;
    try {
      await api.delete(`/jobs/${jobId}/team/${m.user_id}`);
      toast.success('Removed');
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const toggleSalary = async (m, next) => {
    try {
      await api.patch(`/jobs/${jobId}/team/${m.user_id}`, { salary_visible: next });
      toast.success(next ? 'Salary/budget now visible' : 'Salary/budget hidden');
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-3" data-testid="job-team-panel">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4" />
          <h3 className="font-semibold text-sm">Team & Access</h3>
          <Badge variant="secondary" className="text-[10px]">{members.length} member{members.length === 1 ? '' : 's'}</Badge>
        </div>
        <Button size="sm" onClick={() => setAddOpen(true)} data-testid="job-team-add-button">
          <UserPlus className="h-3.5 w-3.5 mr-1" /> Add
        </Button>
      </div>

      {loading && <p className="text-xs text-muted-foreground text-center py-3">Loading team…</p>}
      {!loading && members.length === 0 && (
        <p className="text-xs text-muted-foreground text-center py-4">
          No team members added yet. Interview Panel &amp; Vendor users see this job only after being added here.
        </p>
      )}
      {!loading && members.length > 0 && (
        <div className="space-y-1.5">
          {members.map((m) => (
            <div key={m.user_id} className="flex items-center gap-3 rounded-lg border border-border p-2.5 bg-card" data-testid={`job-team-member-${m.user_id}`}>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{m.user_name || m.user_email || 'Unknown user'}</div>
                <div className="text-xs text-muted-foreground truncate">
                  {m.user_email} · <span className="capitalize">{ROLE_ON_JOB_LABELS[m.role_on_job] || m.role_on_job}</span>
                  {m.user_role && m.user_role !== m.role_on_job && (
                    <span className="ml-1 text-[10px] opacity-75">({ROLE_LABELS[m.user_role] || m.user_role})</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <div className="flex items-center gap-1.5" title="Can view salary / budget on this job">
                  {m.salary_visible ? <Shield className="h-3.5 w-3.5 text-emerald-600" /> : <ShieldOff className="h-3.5 w-3.5 text-muted-foreground" />}
                  <Switch
                    checked={!!m.salary_visible}
                    onCheckedChange={(v) => toggleSalary(m, v)}
                    aria-label="Toggle salary visibility"
                    data-testid={`job-team-salary-${m.user_id}`}
                  />
                  <span className="text-[10px] text-muted-foreground hidden sm:inline">$$</span>
                </div>
                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => removeMember(m)} data-testid={`job-team-remove-${m.user_id}`}>
                  <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Add team member to this job</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>User</Label>
              <Select value={form.user_id} onValueChange={(v) => setForm((f) => ({ ...f, user_id: v }))}>
                <SelectTrigger data-testid="job-team-user-select"><SelectValue placeholder={eligibleToAdd.length ? 'Choose a user' : 'No eligible users — create Interview Panel or Vendor users in Admin'} /></SelectTrigger>
                <SelectContent>
                  {eligibleToAdd.map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      <div className="flex flex-col">
                        <span>{u.name}</span>
                        <span className="text-[10px] text-muted-foreground">{u.email} · {ROLE_LABELS[u.role] || u.role}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {eligibleToAdd.length === 0 && (
                <p className="text-[11px] text-muted-foreground">Create Interview Panel / Vendor users in Admin → Users first.</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label>Access level on this job</Label>
              <Select value={form.role_on_job} onValueChange={(v) => setForm((f) => ({ ...f, role_on_job: v }))}>
                <SelectTrigger data-testid="job-team-role-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ROLE_ON_JOB_OPTIONS.map((r) => (
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
            <div className="flex items-center gap-3 rounded-lg border border-border p-3 bg-secondary/40">
              <Switch
                checked={form.salary_visible}
                onCheckedChange={(v) => setForm((f) => ({ ...f, salary_visible: v }))}
                data-testid="job-team-salary-switch"
              />
              <div className="flex-1">
                <div className="text-sm font-medium">Show salary / budget</div>
                <div className="text-xs text-muted-foreground">Grants access to salary range and budget for this job only.</div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button onClick={addMember} data-testid="job-team-add-confirm">
              <Plus className="h-4 w-4 mr-1" /> Add
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
