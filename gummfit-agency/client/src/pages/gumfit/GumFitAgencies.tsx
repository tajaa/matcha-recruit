import { useEffect, useState } from 'react';
import { Search, CheckCircle, XCircle, Eye, MoreHorizontal, Building2 } from 'lucide-react';
import { api } from '../../api/client';
import type { GumFitAgency } from '../../api/client';

export function GumFitAgencies() {
  const [agencies, setAgencies] = useState<GumFitAgency[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'verified' | 'unverified'>('all');

  useEffect(() => {
    loadAgencies();
  }, [search, filter]);

  const loadAgencies = async () => {
    try {
      const verified = filter === 'verified' ? true : filter === 'unverified' ? false : undefined;
      const res = await api.gumfit.listAgencies({ search: search || undefined, verified });
      setAgencies(res.agencies);
    } catch (err) {
      console.error('Failed to load agencies:', err);
    } finally {
      setLoading(false);
    }
  };

  // Filtering is now done on the server side
  const filteredAgencies = agencies;

  const toggleVerified = async (agencyId: string, currentStatus: boolean) => {
    try {
      await api.gumfit.toggleAgencyVerification(agencyId, !currentStatus);
      setAgencies(
        agencies.map((a) =>
          a.id === agencyId ? { ...a, is_verified: !currentStatus } : a
        )
      );
    } catch (err) {
      console.error('Failed to toggle verification:', err);
    }
  };

  const getAgencyTypeLabel = (type: string) => {
    switch (type) {
      case 'brand':
        return { label: 'Brand', color: 'text-blue-400 bg-blue-500/10' };
      case 'talent':
        return { label: 'Talent', color: 'text-purple-400 bg-purple-500/10' };
      case 'hybrid':
        return { label: 'Hybrid', color: 'text-cyan-400 bg-cyan-500/10' };
      default:
        return { label: type, color: 'text-zinc-400 bg-zinc-500/10' };
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
        <h1 className="text-2xl font-bold text-white">Agencies</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Manage and verify agencies on the platform
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            placeholder="Search agencies..."
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

      {/* Agencies Table */}
      <div className="border border-white/10 bg-zinc-900/30">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Agency
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Type
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Industries
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Members
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
              {filteredAgencies.map((agency) => {
                const typeInfo = getAgencyTypeLabel(agency.agency_type);
                return (
                  <tr key={agency.id} className="hover:bg-white/5 transition-colors">
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-3">
                        {agency.logo_url ? (
                          <img
                            src={agency.logo_url}
                            alt={agency.agency_name}
                            className="w-10 h-10 rounded object-cover"
                          />
                        ) : (
                          <div className="w-10 h-10 rounded bg-zinc-800 flex items-center justify-center">
                            <Building2 className="w-5 h-5 text-zinc-600" />
                          </div>
                        )}
                        <div>
                          <div className="text-sm font-medium text-white">
                            {agency.agency_name}
                          </div>
                          <div className="text-xs text-zinc-500">{agency.email}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      <span
                        className={`px-2 py-1 text-xs uppercase tracking-widest ${typeInfo.color}`}
                      >
                        {typeInfo.label}
                      </span>
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex flex-wrap gap-1">
                        {agency.industries.slice(0, 2).map((industry) => (
                          <span
                            key={industry}
                            className="px-2 py-0.5 bg-white/5 text-zinc-400 text-xs"
                          >
                            {industry}
                          </span>
                        ))}
                        {agency.industries.length > 2 && (
                          <span className="px-2 py-0.5 text-zinc-500 text-xs">
                            +{agency.industries.length - 2}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      <div className="text-sm text-white">{agency.member_count}</div>
                    </td>
                    <td className="px-4 py-4">
                      {agency.is_verified ? (
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
                        {new Date(agency.created_at).toLocaleDateString()}
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => toggleVerified(agency.id, agency.is_verified)}
                          className={`p-2 transition-colors ${
                            agency.is_verified
                              ? 'text-amber-400 hover:text-amber-300'
                              : 'text-emerald-400 hover:text-emerald-300'
                          }`}
                          title={agency.is_verified ? 'Unverify' : 'Verify'}
                        >
                          {agency.is_verified ? (
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
                );
              })}
            </tbody>
          </table>
        </div>

        {filteredAgencies.length === 0 && (
          <div className="text-center py-12">
            <p className="text-zinc-500 text-sm">No agencies found</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default GumFitAgencies;
