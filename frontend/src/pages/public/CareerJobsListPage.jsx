import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Briefcase, MapPin, Search } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { api } from '@/lib/api';

export default function CareerJobsListPage() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [department, setDepartment] = useState('all');
  const [remoteType, setRemoteType] = useState('all');

  useEffect(() => {
    setLoading(true);
    const params = {};
    if (q) params.q = q;
    if (department !== 'all') params.department = department;
    if (remoteType !== 'all') params.remote_type = remoteType;
    api.get('/career/public/jobs', { params }).then((r) => setJobs(r.data || [])).finally(() => setLoading(false));
  }, [q, department, remoteType]);

  const departments = [...new Set(jobs.map((j) => j.department).filter(Boolean))];

  return (
    <div className="px-4 sm:px-6 py-12 max-w-6xl mx-auto" data-testid="career-jobs-list-page">
      <h1 className="font-display text-3xl font-semibold tracking-tight mb-2">Open Roles</h1>
      <p className="text-muted-foreground mb-8">Find your next opportunity with us.</p>

      <div className="flex flex-wrap gap-3 mb-8">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search jobs..." value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" data-testid="career-jobs-search-input" />
        </div>
        <Select value={department} onValueChange={setDepartment}>
          <SelectTrigger className="w-48" data-testid="career-jobs-department-filter"><SelectValue placeholder="Department" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Departments</SelectItem>
            {departments.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={remoteType} onValueChange={setRemoteType}>
          <SelectTrigger className="w-40" data-testid="career-jobs-remote-filter"><SelectValue placeholder="Work Type" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Work Types</SelectItem>
            <SelectItem value="Remote">Remote</SelectItem>
            <SelectItem value="Hybrid">Hybrid</SelectItem>
            <SelectItem value="On-site">On-site</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {loading && <div className="space-y-3">{[1, 2, 3].map((i) => <div key={i} className="h-24 bg-secondary rounded-xl animate-pulse" />)}</div>}

      {!loading && jobs.length === 0 && (
        <p className="text-center text-muted-foreground py-16" data-testid="career-jobs-empty">No open roles match your search right now. Check back soon!</p>
      )}

      <div className="space-y-3">
        {jobs.map((j) => (
          <Link
            key={j.id}
            to={`/careers/jobs/${j.slug}`}
            className="block border border-border rounded-xl p-5 hover:border-primary/50 hover:shadow-sm transition-all bg-card"
            data-testid={`career-job-card-${j.id}`}
          >
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <h3 className="font-display font-semibold text-lg">{j.title}</h3>
                <div className="flex items-center gap-3 text-sm text-muted-foreground mt-1 flex-wrap">
                  <span className="flex items-center gap-1"><Briefcase className="h-3.5 w-3.5" /> {j.department}</span>
                  <span className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5" /> {j.location || 'Remote'}</span>
                </div>
              </div>
              <div className="flex gap-2 flex-wrap">
                {j.employment_type && <Badge variant="outline">{j.employment_type}</Badge>}
                {j.remote_type && <Badge variant="outline">{j.remote_type}</Badge>}
                {j.experience_level && <Badge variant="outline">{j.experience_level}</Badge>}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
