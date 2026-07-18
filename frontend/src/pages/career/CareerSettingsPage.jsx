import { useCallback, useEffect, useRef, useState } from 'react';
import { ExternalLink, Plus, Upload, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { api, errMsg } from '@/lib/api';

export default function CareerSettingsPage() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newBenefit, setNewBenefit] = useState('');
  const [logoVersion, setLogoVersion] = useState(0);
  const logoInputRef = useRef();

  const load = useCallback(() => {
    api.get('/career/settings').then((r) => setSettings(r.data)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async (overrides = {}) => {
    setSaving(true);
    try {
      const body = { ...settings, ...overrides };
      delete body.portal_url;
      delete body.key;
      delete body.created_at;
      delete body.updated_at;
      delete body.logo_file_id;
      const { data } = await api.put('/career/settings', body);
      setSettings(data);
      toast.success('Career portal settings saved');
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  const uploadLogo = async (file) => {
    const fd = new FormData();
    fd.append('file', file);
    try {
      await api.post('/career/settings/logo', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('Logo uploaded');
      setLogoVersion((v) => v + 1);
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not upload logo'));
    }
  };

  const addBenefit = () => {
    if (!newBenefit.trim()) return;
    setSettings((s) => ({ ...s, benefits: [...(s.benefits || []), newBenefit.trim()] }));
    setNewBenefit('');
  };

  const removeBenefit = (i) => {
    setSettings((s) => ({ ...s, benefits: s.benefits.filter((_, idx) => idx !== i) }));
  };

  if (loading || !settings) {
    return <div className="p-6"><div className="h-8 w-48 bg-secondary rounded animate-pulse" /></div>;
  }

  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  return (
    <div className="p-6 space-y-6 max-w-3xl" data-testid="career-settings-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Career Portal Settings</h1>
          <p className="text-sm text-muted-foreground mt-1">Control visibility and branding of your public careers site.</p>
        </div>
        <a href={settings.portal_url} target="_blank" rel="noreferrer">
          <Button variant="outline" size="sm"><ExternalLink className="h-3.5 w-3.5 mr-1" /> Preview Portal</Button>
        </a>
      </div>

      <Card className="shadow-none">
        <CardContent className="py-4 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">Enable Career Portal</p>
            <p className="text-xs text-muted-foreground">When off, the public site returns a &ldquo;not available&rdquo; message.</p>
          </div>
          <Switch
            checked={settings.portal_enabled}
            onCheckedChange={(v) => { setSettings((s) => ({ ...s, portal_enabled: v })); save({ portal_enabled: v }); }}
            data-testid="career-portal-enabled-switch"
          />
        </CardContent>
      </Card>

      <Card className="shadow-none">
        <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Branding</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 rounded-xl border border-border flex items-center justify-center overflow-hidden bg-secondary shrink-0">
              {settings.logo_file_id ? (
                <img key={logoVersion} src={`${backendUrl}/api/career/public/logo?v=${logoVersion}`} alt="Logo" className="h-full w-full object-cover" />
              ) : (
                <span className="text-xs text-muted-foreground">No logo</span>
              )}
            </div>
            <div>
              <Button size="sm" variant="outline" onClick={() => logoInputRef.current?.click()} data-testid="career-logo-upload-button">
                <Upload className="h-3.5 w-3.5 mr-1" /> Upload Logo
              </Button>
              <input ref={logoInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadLogo(e.target.files[0])} />
            </div>
          </div>
          <div>
            <Label>Company Name</Label>
            <Input value={settings.company_name || ''} onChange={(e) => setSettings((s) => ({ ...s, company_name: e.target.value }))} data-testid="career-company-name-input" />
          </div>
          <div>
            <Label>Primary Color</Label>
            <div className="flex items-center gap-2">
              <input type="color" value={settings.primary_color || '#1a5c47'} onChange={(e) => setSettings((s) => ({ ...s, primary_color: e.target.value }))} className="h-9 w-14 rounded border border-border" data-testid="career-primary-color-input" />
              <span className="text-xs font-mono text-muted-foreground">{settings.primary_color}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="shadow-none">
        <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Homepage Content</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>Headline</Label>
            <Input value={settings.headline || ''} onChange={(e) => setSettings((s) => ({ ...s, headline: e.target.value }))} data-testid="career-headline-input" />
          </div>
          <div>
            <Label>Subheadline</Label>
            <Textarea rows={2} value={settings.subheadline || ''} onChange={(e) => setSettings((s) => ({ ...s, subheadline: e.target.value }))} data-testid="career-subheadline-input" />
          </div>
          <div>
            <Label>Tagline (browser tab / SEO)</Label>
            <Input value={settings.tagline || ''} onChange={(e) => setSettings((s) => ({ ...s, tagline: e.target.value }))} data-testid="career-tagline-input" />
          </div>
          <div>
            <Label>About Us</Label>
            <Textarea rows={4} value={settings.about_text || ''} onChange={(e) => setSettings((s) => ({ ...s, about_text: e.target.value }))} data-testid="career-about-input" />
          </div>
          <div>
            <Label>Benefits</Label>
            <div className="flex flex-wrap gap-2 mb-2">
              {(settings.benefits || []).map((b, i) => (
                <Badge key={i} variant="outline" className="gap-1" data-testid={`career-benefit-${i}`}>
                  {b}
                  <button onClick={() => removeBenefit(i)} className="hover:text-destructive"><X className="h-3 w-3" /></button>
                </Badge>
              ))}
            </div>
            <div className="flex gap-2">
              <Input value={newBenefit} onChange={(e) => setNewBenefit(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addBenefit())} placeholder="e.g. Health insurance" data-testid="career-benefit-input" />
              <Button variant="outline" onClick={addBenefit} data-testid="career-benefit-add-button"><Plus className="h-4 w-4" /></Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={() => save()} disabled={saving} data-testid="career-settings-save-button">Save Changes</Button>
      </div>
    </div>
  );
}
