import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  DollarSign,
  TrendingUp,
  Briefcase,
  Link2,
  ArrowUpRight,
  Activity,
  Wallet,
  Receipt
} from 'lucide-react';
import { api } from '../../api/client';
import type { RevenueOverview, PlatformConnection } from '../../types/creator';
import type { DealApplication } from '../../types/deals';

export function CreatorDashboard() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<RevenueOverview | null>(null);
  const [applications, setApplications] = useState<DealApplication[]>([]);
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      const [overviewRes, appsRes, connectionsRes] = await Promise.all([
        api.creators.getDashboard(),
        api.deals.listMyApplications(),
        api.creators.listPlatformConnections(),
      ]);
      setOverview(overviewRes);
      setApplications(appsRes);
      setConnections(connectionsRes);
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

  const getChangePercent = (current: number, previous: number) => {
    if (previous === 0) return current > 0 ? '+100%' : '0%';
    const change = ((current - previous) / previous) * 100;
    return change >= 0 ? `+${change.toFixed(0)}%` : `${change.toFixed(0)}%`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  const stats = overview ? [
    {
      label: 'Monthly Revenue',
      value: formatCurrency(overview.current_month.total_revenue),
      change: getChangePercent(overview.current_month.total_revenue, overview.previous_month.total_revenue),
      icon: DollarSign,
      color: 'text-emerald-500'
    },
    {
      label: 'Monthly Expenses',
      value: formatCurrency(overview.current_month.total_expenses),
      change: getChangePercent(overview.current_month.total_expenses, overview.previous_month.total_expenses),
      icon: Receipt,
      color: 'text-amber-500'
    },
    {
      label: 'Net Income',
      value: formatCurrency(overview.current_month.net_income),
      change: getChangePercent(overview.current_month.net_income, overview.previous_month.net_income),
      icon: TrendingUp,
      color: overview.current_month.net_income >= 0 ? 'text-emerald-500' : 'text-red-500'
    },
    {
      label: 'YTD Revenue',
      value: formatCurrency(overview.year_to_date.total_revenue),
      change: 'Year to date',
      icon: Wallet,
      color: 'text-white'
    },
  ] : [];

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Creator Dashboard
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Revenue Hub
          </h1>
        </div>
        <div className="flex gap-4">
          <button
            onClick={() => navigate('/app/creator/revenue')}
            className="px-6 py-3 border border-white/20 hover:bg-white hover:text-black text-xs font-mono uppercase tracking-widest transition-all"
          >
            View Revenue
          </button>
          <button
            onClick={() => navigate('/app/creator/deals')}
            className="px-6 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest transition-all font-bold"
          >
            Browse Deals
          </button>
        </div>
      </div>

      {/* Stats Grid */}
      {overview && (
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
                <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-400 uppercase">
                  <span className="w-1 h-1 bg-zinc-600 rounded-full" />
                  {stat.change}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Dashboard Widgets */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

        {/* Recent Applications */}
        <div className="lg:col-span-2 border border-white/10 bg-zinc-900/30">
          <div className="p-6 border-b border-white/10 flex justify-between items-center">
            <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Recent Applications</h2>
            <Briefcase className="w-4 h-4 text-zinc-500" />
          </div>
          <div className="divide-y divide-white/5">
            {applications.length === 0 ? (
              <div className="p-8 text-center text-zinc-500">
                <Briefcase className="w-8 h-8 mx-auto mb-3 opacity-50" />
                <p className="text-sm">No applications yet</p>
                <button
                  onClick={() => navigate('/app/creator/deals')}
                  className="mt-4 text-xs text-emerald-400 hover:text-emerald-300"
                >
                  Browse available deals →
                </button>
              </div>
            ) : (
              applications.map((app) => (
                <div
                  key={app.id}
                  className="p-4 flex items-center justify-between hover:bg-white/5 transition-colors group cursor-pointer"
                  onClick={() => navigate(`/app/creator/applications/${app.id}`)}
                >
                  <div className="flex items-center gap-4">
                    <div className={`w-2 h-2 rounded-full ${
                      app.status === 'accepted' ? 'bg-emerald-500' :
                      app.status === 'rejected' ? 'bg-red-500' :
                      app.status === 'pending' ? 'bg-amber-500 animate-pulse' :
                      'bg-zinc-600'
                    }`} />
                    <div>
                      <span className="text-sm text-zinc-300 group-hover:text-white transition-colors">
                        {app.deal_title}
                      </span>
                      <div className="text-[10px] text-zinc-500 mt-0.5 capitalize">{app.status}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {app.proposed_rate && (
                      <span className="text-xs font-mono text-zinc-400">
                        {formatCurrency(app.proposed_rate)}
                      </span>
                    )}
                    <ArrowUpRight className="w-4 h-4 text-zinc-600 group-hover:text-white transition-colors" />
                  </div>
                </div>
              ))
            )}
          </div>
          {applications.length > 0 && (
            <div className="p-4 border-t border-white/10 bg-white/5">
              <button
                onClick={() => navigate('/app/creator/applications')}
                className="w-full text-center text-[10px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white transition-colors"
              >
                View All Applications
              </button>
            </div>
          )}
        </div>

        {/* Platform Connections & Quick Actions */}
        <div className="space-y-8">
          {/* Platform Connections Widget */}
          <div className="border border-white/10 bg-zinc-900/30 p-6 relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/10 rounded-full blur-[50px] pointer-events-none" />

            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Connected Platforms</h2>
              <Link2 className="w-4 h-4 text-blue-500" />
            </div>

            <div className="space-y-3">
              {connections.length === 0 ? (
                <div className="text-center py-4">
                  <p className="text-xs text-zinc-500 mb-3">No platforms connected</p>
                  <button
                    onClick={() => navigate('/app/creator/platforms')}
                    className="text-xs text-blue-400 hover:text-blue-300"
                  >
                    Connect platforms →
                  </button>
                </div>
              ) : (
                connections.slice(0, 4).map((conn) => (
                  <div key={conn.id} className="flex items-center justify-between p-2 bg-white/5 rounded">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${
                        conn.sync_status === 'synced' ? 'bg-emerald-500' :
                        conn.sync_status === 'syncing' ? 'bg-blue-500 animate-pulse' :
                        conn.sync_status === 'failed' ? 'bg-red-500' :
                        'bg-zinc-500'
                      }`} />
                      <span className="text-xs text-zinc-300 capitalize">{conn.platform}</span>
                    </div>
                    <span className="text-[10px] text-zinc-500">
                      {conn.platform_username || 'Connected'}
                    </span>
                  </div>
                ))
              )}
            </div>

            {connections.length > 0 && (
              <button
                onClick={() => navigate('/app/creator/platforms')}
                className="mt-4 w-full py-2 border border-white/10 text-[10px] uppercase tracking-widest text-zinc-400 hover:text-white hover:border-white/30 transition-all"
              >
                Manage Connections
              </button>
            )}
          </div>

          {/* Quick Actions */}
          <div className="border border-white/10 bg-zinc-900/30 p-6">
            <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em] mb-4">Quick Actions</h2>
            <div className="space-y-3">
              <button
                onClick={() => navigate('/app/creator/revenue/new')}
                className="w-full p-3 bg-emerald-500/10 border border-emerald-500/20 flex items-center gap-3 hover:bg-emerald-500/20 transition-colors text-left"
              >
                <DollarSign className="w-4 h-4 text-emerald-500" />
                <div>
                  <div className="text-xs text-emerald-200 font-medium">Log Revenue</div>
                  <div className="text-[10px] text-emerald-500/70">Add income entry</div>
                </div>
                <ArrowUpRight className="w-4 h-4 text-emerald-500 ml-auto" />
              </button>

              <button
                onClick={() => navigate('/app/creator/expenses/new')}
                className="w-full p-3 bg-amber-500/10 border border-amber-500/20 flex items-center gap-3 hover:bg-amber-500/20 transition-colors text-left"
              >
                <Receipt className="w-4 h-4 text-amber-500" />
                <div>
                  <div className="text-xs text-amber-200 font-medium">Log Expense</div>
                  <div className="text-[10px] text-amber-500/70">Track deductions</div>
                </div>
                <ArrowUpRight className="w-4 h-4 text-amber-500 ml-auto" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Revenue Trend Chart Placeholder */}
      {overview && overview.monthly_trend.length > 0 && (
        <div className="border border-white/10 bg-zinc-900/30 p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Monthly Trend</h2>
            <Activity className="w-4 h-4 text-zinc-500" />
          </div>

          <div className="h-48 flex items-end gap-2">
            {overview.monthly_trend.map((month, i) => {
              const maxRevenue = Math.max(...overview.monthly_trend.map(m => m.revenue));
              const height = maxRevenue > 0 ? (month.revenue / maxRevenue) * 100 : 0;
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-2">
                  <div
                    className="w-full bg-emerald-500/30 hover:bg-emerald-500/50 transition-colors rounded-t relative group"
                    style={{ height: `${Math.max(height, 4)}%` }}
                  >
                    <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <div className="bg-zinc-800 px-2 py-1 rounded text-[10px] text-white whitespace-nowrap">
                        {formatCurrency(month.revenue)}
                      </div>
                    </div>
                  </div>
                  <span className="text-[9px] text-zinc-600 uppercase">
                    {new Date(month.month + '-01').toLocaleDateString('en-US', { month: 'short' })}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default CreatorDashboard;
