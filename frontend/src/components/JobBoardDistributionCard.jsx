import { useCallback, useEffect, useState } from 'react';
import { Beaker, ExternalLink, Loader2, RefreshCw, Rss, Send, Trash2, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { api, errMsg } from '@/lib/api';

const PUB_STATUS_META = {
  draft: { label: 'Draft', className: 'bg-secondary text-muted-foreground' },
  publishing: { label: 'Publishing', className: 'bg-amber-100 text-amber-800' },
  published: { label: 'Live', className: 'bg-emerald-100 text-emerald-800' },
  update_pending: { label: 'Update Pending', className: 'bg-amber-100 text-amber-800' },
  updated: { label: 'Updated', className: 'bg-emerald-100 text-emerald-800' },
  failed: { label: 'Failed', className: 'bg-red-100 text-red-800' },
  expired: { label: 'Expired', className: 'bg-secondary text-muted-foreground' },
  closed: { label: 'Closed', className: 'bg-secondary text-muted-foreground' },
  partner_approval_required: { label: 'Partner Approval Required', className: 'bg-orange-100 text-orange-800' },
  not_published: { label: 'Not Published', className: 'bg-secondary text-muted-foreground' },
};

function PubStatusBadge({ status }) {
  const meta = PUB_STATUS_META[status] || PUB_STATUS_META.draft;
  return <Badge className={meta.className} data-testid={`job-board-pub-status-${status}`}>{meta.label}</Badge>;
}

function PublishDialog({ jobId, open, onOpenChange, onPublished }) {
  const [providers, setProviders] = useState([]);
  const [selected, setSelected] = useState([]);
  const [preview, setPreview] = useState([]);
  const [step, setStep] = useState('select'); // select | preview
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setStep('select');
    setSelected([]);
    api.get('/job-boards/integrations').then((r) => setProviders(r.data.filter((p) => p.key !== 'mock' || true))).catch(() => {});
  }, [open]);

  const toggle = (key) => setSelected((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

  const goPreview = async () => {
    if (selected.length === 0) return toast.error('Select at least one job board');
    setBusy(true);
    try {
      const r = await api.post(`/job-boards/jobs/${jobId}/publish-preview`, { providers: selected });
      setPreview(r.data);
      setStep('preview');
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const confirmPublish = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/job-boards/jobs/${jobId}/publish`, { providers: selected });
      const failed = r.data.results.filter((x) => !x.ok);
      if (failed.length) toast.warning(`${failed.length} board(s) failed — see Job Board Distribution for details`);
      else toast.success('Published');
      onOpenChange(false);
      onPublished();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="publish-job-boards-dialog">
        <DialogHeader><DialogTitle>Publish to Job Boards</DialogTitle></DialogHeader>
        {step === 'select' ? (
          <div className="space-y-2">
            {providers.map((p) => (
              <label key={p.key} className="flex items-center gap-2.5 rounded-md border p-2.5 cursor-pointer hover:bg-secondary/50" data-testid={`publish-checkbox-row-${p.key}`}>
                <Checkbox checked={selected.includes(p.key)} onCheckedChange={() => toggle(p.key)} data-testid={`publish-checkbox-${p.key}`} />
                <span className="text-sm flex-1">{p.display_name}</span>
                {!p.connected && <span className="text-xs text-muted-foreground">Not connected</span>}
              </label>
            ))}
          </div>
        ) : (
          <div className="space-y-3 max-h-96 overflow-y-auto thin-scroll">
            {preview.map((pv) => (
              <div key={pv.provider} className="rounded-md border p-3 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{pv.display_name}</span>
                  {pv.requires_partner_approval && <Badge className="bg-orange-100 text-orange-800 text-xs">Partner Approval Required</Badge>}
                </div>
                {pv.unsupported_field_warnings.length > 0 && (
                  <p className="text-xs text-amber-700 bg-amber-50 rounded p-1.5">
                    Not supported by this board: {pv.unsupported_field_warnings.join(', ')}
                  </p>
                )}
                <p className="text-xs text-muted-foreground truncate">{pv.mapped_fields.title} — {pv.mapped_fields.location || 'No location set'}</p>
              </div>
            ))}
          </div>
        )}
        <DialogFooter>
          {step === 'select' ? (
            <Button onClick={goPreview} disabled={busy} data-testid="publish-continue-button">
              {busy && <Loader2 className="h-4 w-4 animate-spin mr-2" />} Review & Continue
            </Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => setStep('select')}>Back</Button>
              <Button onClick={confirmPublish} disabled={busy} data-testid="publish-confirm-button">
                {busy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />} Publish
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function JobBoardDistributionCard({ jobId, canManage, onApplicationIngested }) {
  const [pubs, setPubs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [publishOpen, setPublishOpen] = useState(false);
  const [busyProvider, setBusyProvider] = useState(null);

  const load = useCallback(() => {
    api.get(`/job-boards/jobs/${jobId}/publications`).then((r) => setPubs(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, [jobId]);
  useEffect(() => { load(); }, [load]);

  const act = async (pub, action) => {
    setBusyProvider(pub.provider);
    try {
      if (action === 'remove') {
        if (!window.confirm(`Remove ${pub.display_name} from this job's distribution list?`)) { setBusyProvider(null); return; }
        await api.delete(`/job-boards/publications/${pub.id}`);
      } else if (action === 'update') {
        await api.put(`/job-boards/publications/${pub.id}`);
      } else if (action === 'close') {
        await api.post(`/job-boards/publications/${pub.id}/close`);
      } else if (action === 'retry') {
        await api.post(`/job-boards/publications/${pub.id}/retry`);
      }
      toast.success('Done');
      load();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusyProvider(null);
    }
  };

  const simulate = async (pub) => {
    setBusyProvider(pub.provider);
    try {
      const r = await api.post('/job-boards/integrations/mock/simulate-application', { job_id: jobId, name: 'Sandbox Test Candidate' });
      toast.success(`Simulated application ingested — candidate created (status: ${r.data.status})`);
      load();
      onApplicationIngested?.();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusyProvider(null);
    }
  };

  return (
    <Card className="shadow-none">
      <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <Rss className="h-4 w-4" /> Job Board Distribution
        </CardTitle>
        {canManage && (
          <Button size="sm" onClick={() => setPublishOpen(true)} data-testid="publish-to-job-boards-button">
            <Send className="h-3.5 w-3.5 mr-1.5" /> Publish
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-2" data-testid="job-board-distribution-list">
        {loading ? <Loader2 className="h-4 w-4 animate-spin mx-auto my-3" /> : pubs.map((p) => (
          <div key={p.provider} className="flex items-center justify-between gap-3 rounded-md border p-2.5" data-testid={`job-board-distribution-row-${p.provider}`}>
            <div className="flex items-center gap-2.5 min-w-0">
              <span className="text-sm font-medium">{p.display_name}</span>
              <PubStatusBadge status={p.status} />
              {p.applications_received > 0 && <span className="text-xs text-muted-foreground">{p.applications_received} applications</span>}
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              {p.error && <XCircle className="h-3.5 w-3.5 text-red-600" titleAccess={p.error} />}
              {p.external_url && (p.status === 'published' || p.status === 'updated') && (
                <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => window.open(p.external_url, '_blank')} data-testid={`job-board-view-posting-${p.provider}`}>
                  <ExternalLink className="h-3.5 w-3.5" />
                </Button>
              )}
              {!p.is_virtual && canManage && (
                <>
                  {p.provider === 'mock' && (p.status === 'published' || p.status === 'updated') && (
                    <Button size="sm" variant="outline" className="h-7" disabled={busyProvider === p.provider} onClick={() => simulate(p)} data-testid={`job-board-simulate-${p.provider}`}>
                      <Beaker className="h-3.5 w-3.5 mr-1" /> Simulate Application
                    </Button>
                  )}
                  {(p.status === 'published' || p.status === 'updated') && (
                    <Button size="sm" variant="ghost" className="h-7" disabled={busyProvider === p.provider} onClick={() => act(p, 'update')} data-testid={`job-board-update-${p.provider}`}>
                      <RefreshCw className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  {(p.status === 'published' || p.status === 'updated') && (
                    <Button size="sm" variant="ghost" className="h-7 text-destructive" disabled={busyProvider === p.provider} onClick={() => act(p, 'close')} data-testid={`job-board-close-${p.provider}`}>
                      Close
                    </Button>
                  )}
                  {p.status === 'failed' && (
                    <Button size="sm" variant="outline" className="h-7" disabled={busyProvider === p.provider} onClick={() => act(p, 'retry')} data-testid={`job-board-retry-${p.provider}`}>
                      Retry
                    </Button>
                  )}
                  <Button size="icon" variant="ghost" className="h-7 w-7 text-muted-foreground hover:text-destructive" disabled={busyProvider === p.provider} onClick={() => act(p, 'remove')} data-testid={`job-board-remove-${p.provider}`}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </>
              )}
            </div>
          </div>
        ))}
      </CardContent>
      <PublishDialog jobId={jobId} open={publishOpen} onOpenChange={setPublishOpen} onPublished={load} />
    </Card>
  );
}
