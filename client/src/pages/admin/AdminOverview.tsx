import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminOverview, adminTestAccounts } from '../../api/client';
import type { AdminOverviewCompany, AdminOverviewTotals } from '../../api/client';
import type { TestAccountProvisionResponse } from '../../types';
import { Building2, Users, UserCheck, UserPlus, Calendar, KeyRound } from 'lucide-react';

const COMPANY_SIZE_OPTIONS = [
  { value: '1-10', label: '1-10 employees' },
  { value: '11-50', label: '11-50 employees' },
  { value: '51-200', label: '51-200 employees' },
  { value: '201-500', label: '201-500 employees' },
  { value: '500+', label: '500+ employees' },
];

export function AdminOverview() {
  const navigate = useNavigate();
  const [companies, setCompanies] = useState<AdminOverviewCompany[]>([]);
  const [totals, setTotals] = useState<AdminOverviewTotals | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testAccountError, setTestAccountError] = useState<string | null>(null);
  const [creatingTestAccount, setCreatingTestAccount] = useState(false);
  const [createdTestAccount, setCreatedTestAccount] = useState<TestAccountProvisionResponse | null>(null);
  const [testAccountForm, setTestAccountForm] = useState({
    name: '',
    email: '',
    password: '',
    company_name: '',
    industry: '',
    company_size: '',
  });

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

  const handleCreateTestAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setTestAccountError(null);
    setCreatedTestAccount(null);

    if (!testAccountForm.name.trim()) {
      setTestAccountError('Owner name is required');
      return;
    }
    if (!testAccountForm.email.trim()) {
      setTestAccountError('Email is required');
      return;
    }
    if (testAccountForm.password && testAccountForm.password.length < 8) {
      setTestAccountError('Password must be at least 8 characters');
      return;
    }

    try {
      setCreatingTestAccount(true);
      const created = await adminTestAccounts.create({
        name: testAccountForm.name.trim(),
        email: testAccountForm.email.trim(),
        password: testAccountForm.password.trim() || undefined,
        company_name: testAccountForm.company_name.trim() || undefined,
        industry: testAccountForm.industry.trim() || undefined,
        company_size: testAccountForm.company_size || undefined,
      });
      setCreatedTestAccount(created);
      setTestAccountForm({
        name: '',
        email: '',
        password: '',
        company_name: '',
        industry: '',
        company_size: '',
      });
    } catch (err) {
      setTestAccountError(err instanceof Error ? err.message : 'Failed to create test account');
    } finally {
      setCreatingTestAccount(false);
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
      <div className="border-b border-white/10 pb-6 md:pb-8">
        <h1 className="text-2xl md:text-4xl font-bold tracking-tighter text-white uppercase">Platform Overview</h1>
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

      <div className="border border-white/10 bg-zinc-900/30 p-4 md:p-6">
        <div className="flex items-start gap-3 mb-6">
          <div className="w-8 h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0">
            <KeyRound size={15} className="text-zinc-300" />
          </div>
          <div className="min-w-0">
            <h2 className="text-sm font-bold text-white uppercase tracking-wider">Provision Test Account</h2>
            <p className="text-[11px] text-zinc-500 font-mono uppercase tracking-wide mt-1 leading-relaxed">
              Admin-only account with all features enabled and seeded demo data
            </p>
          </div>
        </div>

        <form className="space-y-4" onSubmit={handleCreateTestAccount}>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold ml-1">Owner Name</label>
              <input
                type="text"
                placeholder="Owner name"
                value={testAccountForm.name}
                onChange={(e) => setTestAccountForm(prev => ({ ...prev, name: e.target.value }))}
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm focus:border-zinc-600 outline-none transition-colors"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold ml-1">Email</label>
              <input
                type="email"
                placeholder="Owner email"
                value={testAccountForm.email}
                onChange={(e) => setTestAccountForm(prev => ({ ...prev, email: e.target.value }))}
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm focus:border-zinc-600 outline-none transition-colors"
              />
            </div>
            <div className="space-y-1 sm:col-span-2 lg:col-span-1">
              <label className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold ml-1">Password (Optional)</label>
              <input
                type="text"
                placeholder="Auto-generate if blank"
                value={testAccountForm.password}
                onChange={(e) => setTestAccountForm(prev => ({ ...prev, password: e.target.value }))}
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm focus:border-zinc-600 outline-none transition-colors"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold ml-1">Company Name</label>
              <input
                type="text"
                placeholder="Company name"
                value={testAccountForm.company_name}
                onChange={(e) => setTestAccountForm(prev => ({ ...prev, company_name: e.target.value }))}
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm focus:border-zinc-600 outline-none transition-colors"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold ml-1">Industry</label>
              <input
                type="text"
                placeholder="Industry"
                value={testAccountForm.industry}
                onChange={(e) => setTestAccountForm(prev => ({ ...prev, industry: e.target.value }))}
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm focus:border-zinc-600 outline-none transition-colors"
              />
            </div>
            <div className="space-y-1 sm:col-span-2 lg:col-span-1">
              <label className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold ml-1">Company Size</label>
              <select
                value={testAccountForm.company_size}
                onChange={(e) => setTestAccountForm(prev => ({ ...prev, company_size: e.target.value }))}
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm focus:border-zinc-600 outline-none transition-colors appearance-none"
              >
                <option value="">Select size</option>
                {COMPANY_SIZE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {testAccountError && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-mono uppercase tracking-wider">
              Error: {testAccountError}
            </div>
          )}

          {createdTestAccount && (
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 space-y-2 font-mono break-all">
              <div className="flex justify-between">
                <span className="text-emerald-500 uppercase tracking-widest font-bold">Success</span>
                <span className="text-emerald-600">Provisioned</span>
              </div>
              <div className="pt-2 border-t border-emerald-500/10">
                <div>Company: {createdTestAccount.company_name}</div>
                <div>Email: {createdTestAccount.email}</div>
                <div>Password: {createdTestAccount.password}</div>
              </div>
            </div>
          )}

          <div className="pt-2">
            <button
              type="submit"
              disabled={creatingTestAccount}
              className="w-full sm:w-auto px-8 py-3 bg-white text-black border border-white text-[10px] uppercase tracking-widest font-bold disabled:opacity-50 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors"
            >
              {creatingTestAccount ? 'Provisioning...' : 'Provision Test Account'}
            </button>
          </div>
        </form>
      </div>

      {/* Stat Cards */}
      {totals && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          <div className="bg-zinc-900/50 border border-white/10 p-4 md:p-6">
            <div className="flex items-center gap-2 md:gap-3 mb-3 md:mb-4">
              <div className="w-7 h-7 md:w-8 md:h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center">
                <Building2 size={14} className="text-zinc-400 md:hidden" />
                <Building2 size={16} className="text-zinc-400 hidden md:block" />
              </div>
              <span className="text-[9px] md:text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Businesses</span>
            </div>
            <div className="text-2xl md:text-3xl font-bold text-white tracking-tight">{totals.total_companies}</div>
          </div>

          <div className="bg-zinc-900/50 border border-white/10 p-4 md:p-6">
            <div className="flex items-center gap-2 md:gap-3 mb-3 md:mb-4">
              <div className="w-7 h-7 md:w-8 md:h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center">
                <Users size={14} className="text-zinc-400 md:hidden" />
                <Users size={16} className="text-zinc-400 hidden md:block" />
              </div>
              <span className="text-[9px] md:text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Employees</span>
            </div>
            <div className="text-2xl md:text-3xl font-bold text-white tracking-tight">{totals.total_employees}</div>
          </div>

          <div className="bg-zinc-900/50 border border-white/10 p-4 md:p-6">
            <div className="flex items-center gap-2 md:gap-3 mb-3 md:mb-4">
              <div className="w-7 h-7 md:w-8 md:h-8 bg-emerald-900/30 border border-emerald-500/20 flex items-center justify-center">
                <UserCheck size={14} className="text-emerald-400 md:hidden" />
                <UserCheck size={16} className="text-emerald-400 hidden md:block" />
              </div>
              <span className="text-[9px] md:text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Active</span>
            </div>
            <div className="text-2xl md:text-3xl font-bold text-emerald-400 tracking-tight">{totals.active_employees}</div>
          </div>

          <div className="bg-zinc-900/50 border border-white/10 p-4 md:p-6">
            <div className="flex items-center gap-2 md:gap-3 mb-3 md:mb-4">
              <div className="w-7 h-7 md:w-8 md:h-8 bg-amber-900/30 border border-amber-500/20 flex items-center justify-center">
                <UserPlus size={14} className="text-amber-400 md:hidden" />
                <UserPlus size={16} className="text-amber-400 hidden md:block" />
              </div>
              <span className="text-[9px] md:text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Pending</span>
            </div>
            <div className="text-2xl md:text-3xl font-bold text-amber-400 tracking-tight">{totals.pending_employees}</div>
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
          <>
            {/* Desktop table */}
            <div className="hidden md:block overflow-x-auto">
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
                      onClick={() => navigate(`/app/companies/${company.id}`)}
                      className="border-b border-white/5 hover:bg-white/5 transition-colors bg-zinc-950 cursor-pointer"
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

            {/* Mobile card layout */}
            <div className="md:hidden divide-y divide-white/5">
              {companies.map((company) => (
                <div
                  key={company.id}
                  onClick={() => navigate(`/app/companies/${company.id}`)}
                  className="p-4 hover:bg-white/5 transition-colors cursor-pointer active:bg-white/10"
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0">
                        <Building2 size={14} className="text-zinc-400" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm text-white font-bold truncate">{company.name}</div>
                        <div className="flex items-center gap-2 mt-0.5">
                          {company.industry && (
                            <span className="text-[10px] text-zinc-500 font-mono">{company.industry}</span>
                          )}
                          {company.size && (
                            <span className="text-[10px] text-zinc-600 font-mono">{company.size}</span>
                          )}
                        </div>
                      </div>
                    </div>
                    {getStatusBadge(company.status)}
                  </div>
                  <div className="grid grid-cols-4 gap-2">
                    <div>
                      <div className="text-[9px] text-zinc-600 uppercase tracking-wider font-mono">Total</div>
                      <div className="text-sm text-white font-mono">{company.total_employees}</div>
                    </div>
                    <div>
                      <div className="text-[9px] text-zinc-600 uppercase tracking-wider font-mono">Active</div>
                      <div className="text-sm text-emerald-400 font-mono">{company.active_employees}</div>
                    </div>
                    <div>
                      <div className="text-[9px] text-zinc-600 uppercase tracking-wider font-mono">Pending</div>
                      <div className="text-sm text-amber-400 font-mono">{company.pending_employees}</div>
                    </div>
                    <div>
                      <div className="text-[9px] text-zinc-600 uppercase tracking-wider font-mono">Joined</div>
                      <div className="text-[11px] text-zinc-400 font-mono">{formatDate(company.created_at)}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default AdminOverview;
