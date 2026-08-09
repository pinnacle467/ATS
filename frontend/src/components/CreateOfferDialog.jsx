import { useState } from 'react';
import { toast } from 'sonner';
import { Minus, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { api, errMsg } from '@/lib/api';
import { useCachedUsers } from '@/lib/referenceCache';

const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR', 'CAD', 'AUD'];

const emptyForm = {
  start_date: '', base_salary: '', salary_currency: 'USD', bonus: '', equity: '',
  reporting_manager: '', offer_expiry_date: '', custom_notes: '',
};

/**
 * Create an offer for a candidate: comp details + an ordered chain of
 * approvers (any user, any role) who must sign off one at a time before the
 * offer letter can be sent to the candidate.
 */
export default function CreateOfferDialog({ open, onOpenChange, candidateId, onCreated }) {
  const [users] = useCachedUsers();
  const [form, setForm] = useState(emptyForm);
  const [approvers, setApprovers] = useState(['']);
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setForm(emptyForm);
    setApprovers(['']);
  };

  const addApproverRow = () => setApprovers((p) => [...p, '']);
  const removeApproverRow = (idx) => setApprovers((p) => p.filter((_, i) => i !== idx));
  const setApproverAt = (idx, val) => setApprovers((p) => p.map((v, i) => (i === idx ? val : v)));

  const create = async () => {
    const chosen = approvers.filter(Boolean);
    if (chosen.length === 0) {
      toast.error('Add at least one approver');
      return;
    }
    if (new Set(chosen).size !== chosen.length) {
      toast.error('Each approver can only appear once in the chain');
      return;
    }
    setSaving(true);
    try {
      await api.post('/offers', {
        candidate_id: candidateId,
        start_date: form.start_date || null,
        base_salary: form.base_salary ? Number(form.base_salary) : null,
        salary_currency: form.salary_currency,
        bonus: form.bonus || null,
        equity: form.equity || null,
        reporting_manager: form.reporting_manager || null,
        offer_expiry_date: form.offer_expiry_date || null,
        custom_notes: form.custom_notes || null,
        approvers: chosen.map((user_id) => ({ user_id })),
      });
      toast.success('Offer created — first approver notified');
      reset();
      onCreated?.();
    } catch (e) {
      toast.error(errMsg(e, 'Could not create offer'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (saving) return;
        onOpenChange(o);
        if (!o) reset();
      }}
    >
      <DialogContent className="sm:max-w-lg max-h-[88vh] overflow-y-auto" data-testid="create-offer-dialog">
        <DialogHeader>
          <DialogTitle>Create Offer</DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Start Date</Label>
            <Input type="date" value={form.start_date} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))} data-testid="offer-start-date-input" />
          </div>
          <div className="space-y-1.5">
            <Label>Offer Expires</Label>
            <Input type="date" value={form.offer_expiry_date} onChange={(e) => setForm((f) => ({ ...f, offer_expiry_date: e.target.value }))} data-testid="offer-expiry-date-input" />
          </div>
          <div className="space-y-1.5">
            <Label>Base Salary</Label>
            <Input type="number" value={form.base_salary} onChange={(e) => setForm((f) => ({ ...f, base_salary: e.target.value }))} placeholder="120000" data-testid="offer-salary-input" />
          </div>
          <div className="space-y-1.5">
            <Label>Currency</Label>
            <Select value={form.salary_currency} onValueChange={(v) => setForm((f) => ({ ...f, salary_currency: v }))}>
              <SelectTrigger data-testid="offer-currency-select"><SelectValue /></SelectTrigger>
              <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Bonus</Label>
            <Input value={form.bonus} onChange={(e) => setForm((f) => ({ ...f, bonus: e.target.value }))} placeholder="10% annual target" data-testid="offer-bonus-input" />
          </div>
          <div className="space-y-1.5">
            <Label>Equity</Label>
            <Input value={form.equity} onChange={(e) => setForm((f) => ({ ...f, equity: e.target.value }))} placeholder="5,000 RSUs / 4yr" data-testid="offer-equity-input" />
          </div>
          <div className="space-y-1.5 col-span-2">
            <Label>Reporting Manager</Label>
            <Input value={form.reporting_manager} onChange={(e) => setForm((f) => ({ ...f, reporting_manager: e.target.value }))} data-testid="offer-manager-input" />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>Notes for the offer letter (optional)</Label>
          <Textarea value={form.custom_notes} onChange={(e) => setForm((f) => ({ ...f, custom_notes: e.target.value }))} placeholder="Anything extra to include in the letter" data-testid="offer-notes-input" />
        </div>

        <div className="space-y-2">
          <Label>Approval Chain — approvers act one at a time, in this order</Label>
          {approvers.map((val, idx) => (
            <div key={idx} className="flex items-center gap-2" data-testid={`offer-approver-row-${idx}`}>
              <span className="text-xs text-muted-foreground w-5 shrink-0">{idx + 1}.</span>
              <Select value={val} onValueChange={(v) => setApproverAt(idx, v)}>
                <SelectTrigger data-testid={`offer-approver-select-${idx}`}><SelectValue placeholder="Choose approver" /></SelectTrigger>
                <SelectContent>
                  {users.map((u) => <SelectItem key={u.id} value={u.id}>{u.name} ({u.email})</SelectItem>)}
                </SelectContent>
              </Select>
              {approvers.length > 1 && (
                <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => removeApproverRow(idx)} data-testid={`offer-approver-remove-${idx}`}>
                  <Minus className="h-4 w-4" />
                </Button>
              )}
            </div>
          ))}
          <Button variant="outline" size="sm" onClick={addApproverRow} data-testid="offer-approver-add-button">
            <Plus className="h-4 w-4 mr-1" /> Add approver
          </Button>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Cancel</Button>
          <Button onClick={create} disabled={saving} data-testid="create-offer-submit-button">{saving ? 'Creating…' : 'Create Offer'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
