import { useEffect, useState } from 'react';
import { Loader2, Star } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { api, errMsg } from '@/lib/api';

const DEFAULT_ATTRS = ['Communication', 'Technical Skill', 'Problem Solving', 'Culture Fit'];
const RECOMMENDATIONS = [
  { value: 'strong_yes', label: 'Strong Yes' },
  { value: 'yes', label: 'Yes' },
  { value: 'no', label: 'No' },
  { value: 'strong_no', label: 'Strong No' },
];

function RatingRow({ label, value, onChange, testid }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm">{label}</span>
      <div className="flex gap-1" data-testid={testid}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onChange(n)}
            aria-label={`${label} rating ${n}`}
            className="p-0.5"
          >
            <Star className={`h-5 w-5 transition-colors ${n <= value ? 'text-amber-500 fill-amber-500' : 'text-muted-foreground/40'}`} />
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ScorecardDialog({ open, onOpenChange, interview, onSubmitted }) {
  const [attrs, setAttrs] = useState(DEFAULT_ATTRS);
  const [ratings, setRatings] = useState({});
  const [overall, setOverall] = useState(0);
  const [recommendation, setRecommendation] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !interview) return;
    setRatings({});
    setOverall(0);
    setRecommendation('');
    setNotes('');
    api.get('/settings/pipeline').then((r) => {
      const stage = (r.data.stages || []).find((s) => s.name === interview.stage);
      setAttrs(stage?.scorecard_attributes?.length ? stage.scorecard_attributes : DEFAULT_ATTRS);
    }).catch(() => setAttrs(DEFAULT_ATTRS));
  }, [open, interview]);

  const submit = async () => {
    if (overall === 0) return toast.error('Please set an overall rating');
    if (!recommendation) return toast.error('Please choose a recommendation');
    const missing = attrs.filter((a) => !ratings[a]);
    if (missing.length) return toast.error(`Please rate: ${missing.join(', ')}`);
    setSaving(true);
    try {
      await api.post(`/interviews/${interview.id}/scorecard`, { ratings, overall, recommendation, notes: notes || null });
      toast.success('Scorecard submitted');
      onOpenChange(false);
      onSubmitted?.();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  if (!interview) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" data-testid="scorecard-dialog">
        <DialogHeader>
          <DialogTitle>Scorecard — {interview.candidate_name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2.5">
            {attrs.map((a) => (
              <RatingRow key={a} label={a} value={ratings[a] || 0} onChange={(v) => setRatings((r) => ({ ...r, [a]: v }))} testid={`scorecard-rating-${a.toLowerCase().replace(/\s+/g, '-')}`} />
            ))}
          </div>
          <div className="border-t border-border pt-3">
            <RatingRow label="Overall" value={overall} onChange={setOverall} testid="scorecard-rating-overall" />
          </div>
          <div className="space-y-1.5">
            <Label>Recommendation</Label>
            <Select value={recommendation} onValueChange={setRecommendation}>
              <SelectTrigger data-testid="scorecard-recommendation-select"><SelectValue placeholder="Would you hire?" /></SelectTrigger>
              <SelectContent>{RECOMMENDATIONS.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Notes</Label>
            <Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Strengths, concerns, examples from the interview..." data-testid="scorecard-notes-textarea" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={saving} data-testid="scorecard-submit">
            {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null} Submit Feedback
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
