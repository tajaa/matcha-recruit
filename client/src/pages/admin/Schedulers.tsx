import { useState, useEffect, useCallback } from 'react';
import { adminSchedulers } from '../../api/client';
import type { SchedulerSetting, SchedulerStatsResponse, SchedulerLogEntry, SchedulerCompanyLocations, SchedulerLocation } from '../../api/client';

function formatRelative(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  return `${diffDays}d ago`;
}

function formatFuture(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  const now = new Date();
  const diffMs = d.getTime() - now.getTime();
  if (diffMs < 0) return 'Overdue';
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 60) return `in ${diffMin}m`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `in ${diffHr}h`;
  const diffDays = Math.floor(diffHr / 24);
  return `in ${diffDays}d`;
}

export function Schedulers() {
  const [schedulers, setSchedulers] = useState<SchedulerSetting[]>([]);
  const [stats, setStats] = useState<SchedulerStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [updatingLimit, setUpdatingLimit] = useState<string | null>(null);
  const [companies, setCompanies] = useState<SchedulerCompanyLocations[]>([]);
  const [expandedCompanies, setExpandedCompanies] = useState<Set<string>>(new Set());
  const [updatingLocation, setUpdatingLocation] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [schedulerData, statsData, locationData] = await Promise.all([
        adminSchedulers.list(),
        adminSchedulers.stats(),
        adminSchedulers.listLocations(),
      ]);
      setSchedulers(schedulerData);
      setStats(statsData);
      setCompanies(locationData);
    } catch (err) {
      console.error('Failed to fetch scheduler data:', err);
      setError('Failed to load scheduler data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleToggle = async (taskKey: string, currentEnabled: boolean) => {
    setToggling(taskKey);
    try {
      const updated = await adminSchedulers.update(taskKey, { enabled: !currentEnabled });
      setSchedulers(prev => prev.map(s => s.task_key === taskKey ? { ...s, ...updated } : s));
    } catch (err) {
      console.error('Failed to toggle scheduler:', err);
      setError('Failed to update scheduler');
    } finally {
      setToggling(null);
    }
  };

  const handleMaxPerCycleChange = async (taskKey: string, value: number) => {
    setUpdatingLimit(taskKey);
    try {
      const updated = await adminSchedulers.update(taskKey, { max_per_cycle: value });
      setSchedulers(prev => prev.map(s => s.task_key === taskKey ? { ...s, ...updated } : s));
    } catch (err) {
      console.error('Failed to update max_per_cycle:', err);
      setError('Failed to update limit');
    } finally {
      setUpdatingLimit(null);
    }
  };

  const handleTrigger = async (taskKey: string) => {
    setTriggering(taskKey);
    try {
      await adminSchedulers.trigger(taskKey);
      // Refresh data after a short delay to allow the task to start
      setTimeout(fetchData, 2000);
    } catch (err) {
      console.error('Failed to trigger scheduler:', err);
      setError('Failed to trigger task');
    } finally {
      setTriggering(null);
    }
  };

  const toggleCompany = (companyId: string) => {
    setExpandedCompanies(prev => {
      const next = new Set(prev);
      if (next.has(companyId)) next.delete(companyId);
      else next.add(companyId);
      return next;
    });
  };

  const handleLocationUpdate = async (locationId: string, companyId: string, data: { auto_check_enabled?: boolean; auto_check_interval_days?: number }) => {
    setUpdatingLocation(locationId);
    try {
      const updated = await adminSchedulers.updateLocation(locationId, data);
      setCompanies(prev => prev.map(c =>
        c.company_id === companyId
          ? { ...c, locations: c.locations.map(l => l.id === locationId ? { ...l, ...updated } : l) }
          : c
      ));
    } catch (err) {
      console.error('Failed to update location schedule:', err);
      setError('Failed to update location');
    } finally {
      setUpdatingLocation(null);
    }
  };

  const statusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      case 'running': return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
      case 'failed': return 'bg-red-500/10 text-red-400 border-red-500/20';
      default: return 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20';
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-end border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Schedulers</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Control automated background jobs
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="px-4 py-2 text-[10px] tracking-[0.15em] uppercase font-mono text-zinc-400 border border-zinc-700 hover:text-white hover:border-zinc-500 transition-colors disabled:opacity-50"
        >
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-sm font-mono">
          {error}
          <button onClick={() => setError(null)} className="ml-4 underline hover:text-red-300">Dismiss</button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse font-mono">Loading schedulers...</div>
        </div>
      ) : (
        <>
          {/* Stats Bar */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: 'Total Locations', value: stats.overview.total_locations },
                { label: 'Auto-Check Enabled', value: stats.overview.auto_check_enabled },
                { label: 'Checks (24h)', value: stats.overview.checks_24h },
                { label: 'Failed (24h)', value: stats.overview.failed_24h, alert: stats.overview.failed_24h > 0 },
              ].map((stat) => (
                <div key={stat.label} className="bg-zinc-900/50 border border-white/10 p-4">
                  <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono mb-2">{stat.label}</div>
                  <div className={`text-2xl font-bold font-mono ${stat.alert ? 'text-red-400' : 'text-white'}`}>
                    {stat.value}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Job Cards */}
          <div className="space-y-4">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold">
              Scheduled Jobs
            </div>
            {schedulers.map((sched) => (
              <div key={sched.task_key} className="bg-zinc-900/50 border border-white/10">
                <div className="p-6">
                  <div className="flex items-start justify-between gap-4">
                    {/* Left: Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="text-lg font-bold text-white tracking-tight">{sched.display_name}</h3>
                        <span className={`text-[9px] px-2 py-0.5 uppercase tracking-wider font-bold border ${
                          sched.enabled
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                            : 'bg-zinc-700/30 text-zinc-500 border-zinc-600/30'
                        }`}>
                          {sched.enabled ? 'Active' : 'Disabled'}
                        </span>
                      </div>
                      <p className="text-xs text-zinc-500 font-mono leading-relaxed">{sched.description}</p>
                    </div>

                    {/* Right: Controls */}
                    <div className="flex items-center gap-3 flex-shrink-0">
                      {/* Toggle */}
                      <button
                        onClick={() => handleToggle(sched.task_key, sched.enabled)}
                        disabled={toggling === sched.task_key}
                        className={`relative w-10 h-5 rounded-full transition-colors ${
                          sched.enabled ? 'bg-emerald-600' : 'bg-zinc-700'
                        } ${toggling === sched.task_key ? 'opacity-50' : ''}`}
                      >
                        <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                          sched.enabled ? 'translate-x-5' : 'translate-x-0.5'
                        }`} />
                      </button>

                      {/* Run Now */}
                      <button
                        onClick={() => handleTrigger(sched.task_key)}
                        disabled={triggering === sched.task_key}
                        className="px-3 py-1.5 text-[10px] tracking-[0.15em] uppercase font-mono text-white bg-zinc-800 border border-zinc-700 hover:bg-zinc-700 hover:border-zinc-500 transition-colors disabled:opacity-50"
                      >
                        {triggering === sched.task_key ? 'Triggering...' : 'Run Now'}
                      </button>
                    </div>
                  </div>

                  {/* Stats row */}
                  <div className="mt-4 pt-4 border-t border-white/5 flex flex-wrap gap-6">
                    {sched.task_key === 'compliance_checks' && sched.stats && (
                      <>
                        <div>
                          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono mb-1">Last Run</div>
                          <div className="text-xs text-zinc-300 font-mono">
                            {formatRelative(sched.stats.last_run as string | null)}
                            {sched.stats.last_run_status && (
                              <span className={`ml-2 text-[9px] px-1.5 py-0.5 uppercase tracking-wider font-bold border ${statusColor(sched.stats.last_run_status as string)}`}>
                                {sched.stats.last_run_status as string}
                              </span>
                            )}
                          </div>
                        </div>
                        <div>
                          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono mb-1">Next Due</div>
                          <div className="text-xs text-zinc-300 font-mono">{formatFuture(sched.stats.next_due as string | null)}</div>
                        </div>
                        <div>
                          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono mb-1">Locations</div>
                          <div className="text-xs text-zinc-300 font-mono">
                            {sched.stats.auto_check_enabled as number}/{sched.stats.total_locations as number} auto-check
                          </div>
                        </div>
                        <div>
                          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono mb-1">Max Per Cycle</div>
                          <div className="flex items-center gap-2">
                            <input
                              type="number"
                              min={1}
                              max={20}
                              value={sched.max_per_cycle}
                              onChange={(e) => {
                                const val = parseInt(e.target.value, 10);
                                if (!isNaN(val) && val >= 1 && val <= 20) {
                                  handleMaxPerCycleChange(sched.task_key, val);
                                }
                              }}
                              disabled={updatingLimit === sched.task_key}
                              className="w-14 px-2 py-1 text-xs font-mono text-white bg-zinc-800 border border-zinc-700 focus:border-zinc-500 focus:outline-none disabled:opacity-50"
                            />
                            {updatingLimit === sched.task_key && (
                              <span className="text-[9px] text-zinc-500 animate-pulse font-mono">Saving...</span>
                            )}
                          </div>
                        </div>
                      </>
                    )}
                    {sched.task_key === 'deadline_escalation' && sched.stats && (
                      <div>
                        <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono mb-1">Active Legislation</div>
                        <div className="text-xs text-zinc-300 font-mono">{sched.stats.active_legislation as number} items</div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Location Schedules */}
          {companies.length > 0 && (
            <div className="space-y-3">
              <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold">
                Location Schedules
              </div>
              <div className="border border-white/10 bg-zinc-900/30 divide-y divide-white/5">
                {companies.map((company) => {
                  const expanded = expandedCompanies.has(company.company_id);
                  const enabledCount = company.locations.filter(l => l.auto_check_enabled).length;
                  return (
                    <div key={company.company_id}>
                      <button
                        onClick={() => toggleCompany(company.company_id)}
                        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors text-left"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className={`text-[10px] font-mono transition-transform ${expanded ? 'rotate-90' : ''}`}>&#9654;</span>
                          <span className="text-sm text-white font-medium truncate">{company.company_name}</span>
                          <span className="text-[9px] text-zinc-500 font-mono flex-shrink-0">
                            {company.locations.length} location{company.locations.length !== 1 ? 's' : ''}
                          </span>
                        </div>
                        <span className={`text-[9px] px-2 py-0.5 uppercase tracking-wider font-bold border flex-shrink-0 ${
                          enabledCount > 0
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                            : 'bg-zinc-700/30 text-zinc-500 border-zinc-600/30'
                        }`}>
                          {enabledCount}/{company.locations.length} enabled
                        </span>
                      </button>
                      {expanded && (
                        <div className="border-t border-white/5">
                          {company.locations.map((loc) => (
                            <div key={loc.id} className="px-4 py-3 pl-10 flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-white/5 last:border-b-0 hover:bg-white/[0.02]">
                              {/* Location info */}
                              <div className="min-w-[180px] flex-1">
                                <div className="text-xs text-zinc-300 font-mono">{loc.name}</div>
                                {(loc.city || loc.state) && (
                                  <div className="text-[10px] text-zinc-600 font-mono">
                                    {[loc.city, loc.state].filter(Boolean).join(', ')}
                                  </div>
                                )}
                              </div>

                              {/* Toggle */}
                              <div className="flex items-center gap-2">
                                <span className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Auto-check</span>
                                <button
                                  onClick={() => handleLocationUpdate(loc.id, company.company_id, { auto_check_enabled: !loc.auto_check_enabled })}
                                  disabled={updatingLocation === loc.id}
                                  className={`relative w-10 h-5 rounded-full transition-colors ${
                                    loc.auto_check_enabled ? 'bg-emerald-600' : 'bg-zinc-700'
                                  } ${updatingLocation === loc.id ? 'opacity-50' : ''}`}
                                >
                                  <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                                    loc.auto_check_enabled ? 'translate-x-5' : 'translate-x-0.5'
                                  }`} />
                                </button>
                              </div>

                              {/* Interval */}
                              <div className="flex items-center gap-2">
                                <span className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Interval</span>
                                <input
                                  type="number"
                                  min={1}
                                  max={90}
                                  value={loc.auto_check_interval_days}
                                  onChange={(e) => {
                                    const val = parseInt(e.target.value, 10);
                                    if (!isNaN(val) && val >= 1 && val <= 90) {
                                      handleLocationUpdate(loc.id, company.company_id, { auto_check_interval_days: val });
                                    }
                                  }}
                                  disabled={updatingLocation === loc.id}
                                  className="w-14 px-2 py-1 text-xs font-mono text-white bg-zinc-800 border border-zinc-700 focus:border-zinc-500 focus:outline-none disabled:opacity-50"
                                />
                                <span className="text-[9px] text-zinc-600 font-mono">days</span>
                              </div>

                              {/* Next auto-check */}
                              <div>
                                <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Next check</div>
                                <div className="text-xs text-zinc-400 font-mono">{formatFuture(loc.next_auto_check)}</div>
                                <div className="flex gap-1 mt-1">
                                  {[2, 5].map(m => (
                                    <button
                                      key={m}
                                      onClick={() => handleLocationUpdate(loc.id, company.company_id, { next_auto_check_minutes: m })}
                                      disabled={updatingLocation === loc.id}
                                      className="px-1.5 py-0.5 text-[9px] font-mono text-amber-400 border border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 transition-colors disabled:opacity-50"
                                    >
                                      {m}m
                                    </button>
                                  ))}
                                </div>
                              </div>

                              {/* Last check */}
                              <div>
                                <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Last check</div>
                                <div className="text-xs text-zinc-400 font-mono">{formatRelative(loc.last_compliance_check)}</div>
                              </div>

                              {updatingLocation === loc.id && (
                                <span className="text-[9px] text-zinc-500 animate-pulse font-mono">Saving...</span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Recent Activity Log */}
          {stats && stats.recent_logs.length > 0 && (
            <div className="space-y-3">
              <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold">
                Recent Activity
              </div>
              <div className="border border-white/10 bg-zinc-900/30 overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-white/10 bg-zinc-950">
                      <th className="text-left px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Location</th>
                      <th className="text-left px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Type</th>
                      <th className="text-left px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Status</th>
                      <th className="text-left px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Started</th>
                      <th className="text-right px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Duration</th>
                      <th className="text-right px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">New</th>
                      <th className="text-right px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Updated</th>
                      <th className="text-right px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Alerts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.recent_logs.map((log: SchedulerLogEntry) => (
                      <tr key={log.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                        <td className="px-4 py-3 text-xs text-zinc-300 font-mono">{log.location_name || log.location_id.slice(0, 8)}</td>
                        <td className="px-4 py-3">
                          <span className="text-[9px] px-1.5 py-0.5 uppercase tracking-wider font-mono text-zinc-400 bg-zinc-800 border border-zinc-700">
                            {log.check_type}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-[9px] px-1.5 py-0.5 uppercase tracking-wider font-bold border ${statusColor(log.status)}`}>
                            {log.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-zinc-400 font-mono">{formatRelative(log.started_at)}</td>
                        <td className="px-4 py-3 text-xs text-zinc-400 font-mono text-right">
                          {log.duration_seconds != null ? `${Math.round(log.duration_seconds)}s` : '—'}
                        </td>
                        <td className="px-4 py-3 text-xs text-zinc-400 font-mono text-right">{log.new_count}</td>
                        <td className="px-4 py-3 text-xs text-zinc-400 font-mono text-right">{log.updated_count}</td>
                        <td className="px-4 py-3 text-xs text-zinc-400 font-mono text-right">{log.alert_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default Schedulers;
