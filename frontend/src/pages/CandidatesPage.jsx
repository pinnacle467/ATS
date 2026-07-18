import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Download, FileSpreadsheet, FileText, Kanban, List, Search, UserPlus, X } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import KanbanBoard from '@/components/KanbanBoard';
import { useAuth } from '@/context/AuthContext';
import { api, errMsg } from '@/lib/api';

export const SOURCES = [
  { value: 'referral', label: 'Referral' },
  { value: 'job_board', label: 'Job Board' },
  { value: 'career_site', label: 'Career Site' },
  { value: 'linkedin', label: 'LinkedIn' },
];

const STAGE_BADGE = {
  Applied: 'bg-sky-100 text-sky-800',
  Screening: 'bg-amber-100 text-amber-800',
  Interview: 'bg-violet-100 text-violet-800',
  Offer: 'bg-emerald-100 text-emerald-800',
  Hired: 'bg-green-100 text-green-800',
  Rejected: 'bg-red-100 text-red-800',
};

export const StageBadge = ({ stage }) => (
  <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${STAGE_BADGE[stage] || 'bg-secondary text-foreground'}`}>{stage}</span>
);

export const REJECTION_REASONS = ['Not Fit', 'No Response', 'Offer Declined', 'Out of Budget'];

export const ResumeIndicator = ({ hasResume, className = '' }) => (
  <span title={hasResume ? 'Resume attached' : 'No resume on file'} className="inline-flex">
    <FileText
      className={`h-3.5 w-3.5 shrink-0 ${hasResume ? 'text-primary' : 'text-muted-foreground/30'} ${className}`}
      aria-label={hasResume ? 'Resume attached' : 'No resume on file'}
      data-testid={hasResume ? 'resume-indicator-yes' : 'resume-indicator-no'}
    />
  </span>
);

export default function CandidatesPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [view, setView] = useState(() => localStorage.getItem('ats_view') || 'table');
  const [data, setData] = useState({ items: [], total: 0 });
  const [jobs, setJobs] = useState([]);
  const [users, setUsers] = useState([]);
  const [tags, setTags] = useState([]);
  const [stages, setStages] = useState(['Applied', 'Screening', 'Interview', 'Offer', 'Hired', 'Rejected']);
  const [q, setQ] = useState(searchParams.get('q') || '');
  const [filters, setFilters] = useState({
    job_id: searchParams.get('job_id') || 'all',
    stage: searchParams.get('stage') || 'all',
    source: searchParams.get('source') || 'all',
    recruiter_id: 'all',
    tag: 'all',
  });
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState([]);
  const [loading, setLoading] = useState(true);
  const [bulkDialog, setBulkDialog] = useState(null); // {action}
  const [bulkValue, setBulkValue] = useState('');
  const [bulkReason, setBulkReason] = useState('');
  const [bulkRejectCategory, setBulkRejectCategory] = useState('');
  const [kanbanReject, setKanbanReject] = useState(null);
  const [kanbanRejectCategory, setKanbanRejectCategory] = useState('');
  const [kanbanRejectDetail, setKanbanRejectDetail] = useState('');

  const isRecruiter = user?.role === 'admin' || user?.role === 'recruiter';
  const limit = view === 'kanban' ? 500 : 25;

  useEffect(() => {
    Promise.all([api.get('/jobs'), api.get('/users'), api.get('/tags'), api.get('/settings/pipeline')])
      .then(([j, u, t, p]) => {
        setJobs(j.data);
        setUsers(u.data);
        setTags(t.data);
        if (p.data?.stages?.length) setStages(p.data.stages.map((s) => s.name));
      })
      .catch(() => {});
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    const params = { page, limit };
    if (q) params.q = q;
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== 'all') params[k] = v;
    });
    api
      .get('/candidates', { params })
      .then((r) => setData(r.data))
      .catch((e) => toast.error(errMsg(e)))
      .finally(() => setLoading(false));
  }, [q, filters, page, limit]);

  useEffect(() => {
    const t = setTimeout(load, q ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  const setViewPersist = (v) => {
    setView(v);
    localStorage.setItem('ats_view', v);
  };

  const activeFilterChips = Object.entries(filters).filter(([, v]) => v !== 'all');

  const onMove = async (cand, stage) => {
    if (stage === 'Rejected') {
      setKanbanReject(cand);
      setKanbanRejectCategory('');
      setKanbanRejectDetail('');
      return;
    }
    // optimistic
    setData((d) => ({ ...d, items: d.items.map((c) => (c.id === cand.id ? { ...c, stage } : c)) }));
    try {
      await api.post(`/candidates/${cand.id}/move-stage`, { stage });
      toast.success(`${cand.name} moved to ${stage}`);
    } catch (e) {
      toast.error(errMsg(e));
      load();
    }
  };

  const confirmKanbanReject = async () => {
    if (!kanbanRejectCategory) {
      toast.error('Please choose a rejection reason');
      return;
    }
    if (kanbanRejectCategory === 'Not Fit' && !kanbanRejectDetail.trim()) {
      toast.error('Please provide details for Not Fit');
      return;
    }
    const reason = kanbanRejectCategory === 'Not Fit' ? `Not Fit: ${kanbanRejectDetail.trim()}` : kanbanRejectCategory;
    try {
      await api.post(`/candidates/${kanbanReject.id}/move-stage`, { stage: 'Rejected', reason });
      toast.success(`${kanbanReject.name} moved to Rejected`);
      setKanbanReject(null);
      setKanbanRejectCategory('');
      setKanbanRejectDetail('');
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const runBulk = async () => {
    const action = bulkDialog;
    const body = { candidate_ids: selected, action };
    if (action === 'move_stage') body.stage = bulkValue;
    if (action === 'tag') body.tag = bulkValue;
    if (action === 'assign') body.recruiter_id = bulkValue;
    if ((action === 'move_stage' || action === 'tag' || action === 'assign') && !bulkValue) {
      toast.error('Please choose a value');
      return;
    }
    if (action === 'reject') {
      if (!bulkRejectCategory) {
        toast.error('Please choose a rejection reason');
        return;
      }
      if (bulkRejectCategory === 'Not Fit' && !bulkReason.trim()) {
        toast.error('Please provide details for Not Fit');
        return;
      }
      body.reason = bulkRejectCategory === 'Not Fit' ? `Not Fit: ${bulkReason.trim()}` : bulkRejectCategory;
    }
    try {
      const r = await api.post('/candidates/bulk-action', body);
      toast.success(`Updated ${r.data.count} candidate${r.data.count === 1 ? '' : 's'}`);
      setSelected([]);
      setBulkDialog(null);
      setBulkValue('');
      setBulkReason('');
      setBulkRejectCategory('');
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const exportCsv = async () => {
    try {
      const params = {};
      if (q) params.q = q;
      Object.entries(filters).forEach(([k, v]) => {
        if (v !== 'all') params[k] = v;
      });
      const r = await api.get('/candidates/export/csv', { params, responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'candidates.csv';
      a.click();
      URL.revokeObjectURL(url);
      toast.success('CSV export downloaded');
    } catch (e) {
      toast.error(errMsg(e, 'Export failed'));
    }
  };

  const totalPages = Math.max(1, Math.ceil(data.total / limit));

  const recruiters = useMemo(() => users.filter((u) => u.role === 'recruiter' || u.role === 'admin'), [users]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Candidates</h1>
          <p className="text-sm text-muted-foreground">{data.total} candidate{data.total === 1 ? '' : 's'} {user?.role === 'interviewer' ? 'assigned to you' : 'in pipeline'}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-border overflow-hidden" data-testid="kanban-view-toggle">
            <button
              onClick={() => setViewPersist('table')}
              data-testid="view-toggle-table"
              className={`px-3 py-1.5 text-sm flex items-center gap-1.5 transition-colors ${view === 'table' ? 'bg-primary text-primary-foreground' : 'bg-card hover:bg-secondary'}`}
            >
              <List className="h-4 w-4" /> Table
            </button>
            <button
              onClick={() => setViewPersist('kanban')}
              data-testid="view-toggle-kanban"
              className={`px-3 py-1.5 text-sm flex items-center gap-1.5 transition-colors ${view === 'kanban' ? 'bg-primary text-primary-foreground' : 'bg-card hover:bg-secondary'}`}
            >
              <Kanban className="h-4 w-4" /> Kanban
            </button>
          </div>
          {isRecruiter && (
            <>
              <Button variant="outline" onClick={exportCsv} data-testid="candidates-export-csv-button">
                <Download className="h-4 w-4 mr-1" /> CSV
              </Button>
              <Button variant="outline" onClick={() => navigate('/candidates/import')} data-testid="candidates-import-button">
                <FileSpreadsheet className="h-4 w-4 mr-1" /> Import from Excel/CSV
              </Button>
              <Button onClick={() => navigate('/candidates/new')} data-testid="candidates-add-button">
                <UserPlus className="h-4 w-4 mr-1" /> Add Candidate
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 bg-card border border-border rounded-xl p-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            data-testid="candidates-search-input"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder="Search name, email, title, skills..."
            className="pl-9 h-9"
          />
        </div>
        <Select value={filters.job_id} onValueChange={(v) => { setFilters((f) => ({ ...f, job_id: v })); setPage(1); }}>
          <SelectTrigger className="w-[170px] h-9" data-testid="candidates-filter-job-select"><SelectValue placeholder="Job" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All jobs</SelectItem>
            {jobs.map((j) => <SelectItem key={j.id} value={j.id}>{j.title}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filters.stage} onValueChange={(v) => { setFilters((f) => ({ ...f, stage: v })); setPage(1); }}>
          <SelectTrigger className="w-[140px] h-9" data-testid="candidates-filter-stage-select"><SelectValue placeholder="Stage" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All stages</SelectItem>
            {stages.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filters.source} onValueChange={(v) => { setFilters((f) => ({ ...f, source: v })); setPage(1); }}>
          <SelectTrigger className="w-[140px] h-9" data-testid="candidates-filter-source-select"><SelectValue placeholder="Source" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All sources</SelectItem>
            {SOURCES.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filters.recruiter_id} onValueChange={(v) => { setFilters((f) => ({ ...f, recruiter_id: v })); setPage(1); }}>
          <SelectTrigger className="w-[150px] h-9" data-testid="candidates-filter-owner-select"><SelectValue placeholder="Recruiter" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All recruiters</SelectItem>
            {recruiters.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filters.tag} onValueChange={(v) => { setFilters((f) => ({ ...f, tag: v })); setPage(1); }}>
          <SelectTrigger className="w-[130px] h-9" data-testid="candidates-filter-tag-select"><SelectValue placeholder="Tag" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All tags</SelectItem>
            {tags.map((t) => <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>)}
          </SelectContent>
        </Select>
        {activeFilterChips.length > 0 && (
          <Button variant="ghost" size="sm" className="h-9" onClick={() => { setFilters({ job_id: 'all', stage: 'all', source: 'all', recruiter_id: 'all', tag: 'all' }); setQ(''); setPage(1); }}>
            <X className="h-4 w-4 mr-1" /> Clear
          </Button>
        )}
      </div>

      {/* Bulk actions bar */}
      {selected.length > 0 && isRecruiter && (
        <div className="flex flex-wrap items-center gap-2 bg-accent border border-border rounded-xl px-4 py-2.5" data-testid="candidates-bulk-actions-bar">
          <span className="text-sm font-medium text-accent-foreground">{selected.length} selected</span>
          <div className="flex gap-2 ml-auto">
            <Button size="sm" variant="outline" className="bg-card" onClick={() => setBulkDialog('move_stage')} data-testid="bulk-move-stage-button">Move Stage</Button>
            <Button size="sm" variant="outline" className="bg-card" onClick={() => setBulkDialog('tag')} data-testid="bulk-tag-button">Tag</Button>
            <Button size="sm" variant="outline" className="bg-card" onClick={() => setBulkDialog('assign')} data-testid="bulk-assign-button">Assign</Button>
            <Button size="sm" variant="destructive" onClick={() => { setBulkRejectCategory(''); setBulkReason(''); setBulkDialog('reject'); }} data-testid="bulk-reject-button">Reject</Button>
            {user?.role === 'admin' && (
              <Button size="sm" variant="destructive" onClick={() => setBulkDialog('delete')} data-testid="bulk-delete-button">Delete</Button>
            )}
          </div>
        </div>
      )}

      {/* Content */}
      {view === 'kanban' ? (
        <KanbanBoard stages={stages} candidates={data.items} onMove={onMove} canDrag={isRecruiter} />
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="bg-secondary/50 hover:bg-secondary/50">
                {isRecruiter && (
                  <TableHead className="w-10">
                    <Checkbox
                      data-testid="candidates-select-all"
                      checked={selected.length > 0 && selected.length === data.items.length}
                      onCheckedChange={(ck) => setSelected(ck ? data.items.map((c) => c.id) : [])}
                      aria-label="Select all"
                    />
                  </TableHead>
                )}
                <TableHead>Candidate</TableHead>
                <TableHead className="hidden sm:table-cell">ID</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead className="hidden md:table-cell">Source</TableHead>
                <TableHead className="hidden md:table-cell">Recruiter</TableHead>
                <TableHead className="hidden lg:table-cell">Notice Period</TableHead>
                <TableHead className="hidden lg:table-cell">Tags</TableHead>
                <TableHead className="hidden lg:table-cell">Applied</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow><TableCell colSpan={10} className="text-center py-10 text-muted-foreground">Loading candidates...</TableCell></TableRow>
              )}
              {!loading && data.items.length === 0 && (
                <TableRow><TableCell colSpan={10} className="text-center py-10 text-muted-foreground">No candidates found. Try adjusting filters.</TableCell></TableRow>
              )}
              {!loading && data.items.map((c) => (
                <TableRow key={c.id} className="cursor-pointer" data-testid={`candidate-row-${c.id}`} onClick={() => navigate(`/candidates/${c.id}`)}>
                  {isRecruiter && (
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selected.includes(c.id)}
                        onCheckedChange={(ck) => setSelected((s) => (ck ? [...s, c.id] : s.filter((x) => x !== c.id)))}
                        aria-label={`Select ${c.name}`}
                        data-testid={`candidate-select-${c.id}`}
                      />
                    </TableCell>
                  )}
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium">{c.name}</span>
                      <ResumeIndicator hasResume={!!c.resume_file_id} />
                    </div>
                    <div className="text-xs text-muted-foreground">{c.email || 'no email'}</div>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell text-xs font-mono text-muted-foreground" data-testid={`candidate-code-${c.id}`}>{c.candidate_code || '—'}</TableCell>
                  <TableCell className="text-sm">{c.job_title || '—'}</TableCell>
                  <TableCell><StageBadge stage={c.stage} /></TableCell>
                  <TableCell className="hidden md:table-cell text-sm capitalize">{(c.source || '').replace('_', ' ')}</TableCell>
                  <TableCell className="hidden md:table-cell text-sm">{c.recruiter_name || '—'}</TableCell>
                  <TableCell className="hidden lg:table-cell text-sm">{c.notice_period || '—'}</TableCell>
                  <TableCell className="hidden lg:table-cell">
                    <div className="flex flex-wrap gap-1">
                      {(c.tags || []).slice(0, 2).map((t) => <Badge key={t} variant="secondary" className="text-[10px]">{t}</Badge>)}
                    </div>
                  </TableCell>
                  <TableCell className="hidden lg:table-cell text-xs text-muted-foreground font-mono">
                    {c.applied_at ? new Date(c.applied_at).toLocaleDateString() : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-border">
              <span className="text-xs text-muted-foreground">Page {page} of {totalPages}</span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next</Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Bulk action dialog */}
      <Dialog open={!!bulkDialog} onOpenChange={(o) => !o && setBulkDialog(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {bulkDialog === 'move_stage' && `Move ${selected.length} candidates to stage`}
              {bulkDialog === 'reject' && `Reject ${selected.length} candidates`}
              {bulkDialog === 'tag' && `Tag ${selected.length} candidates`}
              {bulkDialog === 'assign' && `Assign ${selected.length} candidates`}
              {bulkDialog === 'delete' && `Delete ${selected.length} candidate${selected.length === 1 ? '' : 's'}?`}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {bulkDialog === 'move_stage' && (
              <Select value={bulkValue} onValueChange={setBulkValue}>
                <SelectTrigger data-testid="bulk-stage-select"><SelectValue placeholder="Choose stage" /></SelectTrigger>
                <SelectContent>{stages.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            )}
            {bulkDialog === 'tag' && (
              <Select value={bulkValue} onValueChange={setBulkValue}>
                <SelectTrigger data-testid="bulk-tag-select"><SelectValue placeholder="Choose tag" /></SelectTrigger>
                <SelectContent>{tags.map((t) => <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>)}</SelectContent>
              </Select>
            )}
            {bulkDialog === 'assign' && (
              <Select value={bulkValue} onValueChange={setBulkValue}>
                <SelectTrigger data-testid="bulk-recruiter-select"><SelectValue placeholder="Choose recruiter" /></SelectTrigger>
                <SelectContent>{recruiters.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}</SelectContent>
              </Select>
            )}
            {bulkDialog === 'reject' && (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label>Rejection reason</Label>
                  <Select value={bulkRejectCategory} onValueChange={setBulkRejectCategory}>
                    <SelectTrigger data-testid="bulk-reject-reason-select"><SelectValue placeholder="Choose a reason" /></SelectTrigger>
                    <SelectContent>{REJECTION_REASONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                {bulkRejectCategory === 'Not Fit' && (
                  <div className="space-y-1.5">
                    <Label>Details</Label>
                    <Textarea value={bulkReason} onChange={(e) => setBulkReason(e.target.value)} placeholder="e.g. Not a technical fit for the role" data-testid="bulk-reject-detail-textarea" />
                  </div>
                )}
              </div>
            )}
            {bulkDialog === 'delete' && (
              <p className="text-sm text-muted-foreground" data-testid="bulk-delete-warning">
                This will permanently delete {selected.length} candidate{selected.length === 1 ? '' : 's'} and all their notes/history. This action cannot be undone.
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBulkDialog(null)}>Cancel</Button>
            <Button
              onClick={runBulk}
              data-testid="bulk-confirm-button"
              variant={bulkDialog === 'reject' || bulkDialog === 'delete' ? 'destructive' : 'default'}
            >
              {bulkDialog === 'delete' ? 'Delete' : 'Confirm'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Kanban drag-to-Rejected dialog */}
      <Dialog open={!!kanbanReject} onOpenChange={(o) => !o && setKanbanReject(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Reject {kanbanReject?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>Rejection reason</Label>
              <Select value={kanbanRejectCategory} onValueChange={setKanbanRejectCategory}>
                <SelectTrigger data-testid="kanban-reject-reason-select"><SelectValue placeholder="Choose a reason" /></SelectTrigger>
                <SelectContent>{REJECTION_REASONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            {kanbanRejectCategory === 'Not Fit' && (
              <div className="space-y-1.5">
                <Label>Details</Label>
                <Textarea value={kanbanRejectDetail} onChange={(e) => setKanbanRejectDetail(e.target.value)} placeholder="e.g. Not a technical fit for the role" data-testid="kanban-reject-detail-textarea" />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setKanbanReject(null)}>Cancel</Button>
            <Button variant="destructive" onClick={confirmKanbanReject} data-testid="kanban-reject-confirm-button">Reject Candidate</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
