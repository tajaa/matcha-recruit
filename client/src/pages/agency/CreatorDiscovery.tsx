import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  Search,
  Filter,
  ChevronDown,
  CheckCircle2,
  UserPlus,
  ArrowUpRight,
  BarChart3
} from 'lucide-react';
import { api } from '../../api/client';
import type { CreatorPublic } from '../../types/creator';

export function CreatorDiscovery() {
  const navigate = useNavigate();
  const [creators, setCreators] = useState<CreatorPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNiche, setSelectedNiche] = useState<string>('all');
  const [minFollowers, setMinFollowers] = useState<string>('');
  const [maxFollowers, setMaxFollowers] = useState<string>('');

  useEffect(() => {
    loadCreators();
  }, []);

  const loadCreators = async () => {
    try {
      const res = await api.agencies.searchCreators({
        limit: 50,
        niches: selectedNiche !== 'all' ? selectedNiche : undefined,
        min_followers: minFollowers ? parseInt(minFollowers) : undefined,
      });
      setCreators(res);
    } catch (err) {
      console.error('Failed to load creators:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatFollowers = (count: number | undefined) => {
    if (!count) return 'N/A';
    if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M`;
    if (count >= 1000) return `${(count / 1000).toFixed(0)}K`;
    return count.toString();
  };

  // Get unique niches
  const allNiches = [...new Set(creators.flatMap(c => c.niches))];

  // Filter creators
  const filteredCreators = creators.filter(creator => {
    const matchesSearch = searchQuery === '' ||
      creator.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (creator.bio && creator.bio.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesNiche = selectedNiche === 'all' ||
      creator.niches.includes(selectedNiche);

    return matchesSearch && matchesNiche;
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
            <div className="px-2 py-1 border border-blue-500/20 bg-blue-900/10 text-blue-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Creator Discovery
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Find Creators
          </h1>
        </div>
      </div>

      {/* Search & Filters */}
      <div className="space-y-4">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search creators by name or bio..."
              className="w-full pl-12 pr-4 py-3 bg-zinc-900 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
            />
          </div>
          <div className="relative min-w-[180px]">
            <select
              value={selectedNiche}
              onChange={(e) => setSelectedNiche(e.target.value)}
              className="w-full appearance-none px-4 py-3 pr-10 bg-zinc-900 border border-white/10 text-white focus:outline-none focus:border-white/30"
            >
              <option value="all">All Niches</option>
              {allNiches.map(niche => (
                <option key={niche} value={niche}>{niche}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
          </div>
        </div>

        <div className="flex flex-wrap gap-4">
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-widest text-zinc-500">Followers:</span>
            <input
              type="number"
              value={minFollowers}
              onChange={(e) => setMinFollowers(e.target.value)}
              placeholder="Min"
              className="w-24 px-3 py-2 bg-zinc-900 border border-white/10 text-white text-sm placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
            />
            <span className="text-zinc-600">-</span>
            <input
              type="number"
              value={maxFollowers}
              onChange={(e) => setMaxFollowers(e.target.value)}
              placeholder="Max"
              className="w-24 px-3 py-2 bg-zinc-900 border border-white/10 text-white text-sm placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
            />
          </div>
          <button
            onClick={loadCreators}
            className="px-4 py-2 bg-white text-black text-xs font-mono uppercase tracking-widest hover:bg-zinc-200 transition-colors"
          >
            Apply Filters
          </button>
        </div>
      </div>

      {/* Results count */}
      <div className="flex items-center gap-2 text-zinc-500">
        <Filter className="w-4 h-4" />
        <span className="text-xs">{filteredCreators.length} creators found</span>
      </div>

      {/* Creators Grid */}
      {filteredCreators.length === 0 ? (
        <div className="border border-white/10 bg-zinc-900/30 p-12 text-center">
          <Users className="w-12 h-12 mx-auto mb-4 text-zinc-600" />
          <p className="text-zinc-400 mb-2">No creators found</p>
          <p className="text-xs text-zinc-600">
            Try adjusting your search or filters
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredCreators.map((creator) => (
            <div
              key={creator.id}
              className="border border-white/10 bg-zinc-900/30 p-6 hover:border-white/30 hover:bg-zinc-800/50 transition-all group"
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  {creator.profile_image_url ? (
                    <img
                      src={creator.profile_image_url}
                      alt={creator.display_name}
                      className="w-12 h-12 rounded-full object-cover"
                    />
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center text-white font-bold">
                      {creator.display_name.charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-medium text-white">
                        {creator.display_name}
                      </h3>
                      {creator.is_verified && (
                        <CheckCircle2 className="w-4 h-4 text-blue-400" />
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Bio */}
              {creator.bio && (
                <p className="text-sm text-zinc-400 line-clamp-2 mb-4">
                  {creator.bio}
                </p>
              )}

              {/* Niches */}
              <div className="flex flex-wrap gap-2 mb-4">
                {creator.niches.slice(0, 3).map(niche => (
                  <span
                    key={niche}
                    className="px-2 py-1 bg-purple-500/10 text-purple-400 text-[10px] uppercase tracking-widest rounded"
                  >
                    {niche}
                  </span>
                ))}
                {creator.niches.length > 3 && (
                  <span className="text-[10px] text-zinc-600">
                    +{creator.niches.length - 3}
                  </span>
                )}
              </div>

              {/* Metrics */}
              <div className="flex items-center gap-4 pt-4 border-t border-white/5">
                {creator.metrics && typeof creator.metrics === 'object' && (
                  <>
                    {(creator.metrics as any).followers && (
                      <div className="flex items-center gap-1.5">
                        <Users className="w-3 h-3 text-zinc-500" />
                        <span className="text-xs text-zinc-400">
                          {formatFollowers((creator.metrics as any).followers)}
                        </span>
                      </div>
                    )}
                    {(creator.metrics as any).engagement_rate && (
                      <div className="flex items-center gap-1.5">
                        <BarChart3 className="w-3 h-3 text-zinc-500" />
                        <span className="text-xs text-zinc-400">
                          {((creator.metrics as any).engagement_rate * 100).toFixed(1)}%
                        </span>
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 mt-4">
                <button
                  onClick={() => navigate(`/app/agency/creators/${creator.id}`)}
                  className="flex-1 px-4 py-2 border border-white/20 text-xs font-mono uppercase tracking-widest hover:bg-white/5 transition-colors flex items-center justify-center gap-2"
                >
                  View Profile
                  <ArrowUpRight className="w-3 h-3" />
                </button>
                <button
                  className="px-4 py-2 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono uppercase tracking-widest hover:bg-emerald-500/20 transition-colors flex items-center gap-2"
                >
                  <UserPlus className="w-3 h-3" />
                  Invite
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default CreatorDiscovery;
