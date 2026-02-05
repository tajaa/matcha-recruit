import { useEffect, useState } from 'react';
import { Search, CheckCircle, XCircle, Eye, MoreHorizontal, User } from 'lucide-react';
import { api } from '../../api/client';
import type { GumFitCreator } from '../../api/client';

export function GumFitCreators() {
  const [creators, setCreators] = useState<GumFitCreator[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'verified' | 'unverified'>('all');

  useEffect(() => {
    loadCreators();
  }, [search, filter]);

  const loadCreators = async () => {
    try {
      const verified = filter === 'verified' ? true : filter === 'unverified' ? false : undefined;
      const res = await api.gumfit.listCreators({ search: search || undefined, verified });
      setCreators(res.creators);
    } catch (err) {
      console.error('Failed to load creators:', err);
    } finally {
      setLoading(false);
    }
  };

  // Filtering is now done on the server side
  const filteredCreators = creators;

  const formatNumber = (num: number): string => {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
  };

  const toggleVerified = async (creatorId: string, currentStatus: boolean) => {
    try {
      await api.gumfit.toggleCreatorVerification(creatorId, !currentStatus);
      setCreators(
        creators.map((c) =>
          c.id === creatorId ? { ...c, is_verified: !currentStatus } : c
        )
      );
    } catch (err) {
      console.error('Failed to toggle verification:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Header */}
      <div>
        <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">
          GumFit Admin
        </div>
        <h1 className="text-2xl font-bold text-white">Creators</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Manage and verify creators on the platform
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            placeholder="Search creators..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-zinc-900 border border-white/10 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-white/30"
          />
        </div>
        <div className="flex gap-2">
          {(['all', 'verified', 'unverified'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 text-xs uppercase tracking-widest transition-colors ${
                filter === f
                  ? 'bg-white text-black'
                  : 'bg-zinc-900 text-zinc-400 hover:text-white border border-white/10'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Creators Table */}
      <div className="border border-white/10 bg-zinc-900/30">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Creator
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Niches
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Followers
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Status
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Joined
                </th>
                <th className="text-right px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredCreators.map((creator) => (
                <tr key={creator.id} className="hover:bg-white/5 transition-colors">
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-3">
                      {creator.profile_image_url ? (
                        <img
                          src={creator.profile_image_url}
                          alt={creator.display_name}
                          className="w-10 h-10 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-zinc-800 flex items-center justify-center">
                          <User className="w-5 h-5 text-zinc-600" />
                        </div>
                      )}
                      <div>
                        <div className="text-sm font-medium text-white">
                          {creator.display_name}
                        </div>
                        <div className="text-xs text-zinc-500">{creator.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex flex-wrap gap-1">
                      {creator.niches.slice(0, 2).map((niche) => (
                        <span
                          key={niche}
                          className="px-2 py-0.5 bg-white/5 text-zinc-400 text-xs"
                        >
                          {niche}
                        </span>
                      ))}
                      {creator.niches.length > 2 && (
                        <span className="px-2 py-0.5 text-zinc-500 text-xs">
                          +{creator.niches.length - 2}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="text-sm text-white">
                      {formatNumber(creator.total_followers)}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    {creator.is_verified ? (
                      <span className="flex items-center gap-1 text-emerald-400 text-xs">
                        <CheckCircle className="w-3 h-3" />
                        Verified
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-zinc-500 text-xs">
                        <XCircle className="w-3 h-3" />
                        Unverified
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-4">
                    <div className="text-sm text-zinc-400">
                      {new Date(creator.created_at).toLocaleDateString()}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => toggleVerified(creator.id, creator.is_verified)}
                        className={`p-2 transition-colors ${
                          creator.is_verified
                            ? 'text-amber-400 hover:text-amber-300'
                            : 'text-emerald-400 hover:text-emerald-300'
                        }`}
                        title={creator.is_verified ? 'Unverify' : 'Verify'}
                      >
                        {creator.is_verified ? (
                          <XCircle className="w-4 h-4" />
                        ) : (
                          <CheckCircle className="w-4 h-4" />
                        )}
                      </button>
                      <button
                        className="p-2 text-zinc-400 hover:text-white transition-colors"
                        title="View Profile"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                      <button
                        className="p-2 text-zinc-400 hover:text-white transition-colors"
                        title="More Actions"
                      >
                        <MoreHorizontal className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {filteredCreators.length === 0 && (
          <div className="text-center py-12">
            <p className="text-zinc-500 text-sm">No creators found</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default GumFitCreators;
