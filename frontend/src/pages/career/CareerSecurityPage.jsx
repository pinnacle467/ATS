import { useCallback, useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  Globe,
  Mail,
  RefreshCw,
  Save,
  Send,
  Shield,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { api, errMsg } from '@/lib/api';

// -------- Custom Domain tab --------
function CustomDomainTab() {
  const [state, setState] = useState(null);
  const [domain, setDomain] = useState('');
  const [busy, setBusy] = useState(false);
  const [lastVerify, setLastVerify] = useState(null);

  const load = useCallback(() => {
    api.get('/career/settings/custom-domain').then((r) => {
      setState(r.data);
      setDomain(r.data.domain || '');
    });
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!domain.trim()) return toast.error('Enter a domain first');
    setBusy(true);
    try {
      await api.put('/career/settings/custom-domain', { domain: domain.trim() });
      toast.success('Domain saved. Now add the DNS records below and click Verify.');
      load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const verify = async () => {
    setBusy(true);
    try {
      const { data } = await api.post('/career/settings/custom-domain/verify');
      setLastVerify(data);
      if (data.status === 'verified') toast.success('Domain verified!');
      else toast.error('Verification failed — check the records again in ~5 minutes.');
      load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const remove = async () => {
    if (!confirm('Remove the custom domain? Visitors will need to use the default URL.')) return;
    setBusy(true);
    try {
      await api.delete('/career/settings/custom-domain');
      setLastVerify(null);
      setDomain('');
      toast.success('Custom domain removed');
      load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const copy = (t) => { navigator.clipboard.writeText(t); toast.success('Copied'); };

  if (!state) return <div className="h-32 bg-secondary rounded animate-pulse" />;

  const statusBadge = ({
    none: <Badge variant="outline">Not configured</Badge>,
    pending: <Badge variant="outline" className="border-amber-500/50 text-amber-700"><Clock className="h-3 w-3 mr-1" /> Pending verification</Badge>,
    verified: <Badge className="bg-emerald-600"><CheckCircle2 className="h-3 w-3 mr-1" /> Verified</Badge>,
    failed: <Badge variant="destructive"><AlertCircle className="h-3 w-3 mr-1" /> Verification failed</Badge>,
  })[state.status || 'none'];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2"><Globe className="h-4 w-4" /> Custom Domain</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <Label>Custom domain</Label>
              <Input
                placeholder="careers.acme.com"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                data-testid="custom-domain-input"
              />
              <p className="text-xs text-muted-foreground mt-1">Use a subdomain like <code>careers.acme.com</code>. Root domains (<code>acme.com</code>) are not supported.</p>
            </div>
            <div className="pt-6">{statusBadge}</div>
          </div>
          <div className="flex gap-2">
            <Button onClick={save} disabled={busy} data-testid="custom-domain-save">
              <Save className="h-3.5 w-3.5 mr-1" /> Save Domain
            </Button>
            {state.domain && (
              <>
                <Button variant="outline" onClick={verify} disabled={busy} data-testid="custom-domain-verify">
                  <RefreshCw className={`h-3.5 w-3.5 mr-1 ${busy ? 'animate-spin' : ''}`} /> Verify DNS
                </Button>
                <Button variant="ghost" onClick={remove} disabled={busy} className="text-destructive ml-auto" data-testid="custom-domain-remove">
                  <Trash2 className="h-3.5 w-3.5 mr-1" /> Remove
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {state.domain && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">DNS records to add at your registrar</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs text-muted-foreground">Add both records at your DNS host (Cloudflare, Route53, GoDaddy, Namecheap, etc). Verification usually works within 5–15 minutes but can take up to a few hours.</p>

            <div className="rounded-lg border border-border overflow-hidden">
              <div className="grid grid-cols-[80px_1fr_1fr] text-xs bg-secondary/60 px-3 py-2 font-medium">
                <span>Type</span><span>Host / Name</span><span>Value / Target</span>
              </div>
              <div className="grid grid-cols-[80px_1fr_1fr] text-xs px-3 py-3 border-t border-border items-center">
                <Badge variant="outline">CNAME</Badge>
                <div className="font-mono flex items-center gap-1">{state.domain} <button onClick={() => copy(state.domain)}><Copy className="h-3 w-3 text-muted-foreground hover:text-foreground" /></button></div>
                <div className="font-mono flex items-center gap-1 break-all">{state.cname_target} <button onClick={() => copy(state.cname_target)}><Copy className="h-3 w-3 text-muted-foreground hover:text-foreground shrink-0" /></button></div>
              </div>
              <div className="grid grid-cols-[80px_1fr_1fr] text-xs px-3 py-3 border-t border-border items-center">
                <Badge variant="outline">TXT</Badge>
                <div className="font-mono flex items-center gap-1">{state.txt_record_host} <button onClick={() => copy(state.txt_record_host)}><Copy className="h-3 w-3 text-muted-foreground hover:text-foreground" /></button></div>
                <div className="font-mono flex items-center gap-1 break-all">{state.verification_token} <button onClick={() => copy(state.verification_token)}><Copy className="h-3 w-3 text-muted-foreground hover:text-foreground shrink-0" /></button></div>
              </div>
            </div>

            <div className="rounded-lg bg-secondary/40 border border-border p-3 text-xs text-muted-foreground space-y-1">
              <p className="font-medium text-foreground">SSL / HTTPS</p>
              <p>SSL is provisioned automatically once the CNAME resolves — the hosting reverse proxy will issue a Let's Encrypt certificate within a few minutes of verification. No action needed on your end.</p>
              <p className="mt-1">If your DNS host offers "Proxied" mode (e.g. Cloudflare's orange cloud), turn it <em>off</em> for this CNAME so our proxy can terminate SSL directly.</p>
            </div>

            {lastVerify && (
              <Alert>
                <AlertDescription className="text-xs">
                  <div className="font-medium mb-1">Last verification result: <span className={lastVerify.status === 'verified' ? 'text-emerald-600' : 'text-destructive'}>{lastVerify.status}</span></div>
                  <div className="grid grid-cols-2 gap-3 mt-2">
                    <div>
                      <div className="font-medium">TXT check</div>
                      <div>{lastVerify.checks?.txt?.ok ? '✓ matched' : '✗ not found'}</div>
                      {lastVerify.checks?.txt?.found?.length > 0 && (
                        <div className="text-muted-foreground mt-1">Found: {lastVerify.checks.txt.found.slice(0, 2).join(', ')}</div>
                      )}
                      {lastVerify.checks?.txt?.error && <div className="text-muted-foreground mt-1">Error: {lastVerify.checks.txt.error}</div>}
                    </div>
                    <div>
                      <div className="font-medium">CNAME check</div>
                      <div>{lastVerify.checks?.cname?.ok ? '✓ matched' : '✗ not matched'}</div>
                      {lastVerify.checks?.cname?.found?.length > 0 && (
                        <div className="text-muted-foreground mt-1">Found: {lastVerify.checks.cname.found.slice(0, 2).join(', ')}</div>
                      )}
                      {lastVerify.checks?.cname?.error && <div className="text-muted-foreground mt-1">Error: {lastVerify.checks.cname.error}</div>}
                    </div>
                  </div>
                </AlertDescription>
              </Alert>
            )}

            {state.status === 'verified' && (
              <a href={`https://${state.domain}`} target="_blank" rel="noreferrer">
                <Button variant="outline" size="sm"><ExternalLink className="h-3.5 w-3.5 mr-1" /> Open https://{state.domain}</Button>
              </a>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// -------- Email Templates tab --------
function EmailTemplatesTab() {
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewHtml, setPreviewHtml] = useState('');
  const [previewSubject, setPreviewSubject] = useState('');
  const [testEmail, setTestEmail] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get('/career/email-templates').then((r) => setData(r.data));
  }, []);
  useEffect(() => { load(); }, [load]);

  const openEditor = (tpl) => setEditing({ ...tpl });

  const save = async () => {
    setBusy(true);
    try {
      await api.put(`/career/email-templates/${editing.key}`, {
        subject: editing.subject,
        html_body: editing.html_body,
        enabled: editing.enabled,
        auto_send: editing.auto_send,
      });
      toast.success('Template saved');
      setEditing(null);
      load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const preview = async (key) => {
    try {
      const { data: p } = await api.get(`/career/email-templates/${key}/preview`);
      setPreviewSubject(p.subject);
      setPreviewHtml(p.html);
      setPreviewOpen(true);
    } catch (e) { toast.error(errMsg(e)); }
  };

  const previewCurrentEdit = () => {
    // Simple client-side preview using the current draft (renders {{vars}} with sample values)
    const sample = {
      candidate_name: 'Jane Doe', candidate_first_name: 'Jane', candidate_email: 'jane@example.com',
      job_title: 'Senior Product Designer', company_name: 'Acme', stage: 'Screening', primary_color: '#1a5c47',
    };
    const render = (s) => (s || '').replace(/\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g, (_, k) => sample[k] ?? `{{${k}}}`);
    setPreviewSubject(render(editing.subject));
    setPreviewHtml(render(editing.html_body));
    setPreviewOpen(true);
  };

  const sendTest = async () => {
    if (!testEmail.trim()) return toast.error('Enter a test email address');
    setBusy(true);
    try {
      const { data: r } = await api.post(`/career/email-templates/${editing.key}/test`, { to_email: testEmail.trim() });
      if (r.sent) toast.success(`Test email sent to ${testEmail} from ${r.sender || 'admin'}`);
      else toast.error(r.reason === 'no_gmail_connected'
        ? 'No admin has connected Google yet. Connect Google Calendar/Gmail from the Interviews page first.'
        : (r.error || r.reason || 'Send failed'));
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const reset = async (key) => {
    if (!confirm('Reset this template to default? Your customisations will be lost.')) return;
    setBusy(true);
    try {
      await api.post(`/career/email-templates/${key}/reset`);
      toast.success('Reset to default');
      if (editing?.key === key) setEditing(null);
      load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  if (!data) return <div className="h-32 bg-secondary rounded animate-pulse" />;

  return (
    <div className="space-y-4">
      {!editing && (
        <div className="space-y-3">
          {data.templates.map((t) => (
            <Card key={t.key}>
              <CardContent className="py-4 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-medium">{t.name}</p>
                    {t.enabled ? <Badge variant="outline" className="text-emerald-700 border-emerald-500/40">Enabled</Badge> : <Badge variant="outline" className="text-muted-foreground">Disabled</Badge>}
                    {t.auto_send && <Badge variant="outline" className="text-blue-700 border-blue-500/40">Auto-send</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1 truncate">{t.description}</p>
                  <p className="text-xs text-muted-foreground mt-1"><span className="font-mono">Subject:</span> {t.subject}</p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <Button size="sm" variant="outline" onClick={() => preview(t.key)} data-testid={`email-preview-${t.key}`}>Preview</Button>
                  <Button size="sm" onClick={() => openEditor(t)} data-testid={`email-edit-${t.key}`}>Edit</Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {editing && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2"><Mail className="h-4 w-4" /> {editing.name}</CardTitle>
            <p className="text-xs text-muted-foreground">{editing.description}</p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <Switch checked={editing.enabled} onCheckedChange={(v) => setEditing((s) => ({ ...s, enabled: v }))} data-testid="email-enabled-switch" />
                <Label>Enabled</Label>
              </div>
              {'auto_send' in editing && (
                <div className="flex items-center gap-2" title="Automatically send this template when triggered (currently: on new applicant submission)">
                  <Switch checked={editing.auto_send} onCheckedChange={(v) => setEditing((s) => ({ ...s, auto_send: v }))} data-testid="email-autosend-switch" />
                  <Label>Auto-send</Label>
                </div>
              )}
            </div>

            <div>
              <Label>Subject line</Label>
              <Input value={editing.subject} onChange={(e) => setEditing((s) => ({ ...s, subject: e.target.value }))} data-testid="email-subject-input" />
            </div>
            <div>
              <Label>HTML body</Label>
              <Textarea rows={14} value={editing.html_body} onChange={(e) => setEditing((s) => ({ ...s, html_body: e.target.value }))} className="font-mono text-xs" data-testid="email-body-input" />
            </div>

            <div className="rounded-lg border border-border p-3 bg-secondary/40">
              <p className="text-xs font-medium mb-2">Available variables (click to insert into the body):</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(data.variables).map(([v, help]) => (
                  <button
                    key={v}
                    type="button"
                    title={help}
                    onClick={() => setEditing((s) => ({ ...s, html_body: (s.html_body || '') + ' ' + v }))}
                    className="font-mono text-xs px-2 py-0.5 rounded bg-background border border-border hover:border-primary transition-colors"
                    data-testid={`email-var-${v.replace(/[^a-z_]/gi, '')}`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap gap-2 pt-2">
              <Button onClick={save} disabled={busy} data-testid="email-save-button"><Save className="h-3.5 w-3.5 mr-1" /> Save</Button>
              <Button variant="outline" onClick={previewCurrentEdit} data-testid="email-preview-button">Preview</Button>
              <div className="flex items-center gap-2 ml-auto">
                <Input placeholder="test@example.com" value={testEmail} onChange={(e) => setTestEmail(e.target.value)} className="w-56" data-testid="email-test-input" />
                <Button variant="outline" onClick={sendTest} disabled={busy} data-testid="email-test-send"><Send className="h-3.5 w-3.5 mr-1" /> Send test</Button>
              </div>
            </div>

            <div className="flex justify-between pt-2 border-t border-border">
              <Button variant="ghost" size="sm" onClick={() => setEditing(null)}>Back to list</Button>
              <Button variant="ghost" size="sm" onClick={() => reset(editing.key)} className="text-destructive">Reset to default</Button>
            </div>

            <Alert className="mt-2">
              <AlertDescription className="text-xs">
                Emails are sent from the connected Gmail account of the job's recruiter (or any admin who has connected Google). If no one has connected Google yet, sending will silently no-op — connect from the Interviews page or the Google Calendar prompt on your profile.
              </AlertDescription>
            </Alert>
          </CardContent>
        </Card>
      )}

      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Email Preview</DialogTitle></DialogHeader>
          <div className="text-xs text-muted-foreground">Subject:</div>
          <div className="text-sm font-medium">{previewSubject}</div>
          <div className="border border-border rounded-lg mt-3 overflow-hidden">
            <iframe title="preview" srcDoc={previewHtml} className="w-full h-96 bg-white" />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// -------- Cookie / Privacy tab --------
function CookiePrivacyTab({ security, setSecurity, save, busy }) {
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Cookie Banner &amp; Privacy Links</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Show cookie banner</p>
            <p className="text-xs text-muted-foreground">A dismissible notice appears once per visitor at the bottom of the careers site.</p>
          </div>
          <Switch checked={security.cookie_banner_enabled} onCheckedChange={(v) => setSecurity((s) => ({ ...s, cookie_banner_enabled: v }))} data-testid="cookie-banner-switch" />
        </div>
        <div>
          <Label>Banner text</Label>
          <Textarea rows={2} value={security.cookie_banner_text || ''} onChange={(e) => setSecurity((s) => ({ ...s, cookie_banner_text: e.target.value }))} data-testid="cookie-banner-text" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <Label>Privacy policy URL</Label>
            <Input placeholder="https://acme.com/privacy" value={security.privacy_policy_url || ''} onChange={(e) => setSecurity((s) => ({ ...s, privacy_policy_url: e.target.value }))} data-testid="privacy-url-input" />
            <p className="text-xs text-muted-foreground mt-1">Shown as a link in the cookie banner and the public footer.</p>
          </div>
          <div>
            <Label>Terms of service URL</Label>
            <Input placeholder="https://acme.com/terms" value={security.terms_url || ''} onChange={(e) => setSecurity((s) => ({ ...s, terms_url: e.target.value }))} data-testid="terms-url-input" />
            <p className="text-xs text-muted-foreground mt-1">Shown in the public footer.</p>
          </div>
        </div>
        <div className="flex justify-end">
          <Button onClick={save} disabled={busy} data-testid="cookie-privacy-save"><Save className="h-3.5 w-3.5 mr-1" /> Save</Button>
        </div>
      </CardContent>
    </Card>
  );
}

// -------- reCAPTCHA tab --------
function RecaptchaTab({ security, setSecurity, save, busy }) {
  const [secretDraft, setSecretDraft] = useState('');
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Google reCAPTCHA v3</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <Alert>
          <AlertDescription className="text-xs">
            Get keys at <a href="https://www.google.com/recaptcha/admin" target="_blank" rel="noreferrer" className="underline">google.com/recaptcha/admin</a>.
            Choose <strong>reCAPTCHA v3</strong>, add your careers domain (and <code>{typeof window !== 'undefined' ? window.location.hostname : ''}</code> for testing), and copy both keys below.
          </AlertDescription>
        </Alert>

        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Enable reCAPTCHA v3 on the apply form</p>
            <p className="text-xs text-muted-foreground">Invisible bot check that runs when applicants submit an application.</p>
          </div>
          <Switch checked={security.recaptcha_enabled} onCheckedChange={(v) => setSecurity((s) => ({ ...s, recaptcha_enabled: v }))} data-testid="recaptcha-enabled-switch" />
        </div>

        <div>
          <Label>Site key (public)</Label>
          <Input placeholder="6Lc..." value={security.recaptcha_site_key || ''} onChange={(e) => setSecurity((s) => ({ ...s, recaptcha_site_key: e.target.value }))} data-testid="recaptcha-site-key-input" />
        </div>
        <div>
          <Label>Secret key {security.recaptcha_secret_key_set && <span className="text-xs text-muted-foreground ml-2">(saved: {security.recaptcha_secret_key_hint})</span>}</Label>
          <Input type="password" placeholder={security.recaptcha_secret_key_set ? 'Enter to replace' : '6Lc...'} value={secretDraft} onChange={(e) => setSecretDraft(e.target.value)} data-testid="recaptcha-secret-key-input" />
          <p className="text-xs text-muted-foreground mt-1">Stored server-side only; never exposed to the browser.</p>
        </div>
        <div>
          <Label>Minimum score threshold ({(security.recaptcha_min_score ?? 0.5).toFixed(2)})</Label>
          <input
            type="range" min="0" max="1" step="0.05"
            value={security.recaptcha_min_score ?? 0.5}
            onChange={(e) => setSecurity((s) => ({ ...s, recaptcha_min_score: parseFloat(e.target.value) }))}
            className="w-full mt-2"
            data-testid="recaptcha-min-score-slider"
          />
          <p className="text-xs text-muted-foreground mt-1">Google returns a score 0.0–1.0 per submission. 0.5 is Google's default; raise to reduce spam, lower if you're getting false positives.</p>
        </div>

        <div className="flex justify-end">
          <Button onClick={() => save({ recaptcha_secret_key: secretDraft || undefined })} disabled={busy} data-testid="recaptcha-save"><Save className="h-3.5 w-3.5 mr-1" /> Save</Button>
        </div>
      </CardContent>
    </Card>
  );
}

// -------- Rate limiting tab --------
function RateLimitTab({ security, setSecurity, save, busy }) {
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Rate Limiting</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <p className="text-xs text-muted-foreground">Sliding-window per-IP limits on the public careers site. Set to <code>0</code> to disable a limit.</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <Label>Job applications per IP per hour</Label>
            <Input type="number" min="0" max="1000" value={security.rate_limit_apply_per_hour ?? 5} onChange={(e) => setSecurity((s) => ({ ...s, rate_limit_apply_per_hour: parseInt(e.target.value || '0', 10) }))} data-testid="ratelimit-apply-input" />
            <p className="text-xs text-muted-foreground mt-1">A single IP can submit up to N applications per hour per job posting. Default 5.</p>
          </div>
          <div>
            <Label>Public page loads per IP per minute</Label>
            <Input type="number" min="0" max="10000" value={security.rate_limit_public_per_minute ?? 60} onChange={(e) => setSecurity((s) => ({ ...s, rate_limit_public_per_minute: parseInt(e.target.value || '0', 10) }))} data-testid="ratelimit-public-input" />
            <p className="text-xs text-muted-foreground mt-1">Applies to job list and job detail API calls. Default 60/min.</p>
          </div>
        </div>
        <Alert>
          <AlertDescription className="text-xs">
            Rate limits are enforced in-memory on the backend process. When the limit is hit, callers get an HTTP 429 with a <code>Retry-After</code> header.
          </AlertDescription>
        </Alert>
        <div className="flex justify-end">
          <Button onClick={save} disabled={busy} data-testid="ratelimit-save"><Save className="h-3.5 w-3.5 mr-1" /> Save</Button>
        </div>
      </CardContent>
    </Card>
  );
}

// -------- Audit log tab --------
function AuditLogTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api.get('/career/audit-log?limit=200').then((r) => setRows(r.data || [])).finally(() => setLoading(false));
  }, []);
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Career Portal Audit Log</CardTitle></CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-24 bg-secondary rounded animate-pulse" />
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground py-6 text-center">No audit entries yet. Changes to security, domains, and email templates will appear here.</p>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <div className="grid grid-cols-[160px_140px_1fr_120px] text-xs bg-secondary/60 px-3 py-2 font-medium">
              <span>When</span><span>Action</span><span>Details</span><span>Actor</span>
            </div>
            {rows.map((r) => (
              <div key={r.id} className="grid grid-cols-[160px_140px_1fr_120px] text-xs px-3 py-2 border-t border-border">
                <span className="text-muted-foreground">{new Date(r.created_at).toLocaleString()}</span>
                <span className="font-mono truncate" title={r.action}>{r.action.replace('career.', '')}</span>
                <span className="truncate" title={r.details}>{r.details}</span>
                <span className="text-muted-foreground truncate">{r.actor_name}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// -------- Page shell --------
export default function CareerSecurityPage() {
  const [security, setSecurity] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get('/career/settings/security').then((r) => setSecurity(r.data));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (overrides = {}) => {
    setBusy(true);
    try {
      const payload = { ...security, ...overrides };
      // Strip masked/derived fields
      delete payload.recaptcha_secret_key_set;
      delete payload.recaptcha_secret_key_hint;
      // Only include secret_key if user provided a new value in this save cycle
      if (!overrides.recaptcha_secret_key) delete payload.recaptcha_secret_key;
      const { data } = await api.put('/career/settings/security', payload);
      setSecurity(data);
      toast.success('Saved');
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  if (!security) return <div className="p-6"><div className="h-8 w-48 bg-secondary rounded animate-pulse" /></div>;

  return (
    <div className="p-6 space-y-6 max-w-4xl" data-testid="career-security-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight flex items-center gap-2">
            <Shield className="h-6 w-6" /> Security &amp; Hardening
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Custom domain, applicant emails, cookie banner, reCAPTCHA, rate limits, and audit log.</p>
        </div>
        <NavLink to="/career-portal/settings"><Button variant="outline" size="sm">Back to Settings</Button></NavLink>
      </div>

      <Tabs defaultValue="domain" className="space-y-4">
        <TabsList className="grid grid-cols-3 md:grid-cols-6 w-full">
          <TabsTrigger value="domain" data-testid="tab-domain">Domain</TabsTrigger>
          <TabsTrigger value="email" data-testid="tab-email">Emails</TabsTrigger>
          <TabsTrigger value="cookies" data-testid="tab-cookies">Cookies</TabsTrigger>
          <TabsTrigger value="recaptcha" data-testid="tab-recaptcha">reCAPTCHA</TabsTrigger>
          <TabsTrigger value="ratelimit" data-testid="tab-ratelimit">Rate limits</TabsTrigger>
          <TabsTrigger value="audit" data-testid="tab-audit">Audit</TabsTrigger>
        </TabsList>
        <TabsContent value="domain"><CustomDomainTab /></TabsContent>
        <TabsContent value="email"><EmailTemplatesTab /></TabsContent>
        <TabsContent value="cookies"><CookiePrivacyTab security={security} setSecurity={setSecurity} save={() => save()} busy={busy} /></TabsContent>
        <TabsContent value="recaptcha"><RecaptchaTab security={security} setSecurity={setSecurity} save={save} busy={busy} /></TabsContent>
        <TabsContent value="ratelimit"><RateLimitTab security={security} setSecurity={setSecurity} save={() => save()} busy={busy} /></TabsContent>
        <TabsContent value="audit"><AuditLogTab /></TabsContent>
      </Tabs>
    </div>
  );
}
