import { useNavigate } from 'react-router-dom';
import { ArrowUpRight, Users, FileText, CheckCircle2, Clock, Activity, ShieldAlert } from 'lucide-react';

export function Dashboard() {
  const navigate = useNavigate();

  const stats = [
    { label: 'Active Policies', value: '14', change: '+2 this week', icon: FileText, color: 'text-emerald-500' },
    { label: 'Pending Signatures', value: '5', change: 'Action required', icon: Clock, color: 'text-amber-500' },
    { label: 'Total Employees', value: '148', change: '+12% vs last month', icon: Users, color: 'text-white' },
    { label: 'Compliance Rate', value: '98%', change: 'Top 1% in industry', icon: CheckCircle2, color: 'text-emerald-500' },
  ];

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
             <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
                Live Overview
             </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Command Center
          </h1>
        </div>
        <div className="flex gap-4">
          <button 
            onClick={() => navigate('/app/policies/new')}
            className="px-6 py-3 border border-white/20 hover:bg-white hover:text-black text-xs font-mono uppercase tracking-widest transition-all"
          >
            New Policy
          </button>
          <button 
            onClick={() => navigate('/app/offer-letters')}
            className="px-6 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest transition-all font-bold"
          >
            Create Offer
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
              <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-400 uppercase">
                 <span className="w-1 h-1 bg-zinc-600 rounded-full" />
                 {stat.change}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Dashboard Widgets */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Activity Feed */}
        <div className="lg:col-span-2 border border-white/10 bg-zinc-900/30">
          <div className="p-6 border-b border-white/10 flex justify-between items-center">
            <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">System Activity</h2>
            <Activity className="w-4 h-4 text-zinc-500" />
          </div>
          <div className="divide-y divide-white/5">
            {[
              { action: 'Sarah Miller signed Remote Work Policy', time: '14:02', date: 'TODAY', type: 'success' },
              { action: 'Offer letter generated for Alex Chen (Engineering)', time: '11:30', date: 'TODAY', type: 'neutral' },
              { action: 'Incident Report #IR-092 flagged for review', time: '09:15', date: 'TODAY', type: 'warning' },
              { action: 'James Wilson viewed Code of Conduct', time: '16:45', date: 'YESTERDAY', type: 'neutral' },
              { action: 'New compliance requirements updated', time: '09:00', date: 'YESTERDAY', type: 'neutral' },
            ].map((item, i) => (
              <div key={i} className="p-4 flex items-center justify-between hover:bg-white/5 transition-colors group">
                <div className="flex items-center gap-4">
                  <div className={`font-mono text-[10px] text-zinc-500 w-16`}>
                     {item.time}
                  </div>
                  <div className="flex items-center gap-3">
                    <div className={`w-1.5 h-1.5 rounded-full ${
                        item.type === 'success' ? 'bg-emerald-500' : 
                        item.type === 'warning' ? 'bg-amber-500 animate-pulse' : 'bg-zinc-600'
                    }`} />
                    <span className="text-sm text-zinc-300 group-hover:text-white transition-colors">{item.action}</span>
                  </div>
                </div>
                <div className="hidden sm:block text-[9px] font-mono text-zinc-600 uppercase tracking-widest border border-white/5 px-2 py-1 rounded">
                   {item.date}
                </div>
              </div>
            ))}
          </div>
          <div className="p-4 border-t border-white/10 bg-white/5">
             <button className="w-full text-center text-[10px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white transition-colors">
                View Full Log
             </button>
          </div>
        </div>

        {/* Action / Compliance Column */}
        <div className="space-y-8">
           {/* Compliance Widget */}
           <div className="border border-white/10 bg-zinc-900/30 p-6 relative overflow-hidden group">
              <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/10 rounded-full blur-[50px] pointer-events-none" />
              
              <div className="flex items-center justify-between mb-8">
                 <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Compliance Health</h2>
                 <ShieldAlert className="w-4 h-4 text-emerald-500" />
              </div>

              <div className="relative w-48 h-48 mx-auto mb-8">
                 {/* CSS Radial Progress Hack or simple SVG */}
                 <svg className="w-full h-full transform -rotate-90">
                    <circle cx="96" cy="96" r="88" stroke="currentColor" strokeWidth="12" fill="transparent" className="text-zinc-800" />
                    <circle cx="96" cy="96" r="88" stroke="currentColor" strokeWidth="12" fill="transparent" strokeDasharray="552" strokeDashoffset="27" className="text-emerald-500" />
                 </svg>
                 <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-4xl font-light text-white">95%</span>
                    <span className="text-[9px] uppercase tracking-widest text-zinc-500 mt-1">Secure</span>
                 </div>
              </div>

              <div className="space-y-3">
                 <div className="flex justify-between text-xs text-zinc-400">
                    <span>Policy Ack.</span>
                    <span className="text-white">98%</span>
                 </div>
                 <div className="w-full bg-zinc-800 h-1 rounded-full overflow-hidden">
                    <div className="bg-emerald-500 h-full w-[98%]" />
                 </div>
                 
                 <div className="flex justify-between text-xs text-zinc-400 mt-2">
                    <span>Training Completion</span>
                    <span className="text-white">92%</span>
                 </div>
                 <div className="w-full bg-zinc-800 h-1 rounded-full overflow-hidden">
                    <div className="bg-emerald-500 h-full w-[92%]" />
                 </div>
              </div>
           </div>

           {/* Quick Action */}
           <div className="border border-white/10 bg-zinc-900/30 p-6">
              <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em] mb-4">Pending Actions</h2>
              <div className="space-y-3">
                 <div className="p-3 bg-amber-500/10 border border-amber-500/20 flex items-start gap-3">
                    <div className="mt-1 w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                    <div>
                       <div className="text-xs text-amber-200 font-medium mb-1">Review Incident Report</div>
                       <div className="text-[10px] text-amber-500/70">IR-092 • High Priority</div>
                    </div>
                    <ArrowUpRight className="w-4 h-4 text-amber-500 ml-auto" />
                 </div>
              </div>
           </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;