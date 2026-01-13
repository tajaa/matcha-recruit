import { GlassCard } from '../components/GlassCard';
import { Button } from '../components/Button';
import { ComplianceWidget } from '../components/ComplianceWidget';
import { ArrowUpRight, Users, FileText, CheckCircle2, Clock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function Dashboard() {
  const navigate = useNavigate();

  const stats = [
    { label: 'Active Policies', value: '2', change: '+1 this week', icon: FileText, color: 'text-zinc-600' },
    { label: 'Pending Signatures', value: '5', change: 'Action required', icon: Clock, color: 'text-zinc-600' },
    { label: 'Total Candidates', value: '148', change: '+12% vs last month', icon: Users, color: 'text-zinc-600' },
    { label: 'Offers Accepted', value: '85%', change: 'Top 10% in industry', icon: CheckCircle2, color: 'text-zinc-600' },
  ];

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-light tracking-tight text-zinc-900">
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
              <div className={`p-2 border border-zinc-200 bg-zinc-50 ${stat.color}`}>
                <stat.icon className="w-5 h-5" />
              </div>
              {stat.label === 'Active Policies' && (
                 <ArrowUpRight className="w-4 h-4 text-zinc-400" />
              )}
            </div>
            <div>
              <div className="text-2xl font-light text-zinc-900 mb-1">{stat.value}</div>
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
            <h2 className="text-sm font-medium text-zinc-500 uppercase tracking-widest">Recent Activity</h2>
          </div>
          <GlassCard className="divide-y divide-zinc-100">
            {[
              { action: 'Sarah Miller signed Remote Work Policy', time: '2 hours ago', type: 'success' },
              { action: 'New offer letter drafted for John Doe', time: '5 hours ago', type: 'neutral' },
              { action: 'James Wilson viewed Code of Conduct', time: '1 day ago', type: 'neutral' },
            ].map((item, i) => (
              <div key={i} className="p-4 flex items-center justify-between hover:bg-zinc-50 transition-colors cursor-default">
                <div className="flex items-center gap-3">
                  <div className={`w-1.5 h-1.5 rounded-full ${item.type === 'success' ? 'bg-zinc-900' : 'bg-zinc-300'}`} />
                  <span className="text-sm text-zinc-700">{item.action}</span>
                </div>
                <span className="text-[10px] font-mono text-zinc-400 uppercase">{item.time}</span>
              </div>
            ))}
          </GlassCard>
        </div>

        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-zinc-500 uppercase tracking-widest">Compliance</h2>
          </div>
          <ComplianceWidget />
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
