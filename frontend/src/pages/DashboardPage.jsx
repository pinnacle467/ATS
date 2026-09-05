import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Briefcase, CalendarDays, CheckSquare, Clock, FileText, Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { StageBadge } from '@/pages/CandidatesPage';
import { api } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { useCachedDepartments, useCachedJobs, useCachedUsers } from '@/lib/referenceCache';

const timeAgo = (iso) => {
  if (!iso) return '';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

const initialsOf = (name) => (name || '?').split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase();

// Graduated blue palette — earliest pipeline stages get the lightest fill,
// later stages get progressively darker, mirroring a classic funnel look.
const FUNNEL_COLORS = ['#BFDBFE', '#93C5FD', '#60A5FA', '#3B82F6', '#2563EB', '#1D4ED8'];

const TASK_ICONS = { schedule: CalendarDays, offer: FileText, feedback: CheckSquare, upcoming: Clock };

const KPI_ICON_BG = ['bg-blue-100 text-blue-700', 'bg-violet-100 text-violet-700', 'bg-amber-100 text-amber-700', 'bg-emerald-100 text-emerald-700', 'bg-slate-100 text-slate-700'];

export default function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [activities, setActivities] = useState([]);
  const [recentCandidates, setRecentCandidates] = useState([]);
  const [upcomingInterviews, setUpcomingInterviews] = useState([]);
  const [jobs] = useCachedJobs();
  const [departments] = useCachedDepartments();
  const [users] = useCachedUsers();
  const recruiters = useMemo(() => users.filter((x) => ['super_admin', 'admin', 'recruiter'].includes(x.role)), [users]);
  const [filters, setFilters] = useState({ job_id: 'all', department: 'all', recruiter_id: 'all' });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get('/dashboard/my-tasks'),
      api.get('/activities?limit=15'),
      api.get('/candidates', { params: { sort: 'created_at', order: -1, limit: 5 } }),
      api.get('/interviews', { params: { status: 'scheduled', from_date: new Date().toISOString() } }),
    ])
      .then(([t, a, c, iv]) => {
        setTasks(t.data);
        setActivities(a.data);
        setRecentCandidates(c.data.items || []);
        setUpcomingInterviews((iv.data || []).slice(0, 5));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const params = {};
    if (filters.job_id !== 'all') params.job_id = filters.job_id;
    if (filters.department !== 'all') params.department = filters.department;
    if (filters.recruiter_id !== 'all') params.recruiter_id = filters.recruiter_id;
    api
      .get('/dashboard/stats', { params })
      .then((r) => setStats(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [filters]);

  const kpis = useMemo(
    () => [
      { label: 'Open Roles', value: stats?.open_roles, icon: Briefcase, link: '/jobs?status=open', testid: 'dashboard-kpi-open-roles' },
      { label: 'Active Candidates', value: stats?.active_candidates, icon: Users, link: '/candidates', testid: 'dashboard-kpi-active-candidates' },
      { label: 'Interviews This Week', value: stats?.interviews_this_week, icon: CalendarDays, link: '/interviews', testid: 'dashboard-kpi-interviews' },
      { label: 'Offers Pending', value: stats?.offers_pending, icon: FileText, link: '/candidates?stage=Offer', testid: 'dashboard-kpi-offers' },
      { label: 'Avg. Time to Hire', value: stats?.time_to_hire_avg != null ? `${stats.time_to_hire_avg}d` : '—', icon: Clock, link: '/candidates?stage=Hired', testid: 'dashboard-kpi-time-to-hire' },
    ],
    [stats]
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight" data-testid="dashboard-title">
            Welcome back, {user?.name?.split(' ')[0]}!
          </h1>
          <p className="text-sm text-muted-foreground">Here's what's happening with your hiring today.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={filters.job_id} onValueChange={(v) => setFilters((f) => ({ ...f, job_id: v }))}>
            <SelectTrigger className="w-[180px] h-9 bg-card" data-testid="dashboard-filter-job">
              <SelectValue placeholder="All jobs" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All jobs</SelectItem>
              {jobs.map((j) => (
                <SelectItem key={j.id} value={j.id}>{j.title}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={filters.department} onValueChange={(v) => setFilters((f) => ({ ...f, department: v }))}>
            <SelectTrigger className="w-[160px] h-9 bg-card" data-testid="dashboard-filter-department">
              <SelectValue placeholder="All departments" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All departments</SelectItem>
              {departments.map((d) => (
                <SelectItem key={d.id} value={d.name}>{d.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={filters.recruiter_id} onValueChange={(v) => setFilters((f) => ({ ...f, recruiter_id: v }))}>
            <SelectTrigger className="w-[160px] h-9 bg-card" data-testid="dashboard-filter-recruiter">
              <SelectValue placeholder="All recruiters" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All recruiters</SelectItem>
              {recruiters.map((r) => (
                <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {kpis.map((k, i) => {
          const Icon = k.icon;
          return (
            <Card
              key={k.label}
              className="shadow-none cursor-pointer transition-colors hover:border-primary/50 hover:bg-secondary/40"
              data-testid={k.testid}
              role="button"
              tabIndex={0}
              onClick={() => navigate(k.link)}
              onKeyDown={(e) => e.key === 'Enter' && navigate(k.link)}
            >
              <CardContent className="pt-5 pb-4">
                <div className="flex items-center justify-between">
                  <span className={`h-9 w-9 rounded-lg flex items-center justify-center ${KPI_ICON_BG[i % KPI_ICON_BG.length]}`}>
                    <Icon className="h-4.5 w-4.5" />
                  </span>
                </div>
                <div className="font-display text-3xl font-semibold tabular-nums mt-3">
                  {loading ? <span className="inline-block h-8 w-12 bg-secondary rounded animate-pulse" /> : k.value ?? 0}
                </div>
                <span className="text-xs text-muted-foreground font-medium">{k.label}</span>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Pipeline snapshot + Upcoming interviews */}
      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="shadow-none lg:col-span-2" data-testid="dashboard-pipeline-snapshot">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Hiring Pipeline</CardTitle>
            <p className="text-xs text-muted-foreground">Click a stage to view its candidates</p>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stats?.pipeline || []} margin={{ top: 20, right: 16, bottom: 0, left: -16 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(220 16% 91%)" vertical={false} />
                  <XAxis dataKey="stage" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip cursor={{ fill: 'hsl(220 20% 95%)' }} contentStyle={{ borderRadius: 8, border: '1px solid hsl(220 16% 88%)', fontSize: 13 }} />
                  <Bar
                    dataKey="count"
                    radius={[6, 6, 0, 0]}
                    maxBarSize={56}
                    cursor="pointer"
                    onClick={(entry) => entry?.stage && navigate(`/candidates?stage=${encodeURIComponent(entry.stage)}`)}
                    data-testid="dashboard-pipeline-bar"
                  >
                    <LabelList dataKey="count" position="top" style={{ fontSize: 12, fontWeight: 600, fill: 'hsl(222 47% 20%)' }} />
                    {(stats?.pipeline || []).map((entry, i) => (
                      <Cell key={entry.stage} fill={FUNNEL_COLORS[i % FUNNEL_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-none" data-testid="dashboard-upcoming-interviews">
          <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm font-semibold">Upcoming Interviews</CardTitle>
            <Link to="/interviews" className="text-xs text-primary hover:underline font-medium">View all</Link>
          </CardHeader>
          <CardContent className="space-y-1">
            {upcomingInterviews.length === 0 && <p className="text-sm text-muted-foreground py-4 text-center">No upcoming interviews scheduled.</p>}
            {upcomingInterviews.map((iv) => (
              <button
                key={iv.id}
                onClick={() => navigate(`/candidates/${iv.candidate_id}`)}
                className="w-full flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-secondary transition-colors text-left"
                data-testid={`dashboard-upcoming-interview-${iv.id}`}
              >
                <span className="h-9 w-9 rounded-full bg-blue-100 text-blue-700 text-xs font-semibold flex items-center justify-center shrink-0">
                  {initialsOf(iv.candidate_name)}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{iv.candidate_name}</p>
                  <p className="text-xs text-muted-foreground truncate">{(iv.type || '').replace('_', ' ')}{iv.job_title ? ` · ${iv.job_title}` : ''}</p>
                </div>
                <span className="text-xs text-muted-foreground font-mono shrink-0 text-right">
                  {iv.scheduled_at ? new Date(iv.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : ''}<br />
                  {iv.scheduled_at ? new Date(iv.scheduled_at).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) : ''}
                </span>
              </button>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Recent candidates + tasks/activity */}
      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="shadow-none lg:col-span-2" data-testid="dashboard-recent-candidates">
          <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm font-semibold">Recent Candidates</CardTitle>
            <Link to="/candidates" className="text-xs text-primary hover:underline font-medium">View all</Link>
          </CardHeader>
          <CardContent className="p-0">
            {recentCandidates.length === 0 && <p className="text-sm text-muted-foreground py-6 text-center">No candidates yet.</p>}
            <div className="divide-y divide-border">
              {recentCandidates.map((c) => (
                <button
                  key={c.id}
                  onClick={() => navigate(`/candidates/${c.id}`)}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-secondary/50 transition-colors text-left"
                  data-testid={`dashboard-recent-candidate-${c.id}`}
                >
                  <span className="h-9 w-9 rounded-full bg-primary/10 text-primary text-xs font-semibold flex items-center justify-center shrink-0">
                    {initialsOf(c.name)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{c.name}</p>
                    <p className="text-xs text-muted-foreground truncate">{c.job_title || 'No job assigned'}</p>
                  </div>
                  <StageBadge stage={c.stage} />
                  <span className="text-xs text-muted-foreground font-mono shrink-0 w-20 text-right hidden sm:inline">
                    {c.applied_at ? new Date(c.applied_at).toLocaleDateString() : '—'}
                  </span>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* My tasks */}
        <Card className="shadow-none" data-testid="dashboard-my-tasks">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">My Tasks</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {tasks.length === 0 && <p className="text-sm text-muted-foreground py-4 text-center">You're all caught up. No pending tasks.</p>}
            {tasks.map((t, i) => {
              const Icon = TASK_ICONS[t.type] || CheckSquare;
              return (
                <button
                  key={i}
                  onClick={() => navigate(t.link || '/')}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-secondary transition-colors text-left"
                  data-testid="dashboard-task-item"
                >
                  <span className="h-7 w-7 rounded-md bg-accent flex items-center justify-center shrink-0">
                    <Icon className="h-3.5 w-3.5 text-accent-foreground" />
                  </span>
                  <span className="text-sm flex-1">{t.label}</span>
                  <Badge variant="secondary" className="capitalize text-xs shrink-0">{t.type}</Badge>
                </button>
              );
            })}
          </CardContent>
        </Card>
      </div>

      {/* Activity feed */}
      <Card className="shadow-none" data-testid="dashboard-activity-feed">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Activity Feed</CardTitle>
        </CardHeader>
        <CardContent className="space-y-0.5">
          {activities.length === 0 && <p className="text-sm text-muted-foreground py-4 text-center">No recent activity.</p>}
          {activities.map((a) => (
            <div key={a.id} className="flex items-start gap-3 px-2 py-2 rounded-lg">
              <span className="h-7 w-7 rounded-full bg-secondary text-foreground text-[10px] font-semibold flex items-center justify-center shrink-0 mt-0.5">
                {initialsOf(a.actor_name)}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm">
                  <span className="font-medium">{a.actor_name}</span>{' '}
                  {a.candidate_id ? (
                    <Link to={`/candidates/${a.candidate_id}`} className="hover:underline">{a.message}</Link>
                  ) : a.job_id ? (
                    <Link to={`/jobs/${a.job_id}`} className="hover:underline">{a.message}</Link>
                  ) : (
                    a.message
                  )}
                </p>
              </div>
              <span className="text-xs text-muted-foreground font-mono shrink-0">{timeAgo(a.created_at)}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
