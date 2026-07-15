import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Briefcase, CalendarDays, CheckSquare, Clock, FileText, Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { api } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';

const timeAgo = (iso) => {
  if (!iso) return '';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

const STAGE_COLORS = ['#0F9D6A', '#0EA5E9', '#F59E0B', '#8B5CF6', '#16A34A', '#EF4444'];

const TASK_ICONS = { schedule: CalendarDays, offer: FileText, feedback: CheckSquare, upcoming: Clock };

export default function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [activities, setActivities] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [recruiters, setRecruiters] = useState([]);
  const [filters, setFilters] = useState({ job_id: 'all', department: 'all', recruiter_id: 'all' });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get('/jobs'),
      api.get('/departments'),
      api.get('/users'),
      api.get('/dashboard/my-tasks'),
      api.get('/activities?limit=15'),
    ])
      .then(([j, d, u, t, a]) => {
        setJobs(j.data);
        setDepartments(d.data);
        setRecruiters(u.data.filter((x) => x.role === 'recruiter' || x.role === 'admin'));
        setTasks(t.data);
        setActivities(a.data);
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
      { label: 'Open Roles', value: stats?.open_roles, icon: Briefcase },
      { label: 'Active Candidates', value: stats?.active_candidates, icon: Users },
      { label: 'Interviews This Week', value: stats?.interviews_this_week, icon: CalendarDays },
      { label: 'Offers Pending', value: stats?.offers_pending, icon: FileText },
      { label: 'Avg. Time to Hire', value: stats?.time_to_hire_avg != null ? `${stats.time_to_hire_avg}d` : '—', icon: Clock },
    ],
    [stats]
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight" data-testid="dashboard-title">
            Good {new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 18 ? 'afternoon' : 'evening'}, {user?.name?.split(' ')[0]}
          </h1>
          <p className="text-sm text-muted-foreground">Here's what's happening in your pipeline.</p>
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
        {kpis.map((k) => {
          const Icon = k.icon;
          return (
            <Card key={k.label} className="shadow-none" data-testid="dashboard-kpi-card">
              <CardContent className="pt-5 pb-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-wide text-muted-foreground font-medium">{k.label}</span>
                  <Icon className="h-4 w-4 text-primary" />
                </div>
                <div className="font-display text-3xl font-semibold tabular-nums mt-2">
                  {loading ? <span className="inline-block h-8 w-12 bg-secondary rounded animate-pulse" /> : k.value ?? 0}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Pipeline snapshot */}
      <Card className="shadow-none" data-testid="dashboard-pipeline-snapshot">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Pipeline Snapshot</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats?.pipeline || []} margin={{ top: 8, right: 16, bottom: 0, left: -16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(214 18% 90%)" vertical={false} />
                <XAxis dataKey="stage" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip cursor={{ fill: 'hsl(210 16% 94%)' }} contentStyle={{ borderRadius: 8, border: '1px solid hsl(214 18% 88%)', fontSize: 13 }} />
                <Bar dataKey="count" radius={[6, 6, 0, 0]} maxBarSize={56}>
                  {(stats?.pipeline || []).map((entry, i) => (
                    <Cell key={entry.stage} fill={STAGE_COLORS[i % STAGE_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <div className="grid lg:grid-cols-2 gap-6">
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

        {/* Activity feed */}
        <Card className="shadow-none" data-testid="dashboard-activity-feed">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Recent Activity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-0.5">
            {activities.length === 0 && <p className="text-sm text-muted-foreground py-4 text-center">No recent activity.</p>}
            {activities.map((a) => (
              <div key={a.id} className="flex items-start gap-3 px-2 py-2 rounded-lg">
                <span className="h-7 w-7 rounded-full bg-secondary text-foreground text-[10px] font-semibold flex items-center justify-center shrink-0 mt-0.5">
                  {(a.actor_name || '?').split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm">
                    <span className="font-medium">{a.actor_name}</span>{' '}
                    {a.candidate_id ? (
                      <Link to={`/candidates/${a.candidate_id}`} className="hover:underline">{a.message}</Link>
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
    </div>
  );
}
