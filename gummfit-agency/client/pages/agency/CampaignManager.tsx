import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Target,
  Plus,
  Search,
  Filter,
  ChevronDown,
  Users,
  Calendar,
  DollarSign,
  MoreVertical,
  Edit,
  Trash2,
  Eye,
  Send,
  XCircle,
  Clock,
  CheckCircle,
  AlertTriangle,
} from 'lucide-react';
import { api } from '../../api/client';
import type { Campaign, CampaignCreate, CampaignStatus, CampaignDeliverable } from '../../types/campaigns';

export function CampaignManager() {
  const navigate = useNavigate();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [showNewCampaign, setShowNewCampaign] = useState(false);
  const [actionMenu, setActionMenu] = useState<string | null>(null);
  const [publishing, setPublishing] = useState<string | null>(null);

  const [newCampaign, setNewCampaign] = useState<CampaignCreate>({
    brand_name: '',
    title: '',
    description: '',
    total_budget: 0,
    upfront_percent: 30,
    completion_percent: 70,
    max_creators: 1,
    deliverables: [],
  });

  const [newDeliverable, setNewDeliverable] = useState<CampaignDeliverable>({
    type: '',
    quantity: 1,
    description: '',
  });

  useEffect(() => {
    loadCampaigns();
  }, []);

  const loadCampaigns = async () => {
    try {
      const res = await api.campaigns.list();
      setCampaigns(res);
    } catch (err) {
      console.error('Failed to load campaigns:', err);
    } finally {
      setLoading(false);
    }
  };

  const createCampaign = async () => {
    if (!newCampaign.title || !newCampaign.brand_name || !newCampaign.total_budget) return;
    try {
      const created = await api.campaigns.create(newCampaign);
      setShowNewCampaign(false);
      setNewCampaign({
        brand_name: '',
        title: '',
        description: '',
        total_budget: 0,
        upfront_percent: 30,
        completion_percent: 70,
        max_creators: 1,
        deliverables: [],
      });
      // Navigate to campaign detail to add creators
      navigate(`/app/agency/campaigns/${created.id}`);
    } catch (err) {
      console.error('Failed to create campaign:', err);
    }
  };

  const publishCampaign = async (campaignId: string) => {
    setPublishing(campaignId);
    try {
      await api.campaigns.publish(campaignId);
      setActionMenu(null);
      loadCampaigns();
    } catch (err: unknown) {
      const error = err as Error;
      alert(error.message || 'Failed to publish campaign');
    } finally {
      setPublishing(null);
    }
  };

  const cancelCampaign = async (campaignId: string) => {
    if (!confirm('Cancel this campaign? Pending offers will be expired.')) return;
    try {
      await api.campaigns.cancel(campaignId);
      setActionMenu(null);
      loadCampaigns();
    } catch (err) {
      console.error('Failed to cancel campaign:', err);
    }
  };

  const deleteCampaign = async (campaignId: string) => {
    if (!confirm('Delete this campaign? This action cannot be undone.')) return;
    try {
      await api.campaigns.delete(campaignId);
      setActionMenu(null);
      loadCampaigns();
    } catch (err) {
      console.error('Failed to delete campaign:', err);
    }
  };

  const addDeliverable = () => {
    if (!newDeliverable.type) return;
    setNewCampaign({
      ...newCampaign,
      deliverables: [...(newCampaign.deliverables || []), newDeliverable],
    });
    setNewDeliverable({ type: '', quantity: 1, description: '' });
  };

  const removeDeliverable = (index: number) => {
    const updated = [...(newCampaign.deliverables || [])];
    updated.splice(index, 1);
    setNewCampaign({ ...newCampaign, deliverables: updated });
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

  const getStatusConfig = (status: CampaignStatus) => {
    switch (status) {
      case 'draft': return { color: 'text-zinc-500', bg: 'bg-zinc-500/10', icon: Edit };
      case 'open': return { color: 'text-blue-500', bg: 'bg-blue-500/10', icon: Send };
      case 'active': return { color: 'text-emerald-500', bg: 'bg-emerald-500/10', icon: CheckCircle };
      case 'completed': return { color: 'text-purple-500', bg: 'bg-purple-500/10', icon: CheckCircle };
      case 'cancelled': return { color: 'text-red-500', bg: 'bg-red-500/10', icon: XCircle };
      default: return { color: 'text-zinc-500', bg: 'bg-zinc-500/10', icon: Clock };
    }
  };

  const statuses: CampaignStatus[] = ['draft', 'open', 'active', 'completed', 'cancelled'];
  const deliverableTypes = [
    'instagram_post', 'instagram_story', 'instagram_reel',
    'youtube_video', 'youtube_short',
    'tiktok_video',
    'twitter_post', 'twitter_thread',
    'blog_post', 'podcast_mention', 'other'
  ];

  const filteredCampaigns = campaigns.filter(campaign => {
    const matchesSearch = searchQuery === '' ||
      campaign.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      campaign.brand_name.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesStatus = selectedStatus === 'all' || campaign.status === selectedStatus;

    return matchesSearch && matchesStatus;
  });

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
            <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Campaign Platform
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Campaigns
          </h1>
          <p className="text-zinc-500 mt-2 text-sm">
            Create targeted offers for specific creators. First to accept wins.
          </p>
        </div>
        <button
          onClick={() => setShowNewCampaign(true)}
          className="px-6 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest transition-all font-bold flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Campaign
        </button>
      </div>

      {/* Search & Filters */}
      <div className="flex flex-col md:flex-row gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search campaigns..."
            className="w-full pl-12 pr-4 py-3 bg-zinc-900 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSelectedStatus('all')}
            className={`px-4 py-2 text-xs font-mono uppercase tracking-widest transition-all border ${
              selectedStatus === 'all'
                ? 'bg-white text-black border-white'
                : 'border-white/20 text-zinc-400 hover:border-white/40'
            }`}
          >
            All
          </button>
          {statuses.map((status) => {
            const count = campaigns.filter(c => c.status === status).length;
            if (count === 0) return null;
            return (
              <button
                key={status}
                onClick={() => setSelectedStatus(status)}
                className={`px-4 py-2 text-xs font-mono uppercase tracking-widest transition-all border ${
                  selectedStatus === status
                    ? 'bg-white text-black border-white'
                    : 'border-white/20 text-zinc-400 hover:border-white/40'
                }`}
              >
                {status} ({count})
              </button>
            );
          })}
        </div>
      </div>

      {/* Results count */}
      <div className="flex items-center gap-2 text-zinc-500">
        <Filter className="w-4 h-4" />
        <span className="text-xs">{filteredCampaigns.length} campaigns</span>
      </div>

      {/* Campaigns List */}
      {filteredCampaigns.length === 0 ? (
        <div className="border border-white/10 bg-zinc-900/30 p-12 text-center">
          <Target className="w-12 h-12 mx-auto mb-4 text-zinc-600" />
          <p className="text-zinc-400 mb-2">No campaigns found</p>
          <button
            onClick={() => setShowNewCampaign(true)}
            className="text-xs text-emerald-400 hover:text-emerald-300"
          >
            Create your first campaign →
          </button>
        </div>
      ) : (
        <div className="border border-white/10 bg-zinc-900/30 divide-y divide-white/5">
          {filteredCampaigns.map((campaign) => {
            const statusConfig = getStatusConfig(campaign.status);
            const StatusIcon = statusConfig.icon;
            const slotsRemaining = campaign.max_creators - campaign.accepted_count;

            return (
              <div
                key={campaign.id}
                className="p-6 hover:bg-white/5 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3
                        onClick={() => navigate(`/app/agency/campaigns/${campaign.id}`)}
                        className="text-lg font-medium text-white hover:text-emerald-400 cursor-pointer transition-colors"
                      >
                        {campaign.title}
                      </h3>
                      <span className={`px-2 py-1 rounded text-[10px] uppercase tracking-widest flex items-center gap-1 ${statusConfig.bg} ${statusConfig.color}`}>
                        <StatusIcon className="w-3 h-3" />
                        {campaign.status}
                      </span>
                    </div>

                    <p className="text-sm text-zinc-500 mb-3">{campaign.brand_name}</p>

                    {campaign.description && (
                      <p className="text-sm text-zinc-400 line-clamp-2 mb-4">
                        {campaign.description}
                      </p>
                    )}

                    <div className="flex flex-wrap items-center gap-6 text-xs text-zinc-500">
                      <div className="flex items-center gap-2">
                        <DollarSign className="w-4 h-4 text-emerald-500" />
                        <span className="text-emerald-400">
                          {formatCurrency(campaign.total_budget)}
                        </span>
                        <span className="text-zinc-600">
                          ({campaign.upfront_percent}% / {campaign.completion_percent}%)
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Users className="w-4 h-4" />
                        <span>
                          {campaign.accepted_count}/{campaign.max_creators} accepted
                        </span>
                        {slotsRemaining > 0 && campaign.status === 'open' && (
                          <span className="text-amber-400">
                            ({slotsRemaining} slots open)
                          </span>
                        )}
                      </div>
                      {campaign.expires_at && (
                        <div className="flex items-center gap-2">
                          <Calendar className="w-4 h-4 text-amber-500" />
                          <span className="text-amber-400">
                            Expires: {new Date(campaign.expires_at).toLocaleDateString()}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="relative">
                    <button
                      onClick={() => setActionMenu(actionMenu === campaign.id ? null : campaign.id)}
                      className="p-2 hover:bg-white/5 transition-colors"
                    >
                      <MoreVertical className="w-5 h-5 text-zinc-500" />
                    </button>

                    {actionMenu === campaign.id && (
                      <div className="absolute right-0 top-full mt-2 w-48 bg-zinc-800 border border-white/10 shadow-xl z-10">
                        <button
                          onClick={() => navigate(`/app/agency/campaigns/${campaign.id}`)}
                          className="w-full px-4 py-2 text-left text-sm text-zinc-300 hover:bg-white/5 flex items-center gap-2"
                        >
                          <Eye className="w-4 h-4" /> View Details
                        </button>
                        {campaign.status === 'draft' && (
                          <>
                            <button
                              onClick={() => navigate(`/app/agency/campaigns/${campaign.id}`)}
                              className="w-full px-4 py-2 text-left text-sm text-zinc-300 hover:bg-white/5 flex items-center gap-2"
                            >
                              <Users className="w-4 h-4" /> Add Creators
                            </button>
                            <button
                              onClick={() => publishCampaign(campaign.id)}
                              disabled={publishing === campaign.id}
                              className="w-full px-4 py-2 text-left text-sm text-emerald-400 hover:bg-white/5 flex items-center gap-2"
                            >
                              <Send className="w-4 h-4" />
                              {publishing === campaign.id ? 'Publishing...' : 'Publish Campaign'}
                            </button>
                          </>
                        )}
                        {campaign.status === 'open' && (
                          <button
                            onClick={() => cancelCampaign(campaign.id)}
                            className="w-full px-4 py-2 text-left text-sm text-amber-400 hover:bg-white/5 flex items-center gap-2"
                          >
                            <XCircle className="w-4 h-4" /> Cancel Campaign
                          </button>
                        )}
                        {campaign.status === 'draft' && (
                          <button
                            onClick={() => deleteCampaign(campaign.id)}
                            className="w-full px-4 py-2 text-left text-sm text-red-400 hover:bg-white/5 flex items-center gap-2"
                          >
                            <Trash2 className="w-4 h-4" /> Delete
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* New Campaign Modal */}
      {showNewCampaign && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4 overflow-y-auto">
          <div className="bg-zinc-900 border border-white/10 max-w-2xl w-full my-8">
            <div className="p-6 border-b border-white/10">
              <h2 className="text-lg font-bold text-white">Create Campaign</h2>
              <p className="text-sm text-zinc-500 mt-1">
                Set up your campaign terms, then add creators to receive offers.
              </p>
            </div>
            <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
              {/* Basic Info */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                    Campaign Title *
                  </label>
                  <input
                    type="text"
                    value={newCampaign.title}
                    onChange={(e) => setNewCampaign({ ...newCampaign, title: e.target.value })}
                    placeholder="e.g., Summer Launch 2024"
                    className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                    Brand Name *
                  </label>
                  <input
                    type="text"
                    value={newCampaign.brand_name}
                    onChange={(e) => setNewCampaign({ ...newCampaign, brand_name: e.target.value })}
                    placeholder="e.g., Nike"
                    className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Description
                </label>
                <textarea
                  value={newCampaign.description}
                  onChange={(e) => setNewCampaign({ ...newCampaign, description: e.target.value })}
                  placeholder="Describe the campaign goals and requirements..."
                  rows={3}
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30 resize-none"
                />
              </div>

              {/* Budget & Payment Split */}
              <div className="border border-white/10 p-4 bg-zinc-800/50">
                <h3 className="text-xs font-bold text-white uppercase tracking-widest mb-4">
                  Budget & Payment Terms
                </h3>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                      Total Budget ($) *
                    </label>
                    <input
                      type="number"
                      value={newCampaign.total_budget || ''}
                      onChange={(e) => setNewCampaign({ ...newCampaign, total_budget: parseFloat(e.target.value) || 0 })}
                      placeholder="10000"
                      className="w-full px-4 py-3 bg-zinc-900 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                      Upfront %
                    </label>
                    <input
                      type="number"
                      value={newCampaign.upfront_percent}
                      onChange={(e) => {
                        const upfront = Math.min(100, Math.max(0, parseInt(e.target.value) || 0));
                        setNewCampaign({
                          ...newCampaign,
                          upfront_percent: upfront,
                          completion_percent: 100 - upfront,
                        });
                      }}
                      min={0}
                      max={100}
                      className="w-full px-4 py-3 bg-zinc-900 border border-white/10 text-white focus:outline-none focus:border-white/30"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                      Completion %
                    </label>
                    <input
                      type="number"
                      value={newCampaign.completion_percent}
                      disabled
                      className="w-full px-4 py-3 bg-zinc-950 border border-white/5 text-zinc-500"
                    />
                  </div>
                </div>
                <div className="mt-3 text-xs text-zinc-500 flex items-center gap-2">
                  <AlertTriangle className="w-3 h-3 text-amber-500" />
                  {newCampaign.upfront_percent}% ({formatCurrency((newCampaign.total_budget || 0) * (newCampaign.upfront_percent || 0) / 100)}) will be charged when a creator accepts
                </div>
              </div>

              {/* Creator Slots */}
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Max Creators (first to accept wins)
                </label>
                <div className="relative">
                  <select
                    value={newCampaign.max_creators}
                    onChange={(e) => setNewCampaign({ ...newCampaign, max_creators: parseInt(e.target.value) })}
                    className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white appearance-none focus:outline-none focus:border-white/30"
                  >
                    {[1, 2, 3, 4, 5, 10].map((n) => (
                      <option key={n} value={n}>{n} creator{n > 1 ? 's' : ''}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
                </div>
              </div>

              {/* Deliverables */}
              <div className="border border-white/10 p-4 bg-zinc-800/50">
                <h3 className="text-xs font-bold text-white uppercase tracking-widest mb-4">
                  Deliverables
                </h3>

                {(newCampaign.deliverables || []).length > 0 && (
                  <div className="space-y-2 mb-4">
                    {newCampaign.deliverables?.map((d, i) => (
                      <div key={i} className="flex items-center justify-between p-2 bg-zinc-900 border border-white/5">
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-emerald-400 font-mono">{d.quantity}x</span>
                          <span className="text-sm text-zinc-300">{d.type.replace('_', ' ')}</span>
                          {d.description && (
                            <span className="text-xs text-zinc-500">- {d.description}</span>
                          )}
                        </div>
                        <button
                          onClick={() => removeDeliverable(i)}
                          className="text-zinc-500 hover:text-red-400"
                        >
                          <XCircle className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <div className="grid grid-cols-4 gap-2">
                  <div className="col-span-2">
                    <select
                      value={newDeliverable.type}
                      onChange={(e) => setNewDeliverable({ ...newDeliverable, type: e.target.value })}
                      className="w-full px-3 py-2 bg-zinc-900 border border-white/10 text-white text-sm appearance-none focus:outline-none focus:border-white/30"
                    >
                      <option value="">Select type...</option>
                      {deliverableTypes.map((type) => (
                        <option key={type} value={type}>{type.replace('_', ' ')}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <input
                      type="number"
                      value={newDeliverable.quantity}
                      onChange={(e) => setNewDeliverable({ ...newDeliverable, quantity: parseInt(e.target.value) || 1 })}
                      min={1}
                      placeholder="Qty"
                      className="w-full px-3 py-2 bg-zinc-900 border border-white/10 text-white text-sm focus:outline-none focus:border-white/30"
                    />
                  </div>
                  <button
                    onClick={addDeliverable}
                    disabled={!newDeliverable.type}
                    className="px-3 py-2 bg-white/10 text-white text-xs hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Add
                  </button>
                </div>
              </div>

              {/* Expiration */}
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Campaign Expiration (optional)
                </label>
                <input
                  type="datetime-local"
                  value={newCampaign.expires_at || ''}
                  onChange={(e) => setNewCampaign({ ...newCampaign, expires_at: e.target.value })}
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white focus:outline-none focus:border-white/30"
                />
              </div>
            </div>
            <div className="p-6 border-t border-white/10 flex justify-end gap-4">
              <button
                onClick={() => setShowNewCampaign(false)}
                className="px-6 py-2 border border-white/20 text-xs font-mono uppercase tracking-widest hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={createCampaign}
                disabled={!newCampaign.title || !newCampaign.brand_name || !newCampaign.total_budget}
                className="px-6 py-2 bg-white text-black text-xs font-mono uppercase tracking-widest hover:bg-zinc-200 font-bold disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Create & Add Creators
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CampaignManager;
