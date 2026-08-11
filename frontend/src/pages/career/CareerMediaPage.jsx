import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Copy, Loader2, Search, Trash2, Upload, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { api, errMsg } from '@/lib/api';
import { getTenantSlug } from '@/lib/tenant';

export default function CareerMediaPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [tagFilter, setTagFilter] = useState('all');
  const [uploading, setUploading] = useState(false);
  const [uploadTags, setUploadTags] = useState('');
  const [editing, setEditing] = useState(null); // media item
  const [copied, setCopied] = useState(null);
  const fileInputRef = useRef();
  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  const load = useCallback(() => {
    setLoading(true);
    const params = {};
    if (q) params.q = q;
    if (tagFilter && tagFilter !== 'all') params.tag = tagFilter;
    api.get('/career/media', { params }).then((r) => setItems(r.data)).finally(() => setLoading(false));
  }, [q, tagFilter]);

  useEffect(() => { load(); }, [load]);

  const doUpload = async (files) => {
    if (!files?.length) return;
    setUploading(true);
    try {
      const fd = new FormData();
      Array.from(files).slice(0, 20).forEach((f) => fd.append('files', f));
      if (uploadTags.trim()) fd.append('tags', uploadTags.trim());
      const { data } = await api.post('/career/media', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success(`Uploaded ${data.created.length} image${data.created.length === 1 ? '' : 's'}${data.skipped ? ` (${data.skipped} skipped — non-image or >10MB)` : ''}`);
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Upload failed'));
    } finally {
      setUploading(false);
    }
  };

  const remove = async (id) => {
    if (!window.confirm('Delete this image? Any place using its URL will break.')) return;
    try {
      await api.delete(`/career/media/${id}`);
      setItems((xs) => xs.filter((x) => x.id !== id));
      toast.success('Deleted');
    } catch (e) {
      toast.error(errMsg(e, 'Delete failed'));
    }
  };

  const saveTags = async () => {
    if (!editing) return;
    try {
      const tags = editing._tagsRaw.split(',').map((t) => t.trim()).filter(Boolean);
      const { data } = await api.put(`/career/media/${editing.id}/tags`, { tags });
      setItems((xs) => xs.map((x) => (x.id === data.id ? data : x)));
      setEditing(null);
      toast.success('Tags updated');
    } catch (e) {
      toast.error(errMsg(e, 'Save failed'));
    }
  };

  const copyUrl = (id) => {
    const url = `${backendUrl}/api/career/public/media/${id}?tenant=${getTenantSlug() || ''}`;
    navigator.clipboard?.writeText(url);
    setCopied(id);
    setTimeout(() => setCopied(null), 1500);
  };

  const allTags = Array.from(new Set(items.flatMap((i) => i.tags || []))).sort();

  return (
    <div className="p-6 space-y-4 max-w-6xl" data-testid="career-media-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Media Library</h1>
          <p className="text-sm text-muted-foreground mt-1">Upload and organize images used across your career portal. Copy an image's public URL to embed it in a content page.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Input
            placeholder="Tags to add to next upload (comma-separated)"
            value={uploadTags}
            onChange={(e) => setUploadTags(e.target.value)}
            className="h-9 w-[260px]"
            data-testid="career-media-upload-tags-input"
          />
          <Button onClick={() => fileInputRef.current?.click()} disabled={uploading} data-testid="career-media-upload-button">
            {uploading ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Upload className="h-4 w-4 mr-1" />}
            Upload
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => { doUpload(e.target.files); e.target.value = ''; }}
          />
        </div>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative">
          <Search className="h-4 w-4 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search filenames..." className="pl-8 w-[240px] h-9" data-testid="career-media-search-input" />
        </div>
        <Badge
          variant={tagFilter === 'all' ? 'default' : 'outline'}
          onClick={() => setTagFilter('all')}
          className="cursor-pointer"
          data-testid="career-media-tag-all"
        >
          All
        </Badge>
        {allTags.map((t) => (
          <Badge
            key={t}
            variant={tagFilter === t ? 'default' : 'outline'}
            onClick={() => setTagFilter(t)}
            className="cursor-pointer"
            data-testid={`career-media-tag-${t}`}
          >
            {t}
          </Badge>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading media...</div>
      ) : items.length === 0 ? (
        <div className="border border-dashed rounded-2xl p-12 text-center text-sm text-muted-foreground">
          No media yet. Upload your first image using the button above.
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
          {items.map((m) => (
            <Card key={m.id} className="overflow-hidden group shadow-none" data-testid={`career-media-item-${m.id}`}>
              <div className="aspect-square bg-secondary relative">
                <img src={`${backendUrl}/api/career/public/media/${m.id}?tenant=${getTenantSlug() || ''}`} alt={m.filename} className="h-full w-full object-cover" />
                <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-1">
                  <Button size="icon" variant="secondary" onClick={() => copyUrl(m.id)} title="Copy public URL" data-testid={`career-media-copy-${m.id}`}>
                    {copied === m.id ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                  <Button size="icon" variant="secondary" onClick={() => setEditing({ ...m, _tagsRaw: (m.tags || []).join(', ') })} title="Edit tags">
                    <span className="text-xs">#</span>
                  </Button>
                  <Button size="icon" variant="destructive" onClick={() => remove(m.id)} title="Delete" data-testid={`career-media-delete-${m.id}`}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <CardContent className="py-2 px-2">
                <p className="text-xs truncate" title={m.filename}>{m.filename}</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {(m.tags || []).map((t) => (
                    <Badge key={t} variant="outline" className="text-[10px] px-1.5 py-0">{t}</Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!editing} onOpenChange={(v) => !v && setEditing(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit tags</DialogTitle></DialogHeader>
          {editing && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">{editing.filename}</p>
              <div>
                <Label>Tags (comma-separated)</Label>
                <Input
                  value={editing._tagsRaw}
                  onChange={(e) => setEditing((x) => ({ ...x, _tagsRaw: e.target.value }))}
                  placeholder="hero, team, culture"
                  data-testid="career-media-tags-input"
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}><X className="h-4 w-4 mr-1" /> Cancel</Button>
            <Button onClick={saveTags} data-testid="career-media-tags-save-button"><Check className="h-4 w-4 mr-1" /> Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
