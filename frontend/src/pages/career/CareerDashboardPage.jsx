import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Briefcase, Copy, ExternalLink, FileText, Globe, TrendingUp } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api';

export default function CareerDashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    api.get('/career/dashboard').then((r) => setData(r.data)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const copyUrl = () => {
    navigator.clipboard.writeText(data.portal_url);
    toast.success('Portal URL copied');
  };

  if (loading || !data) {
    return <div className="p-6"><div className="h-8 w-48 bg-secondary rounded animate-pulse" /></div>;
  }

  const kpis = [
    { label: 'Published Jobs', value: data.published_jobs, icon: Briefcase },
    { label: 'Total Applications', value: data.total_applications, icon: FileText },
    { label: 'Applications Today', value: data.applications_today, icon: TrendingUp },
    { label: 'Applications This Week', value: data.applications_this_week, icon: TrendingUp },
  ];

  return (
    <div className="p-6 space-y-6 max-w-6xl" data-testid="career-dashboard-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Career Portal</h1>
          <p className="text-sm text-muted-foreground mt-1">Your public careers site, applications, and portal settings.</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge
            className={data.portal_enabled ? 'bg-green-100 text-green-800' : 'bg-secondary text-muted-foreground'}
            data-testid="career-portal-status-badge"
          >
            {data.portal_enabled ? 'Published' : 'Draft'}
          </Badge>
        </div>
      </div>

      <Card className="shadow-none">
        <CardContent className="py-4 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 text-sm min-w-0">
            <Globe className="h-4 w-4 text-primary shrink-0" />
            <span className="font-mono text-muted-foreground truncate" data-testid="career-portal-url">{data.portal_url}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button size="sm" variant="outline" onClick={copyUrl} data-testid="career-copy-url-button">
              <Copy className="h-3.5 w-3.5 mr-1" /> Copy URL
            </Button>
            <a href={data.portal_url} target="_blank" rel="noreferrer">
              <Button size="sm" variant="outline" data-testid="career-open-portal-button">
                <ExternalLink className="h-3.5 w-3.5 mr-1" /> {data.portal_enabled ? 'Open Portal' : 'Preview Portal'}
              </Button>
            </a>
            {!data.portal_enabled && (
              <Link to="/career-portal/settings">
                <Button size="sm" data-testid="career-enable-portal-cta">Enable Portal</Button>
              </Link>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {kpis.map((k) => {
          const Icon = k.icon;
          return (
            <Card key={k.label} className="shadow-none" data-testid={`career-kpi-${k.label.toLowerCase().replace(/\s+/g, '-')}`}>
              <CardContent className="pt-5 pb-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-wide text-muted-foreground font-medium">{k.label}</span>
                  <Icon className="h-4 w-4 text-primary" />
                </div>
                <div className="font-display text-3xl font-semibold tabular-nums mt-2">{k.value ?? 0}</div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card className="shadow-none">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Latest Applications</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-border">
          {data.latest_applications.length === 0 && (
            <p className="text-sm text-muted-foreground py-6 text-center" data-testid="career-no-applications">
              No applications yet. Publish a job to start receiving applicants.
            </p>
          )}
          {data.latest_applications.map((a) => (
            <div key={a.id} className="py-3 flex items-center justify-between gap-3" data-testid={`career-application-${a.id}`}>
              <div className="min-w-0">
                <Link to={`/candidates/${a.candidate_id}`} className="text-sm font-medium hover:underline">
                  {a.candidate_name} <span className="text-muted-foreground font-mono text-xs">{a.candidate_code}</span>
                </Link>
                <p className="text-xs text-muted-foreground">Applied to {a.job_title}</p>
              </div>
              <span className="text-xs text-muted-foreground whitespace-nowrap">{new Date(a.created_at).toLocaleString()}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
