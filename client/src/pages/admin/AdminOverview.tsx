import { useState, useEffect } from 'react';
import { adminOverview } from '../../api/client';
import type { AdminOverviewCompany, AdminOverviewTotals } from '../../api/client';
import { Building2, Users, UserCheck, UserPlus, Calendar } from 'lucide-react';

export function AdminOverview() {
  const [companies, setCompanies] = useState<AdminOverviewCompany[]>([]);
  const [totals, setTotals] = useState<AdminOverviewTotals | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetch() {
      try {
        setLoading(true);
        const data = await adminOverview.get();
        setCompanies(data.companies);
        setTotals(data.totals);
      } catch (err) {
        console.error('Failed to fetch overview:', err);
        setError('Failed to load overview data');
      } finally {
        setLoading(false);
      }
    }
    fetch();
  }, []);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'approved':
        return (
          <span className="inline-flex items-center px-2.5 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] uppercase tracking-wider font-bold">
            Approved
          </span>
        );
      case 'pending':
        return (
          <span className="inline-flex items-center px-2.5 py-1 bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] uppercase tracking-wider font-bold">
            Pending
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center px-2.5 py-1 bg-red-500/10 text-red-400 border border-red-500/20 text-[10px] uppercase tracking-wider font-bold">
            Rejected
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-1 bg-zinc-500/10 text-zinc-400 border border-zinc-500/20 text-[10px] uppercase tracking-wider font-bold">
            {status}
          </span>
        );
    }
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto flex items-center justify-center py-24">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading overview...</div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="border-b border-white/10 pb-8">
        <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Platform Overview</h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
          Businesses and employee stats across the platform
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Stat Cards */}
      {totals && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-zinc-900/50 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-8 h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center">
                <Building2 size={16} className="text-zinc-400" />
              </div>
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Businesses</span>
            </div>
            <div className="text-3xl font-bold text-white tracking-tight">{totals.total_companies}</div>
          </div>

          <div className="bg-zinc-900/50 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-8 h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center">
                <Users size={16} className="text-zinc-400" />
              </div>
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Total Employees</span>
            </div>
            <div className="text-3xl font-bold text-white tracking-tight">{totals.total_employees}</div>
          </div>

          <div className="bg-zinc-900/50 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-8 h-8 bg-emerald-900/30 border border-emerald-500/20 flex items-center justify-center">
                <UserCheck size={16} className="text-emerald-400" />
              </div>
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Active</span>
            </div>
            <div className="text-3xl font-bold text-emerald-400 tracking-tight">{totals.active_employees}</div>
          </div>

          <div className="bg-zinc-900/50 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-8 h-8 bg-amber-900/30 border border-amber-500/20 flex items-center justify-center">
                <UserPlus size={16} className="text-amber-400" />
              </div>
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Pending Invites</span>
            </div>
            <div className="text-3xl font-bold text-amber-400 tracking-tight">{totals.pending_employees}</div>
          </div>
        </div>
      )}

      {/* Companies Table */}
      <div className="border border-white/10 bg-zinc-900/30">
        {companies.length === 0 ? (
          <div className="text-center py-24 text-zinc-500 font-mono text-sm uppercase tracking-wider">
            No businesses found
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10 bg-zinc-950">
                  <th className="text-left px-6 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                    Company
                  </th>
                  <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                    Status
                  </th>
                  <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                    Total
                  </th>
                  <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                    Active
                  </th>
                  <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                    Pending
                  </th>
                  <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                    Terminated
                  </th>
                  <th className="text-left px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                    Joined
                  </th>
                </tr>
              </thead>
              <tbody>
                {companies.map((company) => (
                  <tr
                    key={company.id}
                    className="border-b border-white/5 hover:bg-white/5 transition-colors bg-zinc-950"
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 bg-zinc-800 border border-zinc-700 flex items-center justify-center">
                          <Building2 size={18} className="text-zinc-400" />
                        </div>
                        <div>
                          <div className="text-sm text-white font-bold">{company.name}</div>
                          <div className="flex items-center gap-3 mt-1">
                            {company.industry && (
                              <span className="text-[10px] text-zinc-500 font-mono">
                                {company.industry}
                              </span>
                            )}
                            {company.size && (
                              <span className="text-[10px] text-zinc-600 font-mono">
                                {company.size}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </td>

                    <td className="px-4 py-4 text-center">
                      {getStatusBadge(company.status)}
                    </td>

                    <td className="px-4 py-4 text-center">
                      <span className="text-sm text-white font-mono">{company.total_employees}</span>
                    </td>

                    <td className="px-4 py-4 text-center">
                      <span className="text-sm text-emerald-400 font-mono">{company.active_employees}</span>
                    </td>

                    <td className="px-4 py-4 text-center">
                      <span className="text-sm text-amber-400 font-mono">{company.pending_employees}</span>
                    </td>

                    <td className="px-4 py-4 text-center">
                      <span className={`text-sm font-mono ${company.terminated_employees > 0 ? 'text-red-400' : 'text-zinc-600'}`}>
                        {company.terminated_employees}
                      </span>
                    </td>

                    <td className="px-4 py-4">
                      <div className="flex items-center gap-1 text-xs text-zinc-400 font-mono">
                        <Calendar size={12} />
                        {formatDate(company.created_at)}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default AdminOverview;
