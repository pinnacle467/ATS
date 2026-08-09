import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileSignature } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { api } from '@/lib/api';
import { OFFER_STATUS_META } from '@/lib/offerStatus';

const FILTERS = [
  { key: 'all', label: 'All Offers' },
  { key: 'mine', label: 'My Approvals' },
];

export default function OffersPage() {
  const [filter, setFilter] = useState('all');
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params = filter === 'mine' ? { pending_my_approval: true } : {};
    api.get('/offers', { params }).then((r) => setOffers(r.data)).catch(() => setOffers([])).finally(() => setLoading(false));
  }, [filter]);

  return (
    <div className="space-y-5" data-testid="offers-page">
      <div>
        <h1 className="text-2xl font-semibold flex items-center gap-2"><FileSignature className="h-5 w-5" /> Offers</h1>
        <p className="text-sm text-muted-foreground mt-1">Offer letters and their approval status across all candidates.</p>
      </div>

      <Tabs value={filter} onValueChange={setFilter}>
        <TabsList data-testid="offers-filter-tabs">
          {FILTERS.map((f) => <TabsTrigger key={f.key} value={f.key} data-testid={`offers-filter-${f.key}`}>{f.label}</TabsTrigger>)}
        </TabsList>
      </Tabs>

      {loading && <div className="text-sm text-muted-foreground py-10 text-center">Loading…</div>}

      {!loading && offers.length === 0 && (
        <div className="text-sm text-muted-foreground text-center py-16 border border-dashed border-border rounded-xl" data-testid="offers-empty-state">
          {filter === 'mine' ? 'Nothing needs your approval right now.' : 'No offers created yet.'}
        </div>
      )}

      <div className="space-y-2">
        {offers.map((o) => {
          const meta = OFFER_STATUS_META[o.status] || {};
          const currentApprover = o.status === 'pending_approval' ? o.approvers?.[o.current_step - 1] : null;
          return (
            <Link key={o.id} to={`/candidates/${o.candidate_id}`} data-testid={`offer-row-${o.id}`}>
              <Card className="shadow-none hover:border-primary/40 transition-colors">
                <CardContent className="py-3.5 flex items-center justify-between gap-4">
                  <div>
                    <p className="font-medium text-sm">{o.candidate_name}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{o.job_title || '—'} · Created by {o.created_by_name} · {new Date(o.created_at).toLocaleDateString()}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    {currentApprover && <span className="text-xs text-muted-foreground hidden sm:inline">Waiting on {currentApprover.user_name}</span>}
                    <Badge variant="outline" className={meta.className}>{meta.label}</Badge>
                  </div>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
