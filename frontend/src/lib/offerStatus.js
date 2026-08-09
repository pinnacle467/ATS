// Shared status → label/style map for the offer approval workflow.
// Used by OfferPanel (candidate profile) and OffersPage (global list) so the
// two views never drift apart.
export const OFFER_STATUS_META = {
  pending_approval: { label: 'Pending Approval', className: 'bg-amber-100 text-amber-800 border-amber-300' },
  approved: { label: 'Approved — Ready to Send', className: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
  rejected: { label: 'Rejected', className: 'bg-red-100 text-red-800 border-red-300' },
  sent: { label: 'Sent — Awaiting Response', className: 'bg-blue-100 text-blue-800 border-blue-300' },
  accepted: { label: 'Accepted', className: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
  declined: { label: 'Declined', className: 'bg-rose-100 text-rose-800 border-rose-300' },
  cancelled: { label: 'Cancelled', className: 'bg-slate-100 text-slate-600 border-slate-300' },
};
