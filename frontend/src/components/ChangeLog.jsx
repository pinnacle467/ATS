import { useEffect, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { Clock, History } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { api, errMsg } from '@/lib/api';
import { toast } from 'sonner';

const ACTION_LABELS = {
  candidate_created: 'Created',
  candidate_updated: 'Updated',
  candidate_deleted: 'Deleted',
  stage_change: 'Stage changed',
  merge_resume: 'Resume merged',
  job_created: 'Created',
  job_updated: 'Updated',
  job_deleted: 'Deleted',
  jd_updated: 'JD updated',
  jd_removed: 'JD removed',
  job_published: 'Published to careers',
  job_unpublished: 'Unpublished',
  job_team_added: 'Team member added',
  job_team_updated: 'Team member updated',
  job_team_removed: 'Team member removed',
  'career.email.sent': 'Email sent',
};

const ACTION_COLOR = {
  candidate_created: 'bg-sky-100 text-sky-800',
  job_created: 'bg-sky-100 text-sky-800',
  candidate_updated: 'bg-amber-100 text-amber-800',
  job_updated: 'bg-amber-100 text-amber-800',
  stage_change: 'bg-violet-100 text-violet-800',
  candidate_deleted: 'bg-red-100 text-red-800',
  job_deleted: 'bg-red-100 text-red-800',
  job_team_added: 'bg-emerald-100 text-emerald-800',
  job_team_removed: 'bg-red-100 text-red-800',
  'career.email.sent': 'bg-blue-100 text-blue-800',
};

/**
 * ChangeLog — shows the audit trail scoped to a specific entity.
 * Props:
 *   entityType: 'candidate' | 'job'
 *   entityId: string
 */
export default function ChangeLog({ entityType, entityId }) {
  const [entries, setEntries] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!entityId) return;
    setLoading(true);
    const path = entityType === 'candidate'
      ? `/candidates/${entityId}/change-log`
      : `/jobs/${entityId}/change-log`;
    api
      .get(path)
      .then((r) => setEntries(r.data.entries || []))
      .catch((e) => {
        // 403 for interview_panel / vendor is expected — silently show empty
        if (e.response?.status !== 403) toast.error(errMsg(e, 'Failed to load change log'));
        setEntries([]);
      })
      .finally(() => setLoading(false));
  }, [entityType, entityId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground py-6 justify-center">
        <Clock className="h-4 w-4 animate-pulse" /> Loading change log…
      </div>
    );
  }

  if (!entries || entries.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground py-8">
        <History className="h-8 w-8 text-muted-foreground/40" />
        <div>No changes recorded yet.</div>
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid={`change-log-${entityType}`}>
      {entries.map((e) => {
        const label = ACTION_LABELS[e.action] || e.action.replace(/_/g, ' ');
        const color = ACTION_COLOR[e.action] || 'bg-secondary text-foreground';
        return (
          <div key={e.id} className="flex items-start gap-3 rounded-lg border border-border bg-card p-3">
            <div className="mt-0.5">
              <Badge className={`text-[10px] font-medium ${color}`} variant="secondary">{label}</Badge>
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">{e.actor_name || 'System'}</div>
              {e.details && (
                <div className="text-xs text-muted-foreground mt-0.5 break-words whitespace-pre-wrap">{e.details}</div>
              )}
            </div>
            <div className="text-xs text-muted-foreground shrink-0" title={e.created_at}>
              {e.created_at ? formatDistanceToNow(new Date(e.created_at), { addSuffix: true }) : ''}
            </div>
          </div>
        );
      })}
    </div>
  );
}
