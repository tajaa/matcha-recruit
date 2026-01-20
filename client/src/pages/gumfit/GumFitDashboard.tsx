import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Users, Building2, UserPlus, Mail, TrendingUp, Activity } from 'lucide-react';
import { api } from '../../api/client';
import type { GumFitStats } from '../../api/client';

export function GumFitDashboard() {
  const [stats, setStats] = useState<GumFitStats>({
    total_creators: 0,
    total_agencies: 0,
    total_users: 0,
    pending_invites: 0,
    active_campaigns: 0,
    recent_signups: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const res = await api.gumfit.getStats();
      setStats(res);
    } catch (err) {
      console.error('Failed to load stats:', err);
    } finally {
      setLoading(false);
    }
  };

  const statCards = [
    {
      label: 'Total Creators',
      value: stats.total_creators,
      icon: <Users className="w-5 h-5" />,
      color: 'text-blue-400',
      bgColor: 'bg-blue-500/10',
      link: '/app/gumfit/creators',
    },
    {
      label: 'Total Agencies',
      value: stats.total_agencies,
      icon: <Building2 className="w-5 h-5" />,
      color: 'text-purple-400',
      bgColor: 'bg-purple-500/10',
      link: '/app/gumfit/agencies',
    },
    {
      label: 'Total Users',
      value: stats.total_users,
      icon: <UserPlus className="w-5 h-5" />,
      color: 'text-emerald-400',
      bgColor: 'bg-emerald-500/10',
      link: '/app/gumfit/users',
    },
    {
      label: 'Pending Invites',
      value: stats.pending_invites,
      icon: <Mail className="w-5 h-5" />,
      color: 'text-amber-400',
      bgColor: 'bg-amber-500/10',
      link: '/app/gumfit/invites',
    },
    {
      label: 'Active Campaigns',
      value: stats.active_campaigns,
      icon: <TrendingUp className="w-5 h-5" />,
      color: 'text-cyan-400',
      bgColor: 'bg-cyan-500/10',
      link: '#',
    },
    {
      label: 'Recent Signups (7d)',
      value: stats.recent_signups,
      icon: <Activity className="w-5 h-5" />,
      color: 'text-pink-400',
      bgColor: 'bg-pink-500/10',
      link: '/app/gumfit/users',
    },
  ];

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
      <div>
        <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">
          GumFit Admin
        </div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Manage creators, agencies, and platform users
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {statCards.map((stat) => (
          <Link
            key={stat.label}
            to={stat.link}
            className="border border-white/10 bg-zinc-900/30 p-4 hover:border-white/20 transition-colors group"
          >
            <div className={`flex items-center gap-2 ${stat.color} mb-3`}>
              <div className={`p-1.5 ${stat.bgColor} rounded`}>
                {stat.icon}
              </div>
            </div>
            <div className="text-2xl font-bold text-white mb-1 group-hover:text-zinc-200 transition-colors">
              {stat.value.toLocaleString()}
            </div>
            <div className="text-[10px] uppercase tracking-widest text-zinc-500">
              {stat.label}
            </div>
          </Link>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="border border-white/10 bg-zinc-900/30 p-6">
          <h2 className="text-xs font-bold text-white uppercase tracking-widest mb-4">
            Quick Actions
          </h2>
          <div className="space-y-3">
            <Link
              to="/app/gumfit/invites"
              className="flex items-center gap-3 p-3 bg-white/5 hover:bg-white/10 transition-colors"
            >
              <Mail className="w-4 h-4 text-zinc-400" />
              <span className="text-sm text-white">Send Invite</span>
            </Link>
            <Link
              to="/app/gumfit/creators"
              className="flex items-center gap-3 p-3 bg-white/5 hover:bg-white/10 transition-colors"
            >
              <Users className="w-4 h-4 text-zinc-400" />
              <span className="text-sm text-white">View Creators</span>
            </Link>
            <Link
              to="/app/gumfit/agencies"
              className="flex items-center gap-3 p-3 bg-white/5 hover:bg-white/10 transition-colors"
            >
              <Building2 className="w-4 h-4 text-zinc-400" />
              <span className="text-sm text-white">View Agencies</span>
            </Link>
          </div>
        </div>

        {/* Recent Activity */}
        <div className="border border-white/10 bg-zinc-900/30 p-6">
          <h2 className="text-xs font-bold text-white uppercase tracking-widest mb-4">
            Recent Activity
          </h2>
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-3 bg-white/5">
              <div className="w-2 h-2 rounded-full bg-emerald-400"></div>
              <div className="flex-1">
                <div className="text-sm text-white">New creator signed up</div>
                <div className="text-xs text-zinc-500">2 minutes ago</div>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 bg-white/5">
              <div className="w-2 h-2 rounded-full bg-blue-400"></div>
              <div className="flex-1">
                <div className="text-sm text-white">Agency verified</div>
                <div className="text-xs text-zinc-500">15 minutes ago</div>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 bg-white/5">
              <div className="w-2 h-2 rounded-full bg-amber-400"></div>
              <div className="flex-1">
                <div className="text-sm text-white">Invite accepted</div>
                <div className="text-xs text-zinc-500">1 hour ago</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default GumFitDashboard;
