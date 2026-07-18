import { useCallback, useEffect, useRef, useState } from 'react';
import { ExternalLink, ImagePlus, Loader2, Upload } from 'lucide-react';
import { toast } from 'sonner';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { api, errMsg } from '@/lib/api';

const PAGE_KEYS = [
  { key: 'about', label: 'About Us' },
  { key: 'benefits', label: 'Benefits & Perks' },
  { key: 'life', label: 'Life at Company' },
  { key: 'testimonials', label: 'Testimonials' },
];

export default function CareerContentPage() {
  const [active, setActive] = useState('about');
  const [pages, setPages] = useState({});
  const [saving, setSaving] = useState(false);
  const [heroVersion, setHeroVersion] = useState(0);
  const [showPreview, setShowPreview] = useState(false);
  const heroInputRef = useRef();
  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  const load = useCallback(async () => {
    try {
      const r = await api.get('/career/pages');
      const map = {};
      r.data.forEach((p) => { map[p.key] = p; });
      setPages(map);
    } catch (e) {
      toast.error(errMsg(e, 'Could not load content pages'));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const current = pages[active];

  const patch = (updates) => {
    setPages((ps) => ({ ...ps, [active]: { ...ps[active], ...updates } }));
  };

  const save = async () => {
    if (!current) return;
    setSaving(true);
    try {
      const body = {
        hero_heading: current.hero_heading || '',
        hero_subheading: current.hero_subheading || '',
        body_markdown: current.body_markdown || '',
        meta_description: current.meta_description || '',
        published: !!current.published,
      };
      const { data } = await api.put(`/career/pages/${active}`, body);
      setPages((ps) => ({ ...ps, [active]: data }));
      toast.success(`${PAGE_KEYS.find((p) => p.key === active)?.label} saved`);
    } catch (e) {
      toast.error(errMsg(e, 'Save failed'));
    } finally {
      setSaving(false);
    }
  };

  const uploadHero = async (file) => {
    const fd = new FormData();
    fd.append('file', file);
    try {
      await api.post(`/career/pages/${active}/hero`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success('Hero image uploaded');
      setHeroVersion((v) => v + 1);
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Upload failed'));
    }
  };

  if (!current) {
    return <div className="p-6"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="p-6 space-y-4 max-w-4xl" data-testid="career-content-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Content Pages</h1>
          <p className="text-sm text-muted-foreground mt-1">Manage the About, Benefits, Life at Company, and Testimonials pages shown on your career portal.</p>
        </div>
      </div>

      <Tabs value={active} onValueChange={setActive}>
        <TabsList data-testid="career-content-tabs">
          {PAGE_KEYS.map((p) => (
            <TabsTrigger key={p.key} value={p.key} data-testid={`career-content-tab-${p.key}`}>
              {p.label}{pages[p.key]?.published ? '' : ' •'}
            </TabsTrigger>
          ))}
        </TabsList>

        {PAGE_KEYS.map((p) => (
          <TabsContent key={p.key} value={p.key} className="space-y-4 mt-4">
            <Card className="shadow-none">
              <CardContent className="py-4 flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">Publish this page</p>
                  <p className="text-xs text-muted-foreground">Unpublished pages return 404 to visitors and are hidden from the header nav.</p>
                </div>
                <div className="flex items-center gap-3">
                  {current.published && (
                    <a href={`${window.location.origin}/careers/${active}`} target="_blank" rel="noreferrer">
                      <Button variant="outline" size="sm"><ExternalLink className="h-3.5 w-3.5 mr-1" /> Preview live</Button>
                    </a>
                  )}
                  <Switch checked={!!current.published} onCheckedChange={(v) => patch({ published: v })} data-testid={`career-content-publish-${active}`} />
                </div>
              </CardContent>
            </Card>

            <Card className="shadow-none">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">Hero</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label>Heading</Label>
                  <Input value={current.hero_heading || ''} onChange={(e) => patch({ hero_heading: e.target.value })} data-testid={`career-content-heading-${active}`} />
                </div>
                <div>
                  <Label>Subheading</Label>
                  <Textarea rows={2} value={current.hero_subheading || ''} onChange={(e) => patch({ hero_subheading: e.target.value })} data-testid={`career-content-subheading-${active}`} />
                </div>
                <div>
                  <Label>Hero image</Label>
                  <div className="rounded-xl border border-border overflow-hidden bg-secondary aspect-[16/6] max-w-2xl mt-1">
                    {current.hero_image_file_id ? (
                      <img key={heroVersion} src={`${backendUrl}/api/career/public/pages/${active}/hero?v=${heroVersion}`} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <div className="h-full w-full flex items-center justify-center text-xs text-muted-foreground"><ImagePlus className="h-6 w-6 mr-2 opacity-40" /> No hero image</div>
                    )}
                  </div>
                  <Button size="sm" variant="outline" onClick={() => heroInputRef.current?.click()} className="mt-2" data-testid={`career-content-hero-upload-${active}`}>
                    <Upload className="h-3.5 w-3.5 mr-1" /> Upload hero image
                  </Button>
                  <input ref={heroInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadHero(e.target.files[0])} />
                </div>
              </CardContent>
            </Card>

            <Card className="shadow-none">
              <CardHeader className="pb-2 flex flex-row items-center justify-between gap-3">
                <CardTitle className="text-sm font-semibold">Body</CardTitle>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Preview</span>
                  <Switch checked={showPreview} onCheckedChange={setShowPreview} />
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-muted-foreground">Supports Markdown: <code>**bold**</code>, <code>*italic*</code>, <code># Heading</code>, <code>- list item</code>, links <code>[text](url)</code>. Images from the Media Library can be embedded as <code>![alt](/api/career/public/media/&lt;id&gt;)</code>.</p>
                {showPreview ? (
                  <div className="prose prose-sm max-w-none border border-border rounded-lg p-4 bg-card" data-testid={`career-content-preview-${active}`}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{current.body_markdown || '_No content yet_'}</ReactMarkdown>
                  </div>
                ) : (
                  <Textarea
                    rows={16}
                    className="font-mono text-sm"
                    value={current.body_markdown || ''}
                    onChange={(e) => patch({ body_markdown: e.target.value })}
                    data-testid={`career-content-body-${active}`}
                    placeholder="# Welcome\n\nTell your story here — mission, values, what makes this a great place to work..."
                  />
                )}
              </CardContent>
            </Card>

            <Card className="shadow-none">
              <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold">SEO for this page</CardTitle></CardHeader>
              <CardContent>
                <Label>Meta description</Label>
                <Textarea rows={2} value={current.meta_description || ''} onChange={(e) => patch({ meta_description: e.target.value })} placeholder="Falls back to the site-wide description if empty." data-testid={`career-content-meta-${active}`} />
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>

      <div className="flex justify-end gap-2 sticky bottom-4 bg-background/90 backdrop-blur py-2 border-t border-border">
        <Button onClick={save} disabled={saving} data-testid="career-content-save-button">
          {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null}
          Save {PAGE_KEYS.find((p) => p.key === active)?.label}
        </Button>
      </div>
    </div>
  );
}
