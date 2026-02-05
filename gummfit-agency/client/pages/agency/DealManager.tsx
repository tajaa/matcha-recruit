import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Briefcase,
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
  EyeOff
} from 'lucide-react';
import { api } from '../../api/client';
import type { BrandDeal, BrandDealCreate, DealStatus, DealVisibility, CompensationType } from '../../types/deals';

export function DealManager() {
  const navigate = useNavigate();
  const [deals, setDeals] = useState<BrandDeal[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [showNewDeal, setShowNewDeal] = useState(false);
  const [actionMenu, setActionMenu] = useState<string | null>(null);

  const [newDeal, setNewDeal] = useState<BrandDealCreate>({
    title: '',
    brand_name: '',
    description: '',
    compensation_type: 'fixed',
    niches: [],
    preferred_platforms: [],
  });

  useEffect(() => {
    loadDeals();
  }, []);

  const loadDeals = async () => {
    try {
      const res = await api.deals.listAgencyDeals();
      setDeals(res);
    } catch (err) {
      console.error('Failed to load deals:', err);
    } finally {
      setLoading(false);
    }
  };

  const createDeal = async () => {
    if (!newDeal.title || !newDeal.brand_name || !newDeal.description) return;
    try {
      await api.deals.createDeal(newDeal);
      setShowNewDeal(false);
      setNewDeal({
        title: '',
        brand_name: '',
        description: '',
        compensation_type: 'fixed',
        niches: [],
        preferred_platforms: [],
      });
      loadDeals();
    } catch (err) {
      console.error('Failed to create deal:', err);
    }
  };

  const updateDealStatus = async (dealId: string, status: DealStatus) => {
    try {
      await api.deals.updateDeal(dealId, { status });
      setActionMenu(null);
      loadDeals();
    } catch (err) {
      console.error('Failed to update deal:', err);
    }
  };

  const deleteDeal = async (dealId: string) => {
    if (!confirm('Delete this deal? This action cannot be undone.')) return;
    try {
      await api.deals.deleteDeal(dealId);
      setActionMenu(null);
      loadDeals();
    } catch (err) {
      console.error('Failed to delete deal:', err);
    }
  };

  const formatCurrency = (amount: number | null) => {
    if (!amount) return 'N/A';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  };

  const getStatusConfig = (status: DealStatus) => {
    switch (status) {
      case 'draft': return { color: 'text-zinc-500', bg: 'bg-zinc-500/10' };
      case 'open': return { color: 'text-emerald-500', bg: 'bg-emerald-500/10' };
      case 'closed': return { color: 'text-zinc-500', bg: 'bg-zinc-500/10' };
      case 'filled': return { color: 'text-blue-500', bg: 'bg-blue-500/10' };
      case 'cancelled': return { color: 'text-red-500', bg: 'bg-red-500/10' };
      default: return { color: 'text-zinc-500', bg: 'bg-zinc-500/10' };
    }
  };

  const statuses: DealStatus[] = ['draft', 'open', 'closed', 'filled', 'cancelled'];
  const compensationTypes: { value: CompensationType; label: string }[] = [
    { value: 'fixed', label: 'Fixed Rate' },
    { value: 'per_deliverable', label: 'Per Deliverable' },
    { value: 'revenue_share', label: 'Revenue Share' },
    { value: 'product_only', label: 'Product Only' },
    { value: 'negotiable', label: 'Negotiable' },
  ];

  const filteredDeals = deals.filter(deal => {
    const matchesSearch = searchQuery === '' ||
      deal.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      deal.brand_name.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesStatus = selectedStatus === 'all' || deal.status === selectedStatus;

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
            <div className="px-2 py-1 border border-purple-500/20 bg-purple-900/10 text-purple-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Deal Management
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Brand Deals
          </h1>
        </div>
        <button
          onClick={() => setShowNewDeal(true)}
          className="px-6 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest transition-all font-bold flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          New Deal
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
            placeholder="Search deals..."
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
            const count = deals.filter(d => d.status === status).length;
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
        <span className="text-xs">{filteredDeals.length} deals</span>
      </div>

      {/* Deals List */}
      {filteredDeals.length === 0 ? (
        <div className="border border-white/10 bg-zinc-900/30 p-12 text-center">
          <Briefcase className="w-12 h-12 mx-auto mb-4 text-zinc-600" />
          <p className="text-zinc-400 mb-2">No deals found</p>
          <button
            onClick={() => setShowNewDeal(true)}
            className="text-xs text-emerald-400 hover:text-emerald-300"
          >
            Create your first deal →
          </button>
        </div>
      ) : (
        <div className="border border-white/10 bg-zinc-900/30 divide-y divide-white/5">
          {filteredDeals.map((deal) => {
            const statusConfig = getStatusConfig(deal.status);

            return (
              <div
                key={deal.id}
                className="p-6 hover:bg-white/5 transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3
                        onClick={() => navigate(`/app/gumfit/agency/deals/${deal.id}`)}
                        className="text-lg font-medium text-white hover:text-emerald-400 cursor-pointer transition-colors"
                      >
                        {deal.title}
                      </h3>
                      <span className={`px-2 py-1 rounded text-[10px] uppercase tracking-widest ${statusConfig.bg} ${statusConfig.color}`}>
                        {deal.status}
                      </span>
                      {deal.visibility === 'private' && (
                        <EyeOff className="w-3 h-3 text-zinc-600" />
                      )}
                    </div>

                    <p className="text-sm text-zinc-500 mb-3">{deal.brand_name}</p>

                    <p className="text-sm text-zinc-400 line-clamp-2 mb-4">
                      {deal.description}
                    </p>

                    <div className="flex flex-wrap items-center gap-6 text-xs text-zinc-500">
                      <div className="flex items-center gap-2">
                        <Users className="w-4 h-4" />
                        <span>{deal.applications_count} applications</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <DollarSign className="w-4 h-4 text-emerald-500" />
                        <span className="text-emerald-400">
                          {deal.compensation_min || deal.compensation_max
                            ? `${formatCurrency(deal.compensation_min)} - ${formatCurrency(deal.compensation_max)}`
                            : 'Negotiable'}
                        </span>
                      </div>
                      {deal.application_deadline && (
                        <div className="flex items-center gap-2">
                          <Calendar className="w-4 h-4 text-amber-500" />
                          <span className="text-amber-400">
                            Deadline: {formatDate(deal.application_deadline)}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="relative">
                    <button
                      onClick={() => setActionMenu(actionMenu === deal.id ? null : deal.id)}
                      className="p-2 hover:bg-white/5 transition-colors"
                    >
                      <MoreVertical className="w-5 h-5 text-zinc-500" />
                    </button>

                    {actionMenu === deal.id && (
                      <div className="absolute right-0 top-full mt-2 w-48 bg-zinc-800 border border-white/10 shadow-xl z-10">
                        <button
                          onClick={() => navigate(`/app/gumfit/agency/deals/${deal.id}`)}
                          className="w-full px-4 py-2 text-left text-sm text-zinc-300 hover:bg-white/5 flex items-center gap-2"
                        >
                          <Eye className="w-4 h-4" /> View Details
                        </button>
                        <button
                          onClick={() => navigate(`/app/gumfit/agency/deals/${deal.id}/edit`)}
                          className="w-full px-4 py-2 text-left text-sm text-zinc-300 hover:bg-white/5 flex items-center gap-2"
                        >
                          <Edit className="w-4 h-4" /> Edit
                        </button>
                        {deal.status === 'draft' && (
                          <button
                            onClick={() => updateDealStatus(deal.id, 'open')}
                            className="w-full px-4 py-2 text-left text-sm text-emerald-400 hover:bg-white/5"
                          >
                            Publish Deal
                          </button>
                        )}
                        {deal.status === 'open' && (
                          <button
                            onClick={() => updateDealStatus(deal.id, 'closed')}
                            className="w-full px-4 py-2 text-left text-sm text-amber-400 hover:bg-white/5"
                          >
                            Close Deal
                          </button>
                        )}
                        <button
                          onClick={() => deleteDeal(deal.id)}
                          className="w-full px-4 py-2 text-left text-sm text-red-400 hover:bg-white/5 flex items-center gap-2"
                        >
                          <Trash2 className="w-4 h-4" /> Delete
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* New Deal Modal */}
      {showNewDeal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4 overflow-y-auto">
          <div className="bg-zinc-900 border border-white/10 max-w-2xl w-full my-8">
            <div className="p-6 border-b border-white/10">
              <h2 className="text-lg font-bold text-white">Create Brand Deal</h2>
            </div>
            <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Deal Title *
                </label>
                <input
                  type="text"
                  value={newDeal.title}
                  onChange={(e) => setNewDeal({ ...newDeal, title: e.target.value })}
                  placeholder="e.g., Summer Campaign 2024"
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Brand Name *
                </label>
                <input
                  type="text"
                  value={newDeal.brand_name}
                  onChange={(e) => setNewDeal({ ...newDeal, brand_name: e.target.value })}
                  placeholder="e.g., Nike"
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Description *
                </label>
                <textarea
                  value={newDeal.description}
                  onChange={(e) => setNewDeal({ ...newDeal, description: e.target.value })}
                  placeholder="Describe the campaign, deliverables, and requirements..."
                  rows={4}
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30 resize-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                    Compensation Type
                  </label>
                  <div className="relative">
                    <select
                      value={newDeal.compensation_type}
                      onChange={(e) => setNewDeal({ ...newDeal, compensation_type: e.target.value as CompensationType })}
                      className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white appearance-none focus:outline-none focus:border-white/30"
                    >
                      {compensationTypes.map((type) => (
                        <option key={type.value} value={type.value}>{type.label}</option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
                  </div>
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                    Visibility
                  </label>
                  <div className="relative">
                    <select
                      value={newDeal.visibility || 'public'}
                      onChange={(e) => setNewDeal({ ...newDeal, visibility: e.target.value as DealVisibility })}
                      className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white appearance-none focus:outline-none focus:border-white/30"
                    >
                      <option value="public">Public</option>
                      <option value="invite_only">Invite Only</option>
                      <option value="private">Private</option>
                    </select>
                    <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                    Compensation Min ($)
                  </label>
                  <input
                    type="number"
                    value={newDeal.compensation_min || ''}
                    onChange={(e) => setNewDeal({ ...newDeal, compensation_min: parseFloat(e.target.value) || undefined })}
                    placeholder="500"
                    className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                    Compensation Max ($)
                  </label>
                  <input
                    type="number"
                    value={newDeal.compensation_max || ''}
                    onChange={(e) => setNewDeal({ ...newDeal, compensation_max: parseFloat(e.target.value) || undefined })}
                    placeholder="5000"
                    className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
                  />
                </div>
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Application Deadline
                </label>
                <input
                  type="date"
                  value={newDeal.application_deadline || ''}
                  onChange={(e) => setNewDeal({ ...newDeal, application_deadline: e.target.value })}
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white focus:outline-none focus:border-white/30"
                />
              </div>
            </div>
            <div className="p-6 border-t border-white/10 flex justify-end gap-4">
              <button
                onClick={() => setShowNewDeal(false)}
                className="px-6 py-2 border border-white/20 text-xs font-mono uppercase tracking-widest hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={createDeal}
                className="px-6 py-2 bg-white text-black text-xs font-mono uppercase tracking-widest hover:bg-zinc-200 font-bold"
              >
                Create Deal
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default DealManager;
