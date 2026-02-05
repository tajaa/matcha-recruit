import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Target,
  DollarSign,
  Users,
  Calendar,
  Send,
  XCircle,
  Plus,
  Search,
  CheckCircle,
  Clock,
  Eye,
  Trash2,
  AlertTriangle,
  FileText,
} from 'lucide-react';
import { api } from '../../api/client';
import type {
  CampaignWithOffers,
  OfferStatus,
} from '../../types/campaigns';
import type { CreatorPublic } from '../../types/creator';

export function CampaignDetail() {
  const { campaignId } = useParams();
  const navigate = useNavigate();
  const [campaign, setCampaign] = useState<CampaignWithOffers | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAddCreator, setShowAddCreator] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<CreatorPublic[]>([]);
  const [searching, setSearching] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [selectedCreator, setSelectedCreator] = useState<CreatorPublic | null>(null);
  const [offerAmount, setOfferAmount] = useState<number>(0);
  const [customMessage, setCustomMessage] = useState('');

  useEffect(() => {
    if (campaignId) {
      loadCampaign();
    }
  }, [campaignId]);

  const loadCampaign = async () => {
    try {
      const res = await api.campaigns.get(campaignId!);
      setCampaign(res);
      setOfferAmount(res.total_budget);
    } catch (err) {
      console.error('Failed to load campaign:', err);
    } finally {
      setLoading(false);
    }
  };

  const searchCreators = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await api.creators.search({ query: searchQuery });
      // Filter out creators who already have an offer
      const existingCreatorIds = new Set(campaign?.offers.map(o => o.creator_id) || []);
      setSearchResults(res.filter((c: CreatorPublic) => !existingCreatorIds.has(c.id)));
    } catch (err) {
      console.error('Failed to search creators:', err);
    } finally {
      setSearching(false);
    }
  };

  const addOffer = async () => {
    if (!selectedCreator || !offerAmount || !campaignId) return;
    try {
      await api.campaigns.addOffer(campaignId, {
        creator_id: selectedCreator.id,
        offered_amount: offerAmount,
        custom_message: customMessage || undefined,
      });
      setShowAddCreator(false);
      setSelectedCreator(null);
      setOfferAmount(campaign?.total_budget || 0);
      setCustomMessage('');
      setSearchQuery('');
      setSearchResults([]);
      loadCampaign();
    } catch (err: unknown) {
      const error = err as Error;
      alert(error.message || 'Failed to add offer');
    }
  };

  const removeOffer = async (creatorId: string) => {
    if (!confirm('Remove this offer? The creator will no longer see this opportunity.')) return;
    try {
      await api.campaigns.removeOffer(campaignId!, creatorId);
      loadCampaign();
    } catch (err) {
      console.error('Failed to remove offer:', err);
    }
  };

  const publishCampaign = async () => {
    if (!confirm('Publish this campaign? Offers will be sent to all selected creators.')) return;
    setPublishing(true);
    try {
      await api.campaigns.publish(campaignId!);
      loadCampaign();
    } catch (err: unknown) {
      const error = err as Error;
      alert(error.message || 'Failed to publish campaign');
    } finally {
      setPublishing(false);
    }
  };

  const cancelCampaign = async () => {
    if (!confirm('Cancel this campaign? Pending offers will be expired.')) return;
    try {
      await api.campaigns.cancel(campaignId!);
      loadCampaign();
    } catch (err) {
      console.error('Failed to cancel campaign:', err);
    }
  };

  const generateContract = async (creatorId: string) => {
    try {
      const contract = await api.campaigns.generateContract(campaignId!, creatorId);
      // Open in new window or modal
      const newWindow = window.open('', '_blank');
      if (newWindow) {
        newWindow.document.write(`
          <html>
          <head><title>Contract - ${contract.template_name}</title></head>
          <body style="font-family: monospace; white-space: pre-wrap; padding: 40px; max-width: 800px; margin: 0 auto;">
          ${contract.content}
          </body>
          </html>
        `);
      }
    } catch (err) {
      console.error('Failed to generate contract:', err);
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

  const getOfferStatusConfig = (status: OfferStatus) => {
    switch (status) {
      case 'pending': return { color: 'text-amber-500', bg: 'bg-amber-500/10', icon: Clock, label: 'Pending' };
      case 'viewed': return { color: 'text-blue-500', bg: 'bg-blue-500/10', icon: Eye, label: 'Viewed' };
      case 'accepted': return { color: 'text-emerald-500', bg: 'bg-emerald-500/10', icon: CheckCircle, label: 'Accepted' };
      case 'declined': return { color: 'text-zinc-500', bg: 'bg-zinc-500/10', icon: XCircle, label: 'Declined' };
      case 'expired': return { color: 'text-zinc-600', bg: 'bg-zinc-600/10', icon: Clock, label: 'Expired' };
      case 'taken': return { color: 'text-red-500', bg: 'bg-red-500/10', icon: XCircle, label: 'Taken' };
      default: return { color: 'text-zinc-500', bg: 'bg-zinc-500/10', icon: Clock, label: status };
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="text-center py-12">
        <p className="text-zinc-500">Campaign not found</p>
      </div>
    );
  }

  const slotsRemaining = campaign.max_creators - campaign.accepted_count;
  const canAddOffers = campaign.status === 'draft' && campaign.offers.length < campaign.max_creators;
  const canPublish = campaign.status === 'draft' && campaign.offers.length > 0;

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Back button */}
      <button
        onClick={() => navigate('/app/gumfit/agency/campaigns')}
        className="flex items-center gap-2 text-zinc-500 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        <span className="text-xs uppercase tracking-widest">Back to Campaigns</span>
      </button>

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <span className={`px-2 py-1 rounded text-[10px] uppercase tracking-widest ${
              campaign.status === 'draft' ? 'bg-zinc-500/10 text-zinc-400' :
              campaign.status === 'open' ? 'bg-blue-500/10 text-blue-400' :
              campaign.status === 'active' ? 'bg-emerald-500/10 text-emerald-400' :
              'bg-zinc-500/10 text-zinc-400'
            }`}>
              {campaign.status}
            </span>
            <span className="text-sm text-zinc-500">{campaign.brand_name}</span>
          </div>
          <h1 className="text-4xl font-bold tracking-tighter text-white mb-2">
            {campaign.title}
          </h1>
          {campaign.description && (
            <p className="text-zinc-500 max-w-2xl">{campaign.description}</p>
          )}
        </div>

        <div className="flex gap-4">
          {campaign.status === 'draft' && (
            <>
              <button
                onClick={publishCampaign}
                disabled={!canPublish || publishing}
                className="px-6 py-3 bg-emerald-500 text-white text-xs font-mono uppercase tracking-widest hover:bg-emerald-600 transition-all font-bold disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                <Send className="w-4 h-4" />
                {publishing ? 'Publishing...' : 'Publish Campaign'}
              </button>
            </>
          )}
          {campaign.status === 'open' && (
            <button
              onClick={cancelCampaign}
              className="px-6 py-3 border border-red-500/50 text-red-400 text-xs font-mono uppercase tracking-widest hover:bg-red-500/10 transition-all flex items-center gap-2"
            >
              <XCircle className="w-4 h-4" />
              Cancel Campaign
            </button>
          )}
        </div>
      </div>

      {/* Campaign Info Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="border border-white/10 bg-zinc-900/30 p-4">
          <div className="flex items-center gap-2 text-zinc-500 mb-2">
            <DollarSign className="w-4 h-4" />
            <span className="text-[10px] uppercase tracking-widest">Budget</span>
          </div>
          <div className="text-2xl font-bold text-emerald-400">{formatCurrency(campaign.total_budget)}</div>
          <div className="text-xs text-zinc-500 mt-1">
            {campaign.upfront_percent}% upfront / {campaign.completion_percent}% completion
          </div>
        </div>
        <div className="border border-white/10 bg-zinc-900/30 p-4">
          <div className="flex items-center gap-2 text-zinc-500 mb-2">
            <Users className="w-4 h-4" />
            <span className="text-[10px] uppercase tracking-widest">Creators</span>
          </div>
          <div className="text-2xl font-bold text-white">
            {campaign.accepted_count}/{campaign.max_creators}
          </div>
          <div className="text-xs text-zinc-500 mt-1">
            {slotsRemaining > 0 ? `${slotsRemaining} slots remaining` : 'All slots filled'}
          </div>
        </div>
        <div className="border border-white/10 bg-zinc-900/30 p-4">
          <div className="flex items-center gap-2 text-zinc-500 mb-2">
            <Target className="w-4 h-4" />
            <span className="text-[10px] uppercase tracking-widest">Offers Sent</span>
          </div>
          <div className="text-2xl font-bold text-blue-400">{campaign.offers.length}</div>
          <div className="text-xs text-zinc-500 mt-1">
            {campaign.pending_offers_count} pending, {campaign.viewed_offers_count} viewed
          </div>
        </div>
        <div className="border border-white/10 bg-zinc-900/30 p-4">
          <div className="flex items-center gap-2 text-zinc-500 mb-2">
            <Calendar className="w-4 h-4" />
            <span className="text-[10px] uppercase tracking-widest">Expires</span>
          </div>
          <div className="text-lg font-bold text-white">
            {campaign.expires_at
              ? new Date(campaign.expires_at).toLocaleDateString()
              : 'No expiration'}
          </div>
        </div>
      </div>

      {/* Deliverables */}
      {campaign.deliverables.length > 0 && (
        <div className="border border-white/10 bg-zinc-900/30 p-6">
          <h2 className="text-xs font-bold text-white uppercase tracking-widest mb-4">Deliverables</h2>
          <div className="flex flex-wrap gap-3">
            {campaign.deliverables.map((d, i) => (
              <div key={i} className="px-3 py-2 bg-zinc-800 border border-white/5">
                <span className="text-emerald-400 font-mono text-sm mr-2">{d.quantity}x</span>
                <span className="text-zinc-300">{d.type.replace('_', ' ')}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Offers Section */}
      <div className="border border-white/10 bg-zinc-900/30">
        <div className="p-6 border-b border-white/10 flex justify-between items-center">
          <h2 className="text-xs font-bold text-white uppercase tracking-widest">
            Creator Offers ({campaign.offers.length})
          </h2>
          {canAddOffers && (
            <button
              onClick={() => setShowAddCreator(true)}
              className="px-4 py-2 bg-white text-black text-xs font-mono uppercase tracking-widest hover:bg-zinc-200 transition-all font-bold flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Add Creator
            </button>
          )}
        </div>

        {campaign.offers.length === 0 ? (
          <div className="p-12 text-center">
            <Users className="w-12 h-12 mx-auto mb-4 text-zinc-600" />
            <p className="text-zinc-400 mb-2">No creators added yet</p>
            <button
              onClick={() => setShowAddCreator(true)}
              className="text-xs text-emerald-400 hover:text-emerald-300"
            >
              Add your first creator →
            </button>
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {campaign.offers.map((offer) => {
              const statusConfig = getOfferStatusConfig(offer.status);
              const StatusIcon = statusConfig.icon;

              return (
                <div key={offer.id} className="p-6 hover:bg-white/5 transition-colors">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-4">
                      {offer.creator_profile_image ? (
                        <img
                          src={offer.creator_profile_image}
                          alt={offer.creator_name || ''}
                          className="w-12 h-12 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center">
                          <Users className="w-6 h-6 text-zinc-500" />
                        </div>
                      )}
                      <div>
                        <div className="flex items-center gap-3 mb-1">
                          <h3 className="text-sm font-medium text-white">
                            {offer.creator_name || 'Unknown Creator'}
                          </h3>
                          <span className={`px-2 py-0.5 rounded text-[10px] uppercase tracking-widest flex items-center gap-1 ${statusConfig.bg} ${statusConfig.color}`}>
                            <StatusIcon className="w-3 h-3" />
                            {statusConfig.label}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-zinc-500">
                          <span className="text-emerald-400 font-mono">
                            {formatCurrency(offer.offered_amount)}
                          </span>
                          {offer.creator_counter_amount && (
                            <span className="text-purple-400">
                              Counter: {formatCurrency(offer.creator_counter_amount)}
                            </span>
                          )}
                          {offer.viewed_at && (
                            <span>Viewed {new Date(offer.viewed_at).toLocaleDateString()}</span>
                          )}
                          {offer.responded_at && (
                            <span>Responded {new Date(offer.responded_at).toLocaleDateString()}</span>
                          )}
                        </div>
                        {offer.creator_notes && (
                          <p className="text-xs text-zinc-400 mt-2 italic">"{offer.creator_notes}"</p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {offer.status === 'accepted' && (
                        <button
                          onClick={() => generateContract(offer.creator_id)}
                          className="p-2 hover:bg-white/10 transition-colors text-zinc-500 hover:text-white"
                          title="Generate Contract"
                        >
                          <FileText className="w-4 h-4" />
                        </button>
                      )}
                      {(offer.status === 'pending' || offer.status === 'viewed') && campaign.status === 'draft' && (
                        <button
                          onClick={() => removeOffer(offer.creator_id)}
                          className="p-2 hover:bg-white/10 transition-colors text-zinc-500 hover:text-red-400"
                          title="Remove Offer"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Warning for draft campaigns */}
      {campaign.status === 'draft' && campaign.offers.length > 0 && (
        <div className="border border-amber-500/30 bg-amber-900/10 p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="text-sm font-medium text-amber-400">Ready to publish?</h3>
            <p className="text-xs text-amber-500/70 mt-1">
              Once published, offers will be visible to creators. When a creator accepts, {campaign.upfront_percent}% ({formatCurrency(campaign.total_budget * campaign.upfront_percent / 100)}) will be charged and held in escrow.
            </p>
          </div>
        </div>
      )}

      {/* Add Creator Modal */}
      {showAddCreator && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-900 border border-white/10 max-w-2xl w-full">
            <div className="p-6 border-b border-white/10">
              <h2 className="text-lg font-bold text-white">Add Creator to Campaign</h2>
              <p className="text-sm text-zinc-500 mt-1">
                Search for creators and send them an offer.
              </p>
            </div>
            <div className="p-6 space-y-4">
              {/* Search */}
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Search Creators
                </label>
                <div className="flex gap-2">
                  <div className="flex-1 relative">
                    <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && searchCreators()}
                      placeholder="Search by name or niche..."
                      className="w-full pl-12 pr-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
                    />
                  </div>
                  <button
                    onClick={searchCreators}
                    disabled={searching}
                    className="px-4 py-3 bg-white text-black text-xs font-mono uppercase tracking-widest hover:bg-zinc-200 font-bold disabled:opacity-50"
                  >
                    {searching ? '...' : 'Search'}
                  </button>
                </div>
              </div>

              {/* Search Results */}
              {searchResults.length > 0 && !selectedCreator && (
                <div className="max-h-60 overflow-y-auto border border-white/10">
                  {searchResults.map((creator) => (
                    <button
                      key={creator.id}
                      onClick={() => setSelectedCreator(creator)}
                      className="w-full p-4 text-left hover:bg-white/5 transition-colors flex items-center gap-4 border-b border-white/5 last:border-b-0"
                    >
                      {creator.profile_image_url ? (
                        <img
                          src={creator.profile_image_url}
                          alt={creator.display_name}
                          className="w-10 h-10 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-zinc-800 flex items-center justify-center">
                          <Users className="w-5 h-5 text-zinc-500" />
                        </div>
                      )}
                      <div>
                        <div className="text-sm font-medium text-white">{creator.display_name}</div>
                        {creator.niches.length > 0 && (
                          <div className="text-xs text-zinc-500">
                            {creator.niches.slice(0, 3).join(', ')}
                          </div>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {/* Selected Creator */}
              {selectedCreator && (
                <div className="border border-emerald-500/30 bg-emerald-900/10 p-4">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      {selectedCreator.profile_image_url ? (
                        <img
                          src={selectedCreator.profile_image_url}
                          alt={selectedCreator.display_name}
                          className="w-10 h-10 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-zinc-800 flex items-center justify-center">
                          <Users className="w-5 h-5 text-zinc-500" />
                        </div>
                      )}
                      <div>
                        <div className="text-sm font-medium text-white">{selectedCreator.display_name}</div>
                        <div className="text-xs text-emerald-400">Selected</div>
                      </div>
                    </div>
                    <button
                      onClick={() => setSelectedCreator(null)}
                      className="text-xs text-zinc-500 hover:text-white"
                    >
                      Change
                    </button>
                  </div>

                  {/* Offer Amount */}
                  <div className="mb-4">
                    <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                      Offer Amount ($)
                    </label>
                    <input
                      type="number"
                      value={offerAmount}
                      onChange={(e) => setOfferAmount(parseFloat(e.target.value) || 0)}
                      className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white font-mono focus:outline-none focus:border-white/30"
                    />
                    <p className="text-xs text-zinc-500 mt-1">
                      Campaign budget: {formatCurrency(campaign.total_budget)}
                    </p>
                  </div>

                  {/* Custom Message */}
                  <div>
                    <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                      Personal Message (optional)
                    </label>
                    <textarea
                      value={customMessage}
                      onChange={(e) => setCustomMessage(e.target.value)}
                      placeholder="Add a personal note to the creator..."
                      rows={3}
                      className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30 resize-none"
                    />
                  </div>
                </div>
              )}
            </div>
            <div className="p-6 border-t border-white/10 flex justify-end gap-4">
              <button
                onClick={() => {
                  setShowAddCreator(false);
                  setSelectedCreator(null);
                  setSearchQuery('');
                  setSearchResults([]);
                }}
                className="px-6 py-2 border border-white/20 text-xs font-mono uppercase tracking-widest hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={addOffer}
                disabled={!selectedCreator || !offerAmount}
                className="px-6 py-2 bg-white text-black text-xs font-mono uppercase tracking-widest hover:bg-zinc-200 font-bold disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Add Offer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CampaignDetail;
