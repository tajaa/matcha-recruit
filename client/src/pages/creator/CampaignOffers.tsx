import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Inbox,
  DollarSign,
  TrendingUp,
  TrendingDown,
  Clock,
  CheckCircle,
  XCircle,
  ArrowLeft,
  Send,
  AlertTriangle,
  Star,
  Calendar,
  Building2,
  BadgeCheck,
} from 'lucide-react';
import { api } from '../../api/client';
import type { CreatorOffer, OfferStatus, CreatorCampaignStats } from '../../types/campaigns';

export function CampaignOffers() {
  const navigate = useNavigate();
  const [offers, setOffers] = useState<CreatorOffer[]>([]);
  const [stats, setStats] = useState<CreatorCampaignStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedStatus, setSelectedStatus] = useState<string>('pending');

  useEffect(() => {
    loadOffers();
  }, [selectedStatus]);

  const loadOffers = async () => {
    try {
      const status = selectedStatus === 'all' ? undefined : selectedStatus;
      const [offersRes, statsRes] = await Promise.all([
        api.campaigns.listMyOffers(status),
        api.campaigns.getMyStats(),
      ]);
      setOffers(offersRes);
      setStats(statsRes);
    } catch (err) {
      console.error('Failed to load offers:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount: number | null) => {
    if (!amount) return '$0';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const getStatusConfig = (status: OfferStatus) => {
    switch (status) {
      case 'pending': return { color: 'text-amber-500', bg: 'bg-amber-500/10', icon: Clock, label: 'New' };
      case 'viewed': return { color: 'text-blue-500', bg: 'bg-blue-500/10', icon: Clock, label: 'Viewed' };
      case 'accepted': return { color: 'text-emerald-500', bg: 'bg-emerald-500/10', icon: CheckCircle, label: 'Accepted' };
      case 'declined': return { color: 'text-zinc-500', bg: 'bg-zinc-500/10', icon: XCircle, label: 'Declined' };
      case 'expired': return { color: 'text-zinc-600', bg: 'bg-zinc-600/10', icon: Clock, label: 'Expired' };
      case 'taken': return { color: 'text-red-500', bg: 'bg-red-500/10', icon: XCircle, label: 'Taken' };
      default: return { color: 'text-zinc-500', bg: 'bg-zinc-500/10', icon: Clock, label: status };
    }
  };

  const getValueIndicator = (ratio: number | null) => {
    if (!ratio) return null;
    if (ratio >= 0.9) return { color: 'text-emerald-400', label: 'Fair', icon: CheckCircle };
    if (ratio >= 0.7) return { color: 'text-amber-400', label: 'Below Value', icon: AlertTriangle };
    return { color: 'text-red-400', label: 'Undervalued', icon: TrendingDown };
  };

  const statusFilters = [
    { value: 'pending', label: 'Pending' },
    { value: 'viewed', label: 'Viewed' },
    { value: 'accepted', label: 'Accepted' },
    { value: 'declined', label: 'Declined' },
    { value: 'all', label: 'All' },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="px-2 py-1 border border-purple-500/20 bg-purple-900/10 text-purple-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Campaign Offers
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Incoming Offers
          </h1>
          <p className="text-zinc-500 mt-2 text-sm">
            Review and respond to campaign offers from brands and agencies.
          </p>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="border border-white/10 bg-zinc-900/30 p-4">
            <div className="flex items-center gap-2 text-zinc-500 mb-2">
              <Inbox className="w-4 h-4" />
              <span className="text-[10px] uppercase tracking-widest">Pending</span>
            </div>
            <div className="text-2xl font-bold text-amber-400">{stats.pending_offers}</div>
          </div>
          <div className="border border-white/10 bg-zinc-900/30 p-4">
            <div className="flex items-center gap-2 text-zinc-500 mb-2">
              <CheckCircle className="w-4 h-4" />
              <span className="text-[10px] uppercase tracking-widest">Accepted</span>
            </div>
            <div className="text-2xl font-bold text-emerald-400">{stats.accepted_offers}</div>
          </div>
          <div className="border border-white/10 bg-zinc-900/30 p-4">
            <div className="flex items-center gap-2 text-zinc-500 mb-2">
              <DollarSign className="w-4 h-4" />
              <span className="text-[10px] uppercase tracking-widest">Earnings</span>
            </div>
            <div className="text-2xl font-bold text-white">{formatCurrency(stats.total_earnings)}</div>
          </div>
          <div className="border border-white/10 bg-zinc-900/30 p-4">
            <div className="flex items-center gap-2 text-zinc-500 mb-2">
              <Clock className="w-4 h-4" />
              <span className="text-[10px] uppercase tracking-widest">Pending Pay</span>
            </div>
            <div className="text-2xl font-bold text-zinc-400">{formatCurrency(stats.pending_earnings)}</div>
          </div>
        </div>
      )}

      {/* Status Filters */}
      <div className="flex flex-wrap gap-2">
        {statusFilters.map((filter) => (
          <button
            key={filter.value}
            onClick={() => {
              setSelectedStatus(filter.value);
              setLoading(true);
            }}
            className={`px-4 py-2 text-xs font-mono uppercase tracking-widest transition-all border ${
              selectedStatus === filter.value
                ? 'bg-white text-black border-white'
                : 'border-white/20 text-zinc-400 hover:border-white/40'
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {/* Offers List */}
      {offers.length === 0 ? (
        <div className="border border-white/10 bg-zinc-900/30 p-12 text-center">
          <Inbox className="w-12 h-12 mx-auto mb-4 text-zinc-600" />
          <p className="text-zinc-400 mb-2">No offers found</p>
          <p className="text-xs text-zinc-600">
            When brands invite you to campaigns, you'll see them here.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {offers.map((offer) => {
            const statusConfig = getStatusConfig(offer.status);
            const StatusIcon = statusConfig.icon;
            const valueIndicator = getValueIndicator(offer.offer_vs_value_ratio);

            return (
              <div
                key={offer.id}
                onClick={() => navigate(`/app/gumfit/offers/${offer.id}`)}
                className="border border-white/10 bg-zinc-900/30 p-6 hover:bg-white/5 transition-colors cursor-pointer group"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    {/* Status & Agency */}
                    <div className="flex items-center gap-3 mb-2">
                      <span className={`px-2 py-1 rounded text-[10px] uppercase tracking-widest flex items-center gap-1 ${statusConfig.bg} ${statusConfig.color}`}>
                        <StatusIcon className="w-3 h-3" />
                        {statusConfig.label}
                      </span>
                      <div className="flex items-center gap-2 text-xs text-zinc-500">
                        <Building2 className="w-3 h-3" />
                        {offer.agency_name}
                        {offer.agency_verified && (
                          <BadgeCheck className="w-3 h-3 text-blue-400" />
                        )}
                      </div>
                    </div>

                    {/* Title & Brand */}
                    <h3 className="text-lg font-medium text-white group-hover:text-emerald-400 transition-colors mb-1">
                      {offer.campaign_title}
                    </h3>
                    <p className="text-sm text-zinc-500 mb-3">{offer.brand_name}</p>

                    {/* Description */}
                    {offer.description && (
                      <p className="text-sm text-zinc-400 line-clamp-2 mb-4">
                        {offer.description}
                      </p>
                    )}

                    {/* Deliverables */}
                    {offer.deliverables.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-4">
                        {offer.deliverables.slice(0, 3).map((d, i) => (
                          <span key={i} className="px-2 py-1 bg-zinc-800 text-xs text-zinc-400">
                            {d.quantity}x {d.type.replace('_', ' ')}
                          </span>
                        ))}
                        {offer.deliverables.length > 3 && (
                          <span className="px-2 py-1 bg-zinc-800 text-xs text-zinc-500">
                            +{offer.deliverables.length - 3} more
                          </span>
                        )}
                      </div>
                    )}

                    {/* Amount & Valuation */}
                    <div className="flex flex-wrap items-center gap-6 text-sm">
                      <div className="flex items-center gap-2">
                        <DollarSign className="w-4 h-4 text-emerald-500" />
                        <span className="text-emerald-400 font-bold">
                          {formatCurrency(offer.offered_amount)}
                        </span>
                      </div>

                      {offer.estimated_value_min && offer.estimated_value_max && (
                        <div className="flex items-center gap-2 text-xs">
                          <TrendingUp className="w-4 h-4 text-zinc-500" />
                          <span className="text-zinc-500">
                            Your value: {formatCurrency(offer.estimated_value_min)} - {formatCurrency(offer.estimated_value_max)}
                          </span>
                        </div>
                      )}

                      {valueIndicator && (
                        <div className={`flex items-center gap-1 text-xs ${valueIndicator.color}`}>
                          <valueIndicator.icon className="w-3 h-3" />
                          {valueIndicator.label}
                        </div>
                      )}

                      {offer.expires_at && (
                        <div className="flex items-center gap-2 text-xs text-zinc-500">
                          <Calendar className="w-4 h-4" />
                          <span>Expires {new Date(offer.expires_at).toLocaleDateString()}</span>
                        </div>
                      )}
                    </div>

                    {/* Counter offer indicator */}
                    {offer.creator_counter_amount && (
                      <div className="mt-3 flex items-center gap-2 text-xs text-purple-400">
                        <Send className="w-3 h-3" />
                        Counter offer sent: {formatCurrency(offer.creator_counter_amount)}
                      </div>
                    )}
                  </div>

                  {/* Quick action preview */}
                  {(offer.status === 'pending' || offer.status === 'viewed') && (
                    <div className="text-xs text-zinc-600 group-hover:text-white transition-colors">
                      Review →
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Offer Detail Page
export function OfferDetail() {
  const { offerId } = useParams();
  const navigate = useNavigate();
  const [offer, setOffer] = useState<CreatorOffer | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [countering, setCountering] = useState(false);
  const [showCounterModal, setShowCounterModal] = useState(false);
  const [counterAmount, setCounterAmount] = useState<number>(0);
  const [counterNotes, setCounterNotes] = useState('');
  const [declineReason, setDeclineReason] = useState('');
  const [showDeclineModal, setShowDeclineModal] = useState(false);

  useEffect(() => {
    if (offerId) {
      loadOffer();
    }
  }, [offerId]);

  const loadOffer = async () => {
    try {
      const res = await api.campaigns.getMyOffer(offerId!);
      setOffer(res);
      setCounterAmount(res.offered_amount);
    } catch (err) {
      console.error('Failed to load offer:', err);
    } finally {
      setLoading(false);
    }
  };

  const acceptOffer = async () => {
    if (!confirm('Accept this offer? The agency will be notified and escrow payment will be initiated.')) return;
    setAccepting(true);
    try {
      const result = await api.campaigns.acceptOffer(offerId!);
      alert(`Offer accepted! Upfront payment of ${formatCurrency(result.upfront_amount)} will be processed.`);
      navigate('/app/gumfit/offers');
    } catch (err: unknown) {
      const error = err as Error;
      alert(error.message || 'Failed to accept offer');
    } finally {
      setAccepting(false);
    }
  };

  const declineOffer = async () => {
    setDeclining(true);
    try {
      await api.campaigns.declineOffer(offerId!, declineReason || undefined);
      navigate('/app/gumfit/offers');
    } catch (err) {
      console.error('Failed to decline offer:', err);
    } finally {
      setDeclining(false);
    }
  };

  const submitCounter = async () => {
    if (counterAmount <= 0) return;
    setCountering(true);
    try {
      await api.campaigns.counterOffer(offerId!, counterAmount, counterNotes || undefined);
      setShowCounterModal(false);
      loadOffer();
    } catch (err) {
      console.error('Failed to submit counter offer:', err);
    } finally {
      setCountering(false);
    }
  };

  const formatCurrency = (amount: number | null) => {
    if (!amount) return '$0';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const getValueIndicator = (ratio: number | null) => {
    if (!ratio) return null;
    if (ratio >= 0.9) return { color: 'text-emerald-400', bg: 'bg-emerald-500/10', label: 'Fair Offer', description: 'This offer is in line with your estimated value.' };
    if (ratio >= 0.7) return { color: 'text-amber-400', bg: 'bg-amber-500/10', label: 'Below Your Value', description: 'This offer is lower than your typical rate. Consider negotiating.' };
    return { color: 'text-red-400', bg: 'bg-red-500/10', label: 'Significantly Undervalued', description: 'This offer is well below your estimated worth. We recommend counter-offering.' };
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  if (!offer) {
    return (
      <div className="text-center py-12">
        <p className="text-zinc-500">Offer not found</p>
      </div>
    );
  }

  const valueIndicator = getValueIndicator(offer.offer_vs_value_ratio);
  const canRespond = offer.status === 'pending' || offer.status === 'viewed';

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Back button */}
      <button
        onClick={() => navigate('/app/gumfit/offers')}
        className="flex items-center gap-2 text-zinc-500 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        <span className="text-xs uppercase tracking-widest">Back to Offers</span>
      </button>

      {/* Header */}
      <div className="border-b border-white/10 pb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="flex items-center gap-2 text-sm text-zinc-500">
            <Building2 className="w-4 h-4" />
            {offer.agency_name}
            {offer.agency_verified && (
              <BadgeCheck className="w-4 h-4 text-blue-400" />
            )}
          </div>
        </div>
        <h1 className="text-4xl font-bold tracking-tighter text-white mb-2">
          {offer.campaign_title}
        </h1>
        <p className="text-zinc-500">{offer.brand_name}</p>
      </div>

      {/* Value Analysis Banner */}
      {valueIndicator && (
        <div className={`p-4 border ${valueIndicator.bg} ${valueIndicator.color.replace('text-', 'border-')}/30`}>
          <div className="flex items-start gap-3">
            <Star className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="font-bold">{valueIndicator.label}</h3>
              <p className="text-sm opacity-80 mt-1">{valueIndicator.description}</p>
              {offer.estimated_value_min && offer.estimated_value_max && (
                <p className="text-sm mt-2">
                  Your estimated value: <strong>{formatCurrency(offer.estimated_value_min)} - {formatCurrency(offer.estimated_value_max)}</strong>
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Description */}
          {offer.description && (
            <div className="border border-white/10 bg-zinc-900/30 p-6">
              <h2 className="text-xs font-bold uppercase tracking-widest text-zinc-500 mb-3">Campaign Description</h2>
              <p className="text-zinc-300 whitespace-pre-wrap">{offer.description}</p>
            </div>
          )}

          {/* Custom Message */}
          {offer.custom_message && (
            <div className="border border-purple-500/20 bg-purple-900/10 p-6">
              <h2 className="text-xs font-bold uppercase tracking-widest text-purple-400 mb-3">Message from Agency</h2>
              <p className="text-zinc-300 whitespace-pre-wrap">{offer.custom_message}</p>
            </div>
          )}

          {/* Deliverables */}
          {offer.deliverables.length > 0 && (
            <div className="border border-white/10 bg-zinc-900/30 p-6">
              <h2 className="text-xs font-bold uppercase tracking-widest text-zinc-500 mb-4">Deliverables</h2>
              <div className="space-y-3">
                {offer.deliverables.map((d, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-zinc-800/50 border border-white/5">
                    <div className="flex items-center gap-3">
                      <span className="text-emerald-400 font-mono text-sm">{d.quantity}x</span>
                      <span className="text-zinc-300 capitalize">{d.type.replace('_', ' ')}</span>
                    </div>
                    {d.description && (
                      <span className="text-xs text-zinc-500">{d.description}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Timeline */}
          {(offer.timeline.start_date || offer.timeline.end_date) && (
            <div className="border border-white/10 bg-zinc-900/30 p-6">
              <h2 className="text-xs font-bold uppercase tracking-widest text-zinc-500 mb-4">Timeline</h2>
              <div className="flex gap-8">
                {offer.timeline.start_date && (
                  <div>
                    <div className="text-[10px] uppercase tracking-widest text-zinc-600 mb-1">Start Date</div>
                    <div className="text-zinc-300">{new Date(offer.timeline.start_date).toLocaleDateString()}</div>
                  </div>
                )}
                {offer.timeline.end_date && (
                  <div>
                    <div className="text-[10px] uppercase tracking-widest text-zinc-600 mb-1">End Date</div>
                    <div className="text-zinc-300">{new Date(offer.timeline.end_date).toLocaleDateString()}</div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Offer Amount */}
          <div className="border border-white/10 bg-zinc-900/30 p-6">
            <h2 className="text-xs font-bold uppercase tracking-widest text-zinc-500 mb-4">Offer Amount</h2>
            <div className="text-4xl font-bold text-emerald-400 mb-4">
              {formatCurrency(offer.offered_amount)}
            </div>

            {offer.creator_counter_amount && (
              <div className="p-3 bg-purple-900/20 border border-purple-500/20 mb-4">
                <div className="text-[10px] uppercase tracking-widest text-purple-400 mb-1">Your Counter Offer</div>
                <div className="text-xl font-bold text-purple-300">
                  {formatCurrency(offer.creator_counter_amount)}
                </div>
              </div>
            )}

            {offer.expires_at && (
              <div className="flex items-center gap-2 text-xs text-amber-400">
                <Clock className="w-4 h-4" />
                Expires {new Date(offer.expires_at).toLocaleDateString()}
              </div>
            )}
          </div>

          {/* Actions */}
          {canRespond && (
            <div className="border border-white/10 bg-zinc-900/30 p-6 space-y-3">
              <button
                onClick={acceptOffer}
                disabled={accepting}
                className="w-full py-3 bg-emerald-500 text-white font-bold text-xs uppercase tracking-widest hover:bg-emerald-600 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <CheckCircle className="w-4 h-4" />
                {accepting ? 'Accepting...' : 'Accept Offer'}
              </button>
              <button
                onClick={() => setShowCounterModal(true)}
                className="w-full py-3 border border-purple-500 text-purple-400 font-bold text-xs uppercase tracking-widest hover:bg-purple-500/10 transition-colors flex items-center justify-center gap-2"
              >
                <Send className="w-4 h-4" />
                Counter Offer
              </button>
              <button
                onClick={() => setShowDeclineModal(true)}
                className="w-full py-3 border border-white/20 text-zinc-400 font-bold text-xs uppercase tracking-widest hover:bg-white/5 transition-colors flex items-center justify-center gap-2"
              >
                <XCircle className="w-4 h-4" />
                Decline
              </button>

              <p className="text-[10px] text-zinc-600 text-center pt-2">
                Accepting locks the deal. Payment will be processed via escrow.
              </p>
            </div>
          )}

          {/* Status */}
          {!canRespond && (
            <div className="border border-white/10 bg-zinc-900/30 p-6 text-center">
              <div className="text-xs uppercase tracking-widest text-zinc-500 mb-2">Status</div>
              <div className="text-lg font-bold text-zinc-400 capitalize">{offer.status}</div>
            </div>
          )}
        </div>
      </div>

      {/* Counter Offer Modal */}
      {showCounterModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-900 border border-white/10 max-w-md w-full">
            <div className="p-6 border-b border-white/10">
              <h2 className="text-lg font-bold text-white">Submit Counter Offer</h2>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Your Counter Amount ($)
                </label>
                <input
                  type="number"
                  value={counterAmount}
                  onChange={(e) => setCounterAmount(parseFloat(e.target.value) || 0)}
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white text-xl font-bold focus:outline-none focus:border-white/30"
                />
                {offer.estimated_value_min && offer.estimated_value_max && (
                  <p className="text-xs text-zinc-500 mt-2">
                    Suggested range: {formatCurrency(offer.estimated_value_min)} - {formatCurrency(offer.estimated_value_max)}
                  </p>
                )}
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Notes (optional)
                </label>
                <textarea
                  value={counterNotes}
                  onChange={(e) => setCounterNotes(e.target.value)}
                  placeholder="Explain your counter offer..."
                  rows={3}
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30 resize-none"
                />
              </div>
            </div>
            <div className="p-6 border-t border-white/10 flex justify-end gap-4">
              <button
                onClick={() => setShowCounterModal(false)}
                className="px-6 py-2 border border-white/20 text-xs font-mono uppercase tracking-widest hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={submitCounter}
                disabled={countering || counterAmount <= 0}
                className="px-6 py-2 bg-purple-500 text-white text-xs font-mono uppercase tracking-widest hover:bg-purple-600 font-bold disabled:opacity-50"
              >
                {countering ? 'Submitting...' : 'Submit Counter'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Decline Modal */}
      {showDeclineModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-900 border border-white/10 max-w-md w-full">
            <div className="p-6 border-b border-white/10">
              <h2 className="text-lg font-bold text-white">Decline Offer</h2>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Reason (optional)
                </label>
                <textarea
                  value={declineReason}
                  onChange={(e) => setDeclineReason(e.target.value)}
                  placeholder="Let the agency know why you're declining..."
                  rows={3}
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30 resize-none"
                />
              </div>
            </div>
            <div className="p-6 border-t border-white/10 flex justify-end gap-4">
              <button
                onClick={() => setShowDeclineModal(false)}
                className="px-6 py-2 border border-white/20 text-xs font-mono uppercase tracking-widest hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={declineOffer}
                disabled={declining}
                className="px-6 py-2 bg-red-500 text-white text-xs font-mono uppercase tracking-widest hover:bg-red-600 font-bold disabled:opacity-50"
              >
                {declining ? 'Declining...' : 'Decline Offer'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CampaignOffers;
