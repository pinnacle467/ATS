import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Copy, Loader2, PlugZap, RefreshCw, ShieldCheck, Unplug, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { api, errMsg } from '@/lib/api';

const STATUS_META = {
  connected: { label: 'Connected', className: 'bg-emerald-100 text-emerald-800' },
  not_connected: { label: 'Not Connected', className: 'bg-secondary text-muted-foreground' },
  connecting: { label: 'Connecting', className: 'bg-amber-100 text-amber-800' },
  connection_error: { label: 'Connection Error', className: 'bg-red-100 text-red-800' },
  partner_approval_required: { label: 'Partner Approval Required', className: 'bg-orange-100 text-orange-800' },
};

const StatusBadge = ({ status }) => {
  const meta = STATUS_META[status] || STATUS_META.not_connected;
  return <Badge className={meta.className} data-testid={`job-board-status-${status}`}>{meta.label}</Badge>;
};

function ConnectDialog({ provider, open, onOpenChange, onConnected }) {
  const [fields, setFields] = useState({});
  const [webhookMode, setWebhookMode] = useState('bearer_token');
  const [busy, setBusy] = useState(false);
  const [revealed, setRevealed] = useState(null);

  useEffect(() => { if (open) { setFields({}); setRevealed(null); } }, [open, provider]);

  if (!provider) return null;

  const connect = async () => {
    setBusy(true);
    try {
      const body = { credentials: fields };
      if (provider.key === 'generic_webhook') body.webhook_auth_mode = webhookMode;
      const r = await api.post(`/job-boards/integrations/${provider.key}/connect`, body);
      if (r.data.webhook_secret) {
        setRevealed({ secret: r.data.webhook_secret, url: r.data.webhook_url });
      } else if (r.data.status === 'connected') {
        toast.success(`${provider.display_name} connected`);
        onOpenChange(false);
      } else if (r.data.status === 'partner_approval_required') {
        toast.warning(`Saved — ${provider.display_name} requires partner approval before it can go live`);
      } else {
        toast.error(r.data.last_error || 'Connection failed');
      }
      onConnected();
    } catch (e) {
      toast.error(errMsg(e, 'Could not connect'));
    } finally {
      setBusy(false);
    }
  };

  const copy = (text, label) => { navigator.clipboard.writeText(text); toast.success(`${label} copied`); };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="job-board-connect-dialog">
        <DialogHeader>
          <DialogTitle>Connect {provider.display_name}</DialogTitle>
        </DialogHeader>
        {revealed ? (
          <div className="space-y-3">
            <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 p-3 text-sm text-amber-900">
              <ShieldCheck className="h-4 w-4 mt-0.5 shrink-0" />
              <span>This secret is shown once. Copy it now and give both values to the system that will send applications.</span>
            </div>
            <div>
              <Label className="text-xs">Webhook URL</Label>
              <div className="flex gap-2 mt-1">
                <Input readOnly value={revealed.url} className="text-xs" data-testid="webhook-url-field" />
                <Button size="icon" variant="outline" onClick={() => copy(revealed.url, 'Webhook URL')}><Copy className="h-3.5 w-3.5" /></Button>
              </div>
            </div>
            <div>
              <Label className="text-xs">{webhookMode === 'hmac_sha256' ? 'Signing Secret' : 'Bearer Token'}</Label>
              <div className="flex gap-2 mt-1">
                <Input readOnly value={revealed.secret} className="text-xs font-mono" data-testid="webhook-secret-field" />
                <Button size="icon" variant="outline" onClick={() => copy(revealed.secret, 'Secret')}><Copy className="h-3.5 w-3.5" /></Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {provider.key === 'generic_webhook' && (
              <div>
                <Label className="text-xs">Auth mode the sender will use</Label>
                <Select value={webhookMode} onValueChange={setWebhookMode}>
                  <SelectTrigger data-testid="webhook-auth-mode-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="bearer_token">Bearer token (Authorization header)</SelectItem>
                    <SelectItem value="hmac_sha256">HMAC-SHA256 signature (X-Webhook-Signature header)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
            {provider.auth_fields.map((f) => (
              <div key={f.key}>
                <Label className="text-xs">{f.label}{f.required && ' *'}</Label>
                <Input
                  type={f.type === 'password' ? 'password' : 'text'} value={fields[f.key] || ''}
                  onChange={(e) => setFields((p) => ({ ...p, [f.key]: e.target.value }))}
                  data-testid={`job-board-auth-field-${f.key}`}
                />
              </div>
            ))}
            {provider.requires_partner_approval && (
              <div className="flex items-start gap-2 rounded-lg bg-orange-50 border border-orange-200 p-3 text-sm text-orange-900">
                <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{provider.description}</span>
              </div>
            )}
            {provider.auth_fields.length === 0 && !provider.requires_partner_approval && (
              <p className="text-sm text-muted-foreground">{provider.description}</p>
            )}
          </div>
        )}
        <DialogFooter>
          {revealed ? (
            <Button onClick={() => onOpenChange(false)} data-testid="webhook-secret-done-button">Done</Button>
          ) : (
            <Button onClick={connect} disabled={busy} data-testid="job-board-connect-submit-button">
              {busy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <PlugZap className="h-4 w-4 mr-2" />}
              Connect
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ConnectionsPanel() {
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connectTarget, setConnectTarget] = useState(null);
  const [busyKey, setBusyKey] = useState(null);

  const load = useCallback(() => {
    api.get('/job-boards/integrations').then((r) => setProviders(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const test = async (p) => {
    setBusyKey(p.key);
    try {
      const r = await api.post(`/job-boards/integrations/${p.key}/test`);
      r.data.ok ? toast.success(`${p.display_name}: connection OK`) : toast.error(r.data.error || 'Connection failed');
      load();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusyKey(null);
    }
  };

  const disconnect = async (p) => {
    if (!window.confirm(`Disconnect ${p.display_name}? Published jobs will remain on the board but no longer sync.`)) return;
    setBusyKey(p.key);
    try {
      await api.post(`/job-boards/integrations/${p.key}/disconnect`);
      toast.success(`${p.display_name} disconnected`);
      load();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusyKey(null);
    }
  };

  if (loading) return <div className="py-8 text-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin mx-auto" /></div>;

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="job-boards-connections-grid">
        {providers.map((p) => (
          <Card key={p.key} data-testid={`job-board-card-${p.key}`}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">{p.display_name}</CardTitle>
                <StatusBadge status={p.status} />
              </div>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p className="text-muted-foreground text-xs leading-relaxed">{p.description}</p>
              {p.account_label && <p><span className="text-muted-foreground">Account:</span> {p.account_label}</p>}
              <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                <span>Active jobs: <strong className="text-foreground">{p.active_job_count}</strong></span>
                <span>Applications: <strong className="text-foreground">{p.applications_received}</strong></span>
                <span>Last sync: {p.last_synced_at ? new Date(p.last_synced_at).toLocaleString() : '—'}</span>
              </div>
              {p.feed_url && (
                <div className="flex gap-2 items-center">
                  <Input readOnly value={p.feed_url} className="text-xs h-8" />
                  <Button size="icon" variant="outline" className="h-8 w-8 shrink-0"
                          onClick={() => { navigator.clipboard.writeText(p.feed_url); toast.success('Feed URL copied'); }}>
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                </div>
              )}
              {p.last_error && (
                <div className="flex items-start gap-1.5 text-xs text-red-700 bg-red-50 rounded p-2">
                  <XCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" /><span>{p.last_error}</span>
                </div>
              )}
              <div className="flex gap-2 pt-1">
                {p.status === 'not_connected' ? (
                  <Button size="sm" onClick={() => setConnectTarget(p)} data-testid={`job-board-connect-button-${p.key}`}>
                    <PlugZap className="h-3.5 w-3.5 mr-1.5" /> Connect
                  </Button>
                ) : (
                  <>
                    <Button size="sm" variant="outline" disabled={busyKey === p.key} onClick={() => test(p)} data-testid={`job-board-test-button-${p.key}`}>
                      {busyKey === p.key ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />}
                      Test Connection
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setConnectTarget(p)}>Reconnect</Button>
                    <Button size="sm" variant="ghost" className="text-destructive" disabled={busyKey === p.key} onClick={() => disconnect(p)} data-testid={`job-board-disconnect-button-${p.key}`}>
                      <Unplug className="h-3.5 w-3.5 mr-1.5" /> Disconnect
                    </Button>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <ConnectDialog provider={connectTarget} open={!!connectTarget} onOpenChange={(v) => !v && setConnectTarget(null)} onConnected={load} />
    </>
  );
}

const APP_STATUS_META = {
  new: { label: 'New', className: 'bg-sky-100 text-sky-800' },
  linked: { label: 'Linked', className: 'bg-emerald-100 text-emerald-800' },
  duplicate_review: { label: 'Needs Review', className: 'bg-orange-100 text-orange-800' },
  rejected_invalid: { label: 'Ignored', className: 'bg-secondary text-muted-foreground' },
};

function ApplicationsPanel() {
  const [apps, setApps] = useState([]);
  const [statusFilter, setStatusFilter] = useState('duplicate_review');
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    const q = statusFilter === 'all' ? '' : `?status=${statusFilter}`;
    api.get(`/job-boards/applications${q}`).then((r) => setApps(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, [statusFilter]);
  useEffect(() => { load(); }, [load]);

  const resolve = async (app, action) => {
    setBusyId(app.id);
    try {
      await api.post(`/job-boards/applications/${app.id}/resolve`, { action });
      toast.success('Application reviewed');
      load();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-3">
      <Select value={statusFilter} onValueChange={setStatusFilter}>
        <SelectTrigger className="w-56" data-testid="job-board-applications-status-filter"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="duplicate_review">Needs Review</SelectItem>
          <SelectItem value="new">New</SelectItem>
          <SelectItem value="linked">Linked</SelectItem>
          <SelectItem value="rejected_invalid">Ignored</SelectItem>
          <SelectItem value="all">All</SelectItem>
        </SelectContent>
      </Select>
      {loading ? <div className="py-8 text-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin mx-auto" /></div> : (
        <Table data-testid="job-board-applications-table">
          <TableHeader>
            <TableRow>
              <TableHead>Candidate</TableHead><TableHead>Job</TableHead><TableHead>Provider</TableHead>
              <TableHead>Applied</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {apps.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">No applications yet</TableCell></TableRow>}
            {apps.map((a) => (
              <TableRow key={a.id} data-testid={`job-board-application-row-${a.id}`}>
                <TableCell>{a.candidate_name || a.candidate_email || '—'}</TableCell>
                <TableCell>{a.job_title || '—'}</TableCell>
                <TableCell className="capitalize">{a.provider}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{a.applied_at ? new Date(a.applied_at).toLocaleDateString() : '—'}</TableCell>
                <TableCell><Badge className={(APP_STATUS_META[a.status] || {}).className}>{(APP_STATUS_META[a.status] || {}).label || a.status}</Badge></TableCell>
                <TableCell className="text-right">
                  {a.status === 'duplicate_review' && (
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="outline" disabled={busyId === a.id} onClick={() => resolve(a, 'add_to_pipeline')} data-testid={`resolve-add-pipeline-${a.id}`}>Add to Pipeline</Button>
                      <Button size="sm" variant="outline" disabled={busyId === a.id} onClick={() => resolve(a, 'create_new_candidate')} data-testid={`resolve-new-candidate-${a.id}`}>Different Person</Button>
                      <Button size="sm" variant="ghost" className="text-destructive" disabled={busyId === a.id} onClick={() => resolve(a, 'ignore')} data-testid={`resolve-ignore-${a.id}`}>Ignore</Button>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

function ActivityLogPanel() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api.get('/job-boards/sync-logs').then((r) => setLogs(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, []);
  if (loading) return <div className="py-8 text-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin mx-auto" /></div>;
  return (
    <Table data-testid="job-board-sync-log-table">
      <TableHeader><TableRow><TableHead>Time</TableHead><TableHead>Provider</TableHead><TableHead>Action</TableHead><TableHead>Status</TableHead><TableHead>Message</TableHead></TableRow></TableHeader>
      <TableBody>
        {logs.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-8">No activity yet</TableCell></TableRow>}
        {logs.map((l) => (
          <TableRow key={l.id}>
            <TableCell className="text-xs text-muted-foreground">{new Date(l.created_at).toLocaleString()}</TableCell>
            <TableCell className="capitalize">{l.provider}</TableCell>
            <TableCell className="capitalize">{l.action.replace(/_/g, ' ')}</TableCell>
            <TableCell>{l.status === 'success' ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <XCircle className="h-4 w-4 text-red-600" />}</TableCell>
            <TableCell className="text-xs text-muted-foreground max-w-md truncate">{l.message}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export default function JobBoardsTab() {
  return (
    <Tabs defaultValue="connections" data-testid="job-boards-subtabs">
      <TabsList>
        <TabsTrigger value="connections" data-testid="job-boards-subtab-connections">Connections</TabsTrigger>
        <TabsTrigger value="applications" data-testid="job-boards-subtab-applications">Applications</TabsTrigger>
        <TabsTrigger value="activity" data-testid="job-boards-subtab-activity">Activity Log</TabsTrigger>
      </TabsList>
      <TabsContent value="connections" className="mt-4"><ConnectionsPanel /></TabsContent>
      <TabsContent value="applications" className="mt-4"><ApplicationsPanel /></TabsContent>
      <TabsContent value="activity" className="mt-4"><ActivityLogPanel /></TabsContent>
    </Tabs>
  );
}
