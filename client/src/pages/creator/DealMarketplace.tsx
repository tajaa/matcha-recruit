import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Briefcase,
  Search,
  Filter,
  ChevronDown,
  DollarSign,
  Calendar,
  Users,
  ArrowUpRight,
  Building,
  CheckCircle2
} from 'lucide-react';
import { api } from '../../api/client';
import type { BrandDealPublic } from '../../types/deals';

export function DealMarketplace() {
  const navigate = useNavigate();
  const [deals, setDeals] = useState<BrandDealPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNiche, setSelectedNiche] = useState<string>('all');
  const [selectedPlatform, setSelectedPlatform] = useState<string>('all');

  useEffect(() => {
    loadDeals();
  }, []);

  const loadDeals = async () => {
    try {
      const res = await api.deals.browseMarketplace({ limit: 50 });
      setDeals(res);
    } catch (err) {
      console.error('Failed to load deals:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount: number | null) => {
    if (!amount) return 'Negotiable';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatCompensation = (deal: BrandDealPublic) => {
    if (deal.compensation_type === 'negotiable') return 'Negotiable';
    if (deal.compensation_type === 'product_only') return 'Product Only';
    if (deal.compensation_min && deal.compensation_max) {
      return `${formatCurrency(deal.compensation_min)} - ${formatCurrency(deal.compensation_max)}`;
    }
    if (deal.compensation_min) return `From ${formatCurrency(deal.compensation_min)}`;
    if (deal.compensation_max) return `Up to ${formatCurrency(deal.compensation_max)}`;
    return 'Contact for rate';
  };

  const formatFollowers = (min: number | null, max: number | null) => {
    const format = (n: number) => {
      if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
      if (n >= 1000) return `${(n / 1000).toFixed(0)}K`;
      return n.toString();
    };
    if (min && max) return `${format(min)} - ${format(max)}`;
    if (min) return `${format(min)}+`;
    if (max) return `Up to ${format(max)}`;
    return 'Any size';
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return null;
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  };

  // Get unique niches and platforms for filters
  const allNiches = [...new Set(deals.flatMap(d => d.niches))];
  const allPlatforms = [...new Set(deals.flatMap(d => d.preferred_platforms))];

  // Filter deals
  const filteredDeals = deals.filter(deal => {
    const matchesSearch = searchQuery === '' ||
      deal.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      deal.brand_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      deal.description.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesNiche = selectedNiche === 'all' ||
      deal.niches.includes(selectedNiche);

    const matchesPlatform = selectedPlatform === 'all' ||
      deal.preferred_platforms.includes(selectedPlatform);

    return matchesSearch && matchesNiche && matchesPlatform;
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
              Brand Partnerships
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Deal Marketplace
          </h1>
        </div>
        <div className="flex gap-4">
          <button
            onClick={() => navigate('/app/creator/applications')}
            className="px-6 py-3 border border-white/20 hover:bg-white hover:text-black text-xs font-mono uppercase tracking-widest transition-all"
          >
            My Applications
          </button>
        </div>
      </div>

      {/* Search & Filters */}
      <div className="flex flex-col md:flex-row gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search deals, brands..."
            className="w-full pl-12 pr-4 py-3 bg-zinc-900 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
          />
        </div>
        <div className="relative">
          <select
            value={selectedNiche}
            onChange={(e) => setSelectedNiche(e.target.value)}
            className="appearance-none px-4 py-3 pr-10 bg-zinc-900 border border-white/10 text-white focus:outline-none focus:border-white/30 min-w-[160px]"
          >
            <option value="all">All Niches</option>
            {allNiches.map(niche => (
              <option key={niche} value={niche}>{niche}</option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
        </div>
        <div className="relative">
          <select
            value={selectedPlatform}
            onChange={(e) => setSelectedPlatform(e.target.value)}
            className="appearance-none px-4 py-3 pr-10 bg-zinc-900 border border-white/10 text-white focus:outline-none focus:border-white/30 min-w-[160px]"
          >
            <option value="all">All Platforms</option>
            {allPlatforms.map(platform => (
              <option key={platform} value={platform}>{platform}</option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
        </div>
      </div>

      {/* Results count */}
      <div className="flex items-center gap-2 text-zinc-500">
        <Filter className="w-4 h-4" />
        <span className="text-xs">{filteredDeals.length} deals available</span>
      </div>

      {/* Deals Grid */}
      {filteredDeals.length === 0 ? (
        <div className="border border-white/10 bg-zinc-900/30 p-12 text-center">
          <Briefcase className="w-12 h-12 mx-auto mb-4 text-zinc-600" />
          <p className="text-zinc-400 mb-2">No deals found</p>
          <p className="text-xs text-zinc-600">
            Try adjusting your search or filters
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filteredDeals.map((deal) => (
            <div
              key={deal.id}
              onClick={() => navigate(`/app/creator/deals/${deal.id}`)}
              className="border border-white/10 bg-zinc-900/30 p-6 hover:border-white/30 hover:bg-zinc-800/50 transition-all cursor-pointer group"
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="text-lg font-medium text-white group-hover:text-emerald-400 transition-colors">
                      {deal.title}
                    </h3>
                    {deal.agency_verified && (
                      <CheckCircle2 className="w-4 h-4 text-blue-400" />
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-sm text-zinc-500">
                    <Building className="w-3 h-3" />
                    <span>{deal.brand_name}</span>
                    <span className="text-zinc-700">•</span>
                    <span>{deal.agency_name}</span>
                  </div>
                </div>
                <ArrowUpRight className="w-5 h-5 text-zinc-600 group-hover:text-white transition-colors" />
              </div>

              {/* Description */}
              <p className="text-sm text-zinc-400 line-clamp-2 mb-4">
                {deal.description}
              </p>

              {/* Tags */}
              <div className="flex flex-wrap gap-2 mb-4">
                {deal.niches.slice(0, 3).map(niche => (
                  <span
                    key={niche}
                    className="px-2 py-1 bg-purple-500/10 text-purple-400 text-[10px] uppercase tracking-widest rounded"
                  >
                    {niche}
                  </span>
                ))}
                {deal.preferred_platforms.slice(0, 2).map(platform => (
                  <span
                    key={platform}
                    className="px-2 py-1 bg-blue-500/10 text-blue-400 text-[10px] uppercase tracking-widest rounded"
                  >
                    {platform}
                  </span>
                ))}
              </div>

              {/* Footer Info */}
              <div className="flex flex-wrap items-center gap-4 pt-4 border-t border-white/5">
                <div className="flex items-center gap-2">
                  <DollarSign className="w-4 h-4 text-emerald-500" />
                  <span className="text-sm text-emerald-400 font-medium">
                    {formatCompensation(deal)}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Users className="w-4 h-4 text-zinc-500" />
                  <span className="text-xs text-zinc-500">
                    {formatFollowers(deal.min_followers, deal.max_followers)}
                  </span>
                </div>
                {deal.application_deadline && (
                  <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-amber-500" />
                    <span className="text-xs text-amber-400">
                      Apply by {formatDate(deal.application_deadline)}
                    </span>
                  </div>
                )}
              </div>

              {/* Deliverables Preview */}
              {deal.deliverables.length > 0 && (
                <div className="mt-4 pt-4 border-t border-white/5">
                  <span className="text-[10px] text-zinc-600 uppercase tracking-widest">Deliverables:</span>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {deal.deliverables.slice(0, 3).map((d, i) => (
                      <span key={i} className="text-xs text-zinc-400">
                        {d.quantity && `${d.quantity}x `}{d.type}
                        {d.platform && ` (${d.platform})`}
                      </span>
                    ))}
                    {deal.deliverables.length > 3 && (
                      <span className="text-xs text-zinc-600">
                        +{deal.deliverables.length - 3} more
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default DealMarketplace;
