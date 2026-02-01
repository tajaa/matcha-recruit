import { useState, useEffect, useCallback } from 'react';
import { adminJurisdictions, adminSchedulers } from '../../api/client';
import type {
  Jurisdiction, JurisdictionTotals, JurisdictionDetail, JurisdictionCreate,
  JurisdictionRequirement, JurisdictionLegislation, JurisdictionLocation,
  SchedulerSetting, SchedulerStatsResponse, SchedulerLogEntry,
} from '../../api/client';

const US_STATES = [
  { value: 'AL', label: 'Alabama' }, { value: 'AK', label: 'Alaska' },
  { value: 'AZ', label: 'Arizona' }, { value: 'AR', label: 'Arkansas' },
  { value: 'CA', label: 'California' }, { value: 'CO', label: 'Colorado' },
  { value: 'CT', label: 'Connecticut' }, { value: 'DE', label: 'Delaware' },
  { value: 'FL', label: 'Florida' }, { value: 'GA', label: 'Georgia' },
  { value: 'HI', label: 'Hawaii' }, { value: 'ID', label: 'Idaho' },
  { value: 'IL', label: 'Illinois' }, { value: 'IN', label: 'Indiana' },
  { value: 'IA', label: 'Iowa' }, { value: 'KS', label: 'Kansas' },
  { value: 'KY', label: 'Kentucky' }, { value: 'LA', label: 'Louisiana' },
  { value: 'ME', label: 'Maine' }, { value: 'MD', label: 'Maryland' },
  { value: 'MA', label: 'Massachusetts' }, { value: 'MI', label: 'Michigan' },
  { value: 'MN', label: 'Minnesota' }, { value: 'MS', label: 'Mississippi' },
  { value: 'MO', label: 'Missouri' }, { value: 'MT', label: 'Montana' },
  { value: 'NE', label: 'Nebraska' }, { value: 'NV', label: 'Nevada' },
  { value: 'NH', label: 'New Hampshire' }, { value: 'NJ', label: 'New Jersey' },
  { value: 'NM', label: 'New Mexico' }, { value: 'NY', label: 'New York' },
  { value: 'NC', label: 'North Carolina' }, { value: 'ND', label: 'North Dakota' },
  { value: 'OH', label: 'Ohio' }, { value: 'OK', label: 'Oklahoma' },
  { value: 'OR', label: 'Oregon' }, { value: 'PA', label: 'Pennsylvania' },
  { value: 'RI', label: 'Rhode Island' }, { value: 'SC', label: 'South Carolina' },
  { value: 'SD', label: 'South Dakota' }, { value: 'TN', label: 'Tennessee' },
  { value: 'TX', label: 'Texas' }, { value: 'UT', label: 'Utah' },
  { value: 'VT', label: 'Vermont' }, { value: 'VA', label: 'Virginia' },
  { value: 'WA', label: 'Washington' }, { value: 'WV', label: 'West Virginia' },
  { value: 'WI', label: 'Wisconsin' }, { value: 'WY', label: 'Wyoming' },
  { value: 'DC', label: 'Washington D.C.' },
];

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

const categoryLabel: Record<string, string> = {
  minimum_wage: 'Minimum Wage',
  overtime: 'Overtime',
  sick_leave: 'Sick Leave',
  workers_comp: "Workers' Comp",
  business_license: 'Business License',
  tax_rate: 'Tax Rate',
  posting_requirements: 'Posting Reqs',
};

const levelColor: Record<string, string> = {
  city: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  county: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
  state: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  federal: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/20',
};

const legStatusColor: Record<string, string> = {
  proposed: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/20',
  passed: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  signed: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  effective_soon: 'text-red-400 bg-red-500/10 border-red-500/20',
  effective: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  dismissed: 'text-zinc-600 bg-zinc-800/30 border-zinc-700/30',
};

type DetailTab = 'requirements' | 'legislation' | 'locations';

