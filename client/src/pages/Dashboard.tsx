import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowUpRight, Users, FileText, CheckCircle2, Clock, Activity, ShieldAlert, Calendar, Building, UserPlus, LayoutDashboard, History, AlertTriangle } from 'lucide-react';
import { getAccessToken } from '../api/client';
import { OnboardingWizard } from '../components/OnboardingWizard';
import { Collapsible } from '../components/Collapsible';
import { Tabs } from '../components/Tabs';
import { WidgetContainer } from '../components/WidgetContainer';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

interface PTOSummary {
  pending_count: number;
  upcoming_time_off: number;
}

interface PendingIncident {
  id: string;
  incident_number: string;
  title: string;
  severity: string;
}

interface ActivityItem {
  action: string;
  timestamp: string;
  type: string;
}

interface IncidentSummary {
  total_open: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  recent_7_days: number;
}

interface DashboardStats {
  active_policies: number;
  pending_signatures: number;
  total_employees: number;
  compliance_rate: number;
  pending_incidents: PendingIncident[];
  recent_activity: ActivityItem[];
  incident_summary?: IncidentSummary;
}

export function Dashboard() {
  const navigate = useNavigate();
  const [ptoSummary, setPtoSummary] = useState<PTOSummary | null>(null);
  const [dashStats, setDashStats] = useState<DashboardStats | null>(null);

  useEffect(() => {
    const token = getAccessToken();
    const headers = { Authorization: `Bearer ${token}` };

    fetch(`${API_BASE}/employees/pto/summary`, { headers })
      .then(r => r.ok ? r.json() : null)
      .then(data => data && setPtoSummary(data))
      .catch(err => console.error('Failed to fetch PTO summary:', err));

    fetch(`${API_BASE}/dashboard/stats`, { headers })
      .then(r => r.ok ? r.json() : null)
      .then(data => data && setDashStats(data))
      .catch(err => console.error('Failed to fetch dashboard stats:', err));
  }, []);

  const stats = [
    {
      label: 'Active Policies',
      value: dashStats ? String(dashStats.active_policies) : '-',
      change: dashStats?.active_policies === 0 ? 'No policies yet' : 'Active',
      icon: FileText,
      color: 'text-emerald-500',
      path: '/app/matcha/policies'
    },
    {
      label: 'Pending Signatures',
      value: dashStats ? String(dashStats.pending_signatures) : '-',
      change: dashStats?.pending_signatures === 0 ? 'All signed' : 'Action required',
      icon: Clock,
      color: 'text-amber-500',
      path: '/app/matcha/policies'
    },
    {
      label: 'Total Employees',
      value: dashStats ? String(dashStats.total_employees) : '-',
      change: dashStats?.total_employees === 0 ? 'No employees yet' : 'Active',
      icon: Users,
      color: 'text-white',
      path: '/app/matcha/employees'
    },
    {
      label: 'Compliance Rate',
      value: dashStats ? `${dashStats.compliance_rate}%` : '-',
      change: dashStats?.compliance_rate === 0 ? 'No data yet' : 'Current',
      icon: CheckCircle2,
      color: 'text-emerald-500',
      path: '/app/matcha/compliance'
    },
  ];

  const complianceRate = dashStats?.compliance_rate ?? 0;

  const dashboardWidgets = [
    { id: 'stats', label: 'Key Metrics', icon: Activity },
    { id: 'compliance', label: 'Compliance Health', icon: ShieldAlert },
    { id: 'actions', label: 'Pending Actions', icon: Clock },
    { id: 'activity', label: 'System Activity', icon: History },
    { id: 'incidents', label: 'Incident Reports', icon: AlertTriangle },
    { id: 'pto', label: 'Upcoming Time Off', icon: Calendar },
    { id: 'setup', label: 'Quick Setup', icon: Building },
  ];

  return (
    <>
    <OnboardingWizard />
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-white/10 pb-4">
        <div>
          <div className="flex items-center gap-3 mb-1.5">
             <div className="px-1.5 py-0.5 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[8px] uppercase tracking-widest font-mono rounded">
                Live Overview
             </div>
          </div>
          <h1 className="text-2xl font-bold tracking-tighter text-white uppercase">
            Command Center
          </h1>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => navigate('/app/matcha/policies/new')}
            className="px-4 py-2 border border-white/20 hover:bg-white hover:text-black text-[10px] font-mono uppercase tracking-widest transition-all"
          >
            New Policy
          </button>
          <button
            onClick={() => navigate('/app/matcha/offer-letters')}
            className="px-4 py-2 bg-white text-black hover:bg-zinc-200 text-[10px] font-mono uppercase tracking-widest transition-all font-bold"
          >
            Create Offer
          </button>
        </div>
      </div>

      <WidgetContainer widgets={dashboardWidgets}>
        {(visibleWidgets) => (
          <div className="space-y-6">
            {/* Stats Grid */}
            {visibleWidgets.has('stats') && (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-white/10 border border-white/10">
                {stats.map((stat) => (
                  <button
                    key={stat.label}
                    onClick={() => navigate(stat.path)}
                    className="bg-zinc-950 p-4 hover:bg-zinc-900 transition-all group relative overflow-hidden text-left"
                  >
                    <div className="absolute top-0 right-0 p-3 opacity-5 group-hover:opacity-10 group-hover:scale-110 transition-all duration-500">
                       <stat.icon className="w-10 h-10 text-white" strokeWidth={0.5} />
                    </div>

                    <div className="relative z-10">
                      <div className="flex items-center gap-2 mb-2">
                         <div className={`p-1 rounded bg-white/5 ${stat.color}`}>
                            <stat.icon className="w-3 h-3" />
                         </div>
                         <span className="text-[8px] uppercase tracking-[0.2em] text-zinc-500 font-bold">{stat.label}</span>
                      </div>

                      <div className="text-xl font-light text-white mb-0.5 tabular-nums tracking-tight group-hover:text-emerald-400 transition-colors">{stat.value}</div>
                      <div className="flex items-center gap-2 text-[8px] font-mono text-zinc-500 uppercase">
                         <span className="w-1 h-1 bg-zinc-700 rounded-full" />
                         {stat.change}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}


            {/* Quick Setup — shown for new businesses with no employees and no policies */}
            {visibleWidgets.has('setup') && dashStats && dashStats.total_employees === 0 && dashStats.active_policies === 0 && (
              <Collapsible title="Quick Setup" icon={Activity}>
                <div className="p-4 bg-zinc-900/10">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <button
                      onClick={() => navigate('/app/matcha/company')}
                      className="flex items-center gap-3 p-3 border border-white/10 hover:border-white/30 hover:bg-white/5 transition-all group text-left"
                    >
                      <div className="p-1.5 bg-white/5 group-hover:bg-white/10 transition-colors">
                        <Building className="w-3.5 h-3.5 text-zinc-400 group-hover:text-white transition-colors" />
                      </div>
                      <div className="flex-1">
                        <div className="text-[11px] text-white font-medium group-hover:text-white transition-colors">Company Profile</div>
                        <div className="text-[8px] text-zinc-500 uppercase tracking-wider mt-0.5">Set up company info</div>
                      </div>
                      <ArrowUpRight className="w-3 h-3 text-zinc-600 group-hover:text-white transition-colors" />
                    </button>
                    <button
                      onClick={() => navigate('/app/matcha/employees')}
                      className="flex items-center gap-3 p-3 border border-white/10 hover:border-white/30 hover:bg-white/5 transition-all group text-left"
                    >
                      <div className="p-1.5 bg-white/5 group-hover:bg-white/10 transition-colors">
                        <UserPlus className="w-3.5 h-3.5 text-zinc-400 group-hover:text-white transition-colors" />
                      </div>
                      <div className="flex-1">
                        <div className="text-[11px] text-white font-medium group-hover:text-white transition-colors">Add Employees</div>
                        <div className="text-[8px] text-zinc-500 uppercase tracking-wider mt-0.5">Import team via CSV</div>
                      </div>
                      <ArrowUpRight className="w-3 h-3 text-zinc-600 group-hover:text-white transition-colors" />
                    </button>
                  </div>
                </div>
              </Collapsible>
            )}

            <Tabs
              tabs={[
                { id: 'overview', label: 'Overview', icon: LayoutDashboard },
                { id: 'operations', label: 'Operations', icon: History },
              ]}
            >
              {(activeTab) => (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  {activeTab === 'overview' && (
                    <>
                      <div className="lg:col-span-2 space-y-4">
                        {visibleWidgets.has('actions') && (
                          <div className="border border-white/10 bg-zinc-900/30 p-4 h-fit">
                            <h2 className="text-[9px] font-bold text-white uppercase tracking-[0.2em] mb-3">Pending Actions</h2>
                            <div className="space-y-1.5">
                              {ptoSummary && ptoSummary.pending_count > 0 && (
                                <div
                                  onClick={() => navigate('/app/matcha/pto')}
                                  className="p-2.5 bg-amber-500/10 border border-amber-500/20 flex items-start gap-3 cursor-pointer hover:bg-amber-500/20 transition-colors"
                                >
                                    <Calendar className="w-3.5 h-3.5 text-amber-500 mt-0.5" />
                                    <div className="flex-1">
                                      <div className="text-[11px] text-amber-200 font-medium mb-0.5">PTO Requests Pending</div>
                                      <div className="text-[9px] text-amber-500/70">{ptoSummary.pending_count} request{ptoSummary.pending_count !== 1 ? 's' : ''} awaiting approval</div>
                                    </div>
                                    <ArrowUpRight className="w-3 h-3 text-amber-500 ml-auto" />
                                </div>
                              )}
                              {dashStats?.pending_incidents.map((incident) => (
                                <div
                                  key={incident.id}
                                  onClick={() => navigate(`/app/ir/incidents/${incident.id}`)}
                                  className="p-2.5 bg-amber-500/10 border border-amber-500/20 flex items-start gap-3 cursor-pointer hover:bg-amber-500/20 transition-colors"
                                >
                                    <div className="mt-1.5 w-1 h-1 rounded-full bg-amber-500 animate-pulse" />
                                    <div className="flex-1">
                                      <div className="text-[11px] text-amber-200 font-medium mb-0.5">{incident.title}</div>
                                      <div className="text-[9px] text-amber-500/70">{incident.incident_number} &bull; {incident.severity.charAt(0).toUpperCase() + incident.severity.slice(1)} Priority</div>
                                    </div>
                                    <ArrowUpRight className="w-3 h-3 text-amber-500 ml-auto" />
                                </div>
                              ))}
                              {(!ptoSummary || ptoSummary.pending_count === 0) && (!dashStats || dashStats.pending_incidents.length === 0) && (
                                <div className="p-3 text-center">
                                  <CheckCircle2 className="w-4 h-4 text-zinc-700 mx-auto mb-1.5" />
                                  <p className="text-[9px] text-zinc-500 uppercase tracking-wider">All caught up</p>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                        
                        {visibleWidgets.has('pto') && ptoSummary && ptoSummary.upcoming_time_off > 0 && (
                          <div className="border border-white/10 bg-zinc-900/30 p-4">
                              <div className="flex items-center justify-between mb-3">
                                <h2 className="text-[9px] font-bold text-white uppercase tracking-[0.2em]">Upcoming Time Off</h2>
                                <Calendar className="w-3.5 h-3.5 text-zinc-500" />
                              </div>
                              <div className="text-xl font-light text-white mb-0.5">{ptoSummary.upcoming_time_off}</div>
                              <div className="text-[9px] text-zinc-500 uppercase tracking-wider">employees out (30d)</div>
                              <button
                                onClick={() => navigate('/app/matcha/pto')}
                                className="mt-3 w-full text-center py-1.5 border border-white/10 text-[8px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white hover:border-white/30 transition-colors"
                              >
                                View Calendar
                              </button>
                          </div>
                        )}
                      </div>

                      <div className="space-y-4">
                        {visibleWidgets.has('compliance') && (
                          <div className="border border-white/10 bg-zinc-900/30 p-4 relative overflow-hidden group h-fit">
                            <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/10 rounded-full blur-[40px] pointer-events-none" />

                            <div className="flex items-center justify-between mb-4">
                                <h2 className="text-[9px] font-bold text-white uppercase tracking-[0.2em]">Compliance</h2>
                                <ShieldAlert className="w-3.5 h-3.5 text-emerald-500" />
                            </div>

                            <div className="relative w-32 h-32 mx-auto mb-4">
                                <svg className="w-full h-full transform -rotate-90">
                                  <circle cx="64" cy="64" r="58" stroke="currentColor" strokeWidth="8" fill="transparent" className="text-zinc-800" />
                                  <circle cx="64" cy="64" r="58" stroke="currentColor" strokeWidth="8" fill="transparent"
                                    strokeDasharray={2 * Math.PI * 58}
                                    strokeDashoffset={(2 * Math.PI * 58) - (complianceRate / 100) * (2 * Math.PI * 58)}
                                    className="text-emerald-500 transition-all duration-1000"
                                  />
                                </svg>
                                <div className="absolute inset-0 flex flex-col items-center justify-center">
                                  <span className="text-2xl font-light text-white">{complianceRate > 0 ? `${complianceRate}%` : '--'}</span>
                                  <span className="text-[8px] uppercase tracking-widest text-zinc-500 mt-0.5">{complianceRate > 0 ? 'Compliant' : 'No data'}</span>
                                </div>
                            </div>

                            {dashStats && dashStats.active_policies > 0 ? (
                              <div className="space-y-2">
                                <div className="flex justify-between text-[8px] text-zinc-400 uppercase tracking-wider">
                                    <span>Signatures</span>
                                    <span className="text-white">{complianceRate}%</span>
                                </div>
                                <div className="w-full bg-zinc-800 h-1 rounded-full overflow-hidden">
                                    <div className="bg-emerald-500 h-full transition-all duration-1000" style={{ width: `${complianceRate}%` }} />
                                </div>
                              </div>
                            ) : (
                              <p className="text-[8px] text-zinc-600 text-center uppercase tracking-wider">Create policies to track</p>
                            )}
                          </div>
                        )}
                      </div>
                    </>
                  )}

                  {activeTab === 'operations' && (
                    <div className="lg:col-span-3 space-y-4">
                      {visibleWidgets.has('activity') && (
                        <div className="border border-white/10 bg-zinc-900/30">
                          <div className="p-3 border-b border-white/10 flex justify-between items-center">
                            <h2 className="text-[9px] font-bold text-white uppercase tracking-[0.2em]">System Activity</h2>
                            <Activity className="w-3.5 h-3.5 text-zinc-500" />
                          </div>
                          <div className="divide-y divide-white/5">
                            {dashStats && dashStats.recent_activity.length > 0 ? (
                              dashStats.recent_activity.map((item, i) => {
                                const ts = new Date(item.timestamp);
                                const timeStr = ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
                                const isToday = new Date().toDateString() === ts.toDateString();
                                const dateLabel = isToday ? 'TODAY' : ts.toLocaleDateString([], { month: 'short', day: 'numeric' }).toUpperCase();
                                return (
                                  <div key={i} className="p-2.5 flex items-center justify-between hover:bg-white/5 transition-colors group">
                                    <div className="flex items-center gap-3">
                                      <div className="font-mono text-[8px] text-zinc-500 w-12">
                                        {timeStr}
                                      </div>
                                      <div className="flex items-center gap-2.5">
                                        <div className={`w-1 h-1 rounded-full ${
                                            item.type === 'success' ? 'bg-emerald-500' :
                                            item.type === 'warning' ? 'bg-amber-500 animate-pulse' : 'bg-zinc-600'
                                        }`} />
                                        <span className="text-[11px] text-zinc-300 group-hover:text-white transition-colors">{item.action}</span>
                                      </div>
                                    </div>
                                    <div className="hidden sm:block text-[8px] font-mono text-zinc-600 uppercase tracking-widest border border-white/5 px-1.5 py-0.5 rounded">
                                      {dateLabel}
                                    </div>
                                  </div>
                                );
                              })
                            ) : (
                              <div className="p-4 text-center">
                                <Activity className="w-5 h-5 text-zinc-700 mx-auto mb-1.5" />
                                <p className="text-[11px] text-zinc-500">No recent activity</p>
                              </div>
                            )}
                          </div>
                          {dashStats && dashStats.recent_activity.length > 0 && (
                            <div className="p-2.5 border-t border-white/10 bg-white/5">
                              <button className="w-full text-center text-[8px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white transition-colors">
                                  Full Log
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                      {visibleWidgets.has('incidents') && dashStats?.incident_summary && dashStats.incident_summary.total_open > 0 && (
                        <div className="border border-white/10 bg-zinc-900/30">
                          <div className="p-3 border-b border-white/10 flex justify-between items-center">
                            <h2 className="text-[9px] font-bold text-white uppercase tracking-[0.2em]">Incidents</h2>
                            <ShieldAlert className="w-3.5 h-3.5 text-zinc-500" />
                          </div>
                          <div className="p-4">
                            <div className="flex items-baseline gap-2.5 mb-4">
                              <span className="text-2xl font-light text-white tabular-nums">{dashStats.incident_summary.total_open}</span>
                              <span className="text-[8px] uppercase tracking-[0.2em] text-zinc-500 font-bold">Open Incident{dashStats.incident_summary.total_open !== 1 ? 's' : ''}</span>
                              {dashStats.incident_summary.recent_7_days > 0 && (
                                <span className="ml-auto text-[8px] font-mono text-amber-500 border border-amber-500/20 bg-amber-500/10 px-1.5 py-0.5 rounded">
                                  +{dashStats.incident_summary.recent_7_days}
                                </span>
                              )}
                            </div>
                            <div className="grid grid-cols-4 gap-px bg-white/10">
                              {([
                                { label: 'Crit', count: dashStats.incident_summary.critical, color: 'text-red-400', bg: 'bg-red-500' },
                                { label: 'High', count: dashStats.incident_summary.high, color: 'text-orange-400', bg: 'bg-orange-500' },
                                { label: 'Med', count: dashStats.incident_summary.medium, color: 'text-amber-400', bg: 'bg-amber-500' },
                                { label: 'Low', count: dashStats.incident_summary.low, color: 'text-zinc-400', bg: 'bg-zinc-500' },
                              ] as const).map((sev) => (
                                <div key={sev.label} className="bg-zinc-950 p-2 text-center">
                                  <div className={`text-lg font-light tabular-nums ${sev.count > 0 ? sev.color : 'text-zinc-700'}`}>{sev.count}</div>
                                  <div className="flex items-center justify-center gap-1 mt-1">
                                    <span className={`w-1 h-1 rounded-full ${sev.count > 0 ? sev.bg : 'bg-zinc-800'}`} />
                                    <span className="text-[7px] uppercase tracking-widest text-zinc-500">{sev.label}</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                          <div className="p-2.5 border-t border-white/10 bg-white/5">
                            <button
                              onClick={() => navigate('/app/ir/incidents')}
                              className="w-full text-center text-[8px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white transition-colors"
                            >
                              View All
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </Tabs>
          </div>
        )}
      </WidgetContainer>
    </div>
    </>
  );
}

export default Dashboard;

