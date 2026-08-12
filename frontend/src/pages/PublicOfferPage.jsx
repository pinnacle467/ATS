import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { api, errMsg } from '@/lib/api';
import PinnacleLogo from '@/components/PinnacleLogo';

/**
 * Public, no-login page a candidate lands on from their offer email/link
 * (`/offer/:token`) to review the letter and Accept or Decline.
 */
export default function PublicOfferPage() {
  const { token } = useParams();
  const [offer, setOffer] = useState(null);
  const [error, setError] = useState(null);
  const [comment, setComment] = useState('');
  const [showDecline, setShowDecline] = useState(false);
  const [responding, setResponding] = useState(false);

  const load = () => {
    api.get(`/offers/public/${token}`)
      .then((r) => setOffer(r.data))
      .catch((e) => setError(errMsg(e, 'This offer link is invalid or has expired')));
  };
  useEffect(() => { load(); }, [token]);

  const respond = async (response) => {
    setResponding(true);
    try {
      await api.post(`/offers/public/${token}/respond`, { response, comment: comment || null });
      toast.success(response === 'accepted' ? "You've accepted the offer!" : 'Your response has been recorded');
      load();
    } catch (e) {
      toast.error(errMsg(e, 'Could not submit your response'));
    } finally {
      setResponding(false);
    }
  };

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
        <div className="text-center max-w-sm" data-testid="offer-link-error">
          <XCircle className="h-10 w-10 text-rose-400 mx-auto mb-3" />
          <p className="text-slate-600">{error}</p>
        </div>
      </div>
    );
  }

  if (!offer) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      </div>
    );
  }

  const resolved = offer.status === 'accepted' || offer.status === 'declined';

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4" data-testid="public-offer-page">
      <div className="max-w-xl mx-auto">
        <div className="flex items-center gap-2 mb-6 justify-center">
          <PinnacleLogo size={28} />
          <span className="font-display font-semibold text-lg text-slate-800">{offer.company_name}</span>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-8">
          {/* eslint-disable-next-line react/no-danger */}
          <div dangerouslySetInnerHTML={{ __html: offer.letter_html }} />

          {offer.contract_url && (
            <a
              href={offer.contract_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-5 flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 hover:border-emerald-400 hover:bg-emerald-50/50 transition-colors"
              data-testid="offer-contract-download"
            >
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-100 text-emerald-700 text-lg">📄</span>
              <span className="flex-1 min-w-0">
                <span className="block text-sm font-medium text-slate-800 truncate">{offer.contract_filename || 'Contract document'}</span>
                <span className="block text-xs text-slate-500">Click to view or download</span>
              </span>
            </a>
          )}

          {resolved ? (
            <div
              className={`mt-6 pt-6 border-t border-slate-100 text-center ${offer.status === 'accepted' ? 'text-emerald-700' : 'text-rose-700'}`}
              data-testid="offer-response-recorded"
            >
              {offer.status === 'accepted' ? <CheckCircle2 className="h-8 w-8 mx-auto mb-2" /> : <XCircle className="h-8 w-8 mx-auto mb-2" />}
              <p className="font-medium">{offer.status === 'accepted' ? "You've accepted this offer." : "You've declined this offer."}</p>
              <p className="text-sm text-slate-500 mt-1">Thank you for letting us know. Our team will be in touch shortly.</p>
            </div>
          ) : (
            <div className="mt-6 pt-6 border-t border-slate-100 space-y-3">
              {!showDecline ? (
                <div className="flex flex-col sm:flex-row gap-3">
                  <Button className="flex-1" size="lg" onClick={() => respond('accepted')} disabled={responding} data-testid="offer-accept-button">
                    {responding ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-1.5" />} Accept Offer
                  </Button>
                  <Button className="flex-1" size="lg" variant="outline" onClick={() => setShowDecline(true)} disabled={responding} data-testid="offer-decline-button">
                    <XCircle className="h-4 w-4 mr-1.5" /> Decline
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <Textarea
                    placeholder="Optional — let us know why (helps us improve)"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    data-testid="offer-decline-comment-input"
                  />
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={() => setShowDecline(false)} disabled={responding}>Back</Button>
                    <Button variant="destructive" className="flex-1" onClick={() => respond('declined')} disabled={responding} data-testid="offer-decline-confirm-button">
                      {responding ? 'Submitting…' : 'Confirm Decline'}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
