import { useEffect, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import {
  Building2,
  Copy,
  Cpu,
  KeyRound,
  LogIn,
  LogOut,
  PauseCircle,
  PlayCircle,
  Plus,
  ShieldCheck,
  Trash2,
  Users,
  CalendarClock,
  Zap,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { errMsg, platformApi } from '@/lib/api';
import { setTenantSlug } from '@/lib/tenant';

const slugify = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);

const emptyForm = { name: '', slug: '', admin_name: '', admin_email: '', admin_password: '', plan: 'free' };
const PLANS = ['free', 'pro', 'enterprise'];

export default function PlatformDashboardPage() {
  const navigate = useNavigate();
  const [tenants, setTenants] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [pwOpen, setPwOpen] = useState(false);
  const [pw, setPw] = useState({ current_password: '', new_password: '', confirm: '' });

  // Per-tenant AI provider config
  const [providers, setProviders] = useState([]);
  const [aiTenant, setAiTenant] = useState(null);
  const [aiForm, setAiForm] = useState({ provider: 'grok', model: '', api_key: '' });
  const [aiExisting, setAiExisting] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiTesting, setAiTesting] = useState(false);

  // Per-tenant Google Calendar/Gmail OAuth client
  const [googleTenant, setGoogleTenant] = useState(null);
  const [googleForm, setGoogleForm] = useState({ client_id: '', client_secret: '' });
  const [googleExisting, setGoogleExisting] = useState(null);
  const [googleBusy, setGoogleBusy] = useState(false);

  const admin = (() => {
    try {
      return JSON.parse(localStorage.getItem('ats_platform_admin')) || {};
    } catch {
      return {};
    }
  })();

  const load = () => {
    Promise.all([platformApi.get('/platform/tenants'), platformApi.get('/platform/stats')])
      .then(([t, s]) => {
        setTenants(t.data);
        setStats(s.data);
      })
      .catch((e) => toast.error(errMsg(e, 'Could not load workspaces')))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  useEffect(() => {
    platformApi
      .get('/platform/ai/providers')
      .then((r) => setProviders(r.data))
      .catch(() => {});
  }, []);

  const providerLabel = (id) => providers.find((p) => p.id === id)?.label || id;
  const providerDefaultModel = (id) => providers.find((p) => p.id === id)?.default_model || '';

  const openAi = (t) => {
    setAiTenant(t);
    setAiExisting(t.ai || null);
    const provider = t.ai?.provider || 'grok';
    setAiForm({
      provider,
      model: t.ai?.model || providerDefaultModel(provider),
      api_key: '',
    });
  };

  const onProviderChange = (provider) => {
    // When switching provider, prefill its default model (unless editing the
    // provider already saved for this tenant).
    const keepModel = aiExisting?.provider === provider ? aiExisting?.model : '';
    setAiForm((f) => ({ ...f, provider, model: keepModel || providerDefaultModel(provider) }));
  };

  const testAi = async () => {
    setAiTesting(true);
    try {
      const r = await platformApi.post(`/platform/tenants/${aiTenant.id}/ai/test`, {
        provider: aiForm.provider,
        model: aiForm.model,
        api_key: aiForm.api_key, // empty = use stored key
      });
      if (r.data.ok) toast.success(r.data.message);
      else toast.error(r.data.message);
    } catch (e) {
      toast.error(errMsg(e, 'Test failed'));
    } finally {
      setAiTesting(false);
    }
  };

  const saveAi = async () => {
    setAiBusy(true);
    try {
      const r = await platformApi.put(`/platform/tenants/${aiTenant.id}/ai`, {
        provider: aiForm.provider,
        model: aiForm.model,
        api_key: aiForm.api_key,
      });
      toast.success(`AI provider saved for ${aiTenant.name}`);
      setTenants((prev) => prev.map((x) => (x.id === aiTenant.id ? { ...x, ai: r.data } : x)));
      setAiTenant(null);
    } catch (e) {
      toast.error(errMsg(e, 'Could not save AI settings'));
    } finally {
      setAiBusy(false);
    }
  };

  const clearAi = async () => {
    setAiBusy(true);
    try {
      await platformApi.delete(`/platform/tenants/${aiTenant.id}/ai`);
      toast.success(`AI provider removed for ${aiTenant.name}`);
      setTenants((prev) =>
        prev.map((x) =>
          x.id === aiTenant.id
            ? { ...x, ai: { configured: false, provider: null, model: null, key_masked: null } }
            : x,
        ),
      );
      setAiTenant(null);
    } catch (e) {
      toast.error(errMsg(e, 'Could not remove AI settings'));
    } finally {
      setAiBusy(false);
    }
  };

  const openGoogle = (t) => {
    setGoogleTenant(t);
    setGoogleExisting(t.google || null);
    setGoogleForm({ client_id: t.google?.client_id || '', client_secret: '' });
  };

  const saveGoogle = async () => {
    if (!googleForm.client_id.trim()) {
      toast.error('Client ID is required');
      return;
    }
    setGoogleBusy(true);
    try {
      const r = await platformApi.put(`/platform/tenants/${googleTenant.id}/google`, {
        client_id: googleForm.client_id.trim(),
        client_secret: googleForm.client_secret,
      });
      toast.success(`Google OAuth client saved for ${googleTenant.name}`);
      setTenants((prev) => prev.map((x) => (x.id === googleTenant.id ? { ...x, google: r.data } : x)));
      setGoogleTenant(null);
    } catch (e) {
      toast.error(errMsg(e, 'Could not save Google OAuth settings'));
    } finally {
      setGoogleBusy(false);
    }
  };

  const clearGoogle = async () => {
    setGoogleBusy(true);
    try {
      await platformApi.delete(`/platform/tenants/${googleTenant.id}/google`);
      toast.success(`Google OAuth client removed for ${googleTenant.name}`);
      setTenants((prev) =>
        prev.map((x) =>
          x.id === googleTenant.id ? { ...x, google: { configured: false, client_id: null, has_secret: false } } : x,
        ),
      );
      setGoogleTenant(null);
    } catch (e) {
      toast.error(errMsg(e, 'Could not remove Google OAuth settings'));
    } finally {
      setGoogleBusy(false);
    }
  };

  if (!localStorage.getItem('ats_platform_token')) return <Navigate to="/platform/login" replace />;

  const create = async () => {
    setBusy(true);
    try {
      const payload = { ...form, slug: slugify(form.slug || form.name) };
      const r = await platformApi.post('/platform/tenants', payload);
      setCreated(r.data);
      setOpen(false);
      setForm(emptyForm);
      load();
      toast.success(`${r.data.tenant.name} is live`);
    } catch (e) {
      toast.error(errMsg(e, 'Could not create workspace'));
    } finally {
      setBusy(false);
    }
  };

  const toggleStatus = async (t) => {
    const status = t.status === 'active' ? 'suspended' : 'active';
    try {
      await platformApi.patch(`/platform/tenants/${t.id}`, { status });
      toast.success(`${t.name} ${status === 'active' ? 'reactivated' : 'suspended'}`);
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Update failed'));
    }
  };

  const impersonate = async (t) => {
    try {
      const r = await platformApi.post(`/platform/tenants/${t.id}/impersonate`);
      localStorage.setItem('ats_token', r.data.token);
      localStorage.setItem('ats_user', JSON.stringify(r.data.user));
      localStorage.setItem('ats_tenant', JSON.stringify(r.data.tenant));
      setTenantSlug(r.data.tenant.slug);
      window.location.href = '/';
    } catch (e) {
      toast.error(errMsg(e, 'Could not open workspace'));
    }
  };

  const destroy = async () => {
    const t = confirmDelete;
    setBusy(true);
    try {
      await platformApi.delete(`/platform/tenants/${t.id}`);
      toast.success(`${t.name} and all its data were deleted`);
      setConfirmDelete(null);
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Delete failed'));
    } finally {
      setBusy(false);
    }
  };

  const changePassword = async () => {
    if (pw.new_password !== pw.confirm) {
      toast.error('New passwords do not match');
      return;
    }
    setBusy(true);
    try {
      await platformApi.post('/platform/change-password', {
        current_password: pw.current_password,
        new_password: pw.new_password,
      });
      toast.success('Password updated');
      setPwOpen(false);
      setPw({ current_password: '', new_password: '', confirm: '' });
    } catch (e) {
      toast.error(errMsg(e, 'Could not update password'));
    } finally {
      setBusy(false);
    }
  };

  const signOut = () => {
    localStorage.removeItem('ats_platform_token');
    localStorage.removeItem('ats_platform_admin');
    navigate('/platform/login');
  };

  const origin = window.location.origin;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100" data-testid="platform-dashboard">
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-teal-500/15 border border-teal-400/30">
              <ShieldCheck className="h-4 w-4 text-teal-300" />
            </span>
            <div>
              <div className="font-display font-semibold tracking-tight">Pinnacle Control</div>
              <div className="text-[11px] text-slate-400">{admin.email}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={() => setOpen(true)}
              data-testid="new-tenant-button"
              className="bg-teal-500 hover:bg-teal-400 text-slate-950 font-semibold"
            >
              <Plus className="h-4 w-4 mr-1" /> New workspace
            </Button>
            <Button
              variant="ghost"
              onClick={() => setPwOpen(true)}
              data-testid="change-password-button"
              className="text-slate-300 hover:text-white hover:bg-slate-800"
              title="Change password"
            >
              <KeyRound className="h-4 w-4" />
            </Button>
            <Button variant="ghost" onClick={signOut} data-testid="platform-logout-button" className="text-slate-300 hover:text-white hover:bg-slate-800">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
          {[
            { label: 'Workspaces', value: stats?.tenants ?? '—', icon: Building2 },
            { label: 'Active', value: stats?.active_tenants ?? '—', icon: PlayCircle },
            { label: 'Users', value: stats?.users ?? '—', icon: Users },
            { label: 'Candidates', value: stats?.candidates ?? '—', icon: Users },
          ].map((c) => (
            <div key={c.label} className="rounded-xl border border-slate-800 bg-slate-900/50 p-5" data-testid={`platform-stat-${c.label.toLowerCase()}`}>
              <div className="flex items-center justify-between text-slate-400 text-xs uppercase tracking-wider">
                {c.label}
                <c.icon className="h-4 w-4" />
              </div>
              <div className="mt-2 font-display text-3xl font-semibold">{c.value}</div>
            </div>
          ))}
        </div>

        <h2 className="text-lg font-medium mb-4">Customer workspaces</h2>
        {loading ? (
          <div className="text-slate-400 text-sm">Loading…</div>
        ) : (
          <div className="space-y-3" data-testid="tenant-list">
            {tenants.map((t) => (
              <div
                key={t.id}
                data-testid={`tenant-row-${t.slug}`}
                className="rounded-xl border border-slate-800 bg-slate-900/50 p-5 flex flex-col lg:flex-row lg:items-center gap-4"
              >
                <div className="flex items-center gap-3 min-w-[240px]">
                  <span
                    className="inline-flex h-10 w-10 items-center justify-center rounded-lg font-semibold text-slate-950"
                    style={{ background: t.branding?.accent_color || '#059669' }}
                  >
                    {(t.name || '?').slice(0, 1).toUpperCase()}
                  </span>
                  <div>
                    <div className="font-medium">{t.name}</div>
                    <button
                      className="text-xs text-slate-400 hover:text-teal-300 font-mono inline-flex items-center gap-1"
                      onClick={() => {
                        navigator.clipboard?.writeText(`${origin}/${t.slug}/login`);
                        toast.success('Sign-in link copied');
                      }}
                      data-testid={`copy-login-${t.slug}`}
                    >
                      /{t.slug}/login <Copy className="h-3 w-3" />
                    </button>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm text-slate-400 flex-1">
                  <span>{t.counts?.users ?? 0} users</span>
                  <span>{t.counts?.candidates ?? 0} candidates</span>
                  <span>{t.counts?.jobs ?? 0} jobs</span>
                  <span>{t.counts?.interviews ?? 0} interviews</span>
                  <Badge
                    className={
                      t.status === 'active'
                        ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                        : 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                    }
                    data-testid={`tenant-status-${t.slug}`}
                  >
                    {t.status}
                  </Badge>
                  <Badge className="bg-slate-800 text-slate-300 border border-slate-700">{t.plan}</Badge>
                  {t.ai?.configured ? (
                    <Badge
                      className="bg-violet-500/15 text-violet-300 border border-violet-500/30"
                      data-testid={`tenant-ai-${t.slug}`}
                    >
                      <Cpu className="h-3 w-3 mr-1" /> {providerLabel(t.ai.provider)}
                    </Badge>
                  ) : (
                    <Badge
                      className="bg-slate-800 text-slate-500 border border-slate-700"
                      data-testid={`tenant-ai-${t.slug}`}
                    >
                      No AI key
                    </Badge>
                  )}
                  {t.google?.configured ? (
                    <Badge
                      className="bg-sky-500/15 text-sky-300 border border-sky-500/30"
                      data-testid={`tenant-google-${t.slug}`}
                    >
                      <CalendarClock className="h-3 w-3 mr-1" /> Google connected
                    </Badge>
                  ) : (
                    <Badge
                      className="bg-slate-800 text-slate-500 border border-slate-700"
                      data-testid={`tenant-google-${t.slug}`}
                    >
                      No Google OAuth
                    </Badge>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-700 bg-transparent text-slate-200 hover:bg-slate-800"
                    onClick={() => openAi(t)}
                    data-testid={`ai-config-${t.slug}`}
                  >
                    <Cpu className="h-4 w-4 mr-1" /> AI
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-700 bg-transparent text-slate-200 hover:bg-slate-800"
                    onClick={() => openGoogle(t)}
                    data-testid={`google-config-${t.slug}`}
                  >
                    <CalendarClock className="h-4 w-4 mr-1" /> Google
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-700 bg-transparent text-slate-200 hover:bg-slate-800"
                    onClick={() => impersonate(t)}
                    data-testid={`impersonate-${t.slug}`}
                  >
                    <LogIn className="h-4 w-4 mr-1" /> Open
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-700 bg-transparent text-slate-200 hover:bg-slate-800"
                    onClick={() => toggleStatus(t)}
                    data-testid={`toggle-status-${t.slug}`}
                  >
                    {t.status === 'active' ? <PauseCircle className="h-4 w-4" /> : <PlayCircle className="h-4 w-4" />}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-rose-300 hover:text-rose-200 hover:bg-rose-500/10"
                    onClick={() => setConfirmDelete(t)}
                    data-testid={`delete-${t.slug}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Create workspace */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg" data-testid="create-tenant-dialog">
          <DialogHeader>
            <DialogTitle>New workspace</DialogTitle>
            <DialogDescription>
              Starts completely empty — no demo data. The owner can invite their team and add jobs.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="tname">Company name</Label>
                <Input id="tname" data-testid="tenant-name-input" value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Acme Hiring" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tslug">URL slug</Label>
                <Input id="tslug" data-testid="tenant-slug-input" value={form.slug}
                  onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder={slugify(form.name) || 'acme'} />
                <p className="text-xs text-muted-foreground font-mono">/{slugify(form.slug || form.name) || 'acme'}/login</p>
              </div>
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="aname">Owner name</Label>
                <Input id="aname" data-testid="tenant-admin-name-input" value={form.admin_name}
                  onChange={(e) => setForm({ ...form, admin_name: e.target.value })} placeholder="Jane Doe" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="aemail">Owner email</Label>
                <Input id="aemail" type="email" data-testid="tenant-admin-email-input" value={form.admin_email}
                  onChange={(e) => setForm({ ...form, admin_email: e.target.value })} placeholder="jane@acme.com" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="apass">Temporary password</Label>
              <Input id="apass" data-testid="tenant-admin-password-input" value={form.admin_password}
                onChange={(e) => setForm({ ...form, admin_password: e.target.value })} placeholder="At least 8 characters" />
            </div>
            <div className="space-y-1.5">
              <Label>Plan</Label>
              <div className="flex gap-2">
                {PLANS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setForm({ ...form, plan: p })}
                    data-testid={`tenant-plan-${p}`}
                    className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                      form.plan === p ? 'bg-primary text-primary-foreground border-primary' : 'border-border hover:bg-secondary'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={create} disabled={busy} data-testid="create-tenant-submit">
              {busy ? 'Creating…' : 'Create workspace'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Created confirmation */}
      <Dialog open={!!created} onOpenChange={() => setCreated(null)}>
        <DialogContent data-testid="tenant-created-dialog">
          <DialogHeader>
            <DialogTitle>{created?.tenant?.name} is ready</DialogTitle>
            <DialogDescription>Send these details to the workspace owner.</DialogDescription>
          </DialogHeader>
          <div className="rounded-lg bg-muted p-4 text-sm space-y-1 font-mono break-all">
            <div>{origin}{created?.login_url}</div>
            <div>{created?.owner?.email}</div>
          </div>
          <DialogFooter>
            <Button onClick={() => {
              navigator.clipboard?.writeText(`${origin}${created?.login_url}`);
              toast.success('Link copied');
            }}>
              <Copy className="h-4 w-4 mr-1" /> Copy sign-in link
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Change owner password */}
      <Dialog open={pwOpen} onOpenChange={setPwOpen}>
        <DialogContent className="sm:max-w-md" data-testid="change-password-dialog">
          <DialogHeader>
            <DialogTitle>Change owner password</DialogTitle>
            <DialogDescription>
              Applies to {admin.email}. Once you set it here, it is yours — server config will never overwrite it again.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="cur">Current password</Label>
              <Input id="cur" type="password" data-testid="current-password-input" value={pw.current_password}
                onChange={(e) => setPw({ ...pw, current_password: e.target.value })} placeholder="••••••••" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="np">New password</Label>
              <Input id="np" type="password" data-testid="new-password-input" value={pw.new_password}
                onChange={(e) => setPw({ ...pw, new_password: e.target.value })} placeholder="At least 8 characters" />
              <p className="text-xs text-muted-foreground">
                Needs 8+ characters with upper and lower case letters and a number.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cp">Confirm new password</Label>
              <Input id="cp" type="password" data-testid="confirm-password-input" value={pw.confirm}
                onChange={(e) => setPw({ ...pw, confirm: e.target.value })} placeholder="Repeat it" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPwOpen(false)}>Cancel</Button>
            <Button onClick={changePassword} disabled={busy} data-testid="change-password-submit">
              {busy ? 'Saving…' : 'Update password'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Per-tenant AI provider */}
      <Dialog open={!!aiTenant} onOpenChange={(o) => !o && setAiTenant(null)}>
        <DialogContent className="sm:max-w-lg" data-testid="ai-config-dialog">
          <DialogHeader>
            <DialogTitle>AI provider — {aiTenant?.name}</DialogTitle>
            <DialogDescription>
              Choose which model this workspace uses for resume parsing, reply parsing and fit
              scoring, and paste that provider&apos;s API key. Each workspace is fully independent.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Provider</Label>
              <Select value={aiForm.provider} onValueChange={onProviderChange}>
                <SelectTrigger data-testid="ai-provider-select">
                  <SelectValue placeholder="Choose a provider" />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((p) => (
                    <SelectItem key={p.id} value={p.id} data-testid={`ai-provider-${p.id}`}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ai-model">Model</Label>
              <Input
                id="ai-model"
                data-testid="ai-model-input"
                value={aiForm.model}
                onChange={(e) => setAiForm({ ...aiForm, model: e.target.value })}
                placeholder={providerDefaultModel(aiForm.provider) || 'model name'}
              />
              <p className="text-xs text-muted-foreground">
                Default for {providerLabel(aiForm.provider)}:{' '}
                <span className="font-mono">{providerDefaultModel(aiForm.provider) || '—'}</span>
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ai-key">API key</Label>
              <Input
                id="ai-key"
                type="password"
                data-testid="ai-key-input"
                value={aiForm.api_key}
                onChange={(e) => setAiForm({ ...aiForm, api_key: e.target.value })}
                placeholder={
                  aiExisting?.configured
                    ? `Saved: ${aiExisting.key_masked} — leave blank to keep`
                    : 'Paste the provider API key'
                }
              />
              <p className="text-xs text-muted-foreground">
                Stored securely and never shown again in full. Leave blank to keep the existing key.
              </p>
            </div>
          </div>
          <DialogFooter className="flex-col-reverse sm:flex-row sm:justify-between gap-2">
            <div>
              {aiExisting?.configured && (
                <Button
                  variant="ghost"
                  className="text-rose-500 hover:text-rose-400 hover:bg-rose-500/10"
                  onClick={clearAi}
                  disabled={aiBusy}
                  data-testid="ai-clear-button"
                >
                  Remove key
                </Button>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={testAi} disabled={aiTesting} data-testid="ai-test-button">
                <Zap className="h-4 w-4 mr-1" /> {aiTesting ? 'Testing…' : 'Test key'}
              </Button>
              <Button onClick={saveAi} disabled={aiBusy} data-testid="ai-save-button">
                {aiBusy ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Per-tenant Google OAuth client */}
      <Dialog open={!!googleTenant} onOpenChange={(o) => !o && setGoogleTenant(null)}>
        <DialogContent className="sm:max-w-lg" data-testid="google-config-dialog">
          <DialogHeader>
            <DialogTitle>Google Calendar OAuth — {googleTenant?.name}</DialogTitle>
            <DialogDescription>
              Register this workspace&apos;s own Google Cloud OAuth client for Calendar sync,
              Meet links and Gmail reply scanning. Leave unset to keep using the deployment&apos;s
              default Google app.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-lg bg-muted p-3 text-xs space-y-1">
              <p className="text-muted-foreground">Authorized redirect URI (add this in Google Cloud Console):</p>
              <p className="font-mono break-all" data-testid="google-redirect-uri">{origin}/api/oauth/calendar/callback</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="google-client-id">Client ID</Label>
              <Input
                id="google-client-id"
                data-testid="google-client-id-input"
                value={googleForm.client_id}
                onChange={(e) => setGoogleForm({ ...googleForm, client_id: e.target.value })}
                placeholder="1234567890-abc.apps.googleusercontent.com"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="google-client-secret">Client secret</Label>
              <Input
                id="google-client-secret"
                type="password"
                data-testid="google-client-secret-input"
                value={googleForm.client_secret}
                onChange={(e) => setGoogleForm({ ...googleForm, client_secret: e.target.value })}
                placeholder={
                  googleExisting?.has_secret
                    ? 'Saved — leave blank to keep the existing secret'
                    : 'Paste the OAuth client secret'
                }
              />
              <p className="text-xs text-muted-foreground">
                Encrypted at rest and never shown again in full. Leave blank to keep the existing secret.
              </p>
            </div>
          </div>
          <DialogFooter className="flex-col-reverse sm:flex-row sm:justify-between gap-2">
            <div>
              {googleExisting?.configured && (
                <Button
                  variant="ghost"
                  className="text-rose-500 hover:text-rose-400 hover:bg-rose-500/10"
                  onClick={clearGoogle}
                  disabled={googleBusy}
                  data-testid="google-clear-button"
                >
                  Remove
                </Button>
              )}
            </div>
            <Button onClick={saveGoogle} disabled={googleBusy} data-testid="google-save-button">
              {googleBusy ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={!!confirmDelete} onOpenChange={() => setConfirmDelete(null)}>
        <DialogContent data-testid="delete-tenant-dialog">
          <DialogHeader>
            <DialogTitle>Delete {confirmDelete?.name}?</DialogTitle>
            <DialogDescription>
              This permanently removes {confirmDelete?.counts?.candidates ?? 0} candidates,{' '}
              {confirmDelete?.counts?.jobs ?? 0} jobs and every user in this workspace. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(null)}>Cancel</Button>
            <Button variant="destructive" onClick={destroy} disabled={busy} data-testid="confirm-delete-tenant">
              {busy ? 'Deleting…' : 'Delete permanently'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
