import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ArrowUpRight, Eye, FileText, Loader2, MousePointerClick, TrendingUp, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { api } from '@/lib/api';
import { careersPath } from '@/lib/tenant';

const SOURCE_COLORS = ['#1a5c47', '#2f7a5f', '#4c9578', '#6bb094', '#8bcbb0', '#f4b942', '#e8a52e', '#d99418', '#c88803', '#b57900'];

// Format a YYYY-MM-DD date string as "Jul 18" for x-axis labels
const fmtDate = (d) => {
  try {
    const dt = new Date(d + 'T00:00:00Z');
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
  } catch {
    return d;
  }
};

export default function CareerAnalyticsPage() {
  const [days, setDays] = useState('30');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    api.get('/career/analytics/overview', { params: { days: Number(days) } })
      .then((r) => setData(r.data))
      .finally(() => setLoading(false));
  }, [days]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) {
    return <div className="p-6"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>;
  }
  if (!data) return null;

  const kpis = [
    { label: 'Total Views', value: data.views, icon: Eye, hint: 'Page + job detail views' },
    { label: 'Applications', value: data.applications, icon: FileText, hint: 'Submitted via portal' },
    { label: 'Conversion', value: `${data.conversion_rate}%`, icon: TrendingUp, hint: 'Applications / job views' },
    { label: 'Unique Visitors', value: data.unique_visitors, icon: Users, hint: 'Distinct sessions' },
  ];

  return (
    <div className="p-6 space-y-6 max-w-6xl" data-testid="career-analytics-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Career Portal Analytics</h1>
          <p className="text-sm text-muted-foreground mt-1">Traffic and application performance for your public career site.</p>
        </div>
        <Select value={days} onValueChange={setDays}>
          <SelectTrigger className="w-[150px] h-9" data-testid="career-analytics-range-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="7">Last 7 days</SelectItem>
            <SelectItem value="30">Last 30 days</SelectItem>
            <SelectItem value="90">Last 90 days</SelectItem>
            <SelectItem value="180">Last 180 days</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {kpis.map((k, i) => (
          <Card key={i} className="shadow-none" data-testid={`career-analytics-kpi-${k.label.toLowerCase().replace(/\s+/g, '-')}`}>
            <CardContent className="py-4">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{k.label}</span>
                <k.icon className="h-3.5 w-3.5" />
              </div>
              <p className="font-display text-3xl font-semibold mt-1">{k.value}</p>
              <p className="text-xs text-muted-foreground mt-1">{k.hint}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="shadow-none">
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-semibold">Views &amp; Applications over time</CardTitle>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-primary" /> Views</span>
            <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: '#f4b942' }} /> Applications</span>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-72" data-testid="career-analytics-timeseries">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.timeseries} margin={{ top: 8, right: 16, bottom: 0, left: -16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(214 18% 90%)" vertical={false} />
                <XAxis dataKey="date" tickFormatter={fmtDate} fontSize={11} tickLine={false} axisLine={false} minTickGap={20} />
                <YAxis fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip
                  labelFormatter={fmtDate}
                  contentStyle={{ borderRadius: 8, border: '1px solid hsl(214 18% 88%)', fontSize: 13 }}
                />
                <Line type="monotone" dataKey="views" stroke="hsl(159 60% 26%)" strokeWidth={2} dot={false} name="Views" />
                <Line type="monotone" dataKey="applications" stroke="#f4b942" strokeWidth={2} dot={false} name="Applications" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Traffic Sources</CardTitle>
          </CardHeader>
          <CardContent>
            {data.sources.length === 0 ? (
              <p className="text-xs text-muted-foreground py-8 text-center">No traffic yet — share your portal URL to start seeing sources.</p>
            ) : (
              <div className="h-64" data-testid="career-analytics-sources">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.sources} layout="vertical" margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(214 18% 90%)" horizontal={false} />
                    <XAxis type="number" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                    <YAxis type="category" dataKey="name" fontSize={11} tickLine={false} axisLine={false} width={110} />
                    <Tooltip cursor={{ fill: 'hsl(210 16% 94%)' }} contentStyle={{ borderRadius: 8, border: '1px solid hsl(214 18% 88%)', fontSize: 13 }} />
                    <Bar dataKey="count" radius={[0, 6, 6, 0]}>
                      {data.sources.map((_, i) => (
                        <Cell key={i} fill={SOURCE_COLORS[i % SOURCE_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Funnel</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3" data-testid="career-analytics-funnel">
            <FunnelRow label="Page views" value={data.views} max={data.views} icon={Eye} />
            <FunnelRow label="Job detail views" value={data.job_views} max={data.views} icon={Eye} />
            <FunnelRow label="Started application" value={data.apply_starts} max={data.views} icon={MousePointerClick} />
            <FunnelRow label="Submitted application" value={data.applications} max={data.views} icon={FileText} highlight />
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-none">
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-semibold">Top Jobs</CardTitle>
          <span className="text-xs text-muted-foreground">Sorted by views in the selected window</span>
        </CardHeader>
        <CardContent>
          {data.top_jobs.length === 0 ? (
            <p className="text-xs text-muted-foreground py-8 text-center">No job views yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Role</TableHead>
                  <TableHead className="text-right">Views</TableHead>
                  <TableHead className="text-right">Applications</TableHead>
                  <TableHead className="text-right">Conversion</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody data-testid="career-analytics-top-jobs">
                {data.top_jobs.map((j) => (
                  <TableRow key={j.job_id} data-testid={`career-analytics-top-job-${j.job_id}`}>
                    <TableCell>
                      <div className="font-medium">{j.title}</div>
                      {j.department && <div className="text-xs text-muted-foreground">{j.department}</div>}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">{j.views}</TableCell>
                    <TableCell className="text-right font-mono text-sm">{j.applications}</TableCell>
                    <TableCell className="text-right font-mono text-sm">{j.conversion}%</TableCell>
                    <TableCell className="w-8">
                      {j.slug && (
                        <Link to={careersPath(`/jobs/${j.slug}`)} target="_blank" rel="noreferrer">
                          <Button variant="ghost" size="icon" title="Open public page"><ArrowUpRight className="h-4 w-4" /></Button>
                        </Link>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function FunnelRow({ label, value, max, icon: Icon, highlight }) {
  const pct = max ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="inline-flex items-center gap-1.5"><Icon className="h-3.5 w-3.5 text-muted-foreground" /> {label}</span>
        <span className="font-mono font-medium">{value} · {pct}%</span>
      </div>
      <div className="h-2 rounded-full bg-secondary overflow-hidden">
        <div
          className={`h-full ${highlight ? 'bg-primary' : 'bg-muted-foreground/50'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
