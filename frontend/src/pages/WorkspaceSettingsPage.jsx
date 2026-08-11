import { useRef, useState } from 'react';
import { Palette, Trash2, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import PinnacleLogo from '@/components/PinnacleLogo';
import { useAuth } from '@/context/AuthContext';
import { api, errMsg } from '@/lib/api';
import { applyAccent } from '@/lib/tenant';

const PRESETS = ['#059669', '#0f766e', '#2563eb', '#7c3aed', '#db2777', '#ea580c', '#0f172a'];

export default function WorkspaceSettingsPage() {
  const { tenant, setTenant } = useAuth();
  const fileRef = useRef(null);
  const [companyName, setCompanyName] = useState(tenant?.branding?.company_name || tenant?.name || '');
  const [tagline, setTagline] = useState(tenant?.branding?.tagline || '');
  const [accent, setAccent] = useState(tenant?.branding?.accent_color || '#059669');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.put('/tenant/branding', { company_name: companyName, tagline, accent_color: accent });
      setTenant(r.data);
      applyAccent(r.data.branding?.accent_color);
      toast.success('Branding updated');
    } catch (e) {
      toast.error(errMsg(e, 'Could not save branding'));
    } finally {
      setBusy(false);
    }
  };

  const uploadLogo = async (file) => {
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    setBusy(true);
    try {
      const r = await api.post('/tenant/logo', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setTenant(r.data);
      toast.success('Logo updated');
    } catch (e) {
      toast.error(errMsg(e, 'Logo upload failed'));
    } finally {
      setBusy(false);
    }
  };

  const removeLogo = async () => {
    setBusy(true);
    try {
      const r = await api.delete('/tenant/logo');
      setTenant(r.data);
      toast.success('Logo removed');
    } catch (e) {
      toast.error(errMsg(e, 'Could not remove logo'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-6" data-testid="workspace-settings-page">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Workspace</h1>
        <p className="text-sm text-muted-foreground mt-1">
          White-label how {tenant?.name || 'your workspace'} looks to your team and candidates.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sign-in address</CardTitle>
          <CardDescription>Your team signs in at this URL.</CardDescription>
        </CardHeader>
        <CardContent>
          <code className="text-sm bg-muted px-3 py-2 rounded-md inline-block" data-testid="workspace-login-url">
            {window.location.origin}/{tenant?.slug}/login
          </code>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Identity</CardTitle>
          <CardDescription>Shown on the sign-in page and in the app sidebar.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex items-center gap-4">
            {tenant?.branding?.logo_url ? (
              <img src={tenant.branding.logo_url} alt="Workspace logo" className="h-14 w-14 rounded-xl object-cover border border-border" data-testid="workspace-logo-preview" />
            ) : (
              <PinnacleLogo size={56} />
            )}
            <div className="flex items-center gap-2">
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                className="hidden"
                data-testid="workspace-logo-input"
                onChange={(e) => uploadLogo(e.target.files?.[0])}
              />
              <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={busy} data-testid="workspace-logo-upload-button">
                <Upload className="h-4 w-4 mr-1" /> Upload logo
              </Button>
              {tenant?.branding?.logo_url && (
                <Button variant="ghost" onClick={removeLogo} disabled={busy} data-testid="workspace-logo-remove-button">
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="cname">Company name</Label>
            <Input id="cname" data-testid="workspace-company-name-input" value={companyName} onChange={(e) => setCompanyName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tagline">Tagline</Label>
            <Input id="tagline" data-testid="workspace-tagline-input" value={tagline}
              onChange={(e) => setTagline(e.target.value)} placeholder="Hiring the best, faster" />
          </div>

          <div className="space-y-2">
            <Label className="flex items-center gap-2"><Palette className="h-4 w-4" /> Accent colour</Label>
            <div className="flex items-center gap-3 flex-wrap">
              {PRESETS.map((c) => (
                <button
                  key={c}
                  onClick={() => { setAccent(c); applyAccent(c); }}
                  data-testid={`accent-swatch-${c.replace('#', '')}`}
                  className={`h-9 w-9 rounded-full border-2 transition-transform hover:scale-110 ${accent === c ? 'border-foreground' : 'border-transparent'}`}
                  style={{ background: c }}
                  aria-label={c}
                />
              ))}
              <Input
                value={accent}
                onChange={(e) => setAccent(e.target.value)}
                data-testid="accent-hex-input"
                className="w-32 font-mono"
              />
            </div>
          </div>

          <Button onClick={save} disabled={busy} data-testid="workspace-save-button">
            {busy ? 'Saving…' : 'Save changes'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
