import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, MapPin, Users } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { StageBadge, SOURCES } from '@/pages/CandidatesPage';
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
  const [job, setJob] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

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
    items: candidates.filter((c) => c.stage === s),
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
            <div key={s.value} className="flex items-center gap-3" data-testid={`job-source-${s.value}`}>
              <span className="text-xs w-24 shrink-0 text-muted-foreground truncate">{s.label}</span>
              <div className="flex-1 h-2 rounded-full bg-secondary overflow-hidden">
                <div className="h-full bg-primary rounded-full" style={{ width: `${(s.count / maxSourceCount) * 100}%` }} />
              </div>
              <span className="text-xs font-medium tabular-nums w-16 text-right">
                {s.count}{candidates.length > 0 && <span className="text-muted-foreground"> ({Math.round((s.count / candidates.length) * 100)}%)</span>}
              </span>
            </div>
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
        <h2 className="font-display text-lg font-semibold mb-3">Pipeline</h2>
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
                    <div className="text-xs font-medium truncate">{c.name}</div>
                    <div className="text-[11px] text-muted-foreground truncate">{c.current_title || c.email || '—'}</div>
                  </button>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
