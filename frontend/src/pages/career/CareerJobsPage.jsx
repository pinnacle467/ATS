import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Copy, ExternalLink, Settings2 } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { api, errMsg } from '@/lib/api';

const EMPLOYMENT_TYPES = ['Full-time', 'Part-time', 'Contract', 'Internship'];
const EXPERIENCE_LEVELS = ['Entry-level', 'Mid-level', 'Senior', 'Lead'];
const REMOTE_TYPES = ['Remote', 'Hybrid', 'On-site'];

export default function CareerJobsPage() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [manageJob, setManageJob] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    api.get('/jobs').then((r) => setJobs(r.data || [])).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openManage = (job) => {
    setManageJob(job);
    setForm({
      employment_type: job.employment_type || '',
      experience_level: job.experience_level || '',
      remote_type: job.remote_type || '',
    });
  };

  const saveDetails = async () => {
    setSaving(true);
    try {
      await api.put(`/jobs/${manageJob.id}`, form);
      toast.success('Career portal details saved');
      setManageJob(null);
      load();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  const togglePublish = async (job) => {
    try {
      if (job.published) {
        await api.post(`/jobs/${job.id}/unpublish`);
        toast.success('Job unpublished from career portal');
      } else {
        await api.post(`/jobs/${job.id}/publish`);
        toast.success('Job published to career portal');
      }
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not update publish status'));
    }
  };

  const copyLink = (job) => {
    navigator.clipboard.writeText(job.public_url);
    toast.success('Link copied');
  };

  return (
    <div className="p-6 space-y-4 max-w-6xl" data-testid="career-jobs-page">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Career Portal Jobs</h1>
        <p className="text-sm text-muted-foreground mt-1">Publish open roles to your careers site and set employment details.</p>
      </div>

      {loading && <div className="h-32 bg-secondary rounded-xl animate-pulse" />}

      <div className="space-y-2">
        {jobs.map((j) => (
          <Card key={j.id} className="shadow-none" data-testid={`career-job-row-${j.id}`}>
            <CardContent className="py-3 flex items-center justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Link to={`/jobs/${j.id}`} className="font-medium text-sm hover:underline">{j.title}</Link>
                  <Badge variant="outline" className="text-[10px] capitalize">{j.status.replace('_', ' ')}</Badge>
                  {j.published ? (
                    <Badge className="bg-green-100 text-green-800 text-[10px]" data-testid={`career-job-published-${j.id}`}>Published</Badge>
                  ) : (
                    <Badge variant="outline" className="text-[10px] text-muted-foreground">Not published</Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {j.department} · {j.location || 'Remote'}
                  {j.employment_type ? ` · ${j.employment_type}` : ''}
                  {j.remote_type ? ` · ${j.remote_type}` : ''}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button size="sm" variant="outline" onClick={() => openManage(j)} data-testid={`career-job-manage-${j.id}`}>
                  <Settings2 className="h-3.5 w-3.5 mr-1" /> Details
                </Button>
                {j.published && (
                  <>
                    <Button size="sm" variant="outline" onClick={() => copyLink(j)} data-testid={`career-job-copy-link-${j.id}`}>
                      <Copy className="h-3.5 w-3.5" />
                    </Button>
                    <a href={j.public_url} target="_blank" rel="noreferrer">
                      <Button size="sm" variant="outline"><ExternalLink className="h-3.5 w-3.5" /></Button>
                    </a>
                  </>
                )}
                <Button
                  size="sm"
                  variant={j.published ? 'outline' : 'default'}
                  disabled={j.status !== 'open' && !j.published}
                  onClick={() => togglePublish(j)}
                  data-testid={`career-job-publish-toggle-${j.id}`}
                >
                  {j.published ? 'Unpublish' : 'Publish'}
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={!!manageJob} onOpenChange={(o) => !o && setManageJob(null)}>
        <DialogContent data-testid="career-job-details-dialog">
          <DialogHeader><DialogTitle>Career Portal Details — {manageJob?.title}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Employment Type</Label>
              <Select value={form.employment_type || undefined} onValueChange={(v) => setForm((f) => ({ ...f, employment_type: v }))}>
                <SelectTrigger data-testid="career-job-employment-type"><SelectValue placeholder="Select type" /></SelectTrigger>
                <SelectContent>{EMPLOYMENT_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Experience Level</Label>
              <Select value={form.experience_level || undefined} onValueChange={(v) => setForm((f) => ({ ...f, experience_level: v }))}>
                <SelectTrigger data-testid="career-job-experience-level"><SelectValue placeholder="Select level" /></SelectTrigger>
                <SelectContent>{EXPERIENCE_LEVELS.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Work Type</Label>
              <Select value={form.remote_type || undefined} onValueChange={(v) => setForm((f) => ({ ...f, remote_type: v }))}>
                <SelectTrigger data-testid="career-job-remote-type"><SelectValue placeholder="Select work type" /></SelectTrigger>
                <SelectContent>{REMOTE_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setManageJob(null)}>Cancel</Button>
            <Button onClick={saveDetails} disabled={saving} data-testid="career-job-details-save">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
