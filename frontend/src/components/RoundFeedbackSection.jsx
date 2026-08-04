import { useEffect, useMemo, useState } from 'react';
import { CalendarDays, Clock, MessageSquare, Save, Trash2, UserCheck } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { api, errMsg } from '@/lib/api';

const ROUNDS = [1, 2, 3];

function emptyDraft() {
  return { feedback: '', interview_date: '', interviewer_name: '', duration_min: '' };
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
      });
    } else {
      setDraft(emptyDraft());
    }
  }, [existing]);

  const dirty = useMemo(() => {
    if (!existing) {
      return !!(draft.feedback || draft.interview_date || draft.interviewer_name || draft.duration_min);
    }
    return (
      (existing.feedback || '') !== draft.feedback ||
      (existing.interview_date || '') !== draft.interview_date ||
      (existing.interviewer_name || '') !== draft.interviewer_name ||
      String(existing.duration_min || '') !== draft.duration_min
    );
  }, [existing, draft]);

  const save = async () => {
    if (!draft.feedback.trim() && !draft.interview_date && !draft.interviewer_name.trim() && !draft.duration_min) {
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
        <CardTitle className="text-sm font-semibold flex items-center justify-between gap-2">
          <span className="flex items-center gap-2">
            <span className="inline-flex items-center justify-center h-6 w-6 rounded-full bg-primary/10 text-primary text-xs font-bold">{round}</span>
            Round {round}
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
        the session duration, and detailed notes. Admins and recruiters can edit on behalf of the panel.
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
