import { useCallback, useEffect, useRef, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { ExternalLink, ImagePlus, Plus, Upload, X } from 'lucide-react';
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
  const [assetVersion, setAssetVersion] = useState(0);
  const logoInputRef = useRef();
  const heroInputRef = useRef();
  const ogInputRef = useRef();

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
      ['portal_url', 'key', 'created_at', 'updated_at',
       'logo_file_id', 'hero_image_file_id', 'og_image_file_id'].forEach((k) => delete body[k]);
      const { data } = await api.put('/career/settings', body);
      setSettings(data);
      toast.success('Career portal settings saved');
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  const uploadAsset = async (endpoint, file, label) => {
    const fd = new FormData();
    fd.append('file', file);
    try {
      await api.post(endpoint, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success(`${label} uploaded`);
      setAssetVersion((v) => v + 1);
      load();
    } catch (e) {
      toast.error(errMsg(e, `Could not upload ${label}`));
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
          <p className="text-sm text-muted-foreground mt-1">Control visibility, branding, and SEO for your public careers site.</p>
        </div>
        <div className="flex items-center gap-2">
          <NavLink to="/career-portal/content"><Button variant="outline" size="sm">Edit Content Pages</Button></NavLink>
          <NavLink to="/career-portal/media"><Button variant="outline" size="sm">Media Library</Button></NavLink>
          <a href={settings.portal_url} target="_blank" rel="noreferrer">
            <Button variant="outline" size="sm"><ExternalLink className="h-3.5 w-3.5 mr-1" /> Preview</Button>
          </a>
        </div>
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
        <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Branding — Logo & Colors</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 rounded-xl border border-border flex items-center justify-center overflow-hidden bg-secondary shrink-0">
              {settings.logo_file_id ? (
                <img key={`logo-${assetVersion}`} src={`${backendUrl}/api/career/public/logo?v=${assetVersion}`} alt="Logo" className="h-full w-full object-cover" />
              ) : (
                <span className="text-xs text-muted-foreground">No logo</span>
              )}
            </div>
            <div>
              <Button size="sm" variant="outline" onClick={() => logoInputRef.current?.click()} data-testid="career-logo-upload-button">
                <Upload className="h-3.5 w-3.5 mr-1" /> Upload Logo
              </Button>
              <p className="text-xs text-muted-foreground mt-1">PNG or SVG, under 5MB. Square works best.</p>
              <input ref={logoInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadAsset('/career/settings/logo', e.target.files[0], 'Logo')} />
            </div>
          </div>
          <div>
            <Label>Company Name</Label>
            <Input value={settings.company_name || ''} onChange={(e) => setSettings((s) => ({ ...s, company_name: e.target.value }))} data-testid="career-company-name-input" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Primary Color</Label>
              <div className="flex items-center gap-2">
                <input type="color" value={settings.primary_color || '#1a5c47'} onChange={(e) => setSettings((s) => ({ ...s, primary_color: e.target.value }))} className="h-9 w-14 rounded border border-border" data-testid="career-primary-color-input" />
                <span className="text-xs font-mono text-muted-foreground">{settings.primary_color}</span>
              </div>
            </div>
            <div>
              <Label>Secondary / Accent Color</Label>
              <div className="flex items-center gap-2">
                <input type="color" value={settings.secondary_color || '#f4b942'} onChange={(e) => setSettings((s) => ({ ...s, secondary_color: e.target.value }))} className="h-9 w-14 rounded border border-border" data-testid="career-secondary-color-input" />
                <span className="text-xs font-mono text-muted-foreground">{settings.secondary_color || '#f4b942'}</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="shadow-none">
        <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Branding — Hero Image</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-xl border border-border overflow-hidden bg-secondary aspect-[16/6] max-w-2xl">
            {settings.hero_image_file_id ? (
              <img key={`hero-${assetVersion}`} src={`${backendUrl}/api/career/public/hero?v=${assetVersion}`} alt="Hero" className="h-full w-full object-cover" data-testid="career-hero-preview" />
            ) : (
              <div className="h-full w-full flex items-center justify-center text-xs text-muted-foreground"><ImagePlus className="h-6 w-6 mr-2 opacity-40" /> No hero image yet</div>
            )}
          </div>
          <div>
            <Button size="sm" variant="outline" onClick={() => heroInputRef.current?.click()} data-testid="career-hero-upload-button">
              <Upload className="h-3.5 w-3.5 mr-1" /> Upload Hero Image
            </Button>
            <p className="text-xs text-muted-foreground mt-1">Landscape 16:6 or 16:9 works best. Under 8MB.</p>
            <input ref={heroInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadAsset('/career/settings/hero', e.target.files[0], 'Hero image')} />
          </div>
        </CardContent>
      </Card>

      <Card className="shadow-none">
        <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Branding — Typography</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">Paste a Google Fonts embed URL (e.g. <code>https://fonts.googleapis.com/css2?family=Inter:wght@400;600&amp;display=swap</code>) and the CSS <code>font-family</code> value (e.g. <code>Inter, sans-serif</code>). Leave blank to use system fonts.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>Heading font URL</Label>
              <Input value={settings.heading_font_url || ''} placeholder="https://fonts.googleapis.com/..." onChange={(e) => setSettings((s) => ({ ...s, heading_font_url: e.target.value }))} data-testid="career-heading-font-url-input" />
            </div>
            <div>
              <Label>Heading font-family</Label>
              <Input value={settings.heading_font_family || ''} placeholder="Poppins, sans-serif" onChange={(e) => setSettings((s) => ({ ...s, heading_font_family: e.target.value }))} data-testid="career-heading-font-family-input" />
            </div>
            <div>
              <Label>Body font URL</Label>
              <Input value={settings.body_font_url || ''} placeholder="https://fonts.googleapis.com/..." onChange={(e) => setSettings((s) => ({ ...s, body_font_url: e.target.value }))} data-testid="career-body-font-url-input" />
            </div>
            <div>
              <Label>Body font-family</Label>
              <Input value={settings.body_font_family || ''} placeholder="Inter, sans-serif" onChange={(e) => setSettings((s) => ({ ...s, body_font_family: e.target.value }))} data-testid="career-body-font-family-input" />
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
            <Label>About Us (shown on homepage below hero)</Label>
            <Textarea rows={4} value={settings.about_text || ''} onChange={(e) => setSettings((s) => ({ ...s, about_text: e.target.value }))} data-testid="career-about-input" />
          </div>
          <div>
            <Label>Homepage Benefits (chips)</Label>
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

      <Card className="shadow-none">
        <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">SEO</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>Meta description</Label>
            <Textarea rows={2} value={settings.meta_description || ''} placeholder="One-sentence description used in search results and social previews." onChange={(e) => setSettings((s) => ({ ...s, meta_description: e.target.value }))} data-testid="career-meta-description-input" />
            <p className="text-xs text-muted-foreground mt-1">Aim for 140-160 characters.</p>
          </div>
          <div>
            <Label>Meta keywords (comma-separated)</Label>
            <Input value={settings.meta_keywords || ''} placeholder="hiring, careers, engineering jobs" onChange={(e) => setSettings((s) => ({ ...s, meta_keywords: e.target.value }))} data-testid="career-meta-keywords-input" />
          </div>
          <div className="flex items-center gap-4">
            <div className="h-16 w-32 rounded border border-border overflow-hidden bg-secondary shrink-0">
              {settings.og_image_file_id ? (
                <img key={`og-${assetVersion}`} src={`${backendUrl}/api/career/public/og-image?v=${assetVersion}`} alt="OG" className="h-full w-full object-cover" />
              ) : (
                <span className="text-xs text-muted-foreground flex h-full items-center justify-center">No OG image</span>
              )}
            </div>
            <div>
              <Button size="sm" variant="outline" onClick={() => ogInputRef.current?.click()} data-testid="career-og-upload-button">
                <Upload className="h-3.5 w-3.5 mr-1" /> Upload social preview image
              </Button>
              <p className="text-xs text-muted-foreground mt-1">1200×630 recommended for LinkedIn / Twitter / Slack. Falls back to hero, then logo.</p>
              <input ref={ogInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadAsset('/career/settings/og-image', e.target.files[0], 'Social preview image')} />
            </div>
          </div>
          <div className="flex items-center justify-between gap-3 pt-2 border-t border-border">
            <div>
              <p className="text-sm font-medium">Google Jobs structured data</p>
              <p className="text-xs text-muted-foreground">Auto-embeds JobPosting JSON-LD on every open role so Google Jobs / Indeed can index it.</p>
            </div>
            <Switch
              checked={settings.jobposting_seo_enabled !== false}
              onCheckedChange={(v) => { setSettings((s) => ({ ...s, jobposting_seo_enabled: v })); save({ jobposting_seo_enabled: v }); }}
              data-testid="career-jobposting-seo-switch"
            />
          </div>
          <div className="pt-2 border-t border-border">
            <p className="text-xs text-muted-foreground">
              robots.txt: <a href={`${backendUrl}/api/career/seo/robots.txt`} target="_blank" rel="noreferrer" className="underline">view</a>
              {' · '}
              sitemap.xml: <a href={`${backendUrl}/api/career/seo/sitemap.xml`} target="_blank" rel="noreferrer" className="underline">view</a>
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={() => save()} disabled={saving} data-testid="career-settings-save-button">Save Changes</Button>
      </div>
    </div>
  );
}
