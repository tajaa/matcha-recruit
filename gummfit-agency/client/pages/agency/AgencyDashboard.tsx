import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Briefcase,
  Users,
  FileCheck,
  DollarSign,
  ArrowUpRight,
  Activity,
  Plus,
  Clock,
  CheckCircle2
} from 'lucide-react';
import { api } from '../../api/client';
import type { BrandDeal, DealApplication, DealContract } from '../../types/deals';
import type { AgencyWithMembership } from '../../types/agency';

export function AgencyDashboard() {
  const navigate = useNavigate();
  const [agency, setAgency] = useState<AgencyWithMembership | null>(null);
  const [deals, setDeals] = useState<BrandDeal[]>([]);
  const [recentApplications, setRecentApplications] = useState<DealApplication[]>([]);
  const [contracts, setContracts] = useState<DealContract[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      const [agencyRes, dealsRes] = await Promise.all([
        api.agencies.getMyAgency(),
        api.deals.listAgencyDeals(),
      ]);

      setAgency(agencyRes);

      // Get applications and contracts for first deal if available
      if (dealsRes.length > 0) {
        const appsPromises = dealsRes.slice(0, 3).map((d: BrandDeal) =>
          api.deals.listDealApplications(d.id)
        );
        const appsResults = await Promise.all(appsPromises);
        const allApps = appsResults.flat().slice(0, 5);
        setRecentApplications(allApps);
      }

      // Load contracts
      const contractsRes = await api.deals.listAgencyContracts();
      setContracts(contractsRes);

      setDeals(dealsRes);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  const activeDeals = deals.filter(d => d.status === 'open').length;
  const pendingApps = recentApplications.filter(a => a.status === 'pending').length;
  const activeContracts = contracts.filter(c => c.status === 'active').length;
  const totalContractValue = contracts
    .filter(c => ['active', 'completed'].includes(c.status))
    .reduce((sum, c) => sum + c.agreed_rate, 0);

  const stats = [
    { label: 'Active Deals', value: activeDeals.toString(), icon: Briefcase, color: 'text-emerald-500' },
    { label: 'Pending Applications', value: pendingApps.toString(), icon: Clock, color: 'text-amber-500' },
    { label: 'Active Contracts', value: activeContracts.toString(), icon: FileCheck, color: 'text-blue-500' },
    { label: 'Contract Value', value: formatCurrency(totalContractValue), icon: DollarSign, color: 'text-white' },
  ];

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="px-2 py-1 border border-purple-500/20 bg-purple-900/10 text-purple-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Agency Dashboard
            </div>
            {agency?.agency.is_verified && (
              <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                Verified
              </div>
            )}
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            {agency?.agency.name || 'Agency Hub'}
          </h1>
        </div>
        <div className="flex gap-4">
          <button
            onClick={() => navigate('/app/gumfit/agency/creators')}
            className="px-6 py-3 border border-white/20 hover:bg-white hover:text-black text-xs font-mono uppercase tracking-widest transition-all"
          >
            Find Creators
          </button>
          <button
            onClick={() => navigate('/app/gumfit/agency/deals/new')}
            className="px-6 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest transition-all font-bold flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            New Deal
          </button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-px bg-white/10 border border-white/10">
        {stats.map((stat) => (
          <div key={stat.label} className="bg-zinc-950 p-8 hover:bg-zinc-900/50 transition-colors group relative overflow-hidden">
            <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:opacity-20 group-hover:scale-110 transition-all duration-500">
              <stat.icon className="w-24 h-24 text-white" strokeWidth={0.5} />
            </div>

            <div className="relative z-10">
              <div className="flex items-center gap-3 mb-6">
                <div className={`p-2 rounded bg-white/5 ${stat.color}`}>
                  <stat.icon className="w-4 h-4" />
                </div>
                <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">{stat.label}</span>
              </div>

              <div className="text-4xl font-light text-white mb-2 tabular-nums tracking-tight">{stat.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Dashboard Widgets */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

        {/* Active Deals */}
        <div className="lg:col-span-2 border border-white/10 bg-zinc-900/30">
          <div className="p-6 border-b border-white/10 flex justify-between items-center">
            <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Active Deals</h2>
            <Briefcase className="w-4 h-4 text-zinc-500" />
          </div>
          <div className="divide-y divide-white/5">
            {deals.length === 0 ? (
              <div className="p-8 text-center text-zinc-500">
                <Briefcase className="w-8 h-8 mx-auto mb-3 opacity-50" />
                <p className="text-sm">No deals yet</p>
                <button
                  onClick={() => navigate('/app/gumfit/agency/deals/new')}
                  className="mt-4 text-xs text-emerald-400 hover:text-emerald-300"
                >
                  Create your first deal →
                </button>
              </div>
            ) : (
              deals.slice(0, 5).map((deal) => (
                <div
                  key={deal.id}
                  onClick={() => navigate(`/app/gumfit/agency/deals/${deal.id}`)}
                  className="p-4 flex items-center justify-between hover:bg-white/5 transition-colors group cursor-pointer"
                >
                  <div className="flex items-center gap-4">
                    <div className={`w-2 h-2 rounded-full ${
                      deal.status === 'open' ? 'bg-emerald-500' :
                      deal.status === 'closed' ? 'bg-zinc-500' :
                      deal.status === 'filled' ? 'bg-blue-500' :
                      'bg-amber-500'
                    }`} />
                    <div>
                      <span className="text-sm text-zinc-300 group-hover:text-white transition-colors">
                        {deal.title}
                      </span>
                      <div className="flex items-center gap-2 text-[10px] text-zinc-500 mt-0.5">
                        <span>{deal.brand_name}</span>
                        <span>•</span>
                        <span>{deal.applications_count} applications</span>
                      </div>
                    </div>
                  </div>
                  <ArrowUpRight className="w-4 h-4 text-zinc-600 group-hover:text-white transition-colors" />
                </div>
              ))
            )}
          </div>
          {deals.length > 0 && (
            <div className="p-4 border-t border-white/10 bg-white/5">
              <button
                onClick={() => navigate('/app/gumfit/agency/deals')}
                className="w-full text-center text-[10px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white transition-colors"
              >
                View All Deals
              </button>
            </div>
          )}
        </div>

        {/* Recent Applications */}
        <div className="border border-white/10 bg-zinc-900/30">
          <div className="p-6 border-b border-white/10 flex justify-between items-center">
            <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">New Applications</h2>
            <Users className="w-4 h-4 text-zinc-500" />
          </div>
          <div className="divide-y divide-white/5">
            {recentApplications.length === 0 ? (
              <div className="p-8 text-center text-zinc-500">
                <Users className="w-8 h-8 mx-auto mb-3 opacity-50" />
                <p className="text-sm">No applications yet</p>
              </div>
            ) : (
              recentApplications.map((app) => (
                <div
                  key={app.id}
                  onClick={() => navigate(`/app/gumfit/agency/applications/${app.id}`)}
                  className="p-4 hover:bg-white/5 transition-colors cursor-pointer group"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-zinc-300 group-hover:text-white">
                      {app.creator_name || 'Creator'}
                    </span>
                    <span className={`text-[10px] uppercase ${
                      app.status === 'pending' ? 'text-amber-400' :
                      app.status === 'shortlisted' ? 'text-purple-400' :
                      'text-zinc-500'
                    }`}>
                      {app.status}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-500 line-clamp-2">{app.pitch}</p>
                </div>
              ))
            )}
          </div>
          {recentApplications.length > 0 && (
            <div className="p-4 border-t border-white/10 bg-white/5">
              <button
                onClick={() => navigate('/app/gumfit/agency/applications')}
                className="w-full text-center text-[10px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white transition-colors"
              >
                Review All
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Recent Activity */}
      <div className="border border-white/10 bg-zinc-900/30">
        <div className="p-6 border-b border-white/10 flex justify-between items-center">
          <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Active Contracts</h2>
          <Activity className="w-4 h-4 text-zinc-500" />
        </div>
        <div className="divide-y divide-white/5">
          {contracts.length === 0 ? (
            <div className="p-8 text-center text-zinc-500">
              <FileCheck className="w-8 h-8 mx-auto mb-3 opacity-50" />
              <p className="text-sm">No active contracts</p>
            </div>
          ) : (
            contracts.map((contract) => (
              <div
                key={contract.id}
                onClick={() => navigate(`/app/gumfit/agency/contracts/${contract.id}`)}
                className="p-4 flex items-center justify-between hover:bg-white/5 transition-colors group cursor-pointer"
              >
                <div className="flex items-center gap-4">
                  <div className={`w-2 h-2 rounded-full ${
                    contract.status === 'active' ? 'bg-emerald-500' :
                    contract.status === 'completed' ? 'bg-blue-500' :
                    'bg-zinc-500'
                  }`} />
                  <div>
                    <span className="text-sm text-zinc-300 group-hover:text-white">
                      {contract.creator_name} - {contract.deal_title}
                    </span>
                    <div className="text-[10px] text-zinc-500 mt-0.5">
                      {formatCurrency(contract.agreed_rate)} • {formatCurrency(contract.total_paid)} paid
                    </div>
                  </div>
                </div>
                <ArrowUpRight className="w-4 h-4 text-zinc-600 group-hover:text-white transition-colors" />
              </div>
            ))
          )}
        </div>
        {contracts.length > 0 && (
          <div className="p-4 border-t border-white/10 bg-white/5">
            <button
              onClick={() => navigate('/app/gumfit/agency/contracts')}
              className="w-full text-center text-[10px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white transition-colors"
            >
              Manage Contracts
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default AgencyDashboard;
