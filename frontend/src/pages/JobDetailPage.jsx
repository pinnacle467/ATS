import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, FileText, History, LayoutGrid, MapPin, Search, Sparkles, Trash2, Upload, Users, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import ChangeLog from '@/components/ChangeLog';
import JobBoardDistributionCard from '@/components/JobBoardDistributionCard';
import JobTeamPanel from '@/components/JobTeamPanel';
import KanbanBoard from '@/components/KanbanBoard';
import { StageBadge, SOURCES, ResumeIndicator, REJECTION_REASONS } from '@/pages/CandidatesPage';
import { JdIndicator } from '@/pages/JobsPage';
import { useAuth } from '@/context/AuthContext';
import { isAdminOrHigher } from '@/lib/roles';
import { api, errMsg } from '@/lib/api';

const STATUS_STYLE = {
  open: 'bg-green-100 text-green-800',
  on_hold: 'bg-amber-100 text-amber-800',
  closed: 'bg-secondary text-muted-foreground',
};

const DEFAULT_STAGES = ['Applied', 'Screening', 'Interview', 'Offer', 'Hired', 'Rejected'];

export default function JobDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [job, setJob] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [jdDialogOpen, setJdDialogOpen] = useState(false);
  const [jdText, setJdText] = useState('');
  const [jdSaving, setJdSaving] = useState(false);
  const [detailTab, setDetailTab] = useState('overview');
  const [pipelineView, setPipelineView] = useState(() => localStorage.getItem('ats_job_pipeline_view') || 'kanban');
  const [pipelineSearch, setPipelineSearch] = useState('');
  const [sortByFit, setSortByFit] = useState(() => localStorage.getItem('ats_job_pipeline_sort_by_fit') === '1');
  const [kanbanReject, setKanbanReject] = useState(null);
  const [kanbanRejectCategory, setKanbanRejectCategory] = useState('');
  const [kanbanRejectDetail, setKanbanRejectDetail] = useState('');
  const jdFileRef = useRef();

  const canManage = isAdminOrHigher(user);
  const canDragStages = ['super_admin', 'admin', 'recruiter'].includes(user?.role);

  const setPipelineViewPersist = (v) => {
    setPipelineView(v);
    localStorage.setItem('ats_job_pipeline_view', v);
  };

  const toggleSortByFit = () => {
    setSortByFit((prev) => {
      const next = !prev;
      localStorage.setItem('ats_job_pipeline_sort_by_fit', next ? '1' : '0');
      return next;
    });
  };

  // Filtered + optionally sorted candidate list used by both Kanban and Grid views
  const displayCandidates = useMemo(() => {
    const term = pipelineSearch.trim().toLowerCase();
    let list = candidates;
    if (term) {
      list = list.filter((c) => {
        const hay = [
          c.name,
          c.email,
          c.current_title,
          c.current_company,
          c.location,
          c.candidate_code,
          ...(c.skills || []),
          ...(c.tags || []),
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        return hay.includes(term);
      });
    }
    if (sortByFit) {
      list = [...list].sort((a, b) => {
        const av = typeof a.fit_score === 'number' ? a.fit_score : -1;
        const bv = typeof b.fit_score === 'number' ? b.fit_score : -1;
        return bv - av;
      });
    }
    return list;
  }, [candidates, pipelineSearch, sortByFit]);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      api.get(`/jobs/${id}`),
      api.get('/candidates', { params: { job_id: id, limit: 500 } }),
    ])
      .then(([j, c]) => {
        setJob(j.data);
        setCandidates(c.data.items || []);
      })
      .catch((e) => {
        if (e.response?.status === 403 || e.response?.status === 404) setNotFound(true);
        else toast.error(errMsg(e));
      })
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const openJdDialog = () => {
    setJdText(job.jd_text || '');
    setJdDialogOpen(true);
  };

  const saveJdText = async () => {
    if (!jdText.trim()) return toast.error('Enter the job description text');
    setJdSaving(true);
    try {
      const fd = new FormData();
      fd.append('text', jdText.trim());
      await api.post(`/jobs/${id}/jd`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('Job description saved — matching candidates now');
      setJdDialogOpen(false);
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not save job description'));
    } finally {
      setJdSaving(false);
    }
  };

  const uploadJdFile = async (file) => {
    setJdSaving(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      await api.post(`/jobs/${id}/jd`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('Job description uploaded — matching candidates now');
      setJdDialogOpen(false);
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not upload job description'));
    } finally {
      setJdSaving(false);
    }
  };

  const removeJd = async () => {
    if (!window.confirm('Remove the job description? Candidate fit scores for this job will be cleared.')) return;
    try {
      await api.delete(`/jobs/${id}/jd`);
      toast.success('Job description removed');
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not remove job description'));
    }
  };

  const onKanbanMove = async (cand, stage) => {
    if (stage === 'Rejected') {
      setKanbanReject(cand);
      setKanbanRejectCategory('');
      setKanbanRejectDetail('');
      return;
    }
    // optimistic local update
    setCandidates((cs) => cs.map((c) => (c.id === cand.id ? { ...c, stage } : c)));
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

  if (notFound) {
    return (
      <div className="text-center py-20">
        <p className="text-lg font-medium">Job not available</p>
        <p className="text-sm text-muted-foreground mt-1">This job does not exist or you do not have access.</p>
        <Button className="mt-4" variant="outline" onClick={() => navigate('/jobs')}>Back to jobs</Button>
      </div>
    );
  }

  if (loading || !job) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  const stageNames = job.stages && job.stages.length ? job.stages : DEFAULT_STAGES;
  const byStage = stageNames.map((s) => ({
    name: s,
    items: displayCandidates.filter((c) => c.stage === s),
  }));
  const activeCount = candidates.filter((c) => c.status === 'active').length;

  const knownSourceValues = SOURCES.map((s) => s.value);
  const sourceCounts = SOURCES.map((s) => ({
    ...s,
    count: candidates.filter((c) => c.source === s.value).length,
  }));
  const otherSourceCount = candidates.filter((c) => !knownSourceValues.includes(c.source)).length;
  const maxSourceCount = Math.max(1, ...sourceCounts.map((s) => s.count), otherSourceCount);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate('/jobs')} aria-label="Back" data-testid="job-detail-back-button">
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="font-display text-2xl font-semibold tracking-tight" data-testid="job-detail-title">{job.title}</h1>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${STATUS_STYLE[job.status] || 'bg-secondary'}`}>{(job.status || '').replace('_', ' ')}</span>
            </div>
            <p className="text-sm text-muted-foreground mt-0.5 flex items-center gap-1.5 flex-wrap">
              <span>{job.department}</span>
              {job.location && (
                <span className="flex items-center gap-1"><span>·</span><MapPin className="h-3.5 w-3.5" /> {job.location}</span>
              )}
              <span className="flex items-center gap-1"><span>·</span><Users className="h-3.5 w-3.5" /> {activeCount} active candidate{activeCount === 1 ? '' : 's'}</span>
            </p>
          </div>
        </div>
      </div>

      {job.description && (
        <Card className="shadow-none">
          <CardContent className="pt-5 text-sm text-muted-foreground">{job.description}</CardContent>
        </Card>
      )}

      <Card className="shadow-none" data-testid="job-jd-card">
        <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <FileText className="h-4 w-4" /> Job Description
            <JdIndicator hasJd={job.has_jd} />
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={openJdDialog} data-testid="job-jd-edit-button">
              {job.has_jd ? 'Edit JD' : 'Add JD'}
            </Button>
            {job.has_jd && (
              <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={removeJd} data-testid="job-jd-remove-button">
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {job.has_jd ? (
            <p className="text-sm text-muted-foreground whitespace-pre-wrap max-h-40 overflow-y-auto thin-scroll" data-testid="job-jd-text">{job.jd_text}</p>
          ) : (
            <p className="text-sm text-muted-foreground py-2 text-center">No job description attached yet. Add one so candidate resumes can be auto-matched and scored.</p>
          )}
        </CardContent>
      </Card>

      <JobBoardDistributionCard jobId={job.id} canManage={canManage} onApplicationIngested={load} />

      <Card className="shadow-none">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center justify-between gap-2">
            <span>Candidate Sources</span>
            <span className="text-xs font-normal text-muted-foreground">{candidates.length} total</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2.5" data-testid="job-source-stats">
          {candidates.length === 0 && <p className="text-xs text-muted-foreground text-center py-2">No candidates yet</p>}
          {sourceCounts.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => s.count > 0 && navigate(`/candidates?job_id=${job.id}&source=${s.value}`)}
              disabled={s.count === 0}
              data-testid={`job-source-${s.value}`}
              className={`flex items-center gap-3 w-full text-left rounded-md px-1.5 py-1 -mx-1.5 transition-colors ${s.count > 0 ? 'hover:bg-secondary cursor-pointer' : 'cursor-default'}`}
            >
              <span className="text-xs w-24 shrink-0 text-muted-foreground truncate">{s.label}</span>
              <div className="flex-1 h-2 rounded-full bg-secondary overflow-hidden">
                <div className="h-full bg-primary rounded-full" style={{ width: `${(s.count / maxSourceCount) * 100}%` }} />
              </div>
              <span className="text-xs font-medium tabular-nums w-16 text-right">
                {s.count}{candidates.length > 0 && <span className="text-muted-foreground"> ({Math.round((s.count / candidates.length) * 100)}%)</span>}
              </span>
            </button>
          ))}
          {otherSourceCount > 0 && (
            <div className="flex items-center gap-3" data-testid="job-source-other">
              <span className="text-xs w-24 shrink-0 text-muted-foreground truncate">Other</span>
              <div className="flex-1 h-2 rounded-full bg-secondary overflow-hidden">
                <div className="h-full bg-primary rounded-full" style={{ width: `${(otherSourceCount / maxSourceCount) * 100}%` }} />
              </div>
              <span className="text-xs font-medium tabular-nums w-16 text-right">
                {otherSourceCount}{candidates.length > 0 && <span className="text-muted-foreground"> ({Math.round((otherSourceCount / candidates.length) * 100)}%)</span>}
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      <div>
        <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
          <div>
            <h2 className="font-display text-lg font-semibold">Pipeline</h2>
            {canDragStages && pipelineView === 'kanban' && (
              <p className="text-xs text-muted-foreground mt-0.5">Drag candidate cards between columns to move them across stages</p>
            )}
          </div>
          <div className="flex rounded-lg border border-border overflow-hidden" data-testid="job-pipeline-view-toggle">
            <button
              type="button"
              onClick={() => setPipelineViewPersist('kanban')}
              data-testid="job-pipeline-view-kanban"
              className={`px-3 py-1.5 text-sm flex items-center gap-1.5 transition-colors ${pipelineView === 'kanban' ? 'bg-primary text-primary-foreground' : 'bg-card hover:bg-secondary'}`}
            >
              <LayoutGrid className="h-3.5 w-3.5" /> Kanban
            </button>
            <button
              type="button"
              onClick={() => setPipelineViewPersist('grid')}
              data-testid="job-pipeline-view-grid"
              className={`px-3 py-1.5 text-sm flex items-center gap-1.5 transition-colors ${pipelineView === 'grid' ? 'bg-primary text-primary-foreground' : 'bg-card hover:bg-secondary'}`}
            >
              <Users className="h-3.5 w-3.5" /> Grid
            </button>
          </div>
        </div>

        {/* Quick filter + Sort by fit toolbar */}
        <div className="flex items-center gap-2 mb-3 flex-wrap" data-testid="job-pipeline-toolbar">
          <div className="relative flex-1 min-w-[220px] max-w-md">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={pipelineSearch}
              onChange={(e) => setPipelineSearch(e.target.value)}
              placeholder="Quick filter — name, email, title, skill, tag…"
              className="pl-8 h-9 text-sm"
              data-testid="job-pipeline-search-input"
            />
            {pipelineSearch && (
              <button
                type="button"
                onClick={() => setPipelineSearch('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary"
                data-testid="job-pipeline-search-clear"
                aria-label="Clear search"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={toggleSortByFit}
            data-testid="job-pipeline-sort-by-fit-toggle"
            className={`inline-flex items-center gap-1.5 h-9 px-3 rounded-md text-sm border transition-colors ${sortByFit ? 'bg-primary text-primary-foreground border-primary' : 'bg-card border-border hover:bg-secondary'}`}
            title="Sort candidates by AI fit score (highest first) within each stage"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Sort by Fit
          </button>
          {(pipelineSearch || sortByFit) && (
            <span className="text-xs text-muted-foreground" data-testid="job-pipeline-filter-summary">
              Showing {displayCandidates.length} of {candidates.length}
              {sortByFit && ' · sorted by fit'}
            </span>
          )}
        </div>

        {pipelineView === 'kanban' ? (
          <div data-testid="job-pipeline-kanban">
            <KanbanBoard
              stages={stageNames}
              candidates={displayCandidates}
              onMove={onKanbanMove}
              canDrag={canDragStages}
            />
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4" data-testid="job-pipeline-stages">
            {byStage.map((stage) => (
              <Card key={stage.name} className="shadow-none" data-testid={`job-pipeline-stage-${stage.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold flex items-center justify-between gap-2">
                    <StageBadge stage={stage.name} />
                    <span className="text-xs font-mono text-muted-foreground tabular-nums" data-testid={`job-pipeline-count-${stage.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
                      {stage.items.length}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-1.5 max-h-[420px] overflow-y-auto thin-scroll">
                  {stage.items.length === 0 && (
                    <p className="text-xs text-muted-foreground text-center py-3">No candidates</p>
                  )}
                  {stage.items.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => navigate(`/candidates/${c.id}`)}
                      data-testid={`job-pipeline-candidate-${c.id}`}
                      className="w-full text-left rounded-lg border border-border px-2.5 py-2 hover:bg-secondary transition-colors"
                    >
                      <div className="text-xs font-medium truncate flex items-center gap-1.5">
                        <span className="truncate">{c.name}</span>
                        <ResumeIndicator hasResume={!!c.resume_file_id} />
                      </div>
                      <div className="text-[11px] text-muted-foreground truncate">{c.candidate_code ? `${c.candidate_code} · ` : ''}{c.current_title || c.email || '—'}</div>
                    </button>
                  ))}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Team & Access + Change Log (Admin+ only) */}
      {canManage && (
        <div className="grid lg:grid-cols-2 gap-4">
          <JobTeamPanel jobId={job.id} />
          <div className="rounded-xl border border-border bg-card p-4 space-y-3" data-testid="job-change-log-card">
            <div className="flex items-center gap-2">
              <History className="h-4 w-4" />
              <h3 className="font-semibold text-sm">Change Log</h3>
            </div>
            <div className="max-h-[420px] overflow-y-auto thin-scroll pr-1">
              <ChangeLog entityType="job" entityId={job.id} />
            </div>
          </div>
        </div>
      )}

      {/* Kanban drag-to-Rejected dialog */}
      <Dialog open={!!kanbanReject} onOpenChange={(o) => !o && setKanbanReject(null)}>
        <DialogContent className="sm:max-w-md" data-testid="job-kanban-reject-dialog">
          <DialogHeader><DialogTitle>Reject {kanbanReject?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>Rejection reason</Label>
              <Select value={kanbanRejectCategory} onValueChange={setKanbanRejectCategory}>
                <SelectTrigger data-testid="job-kanban-reject-reason-select"><SelectValue placeholder="Choose a reason" /></SelectTrigger>
                <SelectContent>{REJECTION_REASONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            {kanbanRejectCategory === 'Not Fit' && (
              <div className="space-y-1.5">
                <Label>Details</Label>
                <Textarea value={kanbanRejectDetail} onChange={(e) => setKanbanRejectDetail(e.target.value)} placeholder="e.g. Not a technical fit for the role" data-testid="job-kanban-reject-detail-textarea" />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setKanbanReject(null)}>Cancel</Button>
            <Button variant="destructive" onClick={confirmKanbanReject} data-testid="job-kanban-reject-confirm-button">Reject Candidate</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={jdDialogOpen} onOpenChange={setJdDialogOpen}>
        <DialogContent className="sm:max-w-lg" data-testid="job-jd-dialog">
          <DialogHeader><DialogTitle>{job.has_jd ? 'Edit Job Description' : 'Add Job Description'}</DialogTitle></DialogHeader>
          <Tabs defaultValue="text">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="text" data-testid="job-jd-tab-text">Paste Text</TabsTrigger>
              <TabsTrigger value="file" data-testid="job-jd-tab-file">Upload File</TabsTrigger>
            </TabsList>
            <TabsContent value="text" className="space-y-3">
              <Textarea
                rows={10}
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                placeholder="Paste the full job description here..."
                data-testid="job-jd-textarea"
              />
              <Button className="w-full" onClick={saveJdText} disabled={jdSaving} data-testid="job-jd-save-text-button">
                Save Job Description
              </Button>
            </TabsContent>
            <TabsContent value="file" className="space-y-3">
              <div
                className="border-2 border-dashed rounded-xl p-6 text-center text-sm text-muted-foreground cursor-pointer hover:border-primary/50 transition-colors"
                onClick={() => jdFileRef.current?.click()}
              >
                <Upload className="h-5 w-5 mx-auto mb-2" />
                Click to choose a PDF or DOCX file
              </div>
              <input
                ref={jdFileRef}
                type="file"
                accept=".pdf,.docx"
                className="hidden"
                data-testid="job-jd-file-input"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadJdFile(f);
                  e.target.value = '';
                }}
              />
              {jdSaving && <p className="text-xs text-center text-muted-foreground">Uploading & extracting text...</p>}
            </TabsContent>
          </Tabs>
          <DialogFooter>
            <Button variant="outline" onClick={() => setJdDialogOpen(false)}>Cancel</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
