import { useEffect, useMemo, useState } from 'react';
import { CalendarDays, CheckCircle2, Circle, Clock, MessageSquare, Save, ThumbsDown, ThumbsUp, Trash2, UserCheck } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { api, errMsg } from '@/lib/api';

const ROUNDS = [1, 2, 3];

const VERDICTS = [
  { value: 'recommend', label: 'Recommend', chip: 'bg-emerald-100 text-emerald-800 ring-emerald-200', icon: ThumbsUp },
  { value: 'neutral', label: 'Neutral', chip: 'bg-amber-100 text-amber-800 ring-amber-200', icon: Circle },
  { value: 'reject', label: 'Reject', chip: 'bg-rose-100 text-rose-800 ring-rose-200', icon: ThumbsDown },
];

export function VerdictChip({ verdict, size = 'sm' }) {
  const v = VERDICTS.find((x) => x.value === verdict);
  if (!v) return null;
  const Icon = v.icon;
  const sizeCls = size === 'xs' ? 'text-[10px] px-1.5 py-0 h-4' : 'text-xs px-2 py-0.5 h-5';
  const iconSize = size === 'xs' ? 'h-3 w-3' : 'h-3.5 w-3.5';
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-semibold ring-1 ${v.chip} ${sizeCls}`}
      data-testid={`verdict-chip-${v.value}`}
      title={`Verdict: ${v.label}`}
    >
      <Icon className={iconSize} />
      {v.label}
    </span>
  );
}

function emptyDraft() {
  return { feedback: '', interview_date: '', interviewer_name: '', duration_min: '', verdict: '' };
}

function RoundCard({ round, existing, canEdit, candidateId, onSaved }) {
  const [draft, setDraft] = useState(emptyDraft());
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    if (existing) {
      setDraft({
        feedback: existing.feedback || '',
        interview_date: existing.interview_date || '',
        interviewer_name: existing.interviewer_name || '',
        duration_min: existing.duration_min ? String(existing.duration_min) : '',
        verdict: existing.verdict || '',
      });
    } else {
      setDraft(emptyDraft());
    }
  }, [existing]);

  const dirty = useMemo(() => {
    if (!existing) {
      return !!(draft.feedback || draft.interview_date || draft.interviewer_name || draft.duration_min || draft.verdict);
    }
    return (
      (existing.feedback || '') !== draft.feedback ||
      (existing.interview_date || '') !== draft.interview_date ||
      (existing.interviewer_name || '') !== draft.interviewer_name ||
      String(existing.duration_min || '') !== draft.duration_min ||
      (existing.verdict || '') !== draft.verdict
    );
  }, [existing, draft]);

  const save = async () => {
    if (!draft.feedback.trim() && !draft.interview_date && !draft.interviewer_name.trim() && !draft.duration_min && !draft.verdict) {
      toast.error('Enter at least one field before saving');
      return;
    }
    const dur = draft.duration_min ? parseInt(draft.duration_min, 10) : null;
    if (draft.duration_min && (Number.isNaN(dur) || dur <= 0)) {
      toast.error('Duration must be a positive number of minutes');
      return;
    }
    setSaving(true);
    try {
      await api.put(`/candidates/${candidateId}/round-feedback/${round}`, {
        feedback: draft.feedback,
        interview_date: draft.interview_date || null,
        interviewer_name: draft.interviewer_name,
        duration_min: dur,
        verdict: draft.verdict || null,
      });
      toast.success(`Round ${round} feedback saved`);
      onSaved?.();
    } catch (e) {
      toast.error(errMsg(e, 'Could not save feedback'));
    } finally {
      setSaving(false);
    }
  };

  const clear = async () => {
    if (!existing) {
      setDraft(emptyDraft());
      return;
    }
    if (!window.confirm(`Clear all Round ${round} feedback?`)) return;
    setClearing(true);
    try {
      await api.delete(`/candidates/${candidateId}/round-feedback/${round}`);
      toast.success(`Round ${round} feedback cleared`);
      onSaved?.();
    } catch (e) {
      toast.error(errMsg(e, 'Could not clear feedback'));
    } finally {
      setClearing(false);
    }
  };

  const meta = existing?.updated_at
    ? `Last updated ${new Date(existing.updated_at).toLocaleString()}${existing.updated_by_name ? ` by ${existing.updated_by_name}` : ''}`
    : 'No feedback recorded yet';

  return (
    <Card className="shadow-none" data-testid={`round-feedback-card-${round}`}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center justify-between gap-2 flex-wrap">
          <span className="flex items-center gap-2">
            <span className="inline-flex items-center justify-center h-6 w-6 rounded-full bg-primary/10 text-primary text-xs font-bold">{round}</span>
            Round {round}
            {existing?.verdict && <VerdictChip verdict={existing.verdict} />}
          </span>
          {existing && (
            <span className="text-[11px] font-normal text-muted-foreground">{meta}</span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid sm:grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
              <CalendarDays className="h-3.5 w-3.5" /> Interview date
            </Label>
            <Input
              type="date"
              value={draft.interview_date}
              onChange={(e) => setDraft({ ...draft, interview_date: e.target.value })}
              disabled={!canEdit || saving}
              data-testid={`round-${round}-date-input`}
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
              <UserCheck className="h-3.5 w-3.5" /> Interviewer
            </Label>
            <Input
              placeholder="e.g. David Lee"
              value={draft.interviewer_name}
              onChange={(e) => setDraft({ ...draft, interviewer_name: e.target.value })}
              disabled={!canEdit || saving}
              data-testid={`round-${round}-interviewer-input`}
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5" /> Duration (min)
            </Label>
            <Input
              type="number"
              min="1"
              step="1"
              placeholder="e.g. 45"
              value={draft.duration_min}
              onChange={(e) => setDraft({ ...draft, duration_min: e.target.value })}
              disabled={!canEdit || saving}
              data-testid={`round-${round}-duration-input`}
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
            <CheckCircle2 className="h-3.5 w-3.5" /> Verdict
          </Label>
          <div className="flex flex-wrap gap-2" data-testid={`round-${round}-verdict-group`}>
            {VERDICTS.map((v) => {
              const Icon = v.icon;
              const selected = draft.verdict === v.value;
              return (
                <button
                  key={v.value}
                  type="button"
                  onClick={() => canEdit && !saving && setDraft({ ...draft, verdict: selected ? '' : v.value })}
                  disabled={!canEdit || saving}
                  data-testid={`round-${round}-verdict-${v.value}`}
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-all ring-1 ${selected ? v.chip : 'bg-card ring-border text-muted-foreground hover:bg-secondary'} ${!canEdit ? 'cursor-not-allowed opacity-70' : 'cursor-pointer'}`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {v.label}
                </button>
              );
            })}
            {draft.verdict && canEdit && (
              <button
                type="button"
                onClick={() => setDraft({ ...draft, verdict: '' })}
                disabled={saving}
                data-testid={`round-${round}-verdict-clear`}
                className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
              >
                clear
              </button>
            )}
          </div>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
            <MessageSquare className="h-3.5 w-3.5" /> Feedback notes
          </Label>
          <Textarea
            rows={5}
            placeholder={`Detailed notes from Round ${round} interview...`}
            value={draft.feedback}
            onChange={(e) => setDraft({ ...draft, feedback: e.target.value })}
            disabled={!canEdit || saving}
            data-testid={`round-${round}-feedback-textarea`}
          />
        </div>
        {canEdit && (
          <div className="flex items-center justify-end gap-2 pt-1">
            {existing && (
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={clear}
                disabled={saving || clearing}
                data-testid={`round-${round}-clear-button`}
              >
                <Trash2 className="h-3.5 w-3.5 mr-1" /> Clear
              </Button>
            )}
            <Button
              size="sm"
              onClick={save}
              disabled={saving || clearing || !dirty}
              data-testid={`round-${round}-save-button`}
            >
              <Save className="h-3.5 w-3.5 mr-1" /> {saving ? 'Saving…' : 'Save Round ' + round}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function RoundFeedbackSection({ candidateId, roundFeedback = [], canEdit, onChanged }) {
  const byRound = useMemo(() => {
    const m = {};
    (roundFeedback || []).forEach((r) => {
      if (r && r.round) m[r.round] = r;
    });
    return m;
  }, [roundFeedback]);

  return (
    <div className="space-y-4" data-testid="round-feedback-section">
      <div className="rounded-xl border border-dashed border-border bg-secondary/40 px-4 py-3 text-xs text-muted-foreground">
        Capture free-text feedback for up to three interview rounds. Each round tracks the interview date, the interviewer,
        the session duration, a verdict chip (Recommend / Neutral / Reject), and detailed notes. Admins and recruiters can edit
        on behalf of the panel.
      </div>
      {ROUNDS.map((r) => (
        <RoundCard
          key={r}
          round={r}
          existing={byRound[r]}
          canEdit={canEdit}
          candidateId={candidateId}
          onSaved={onChanged}
        />
      ))}
    </div>
  );
}
