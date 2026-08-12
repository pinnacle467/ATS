import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { FileUp, Minus, Plus, Sparkles, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import RichTextEditor from '@/components/RichTextEditor';
import { api, errMsg } from '@/lib/api';
import { useCachedUsers } from '@/lib/referenceCache';

const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR', 'CAD', 'AUD'];

const emptyForm = {
  start_date: '', base_salary: '', salary_currency: 'USD', bonus: '', equity: '',
  reporting_manager: '', offer_expiry_date: '', custom_notes: '',
};

/**
 * Create OR edit an offer for a candidate: comp details, an editable rich-text
 * offer letter, an optional standard contract document (PDF/Word), and an
 * ordered chain of approvers who must sign off before the letter can be sent.
 *
 * Pass `offer` to open in edit mode (approver chain is read-only when editing).
 */
export default function CreateOfferDialog({ open, onOpenChange, candidateId, offer, onCreated }) {
  const isEdit = !!offer;
  const [users] = useCachedUsers();
  const [form, setForm] = useState(emptyForm);
  const [approvers, setApprovers] = useState(['']);
  const [letterHtml, setLetterHtml] = useState('');
  const [contract, setContract] = useState(null); // { file_id, filename }
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  // Hydrate the form when opening (edit mode) or reset (create mode).
  useEffect(() => {
    if (!open) return;
    if (offer) {
      setForm({
        start_date: offer.start_date || '',
        base_salary: offer.base_salary != null ? String(offer.base_salary) : '',
        salary_currency: offer.salary_currency || 'USD',
        bonus: offer.bonus || '',
        equity: offer.equity || '',
        reporting_manager: offer.reporting_manager || '',
        offer_expiry_date: offer.offer_expiry_date || '',
        custom_notes: offer.custom_notes || '',
      });
      setLetterHtml(offer.letter_body_html || '');
      setContract(offer.contract_file_id ? { file_id: offer.contract_file_id, filename: offer.contract_filename } : null);
      setApprovers((offer.approvers || []).map((a) => a.user_id));
    } else {
      setForm(emptyForm);
      setApprovers(['']);
      setLetterHtml('');
      setContract(null);
    }
  }, [open, offer]);

  const cid = candidateId || offer?.candidate_id;

  const addApproverRow = () => setApprovers((p) => [...p, '']);
  const removeApproverRow = (idx) => setApprovers((p) => p.filter((_, i) => i !== idx));
  const setApproverAt = (idx, val) => setApprovers((p) => p.map((v, i) => (i === idx ? val : v)));

  const generateLetter = async () => {
    setGenerating(true);
    try {
      const r = await api.post('/offers/preview-draft', {
        candidate_id: cid,
        start_date: form.start_date || null,
        base_salary: form.base_salary ? Number(form.base_salary) : null,
        salary_currency: form.salary_currency,
        bonus: form.bonus || null,
        equity: form.equity || null,
        reporting_manager: form.reporting_manager || null,
        offer_expiry_date: form.offer_expiry_date || null,
        custom_notes: form.custom_notes || null,
      });
      setLetterHtml(r.data.html || '');
      toast.success('Draft letter generated — edit it below');
    } catch (e) {
      toast.error(errMsg(e, 'Could not generate the letter'));
    } finally {
      setGenerating(false);
    }
  };

  const onPickFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const ok = /\.(pdf|docx?|doc)$/i.test(file.name);
    if (!ok) {
      toast.error('Only PDF and Word documents (.pdf, .doc, .docx) are allowed');
      if (fileRef.current) fileRef.current.value = '';
      return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await api.post('/offers/upload-contract', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setContract({ file_id: r.data.file_id, filename: r.data.filename });
      toast.success('Contract attached');
    } catch (err) {
      toast.error(errMsg(err, 'Could not upload the document'));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const commonPayload = () => ({
    start_date: form.start_date || null,
    base_salary: form.base_salary ? Number(form.base_salary) : null,
    salary_currency: form.salary_currency,
    bonus: form.bonus || null,
    equity: form.equity || null,
    reporting_manager: form.reporting_manager || null,
    offer_expiry_date: form.offer_expiry_date || null,
    custom_notes: form.custom_notes || null,
    letter_body_html: letterHtml || '',
    contract_file_id: contract?.file_id || null,
    contract_filename: contract?.filename || null,
  });

  const save = async () => {
    if (isEdit) {
      setSaving(true);
      try {
        await api.put(`/offers/${offer.id}`, { ...commonPayload(), remove_contract: !contract });
        toast.success('Offer updated');
        onCreated?.();
      } catch (e) {
        toast.error(errMsg(e, 'Could not update offer'));
      } finally {
        setSaving(false);
      }
      return;
    }
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
        candidate_id: cid,
        ...commonPayload(),
        approvers: chosen.map((user_id) => ({ user_id })),
      });
      toast.success('Offer created — first approver notified');
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
      }}
    >
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="create-offer-dialog">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Offer' : 'Create Offer'}</DialogTitle>
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
          <Label>Extra notes (merged into the generated letter)</Label>
          <Textarea value={form.custom_notes} onChange={(e) => setForm((f) => ({ ...f, custom_notes: e.target.value }))} placeholder="Anything extra to include when you generate the letter" data-testid="offer-notes-input" />
        </div>

        {/* Editable offer letter */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label>Offer letter</Label>
            <Button type="button" variant="outline" size="sm" onClick={generateLetter} disabled={generating} data-testid="offer-generate-letter-button">
              <Sparkles className="h-3.5 w-3.5 mr-1.5" /> {generating ? 'Generating…' : 'Generate from details'}
            </Button>
          </div>
          <RichTextEditor
            value={letterHtml}
            onChange={setLetterHtml}
            placeholder="Click “Generate from details” to start from the template, then edit freely — or write your own letter."
            testId="offer-letter-editor"
          />
          <p className="text-xs text-muted-foreground">Leave blank to use the standard company template automatically.</p>
        </div>

        {/* Contract document */}
        <div className="space-y-1.5">
          <Label>Standard contract document (optional)</Label>
          {contract ? (
            <div className="flex items-center justify-between rounded-md border border-border bg-secondary/40 px-3 py-2 text-sm" data-testid="offer-contract-attached">
              <span className="truncate">📎 {contract.filename}</span>
              <Button type="button" variant="ghost" size="icon" className="h-7 w-7" onClick={() => setContract(null)} data-testid="offer-contract-remove">
                <X className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <div>
              <input ref={fileRef} type="file" accept=".pdf,.doc,.docx" className="hidden" onChange={onPickFile} data-testid="offer-contract-file-input" />
              <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="offer-contract-upload-button">
                <FileUp className="h-4 w-4 mr-1.5" /> {uploading ? 'Uploading…' : 'Upload PDF / Word'}
              </Button>
              <p className="text-xs text-muted-foreground mt-1">Attached to the offer email and shown on the candidate&apos;s offer page.</p>
            </div>
          )}
        </div>

        {!isEdit && (
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
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Cancel</Button>
          <Button onClick={save} disabled={saving} data-testid="create-offer-submit-button">
            {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Create Offer'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
