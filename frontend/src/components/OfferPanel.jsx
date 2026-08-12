import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { CheckCircle2, Circle, FileSignature, Link as LinkIcon, Loader2, Paperclip, Pencil, Send, ThumbsDown, ThumbsUp, Trash2, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { api, errMsg } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { OFFER_STATUS_META } from '@/lib/offerStatus';
import CreateOfferDialog from '@/components/CreateOfferDialog';

/**
 * "Offer" tab on the Candidate Profile page — create an offer, watch the
 * sequential approval chain, and once fully approved, preview + send the
 * letter (a shareable no-login Accept/Decline link the candidate can use).
 */
export default function OfferPanel({ candidateId, candidateName, isRecruiter }) {
  const { user } = useAuth();
  const [offers, setOffers] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOffer, setEditOffer] = useState(null);
  const [actingOn, setActingOn] = useState(null);
  const [rejectDialog, setRejectDialog] = useState(null);
  const [rejectComment, setRejectComment] = useState('');
  const [letterPreview, setLetterPreview] = useState(null);
  const [sending, setSending] = useState(false);

  const load = () => {
    api.get('/offers', { params: { candidate_id: candidateId } }).then((r) => setOffers(r.data)).catch(() => setOffers([]));
  };
  useEffect(() => { load(); }, [candidateId]);

  const approve = async (offerId) => {
    setActingOn(offerId);
    try {
      await api.post(`/offers/${offerId}/approve`, {});
      toast.success('Offer approved');
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not approve'));
    } finally {
      setActingOn(null);
    }
  };

  const reject = async () => {
    if (!rejectComment.trim()) {
      toast.error('Please provide a reason');
      return;
    }
    setActingOn(rejectDialog);
    try {
      await api.post(`/offers/${rejectDialog}/reject`, { comment: rejectComment });
      toast.success('Offer rejected');
      setRejectDialog(null);
      setRejectComment('');
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not reject'));
    } finally {
      setActingOn(null);
    }
  };

  const cancelOffer = async (offerId) => {
    if (!window.confirm('Cancel this offer? This cannot be undone.')) return;
    setActingOn(offerId);
    try {
      await api.post(`/offers/${offerId}/cancel`);
      toast.success('Offer cancelled');
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not cancel'));
    } finally {
      setActingOn(null);
    }
  };

  const deleteOffer = async (offerId) => {
    if (!window.confirm('Delete this offer permanently? This cannot be undone.')) return;
    setActingOn(offerId);
    try {
      await api.delete(`/offers/${offerId}`);
      toast.success('Offer deleted');
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not delete offer'));
    } finally {
      setActingOn(null);
    }
  };

  const previewLetter = async (offerId) => {
    try {
      const r = await api.get(`/offers/${offerId}/letter`);
      setLetterPreview({ offerId, ...r.data });
    } catch (e) {
      toast.error(errMsg(e, 'Could not load letter preview'));
    }
  };

  const sendOffer = async (offerId) => {
    setSending(true);
    try {
      const r = await api.post(`/offers/${offerId}/send`);
      if (r.data.email_sent) toast.success('Offer sent — email delivered to the candidate');
      else toast.success('Offer link generated — copy it below to share manually (candidate email not sent)');
      setLetterPreview(null);
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not send offer'));
    } finally {
      setSending(false);
    }
  };

  const copyLink = (link) => navigator.clipboard.writeText(link).then(() => toast.success('Link copied'));

  if (offers === null) return <div className="text-sm text-muted-foreground py-8 text-center">Loading offers…</div>;

  return (
    <div className="space-y-4 max-w-3xl" data-testid="offer-panel">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Offer Approvals</h3>
        {isRecruiter && (
          <Button size="sm" onClick={() => setCreateOpen(true)} data-testid="create-offer-button">
            <FileSignature className="h-4 w-4 mr-1.5" /> Create Offer
          </Button>
        )}
      </div>

      {offers.length === 0 && (
        <div className="text-sm text-muted-foreground text-center py-10 border border-dashed border-border rounded-xl" data-testid="offer-empty-state">
          No offer created yet for {candidateName}.
        </div>
      )}

      {offers.map((o) => {
        const meta = OFFER_STATUS_META[o.status] || {};
        const myTurn = o.status === 'pending_approval' && o.approvers[o.current_step - 1]?.user_id === user?.id;
        const link = o.public_token ? `${window.location.origin}/offer/${o.public_token}` : null;
        return (
          <Card key={o.id} className="shadow-none" data-testid={`offer-card-${o.id}`}>
            <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle className="text-sm font-semibold">{o.job_title || 'Offer'}</CardTitle>
                <p className="text-xs text-muted-foreground mt-0.5">Created by {o.created_by_name} · {new Date(o.created_at).toLocaleDateString()}</p>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <Badge variant="outline" className={meta.className}>{meta.label}</Badge>
                {isRecruiter && (
                  <Button
                    size="icon" variant="ghost"
                    className="h-7 w-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10 shrink-0"
                    onClick={() => deleteOffer(o.id)} disabled={actingOn === o.id}
                    data-testid={`offer-delete-button-${o.id}`}
                    title="Delete offer"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
                {o.start_date && <div><p className="text-xs text-muted-foreground">Start Date</p><p className="font-medium">{o.start_date}</p></div>}
                {o.base_salary != null && <div><p className="text-xs text-muted-foreground">Base Salary</p><p className="font-medium">{o.salary_currency} {Number(o.base_salary).toLocaleString()}</p></div>}
                {o.bonus && <div><p className="text-xs text-muted-foreground">Bonus</p><p className="font-medium">{o.bonus}</p></div>}
                {o.equity && <div><p className="text-xs text-muted-foreground">Equity</p><p className="font-medium">{o.equity}</p></div>}
                {o.reporting_manager && <div><p className="text-xs text-muted-foreground">Reporting Manager</p><p className="font-medium">{o.reporting_manager}</p></div>}
                {o.offer_expiry_date && <div><p className="text-xs text-muted-foreground">Expires</p><p className="font-medium">{o.offer_expiry_date}</p></div>}
              </div>

              {(o.contract_filename || (isRecruiter && ['pending_approval', 'approved'].includes(o.status))) && (
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  {o.contract_filename ? (
                    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground" data-testid={`offer-contract-${o.id}`}>
                      <Paperclip className="h-3.5 w-3.5" /> {o.contract_filename}
                    </span>
                  ) : <span />}
                  {isRecruiter && ['pending_approval', 'approved'].includes(o.status) && (
                    <Button size="sm" variant="outline" onClick={() => setEditOffer(o)} data-testid={`offer-edit-button-${o.id}`}>
                      <Pencil className="h-3.5 w-3.5 mr-1.5" /> Edit offer
                    </Button>
                  )}
                </div>
              )}

              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Approval Chain</p>
                {o.approvers.map((a) => (
                  <div key={a.step} className="flex items-start gap-2.5 text-sm" data-testid={`offer-approver-step-${o.id}-${a.step}`}>
                    {a.status === 'approved' && <CheckCircle2 className="h-4 w-4 text-emerald-600 mt-0.5 shrink-0" />}
                    {a.status === 'rejected' && <XCircle className="h-4 w-4 text-red-600 mt-0.5 shrink-0" />}
                    {a.status === 'pending' && <Circle className={`h-4 w-4 mt-0.5 shrink-0 ${o.current_step === a.step ? 'text-amber-600' : 'text-muted-foreground/40'}`} />}
                    <div className="flex-1">
                      <span className="font-medium">{a.user_name}</span>{' '}
                      <span className="text-muted-foreground">— step {a.step}</span>
                      {a.comment && <p className="text-xs text-muted-foreground italic mt-0.5">&ldquo;{a.comment}&rdquo;</p>}
                    </div>
                    {a.acted_at && <span className="text-xs text-muted-foreground shrink-0">{new Date(a.acted_at).toLocaleDateString()}</span>}
                  </div>
                ))}
              </div>

              {myTurn && (
                <div className="flex gap-2 pt-2 border-t border-border">
                  <Button size="sm" onClick={() => approve(o.id)} disabled={actingOn === o.id} data-testid={`offer-approve-button-${o.id}`}>
                    {actingOn === o.id ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <ThumbsUp className="h-4 w-4 mr-1.5" />} Approve
                  </Button>
                  <Button size="sm" variant="outline" className="text-destructive border-destructive/40 hover:bg-destructive/10"
                          onClick={() => { setRejectDialog(o.id); setRejectComment(''); }} data-testid={`offer-reject-button-${o.id}`}>
                    <ThumbsDown className="h-4 w-4 mr-1.5" /> Reject
                  </Button>
                </div>
              )}

              {o.status === 'approved' && isRecruiter && (
                <div className="flex gap-2 pt-2 border-t border-border">
                  <Button size="sm" variant="outline" onClick={() => previewLetter(o.id)} data-testid={`offer-preview-button-${o.id}`}>Preview Letter</Button>
                  <Button size="sm" onClick={() => sendOffer(o.id)} disabled={sending} data-testid={`offer-send-button-${o.id}`}>
                    {sending ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Send className="h-4 w-4 mr-1.5" />} Send to Candidate
                  </Button>
                </div>
              )}

              {o.status === 'sent' && (
                <div className="pt-2 border-t border-border space-y-2">
                  <p className="text-xs text-muted-foreground">
                    {o.email_sent ? 'Emailed to the candidate.' : 'Could not email automatically (Gmail not connected) — share this link manually:'}
                  </p>
                  {link && (
                    <div className="flex items-center gap-2">
                      <code className="flex-1 text-xs bg-secondary/60 border border-border rounded-md px-2 py-1.5 truncate">{link}</code>
                      <Button size="sm" variant="outline" onClick={() => copyLink(link)} data-testid={`offer-copy-link-${o.id}`}><LinkIcon className="h-3.5 w-3.5 mr-1" /> Copy</Button>
                    </div>
                  )}
                  <p className="text-xs text-amber-700">Awaiting candidate response…</p>
                </div>
              )}

              {(o.status === 'accepted' || o.status === 'declined') && (
                <div className={`pt-2 border-t border-border text-sm ${o.status === 'accepted' ? 'text-emerald-700' : 'text-rose-700'}`}>
                  Candidate {o.status} the offer{o.responded_at ? ` on ${new Date(o.responded_at).toLocaleDateString()}` : ''}.
                  {o.response_comment && <p className="text-xs italic mt-1">&ldquo;{o.response_comment}&rdquo;</p>}
                </div>
              )}

              {isRecruiter && ['pending_approval', 'approved', 'rejected'].includes(o.status) && (
                <div className="pt-1">
                  <Button size="sm" variant="ghost" className="text-xs text-muted-foreground h-7" onClick={() => cancelOffer(o.id)} data-testid={`offer-cancel-button-${o.id}`}>
                    Cancel this offer
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}

      <CreateOfferDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        candidateId={candidateId}
        onCreated={() => { setCreateOpen(false); load(); }}
      />

      <CreateOfferDialog
        open={!!editOffer}
        onOpenChange={(o) => !o && setEditOffer(null)}
        offer={editOffer}
        onCreated={() => { setEditOffer(null); load(); }}
      />

      <Dialog open={!!rejectDialog} onOpenChange={(o) => !o && setRejectDialog(null)}>
        <DialogContent className="sm:max-w-md" data-testid="offer-reject-dialog">
          <DialogHeader><DialogTitle>Reject this offer</DialogTitle></DialogHeader>
          <Textarea value={rejectComment} onChange={(e) => setRejectComment(e.target.value)} placeholder="Reason for rejecting (required)" data-testid="offer-reject-comment-input" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectDialog(null)}>Cancel</Button>
            <Button variant="destructive" onClick={reject} disabled={actingOn === rejectDialog} data-testid="offer-reject-confirm-button">Reject Offer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!letterPreview} onOpenChange={(o) => !o && setLetterPreview(null)}>
        <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto" data-testid="offer-letter-preview-dialog">
          <DialogHeader><DialogTitle>{letterPreview?.subject}</DialogTitle></DialogHeader>
          {/* eslint-disable-next-line react/no-danger */}
          <div className="border border-border rounded-lg p-4 bg-white" dangerouslySetInnerHTML={{ __html: letterPreview?.html || '' }} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setLetterPreview(null)}>Close</Button>
            <Button onClick={() => sendOffer(letterPreview.offerId)} disabled={sending} data-testid="offer-confirm-send-button">
              {sending ? 'Sending…' : 'Confirm & Send to Candidate'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
