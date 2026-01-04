import { GlassCard } from '../components/GlassCard';
import { Button } from '../components/Button';
import { ArrowUpRight, Users, FileText, CheckCircle2, Clock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function Dashboard() {
  const navigate = useNavigate();

  const stats = [
    { label: 'Active Policies', value: '2', change: '+1 this week', icon: FileText, color: 'text-blue-400' },
    { label: 'Pending Signatures', value: '5', change: 'Action required', icon: Clock, color: 'text-amber-400' },
    { label: 'Total Candidates', value: '148', change: '+12% vs last month', icon: Users, color: 'text-emerald-400' },
    { label: 'Offers Accepted', value: '85%', change: 'Top 10% in industry', icon: CheckCircle2, color: 'text-purple-400' },
  ];

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-light tracking-tight text-white">
            Dashboard
          </h1>
          <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Overview & Key Metrics
          </p>
        </div>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={() => navigate('/app/policies/new')}>
            New Policy
          </Button>
          <Button onClick={() => navigate('/app/offer-letters')}>
            Create Offer
          </Button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <GlassCard key={stat.label} className="p-6" hoverEffect>
            <div className="flex items-start justify-between mb-4">
              <div className={`p-2 rounded-lg bg-zinc-900/50 border border-zinc-800 ${stat.color}`}>
                <stat.icon className="w-5 h-5" />
              </div>
              {stat.label === 'Active Policies' && (
                 <ArrowUpRight className="w-4 h-4 text-zinc-600" />
              )}
            </div>
            <div>
              <div className="text-2xl font-light text-white mb-1">{stat.value}</div>
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium mb-3">{stat.label}</div>
              <div className="text-xs text-zinc-400 font-mono">{stat.change}</div>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Recent Activity / Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-widest">Recent Activity</h2>
          </div>
          <GlassCard className="divide-y divide-white/5">
            {[
              { action: 'Sarah Miller signed Remote Work Policy', time: '2 hours ago', type: 'success' },
              { action: 'New offer letter drafted for John Doe', time: '5 hours ago', type: 'neutral' },
              { action: 'James Wilson viewed Code of Conduct', time: '1 day ago', type: 'neutral' },
            ].map((item, i) => (
              <div key={i} className="p-4 flex items-center justify-between hover:bg-white/5 transition-colors cursor-default">
                <div className="flex items-center gap-3">
                  <div className={`w-1.5 h-1.5 rounded-full ${item.type === 'success' ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
                  <span className="text-sm text-zinc-300">{item.action}</span>
                </div>
                <span className="text-[10px] font-mono text-zinc-500 uppercase">{item.time}</span>
              </div>
            ))}
          </GlassCard>
        </div>

        <div className="space-y-6">
           <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-widest">System Status</h2>
          </div>
          <GlassCard className="p-6 space-y-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-zinc-400">API Status</span>
              <span className="flex items-center gap-2 text-emerald-400 font-mono text-xs">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                OPERATIONAL
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-zinc-400">Email Service</span>
              <span className="text-emerald-400 font-mono text-xs">OPERATIONAL</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-zinc-400">Signature Vault</span>
              <span className="text-emerald-400 font-mono text-xs">SECURE</span>
            </div>
            
            <div className="pt-4 mt-4 border-t border-white/5">
              <p className="text-[10px] text-zinc-500 leading-relaxed">
                System backup completed successfully at 04:00 UTC. Next backup scheduled in 12 hours.
              </p>
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