function JurisdictionDetailPanel({ detail, parentJurisdiction, onNavigate }: {
  detail: JurisdictionDetail;
  parentJurisdiction?: Jurisdiction | null;
  onNavigate?: (id: string) => void;
}) {
  const [tab, setTab] = useState<DetailTab>('requirements');

  const hasMetroGroup = detail.parent_id || detail.children.length > 0;

  const tabs: { key: DetailTab; label: string; count: number }[] = [
    { key: 'requirements', label: 'Requirements', count: detail.requirements.length },
    { key: 'legislation', label: 'Legislation', count: detail.legislation.length },
    { key: 'locations', label: 'Locations', count: detail.locations.length },
  ];

  // Group requirements by category
  const reqsByCategory: Record<string, JurisdictionRequirement[]> = {};
  for (const r of detail.requirements) {
    const cat = r.category || 'other';
    if (!reqsByCategory[cat]) reqsByCategory[cat] = [];
    reqsByCategory[cat].push(r);
  }

  return (
    <div className="border-t border-white/5 bg-zinc-950/50">
      {/* Metro Group */}
      {hasMetroGroup && (
        <div className="px-6 py-3 border-b border-white/5 bg-zinc-900/60">
          <div className="text-[9px] uppercase tracking-widest font-mono font-bold text-zinc-500 mb-2">Metro Group</div>
          <div className="flex flex-wrap gap-2">
            {detail.parent_id && parentJurisdiction && (
              <button
                onClick={() => onNavigate?.(detail.parent_id!)}
                className="text-[11px] font-mono px-2 py-1 bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors"
              >
                Parent: {parentJurisdiction.city}, {parentJurisdiction.state}
              </button>
            )}
            {detail.children.map(c => (
              <button
                key={c.id}
                onClick={() => onNavigate?.(c.id)}
                className="text-[11px] font-mono px-2 py-1 bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
              >
                {c.city}, {c.state}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Tab bar */}
      <div className="flex gap-0 border-b border-white/5">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-[10px] uppercase tracking-[0.15em] font-mono font-bold transition-colors ${
              tab === t.key
                ? 'text-white border-b-2 border-white'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {t.label} <span className="text-zinc-600 ml-1">{t.count}</span>
          </button>
        ))}
      </div>

      {/* Requirements tab */}
      {tab === 'requirements' && (
        <div className="divide-y divide-white/5">
          {detail.requirements.length === 0 && (
            <div className="px-6 py-4 text-xs text-zinc-600 font-mono italic">No requirements yet</div>
          )}
          {Object.entries(reqsByCategory).map(([cat, reqs]) => (
            <div key={cat}>
              <div className="px-6 py-2 bg-zinc-900/80">
                <span className="text-[9px] uppercase tracking-widest font-mono font-bold text-zinc-500">
                  {categoryLabel[cat] || cat.replace(/_/g, ' ')}
                </span>
                <span className="text-[9px] text-zinc-600 font-mono ml-2">{reqs.length}</span>
              </div>
              {reqs.map((r: JurisdictionRequirement) => (
                <div key={r.id} className="px-6 py-3 hover:bg-white/[0.02] transition-colors">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs text-zinc-200 font-medium">{r.title}</span>
                        <span className={`text-[8px] px-1.5 py-0.5 uppercase tracking-wider font-bold border ${levelColor[r.jurisdiction_level] || levelColor.federal}`}>
                          {r.jurisdiction_level}
                        </span>
                      </div>
                      {r.description && (
                        <div className="text-[11px] text-zinc-500 font-mono leading-relaxed mb-1 line-clamp-2">{r.description}</div>
                      )}
                      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1">
                        {r.source_name && (
                          <span className="text-[9px] text-zinc-600 font-mono">
                            {r.source_url ? <a href={r.source_url} target="_blank" rel="noreferrer" className="hover:text-zinc-400 underline">{r.source_name}</a> : r.source_name}
                          </span>
                        )}
                        {r.effective_date && <span className="text-[9px] text-zinc-600 font-mono">Effective: {r.effective_date}</span>}
                        {r.last_changed_at && <span className="text-[9px] text-amber-500/70 font-mono">Changed {formatRelative(r.last_changed_at)}</span>}
                        <span className="text-[9px] text-zinc-700 font-mono">Verified {formatRelative(r.last_verified_at)}</span>
                      </div>
                    </div>
                    <div className="text-right flex-shrink-0 min-w-[100px]">
                      {r.current_value && (
                        <div className="text-sm text-white font-mono font-bold">{r.current_value}</div>
                      )}
                      {r.previous_value && r.previous_value !== r.current_value && (
                        <div className="text-[9px] text-zinc-600 font-mono line-through">{r.previous_value}</div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Legislation tab */}
      {tab === 'legislation' && (
        <div className="divide-y divide-white/5">
          {detail.legislation.length === 0 && (
            <div className="px-6 py-4 text-xs text-zinc-600 font-mono italic">No legislation tracked</div>
          )}
          {detail.legislation.map((l: JurisdictionLegislation) => (
            <div key={l.id} className="px-6 py-3 hover:bg-white/[0.02] transition-colors">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-zinc-200 font-medium">{l.title}</span>
                    <span className={`text-[8px] px-1.5 py-0.5 uppercase tracking-wider font-bold border ${legStatusColor[l.current_status] || legStatusColor.proposed}`}>
                      {l.current_status.replace(/_/g, ' ')}
                    </span>
                    {l.category && (
                      <span className="text-[8px] px-1.5 py-0.5 uppercase tracking-wider font-mono text-zinc-600 bg-zinc-800 border border-zinc-700">
                        {categoryLabel[l.category] || l.category.replace(/_/g, ' ')}
                      </span>
                    )}
                  </div>
                  {l.description && (
                    <div className="text-[11px] text-zinc-500 font-mono leading-relaxed mb-1 line-clamp-2">{l.description}</div>
                  )}
                  {l.impact_summary && (
                    <div className="text-[11px] text-zinc-500 font-mono leading-relaxed mb-1 line-clamp-2">Impact: {l.impact_summary}</div>
                  )}
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1">
                    {l.source_name && (
                      <span className="text-[9px] text-zinc-600 font-mono">
                        {l.source_url ? <a href={l.source_url} target="_blank" rel="noreferrer" className="hover:text-zinc-400 underline">{l.source_name}</a> : l.source_name}
                      </span>
                    )}
                    {l.confidence != null && <span className="text-[9px] text-zinc-600 font-mono">Confidence: {Math.round(l.confidence * 100)}%</span>}
                    <span className="text-[9px] text-zinc-700 font-mono">Verified {formatRelative(l.last_verified_at)}</span>
                  </div>
                </div>
                <div className="text-right flex-shrink-0 min-w-[100px]">
                  {l.expected_effective_date && (
                    <div className="text-xs text-zinc-300 font-mono">{l.expected_effective_date}</div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Locations tab */}
      {tab === 'locations' && (
        <div className="divide-y divide-white/5">
          {detail.locations.length === 0 && (
            <div className="px-6 py-4 text-xs text-zinc-600 font-mono italic">No linked locations</div>
          )}
          {detail.locations.map((loc: JurisdictionLocation) => (
            <div key={loc.id} className="px-6 py-3 flex flex-wrap items-center gap-x-6 gap-y-2 hover:bg-white/[0.02]">
              <div className="min-w-[180px] flex-1">
                <div className="text-xs text-zinc-300 font-mono">{loc.name || `${loc.city}, ${loc.state}`}</div>
                <div className="text-[10px] text-zinc-600 font-mono">{loc.company_name}</div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-[9px] px-1.5 py-0.5 uppercase tracking-wider font-bold border ${
                  loc.auto_check_enabled
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    : 'bg-zinc-700/30 text-zinc-500 border-zinc-600/30'
                }`}>
                  {loc.auto_check_enabled ? 'Auto' : 'Manual'}
                </span>
                <span className="text-[9px] text-zinc-600 font-mono">{loc.auto_check_interval_days}d</span>
              </div>
              <div>
                <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Next</div>
                <div className="text-xs text-zinc-400 font-mono">{formatFuture(loc.next_auto_check)}</div>
              </div>
              <div>
                <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Last check</div>
                <div className="text-xs text-zinc-400 font-mono">{formatRelative(loc.last_compliance_check)}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Jurisdictions() {
  const [jurisdictions, setJurisdictions] = useState<Jurisdiction[]>([]);
  const [totals, setTotals] = useState<JurisdictionTotals | null>(null);
  const [schedulers, setSchedulers] = useState<SchedulerSetting[]>([]);
  const [stats, setStats] = useState<SchedulerStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detailCache, setDetailCache] = useState<Record<string, JurisdictionDetail>>({});
  const [detailLoading, setDetailLoading] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createForm, setCreateForm] = useState<JurisdictionCreate>({ city: '', state: '' });
  const [creating, setCreating] = useState(false);
  const [checkingId, setCheckingId] = useState<string | null>(null);
  const [checkTargetId, setCheckTargetId] = useState<string | null>(null);
  const [checkMessages, setCheckMessages] = useState<{ type: string; status?: string; message?: string; location?: string; new?: number; updated?: number; alerts?: number }[]>([]);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [jData, schedulerData, statsData] = await Promise.all([
        adminJurisdictions.list(),
        adminSchedulers.list(),
        adminSchedulers.stats(),
      ]);
      setJurisdictions(jData.jurisdictions);
      setTotals(jData.totals);
      setSchedulers(schedulerData);
      setStats(statsData);
    } catch (err) {
      console.error('Failed to fetch data:', err);
      setError('Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleToggle = async (taskKey: string, currentEnabled: boolean) => {
    setToggling(taskKey);
    try {
      const updated = await adminSchedulers.update(taskKey, { enabled: !currentEnabled });
      setSchedulers(prev => prev.map(s => s.task_key === taskKey ? { ...s, ...updated } : s));
    } catch {
      setError('Failed to update scheduler');
    } finally {
      setToggling(null);
    }
  };

  const handleTrigger = async (taskKey: string) => {
    setTriggering(taskKey);
    try {
      await adminSchedulers.trigger(taskKey);
      setTimeout(fetchData, 2000);
    } catch {
      setError('Failed to trigger task');
    } finally {
      setTriggering(null);
    }
  };

  const handleExpand = async (id: string) => {
    if (expanded === id) {
      setExpanded(null);
      return;
    }
    setExpanded(id);
    if (!detailCache[id]) {
      setDetailLoading(id);
      try {
        const detail = await adminJurisdictions.get(id);
        setDetailCache(prev => ({ ...prev, [id]: detail }));
      } catch {
        setError('Failed to load jurisdiction detail');
        setExpanded(null);
      } finally {
        setDetailLoading(null);
      }
    }
  };

  const handleCreate = async () => {
    if (!createForm.city.trim() || !createForm.state) return;
    setCreating(true);
    try {
      await adminJurisdictions.create({
        city: createForm.city.trim(),
        state: createForm.state,
        county: createForm.county?.trim() || undefined,
        parent_id: createForm.parent_id || undefined,
      });
      setCreateForm({ city: '', state: '' });
      setShowCreateForm(false);
      setDetailCache({});
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create jurisdiction';
      setError(msg);
    } finally {
      setCreating(false);
    }
  };

  const handleNavigate = async (id: string) => {
    setExpanded(id);
    if (!detailCache[id]) {
      setDetailLoading(id);
      try {
        const detail = await adminJurisdictions.get(id);
        setDetailCache(prev => ({ ...prev, [id]: detail }));
      } catch {
        setError('Failed to load jurisdiction detail');
        setExpanded(null);
      } finally {
        setDetailLoading(null);
      }
    }
  };

  const handleCheck = async (id: string) => {
    if (checkingId) return;
    setCheckingId(id);
    setCheckTargetId(id);
    setCheckMessages([]);
    setExpanded(id);
    try {
      const response = await adminJurisdictions.check(id);
      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;
          const payload = trimmed.slice(6);
          if (payload === '[DONE]') continue;
          try {
            const event = JSON.parse(payload);
            setCheckMessages(prev => [...prev, event]);
          } catch { /* skip malformed */ }
        }
      }
      // Refresh data after check completes
      setDetailCache({});
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to run jurisdiction check';
      setCheckMessages(prev => [...prev, { type: 'error', message: msg }]);
    } finally {
      setCheckingId(null);
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
      <style>{`
        @keyframes scanX {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(300%); }
        }
        @keyframes fadeSlideDown {
          from { opacity: 0; transform: translateY(-6px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes popIn {
          0% { opacity: 0; transform: scale(0.5); }
          70% { transform: scale(1.15); }
          100% { opacity: 1; transform: scale(1); }
        }
      `}</style>
      {/* Header */}
      <div className="flex justify-between items-end border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Jurisdictions</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Compliance repository by city &amp; state
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowCreateForm(v => !v)}
            className="px-4 py-2 text-[10px] tracking-[0.15em] uppercase font-mono text-white bg-white/10 border border-zinc-600 hover:bg-white/20 hover:border-zinc-400 transition-colors"
          >
            {showCreateForm ? 'Cancel' : '+ Add Jurisdiction'}
          </button>
          <button
            onClick={fetchData}
            disabled={loading}
            className="px-4 py-2 text-[10px] tracking-[0.15em] uppercase font-mono text-zinc-400 border border-zinc-700 hover:text-white hover:border-zinc-500 transition-colors disabled:opacity-50"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-sm font-mono">
          {error}
          <button onClick={() => setError(null)} className="ml-4 underline hover:text-red-300">Dismiss</button>
        </div>
      )}

      {/* Create Jurisdiction Form */}
      {showCreateForm && (
        <div className="border border-white/10 bg-zinc-900/50 p-6 space-y-4">
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold mb-3">
            New Jurisdiction
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-widest font-mono mb-1">City *</label>
              <input
                type="text"
                value={createForm.city}
                onChange={e => setCreateForm(f => ({ ...f, city: e.target.value }))}
                placeholder="e.g. manhattan"
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-sm text-white font-mono placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
              />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-widest font-mono mb-1">State *</label>
              <select
                value={createForm.state}
                onChange={e => setCreateForm(f => ({ ...f, state: e.target.value }))}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-sm text-white font-mono focus:outline-none focus:border-zinc-500"
              >
                <option value="">Select state</option>
                {US_STATES.map(s => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-widest font-mono mb-1">County</label>
              <input
                type="text"
                value={createForm.county || ''}
                onChange={e => setCreateForm(f => ({ ...f, county: e.target.value }))}
                placeholder="optional"
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-sm text-white font-mono placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
              />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 uppercase tracking-widest font-mono mb-1">Parent</label>
              <select
                value={createForm.parent_id || ''}
                onChange={e => setCreateForm(f => ({ ...f, parent_id: e.target.value || undefined }))}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-sm text-white font-mono focus:outline-none focus:border-zinc-500"
              >
                <option value="">None (top-level)</option>
                {jurisdictions.map(j => (
                  <option key={j.id} value={j.id}>{j.city}, {j.state}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex justify-end">
            <button
              onClick={handleCreate}
              disabled={creating || !createForm.city.trim() || !createForm.state}
              className="px-4 py-2 text-[10px] tracking-[0.15em] uppercase font-mono text-white bg-white/10 border border-zinc-600 hover:bg-white/20 transition-colors disabled:opacity-50"
            >
              {creating ? 'Creating...' : 'Create Jurisdiction'}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse font-mono">Loading...</div>
        </div>
      ) : (
        <>
          {/* Stats */}
          {totals && stats && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {[
                { label: 'Jurisdictions', value: totals.total_jurisdictions },
                { label: 'Requirements', value: totals.total_requirements },
                { label: 'Legislation', value: totals.total_legislation },
                { label: 'Checks (24h)', value: stats.overview.checks_24h },
                { label: 'Failed (24h)', value: stats.overview.failed_24h, alert: stats.overview.failed_24h > 0 },
              ].map((stat) => (
                <div key={stat.label} className="bg-zinc-900/50 border border-white/10 p-4">
                  <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono mb-2">{stat.label}</div>
                  <div className={`text-2xl font-bold font-mono ${'alert' in stat && stat.alert ? 'text-red-400' : 'text-white'}`}>
                    {stat.value}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Scheduler Job Cards */}
          <div className="space-y-4">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold">
              Scheduled Jobs
            </div>
            {schedulers.map((sched) => (
              <div key={sched.task_key} className="bg-zinc-900/50 border border-white/10">
                <div className="p-6">
                  <div className="flex items-start justify-between gap-4">
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
                    <div className="flex items-center gap-3 flex-shrink-0">
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
                      <button
                        onClick={() => handleTrigger(sched.task_key)}
                        disabled={triggering === sched.task_key}
                        className="px-3 py-1.5 text-[10px] tracking-[0.15em] uppercase font-mono text-white bg-zinc-800 border border-zinc-700 hover:bg-zinc-700 hover:border-zinc-500 transition-colors disabled:opacity-50"
                      >
                        {triggering === sched.task_key ? 'Triggering...' : 'Run Now'}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Jurisdictions Table */}
          {jurisdictions.length > 0 && (
            <div className="space-y-3">
              <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold">
                Jurisdictions
              </div>
              <div className="border border-white/10 bg-zinc-900/30 divide-y divide-white/5">
                {jurisdictions.map((j) => {
                  const isExpanded = expanded === j.id;
                  const detail = detailCache[j.id];
                  const isLoading = detailLoading === j.id;
                  return (
                    <div key={j.id} className="relative">
                      <button
                        onClick={() => handleExpand(j.id)}
                        className="w-full flex items-center justify-between px-4 py-3 pr-28 hover:bg-white/5 transition-colors text-left"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className={`text-[10px] font-mono transition-transform ${isExpanded ? 'rotate-90' : ''}`}>&#9654;</span>
                          <span className="text-sm text-white font-medium">
                            {j.city}, {j.state}
                          </span>
                          {j.county && (
                            <span className="text-[9px] text-zinc-600 font-mono">({j.county} County)</span>
                          )}
                          {j.parent_id && j.parent_city && (
                            <span className="text-[8px] px-1.5 py-0.5 font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20">
                              child of {j.parent_city}, {j.parent_state}
                            </span>
                          )}
                          {j.children_count > 0 && (
                            <span className="text-[8px] px-1.5 py-0.5 font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20">
                              {j.children_count} {j.children_count === 1 ? 'child' : 'children'}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-4 flex-shrink-0">
                          <div className="text-right">
                            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Reqs</div>
                            <div className="text-xs text-zinc-300 font-mono font-bold">{j.requirement_count}</div>
                          </div>
                          <div className="text-right">
                            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Leg.</div>
                            <div className="text-xs text-zinc-300 font-mono font-bold">{j.legislation_count}</div>
                          </div>
                          <div className="text-right">
                            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Locations</div>
                            <div className="text-xs text-zinc-300 font-mono font-bold">{j.location_count}</div>
                          </div>
                          <div className="text-right min-w-[80px]">
                            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Verified</div>
                            <div className="text-xs text-zinc-400 font-mono">{formatRelative(j.last_verified_at)}</div>
                          </div>
                          <span className={`text-[9px] px-2 py-0.5 uppercase tracking-wider font-bold border ${
                            j.requirement_count > 0
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                              : 'bg-zinc-700/30 text-zinc-500 border-zinc-600/30'
                          }`}>
                            {j.requirement_count > 0 ? 'Populated' : 'Empty'}
                          </span>
                        </div>
                      </button>
                      {/* Research button — outside the expand toggle */}
                      <div className="absolute top-2 right-4 z-10">
                        <button
                          onClick={(e) => { e.stopPropagation(); handleCheck(j.id); }}
                          disabled={checkingId !== null}
                          className={`group relative px-3 py-1.5 text-[9px] tracking-[0.12em] uppercase font-mono border bg-zinc-900 transition-all duration-300 overflow-hidden ${
                            checkingId === j.id
                              ? 'text-blue-300 border-blue-500/40'
                              : 'text-zinc-400 border-zinc-700 hover:text-white hover:border-zinc-400 disabled:opacity-30'
                          }`}
                        >
                          {checkingId === j.id && (
                            <span className="absolute inset-0 bg-gradient-to-r from-transparent via-blue-500/10 to-transparent" style={{ animation: 'scanX 1.5s ease-in-out infinite' }} />
                          )}
                          <span className="relative flex items-center gap-1.5">
                            {checkingId === j.id ? (
                              <>
                                <svg className="w-3 h-3 animate-spin" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" strokeDasharray="28" strokeDashoffset="8" strokeLinecap="round" /></svg>
                                Researching
                              </>
                            ) : 'Research'}
                          </span>
                        </button>
                      </div>
                      {/* Check progress panel */}
                      {isExpanded && checkTargetId === j.id && checkMessages.length > 0 && (() => {
                        const isActive = checkingId === j.id;
                        const completed = checkMessages.find(m => m.type === 'completed');
                        const hasError = checkMessages.some(m => m.type === 'error');
                        const resultCount = checkMessages.filter(m => m.type === 'result').length;
                        return (
                        <div className="border-t border-white/5 overflow-hidden">
                          {/* Scanning progress bar */}
                          {isActive && (
                            <div className="h-[2px] w-full bg-zinc-800 overflow-hidden">
                              <div className="h-full w-1/3 bg-gradient-to-r from-transparent via-blue-400 to-transparent" style={{ animation: 'scanX 1.2s ease-in-out infinite' }} />
                            </div>
                          )}
                          {/* Completed glow bar */}
                          {completed && !isActive && (
                            <div className="h-[2px] w-full bg-emerald-500/60" style={{ animation: 'fadeIn 0.4s ease-out' }} />
                          )}
                          {/* Error bar */}
                          {hasError && !isActive && (
                            <div className="h-[2px] w-full bg-red-500/60" style={{ animation: 'fadeIn 0.4s ease-out' }} />
                          )}

                          {/* Legend */}
                          {resultCount > 0 && (
                            <div className="flex items-center gap-4 px-6 pt-3 pb-2 border-b border-white/5 bg-zinc-950/40" style={{ animation: 'fadeSlideDown 0.3s ease-out' }}>
                              <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold text-zinc-600">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> New
                              </span>
                              <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold text-zinc-600">
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" /> Updated
                              </span>
                              <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold text-zinc-600">
                                <span className="w-1.5 h-1.5 rounded-full bg-zinc-600" /> Existing
                              </span>
                              {isActive && <span className="ml-auto text-[10px] text-zinc-600 font-mono tabular-nums">{resultCount} found</span>}
                            </div>
                          )}

                          {/* Messages */}
                          <div className="max-h-56 overflow-y-auto bg-zinc-950/30">
                            {checkMessages.map((msg, i) => {
                              const isLast = i === checkMessages.length - 1;
                              const isResult = msg.type === 'result';
                              return (
                              <div
                                key={i}
                                className="flex items-center gap-2.5 text-xs font-mono px-6 py-1.5 transition-colors duration-150 hover:bg-white/[0.02]"
                                style={{ animation: `fadeSlideDown 0.25s ease-out ${Math.min(i * 0.04, 0.4)}s both` }}
                              >
                                {/* Icon */}
                                {msg.type === 'error' ? (
                                  <span className="w-4 h-4 flex items-center justify-center flex-shrink-0 text-red-400">
                                    <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
                                  </span>
                                ) : msg.type === 'completed' ? (
                                  <span className="w-4 h-4 flex items-center justify-center flex-shrink-0 text-emerald-400" style={{ animation: 'popIn 0.3s ease-out' }}>
                                    <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none"><path d="M3 8.5l3.5 3.5L13 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                                  </span>
                                ) : isActive && isLast ? (
                                  <span className="w-4 h-4 flex items-center justify-center flex-shrink-0">
                                    <span className="relative flex h-2.5 w-2.5">
                                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-40" />
                                      <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-400" />
                                    </span>
                                  </span>
                                ) : (
                                  <span className="w-4 h-4 flex items-center justify-center flex-shrink-0 text-zinc-700">
                                    <svg className="w-3 h-3" viewBox="0 0 16 16" fill="none"><path d="M3 8.5l3.5 3.5L13 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                                  </span>
                                )}

                                {/* Status badge for results */}
                                {isResult && msg.status && (
                                  <span className={`text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 border flex-shrink-0 ${
                                    msg.status === 'new' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25' :
                                    msg.status === 'updated' ? 'bg-amber-500/15 text-amber-400 border-amber-500/25' :
                                    'bg-zinc-800/60 text-zinc-500 border-zinc-700/40'
                                  }`} style={{ animation: `fadeSlideDown 0.2s ease-out` }}>
                                    {msg.status === 'existing' ? 'same' : msg.status}
                                  </span>
                                )}

                                {/* Phase badge for non-result steps */}
                                {!isResult && msg.type !== 'completed' && msg.type !== 'error' && msg.type !== 'started' && (
                                  <span className={`text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 border flex-shrink-0 ${
                                    msg.type === 'researching' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                    msg.type === 'scanning' ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                                    msg.type === 'verifying' ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' :
                                    msg.type === 'legislation' ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                                    'bg-zinc-800/60 text-zinc-500 border-zinc-700/40'
                                  }`}>
                                    {msg.type}
                                  </span>
                                )}

                                {/* Message text */}
                                <span className={`truncate ${
                                  msg.type === 'error' ? 'text-red-400' :
                                  msg.type === 'completed' ? 'text-emerald-300 font-medium' :
                                  isResult && msg.status === 'new' ? 'text-emerald-300/80' :
                                  isResult && msg.status === 'updated' ? 'text-amber-300/80' :
                                  isActive && isLast ? 'text-zinc-200' :
                                  isResult ? 'text-zinc-500' :
                                  'text-zinc-500'
                                }`}>
                                  {msg.type === 'completed'
                                    ? `Complete — ${msg.new ?? 0} requirements, ${msg.updated ?? 0} updated`
                                    : msg.message || msg.location || ''}
                                </span>
                              </div>
                              );
                            })}
                          </div>

                          {/* Completed summary */}
                          {completed && !isActive && (
                            <div className="px-6 py-3 border-t border-emerald-500/10 bg-emerald-500/[0.03]" style={{ animation: 'fadeSlideDown 0.4s ease-out' }}>
                              <div className="flex items-center gap-4">
                                <div className="flex items-center gap-2">
                                  <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-40 animate-ping" style={{ animationDuration: '2s' }} /><span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" /></span>
                                  <span className="text-[10px] uppercase tracking-widest font-mono font-bold text-emerald-400">Research Complete</span>
                                </div>
                                <div className="flex items-center gap-3 ml-auto text-[11px] font-mono">
                                  <span className="text-emerald-400">{completed.new ?? 0} <span className="text-zinc-600">reqs</span></span>
                                  <span className="text-amber-400">{completed.updated ?? 0} <span className="text-zinc-600">updated</span></span>
                                  <span className="text-zinc-500">{completed.alerts ?? 0} <span className="text-zinc-600">alerts</span></span>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                        );
                      })()}
                      {isExpanded && isLoading && (
                        <div className="border-t border-white/5 overflow-hidden">
                          <div className="h-[2px] w-full bg-zinc-800 overflow-hidden">
                            <div className="h-full w-1/4 bg-gradient-to-r from-transparent via-zinc-500 to-transparent" style={{ animation: 'scanX 1s ease-in-out infinite' }} />
                          </div>
                          <div className="px-6 py-5 flex items-center justify-center gap-2">
                            <span className="relative flex h-2 w-2"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-zinc-400 opacity-30" /><span className="relative inline-flex rounded-full h-2 w-2 bg-zinc-500" /></span>
                            <span className="text-xs text-zinc-500 uppercase tracking-wider font-mono">Loading detail</span>
                          </div>
                        </div>
                      )}
                      {isExpanded && detail && (
                        <JurisdictionDetailPanel
                          detail={detail}
                          parentJurisdiction={detail.parent_id ? jurisdictions.find(p => p.id === detail.parent_id) : null}
                          onNavigate={handleNavigate}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {jurisdictions.length === 0 && !loading && (
            <div className="border border-white/10 bg-zinc-900/30 p-8 text-center">
              <div className="text-xs text-zinc-500 font-mono">No jurisdictions yet. They are created automatically when locations are added.</div>
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

export default Jurisdictions;
