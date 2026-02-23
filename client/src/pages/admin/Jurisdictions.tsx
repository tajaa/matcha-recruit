import { useState, useEffect, useCallback, useMemo } from 'react';
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

function formatInheritanceParent(city: string, state: string | null): string {
  const normalized = city.trim().toLowerCase();
  const cityLabel = normalized === 'los angeles' ? 'LA' : city;
  return state ? `${cityLabel}, ${state}` : cityLabel;
}

function displayCity(city: string): string {
  if (!city.trim()) return '(unnamed)';
  return city
    .replace(/^_county_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

const categoryLabel: Record<string, string> = {
  minimum_wage: 'Minimum Wage',
  overtime: 'Overtime',
  sick_leave: 'Sick Leave',
  meal_breaks: 'Meal & Rest Breaks',
  pay_frequency: 'Pay Frequency',
  final_pay: 'Final Pay',
  minor_work_permit: 'Minor Work Permits',
  scheduling_reporting: 'Scheduling & Reporting Time',
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

type CheckMessage = {
  type: string;
  status?: string;
  message?: string;
  location?: string;
  new?: number;
  updated?: number;
  alerts?: number;
  confidence?: number;
  low_confidence?: number;
};

type MetroRunCity = {
  city: string;
  state: string;
  phase: string;
  percent: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  message: string;
  newCount: number;
  updatedCount: number;
  alerts: number;
  lowConfidence: number;
};

function JurisdictionDetailPanel({ detail, parentJurisdiction, onNavigate, inheritsFromParent }: {
  detail: JurisdictionDetail;
  parentJurisdiction?: Jurisdiction | null;
  onNavigate?: (id: string) => void;
  inheritsFromParent?: boolean;
}) {
  const [tab, setTab] = useState<DetailTab>('requirements');

  const hasMetroGroup = detail.parent_id || detail.children.length > 0;

  const tabs: { key: DetailTab; label: string; count: number }[] = [
    { key: 'requirements', label: 'Requirements', count: detail.requirements.length },
    { key: 'legislation', label: 'Legislation', count: detail.legislation.length },
    { key: 'locations', label: 'Locations', count: detail.locations.length },
  ];

  const reqsByCategory: Record<string, JurisdictionRequirement[]> = {};
  for (const r of detail.requirements) {
    const cat = r.category || 'other';
    if (!reqsByCategory[cat]) reqsByCategory[cat] = [];
    reqsByCategory[cat].push(r);
  }

  return (
    <div className="border-t border-white/5 bg-zinc-950/50">
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

      {inheritsFromParent && detail.parent_id && parentJurisdiction && (
        <div className="px-6 py-2 border-b border-emerald-500/20 bg-emerald-500/[0.04]">
          <span className="text-[10px] font-mono uppercase tracking-widest text-emerald-300">
            Inherits from {formatInheritanceParent(parentJurisdiction.city, parentJurisdiction.state)}
          </span>
        </div>
      )}

      <div className="flex overflow-x-auto border-b border-white/5 bg-zinc-900/40">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-5 py-2.5 text-[9px] uppercase tracking-[0.2em] font-mono font-bold transition-colors whitespace-nowrap border-b-2 ${
              tab === t.key
                ? 'text-white border-white bg-white/[0.03]'
                : 'text-zinc-500 border-transparent hover:text-zinc-300'
            }`}
          >
            {t.label} <span className="text-zinc-600 ml-1">{t.count}</span>
          </button>
        ))}
      </div>

      {tab === 'requirements' && (
        <div className="divide-y divide-white/5">
          {detail.requirements.length === 0 && (
            <div className="px-6 py-4 text-xs text-zinc-600 font-mono italic">No requirements yet</div>
          )}
          {Object.entries(reqsByCategory).map(([cat, reqs]) => (
            <div key={cat}>
              <div className="px-6 py-2 bg-zinc-900/80 flex items-center gap-2">
                <span className="text-[9px] uppercase tracking-widest font-mono font-bold text-zinc-500">
                  {categoryLabel[cat] || cat.replace(/_/g, ' ')}
                </span>
                <span className="text-[9px] text-zinc-700 font-mono">{reqs.length}</span>
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
                    <div className="text-right flex-shrink-0 min-w-[90px]">
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
                <div className="text-right flex-shrink-0 min-w-[90px]">
                  {l.expected_effective_date && (
                    <div className="text-xs text-zinc-300 font-mono">{l.expected_effective_date}</div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === 'locations' && (
        <div className="divide-y divide-white/5">
          {detail.locations.length === 0 && (
            <div className="px-6 py-4 text-xs text-zinc-600 font-mono italic">No linked locations</div>
          )}
          {detail.locations.map((loc: JurisdictionLocation) => (
            <div key={loc.id} className="px-6 py-3 flex flex-wrap items-center gap-x-6 gap-y-2 hover:bg-white/[0.02]">
              <div className="min-w-[160px] flex-1">
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

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 mb-3">
      <span className="text-[9px] uppercase tracking-[0.2em] font-mono font-bold text-zinc-500 shrink-0">{children}</span>
      <div className="flex-1 h-px bg-white/[0.06]" />
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
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [checkingId, setCheckingId] = useState<string | null>(null);
  const [checkTargetId, setCheckTargetId] = useState<string | null>(null);
  const [checkMessages, setCheckMessages] = useState<CheckMessage[]>([]);
  const [topMetroRunning, setTopMetroRunning] = useState(false);
  const [topMetroCities, setTopMetroCities] = useState<Record<string, MetroRunCity>>({});
  const [topMetroOrder, setTopMetroOrder] = useState<string[]>([]);
  const [topMetroSummary, setTopMetroSummary] = useState<{
    total: number;
    succeeded: number;
    failed: number;
    low_confidence_total: number;
  } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [search, setSearch] = useState('');

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

  const filteredJurisdictions = useMemo(() => {
    if (!search.trim()) return jurisdictions;
    const q = search.trim().toLowerCase();
    return jurisdictions.filter(j =>
      j.city.toLowerCase().includes(q) ||
      (j.state && j.state.toLowerCase().includes(q)) ||
      (j.county && j.county.toLowerCase().includes(q))
    );
  }, [jurisdictions, search]);

  const groupedByState = useMemo(() => {
    const groups: Record<string, Jurisdiction[]> = {};
    for (const j of filteredJurisdictions) {
      const key = j.state || '—';
      if (!groups[key]) groups[key] = [];
      groups[key].push(j);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [filteredJurisdictions]);

  const topMetroRows = useMemo(() => {
    const all = Object.values(topMetroCities);
    if (topMetroOrder.length === 0) return all;
    const ordered = [...all].sort((a, b) => {
      const aIndex = topMetroOrder.indexOf(a.city);
      const bIndex = topMetroOrder.indexOf(b.city);
      const aRank = aIndex === -1 ? Number.MAX_SAFE_INTEGER : aIndex;
      const bRank = bIndex === -1 ? Number.MAX_SAFE_INTEGER : bIndex;
      return aRank - bRank;
    });
    return ordered;
  }, [topMetroCities, topMetroOrder]);

  const topMetroCompletedCount = useMemo(
    () => topMetroRows.filter((row) => row.status === 'completed' || row.status === 'failed').length,
    [topMetroRows],
  );

  const topMetroGlobalPercent = useMemo(() => {
    if (topMetroSummary && topMetroSummary.total > 0) {
      return Math.round(((topMetroSummary.succeeded + topMetroSummary.failed) / topMetroSummary.total) * 100);
    }
    if (topMetroRows.length === 0) return 0;
    return Math.round((topMetroCompletedCount / topMetroRows.length) * 100);
  }, [topMetroSummary, topMetroRows, topMetroCompletedCount]);

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
      setTimeout(() => {
        setDetailCache({});
        fetchData();
      }, 2000);
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
    setNotice(null);
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
      setNotice('Jurisdiction created.');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create jurisdiction';
      setError(msg);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (jurisdiction: Jurisdiction) => {
    if (deletingId || checkingId) return;
    setError(null);
    setNotice(null);

    if (jurisdiction.location_count > 0) {
      setError(
        `Cannot delete ${jurisdiction.city}, ${jurisdiction.state} while ${jurisdiction.location_count} location(s) are linked.`,
      );
      return;
    }

    const confirmMessage = jurisdiction.children_count > 0
      ? `Delete ${jurisdiction.city}, ${jurisdiction.state}? This will detach ${jurisdiction.children_count} child jurisdiction(s).`
      : `Delete ${jurisdiction.city}, ${jurisdiction.state}?`;
    if (!window.confirm(confirmMessage)) return;

    setDeletingId(jurisdiction.id);
    try {
      const result = await adminJurisdictions.delete(jurisdiction.id);
      setDetailCache((prev) => {
        const next = { ...prev };
        delete next[jurisdiction.id];
        return next;
      });
      if (expanded === jurisdiction.id) setExpanded(null);
      if (checkTargetId === jurisdiction.id) {
        setCheckTargetId(null);
        setCheckMessages([]);
      }
      await fetchData();
      setNotice(
        result.detached_children > 0
          ? `Deleted ${result.city}, ${result.state}. Detached ${result.detached_children} child jurisdictions.`
          : `Deleted ${result.city}, ${result.state}.`,
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete jurisdiction';
      setError(msg);
    } finally {
      setDeletingId(null);
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
    if (topMetroRunning || checkingId) return;
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
      setDetailCache({});
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to run jurisdiction check';
      setCheckMessages(prev => [...prev, { type: 'error', message: msg }]);
    } finally {
      setCheckingId(null);
    }
  };

  const handleRunTopMetros = async () => {
    if (topMetroRunning || checkingId || deletingId) return;

    setTopMetroRunning(true);
    setError(null);
    setNotice(null);
    setTopMetroCities({});
    setTopMetroOrder([]);
    setTopMetroSummary(null);

    const keyFor = (city: string, state: string) => `${city}__${state}`;

    try {
      const response = await adminJurisdictions.checkTopMetros();
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
            const event = JSON.parse(payload) as Record<string, unknown>;
            const eventType = String(event.type || '');

            if (eventType === 'run_started') {
              const metros = Array.isArray(event.metros)
                ? event.metros.filter((item): item is string => typeof item === 'string')
                : [];
              if (metros.length > 0) {
                setTopMetroOrder(metros);
              }
              continue;
            }

            if (eventType === 'city_started') {
              const city = String(event.city || '');
              const state = String(event.state || '');
              const key = keyFor(city, state);
              setTopMetroOrder((prev) => (prev.includes(city) ? prev : [...prev, city]));
              setTopMetroCities((prev) => ({
                ...prev,
                [key]: {
                  city,
                  state,
                  phase: 'started',
                  percent: 5,
                  status: 'running',
                  message: '',
                  newCount: 0,
                  updatedCount: 0,
                  alerts: 0,
                  lowConfidence: 0,
                },
              }));
              continue;
            }

            if (eventType === 'city_progress') {
              const city = String(event.city || '');
              const state = String(event.state || '');
              const key = keyFor(city, state);
              const percent = Number(event.percent || 0);
              const phase = String(event.phase || 'running');
              const message = String(event.message || '');
              setTopMetroCities((prev) => {
                const current = prev[key] || {
                  city,
                  state,
                  phase: 'running',
                  percent: 0,
                  status: 'running' as const,
                  message: '',
                  newCount: 0,
                  updatedCount: 0,
                  alerts: 0,
                  lowConfidence: 0,
                };
                return {
                  ...prev,
                  [key]: {
                    ...current,
                    status: 'running',
                    phase,
                    percent: Math.max(current.percent, Number.isFinite(percent) ? percent : current.percent),
                    message: message || current.message,
                  },
                };
              });
              continue;
            }

            if (eventType === 'city_completed') {
              const city = String(event.city || '');
              const state = String(event.state || '');
              const key = keyFor(city, state);
              const newCount = Number(event.new || 0);
              const updatedCount = Number(event.updated || 0);
              const alerts = Number(event.alerts || 0);
              const lowConfidence = Number(event.low_confidence || 0);
              setTopMetroCities((prev) => {
                const current = prev[key];
                return {
                  ...prev,
                  [key]: {
                    city,
                    state,
                    phase: 'completed',
                    percent: 100,
                    status: 'completed',
                    message: current?.message || 'Complete',
                    newCount,
                    updatedCount,
                    alerts,
                    lowConfidence,
                  },
                };
              });
              continue;
            }

            if (eventType === 'city_failed') {
              const city = String(event.city || '');
              const state = String(event.state || '');
              const key = keyFor(city, state);
              const message = String(event.message || 'Failed');
              setTopMetroCities((prev) => {
                const current = prev[key];
                return {
                  ...prev,
                  [key]: {
                    city,
                    state,
                    phase: 'failed',
                    percent: current?.percent || 100,
                    status: 'failed',
                    message,
                    newCount: current?.newCount || 0,
                    updatedCount: current?.updatedCount || 0,
                    alerts: current?.alerts || 0,
                    lowConfidence: current?.lowConfidence || 0,
                  },
                };
              });
              continue;
            }

            if (eventType === 'run_completed') {
              setTopMetroSummary({
                total: Number(event.total || 0),
                succeeded: Number(event.succeeded || 0),
                failed: Number(event.failed || 0),
                low_confidence_total: Number(event.low_confidence_total || 0),
              });
            }
          } catch {
            // skip malformed event
          }
        }
      }

      setDetailCache({});
      await fetchData();
      setNotice('Top-15 metro batch run complete.');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to run top-metro batch check';
      setError(msg);
    } finally {
      setTopMetroRunning(false);
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
    <div className="max-w-7xl mx-auto space-y-6">
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
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-3 border-b border-white/10 pb-6 md:pb-8">
        <div>
          <h1 className="text-2xl md:text-4xl font-bold tracking-tighter text-white uppercase">Jurisdictions</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Compliance repository by city &amp; state
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => { void handleRunTopMetros(); }}
            disabled={topMetroRunning || checkingId !== null || deletingId !== null}
            className="px-3 md:px-4 py-2 text-[10px] tracking-[0.15em] uppercase font-mono text-blue-300 bg-blue-500/10 border border-blue-500/30 hover:bg-blue-500/20 hover:border-blue-400/50 transition-colors disabled:opacity-50"
          >
            {topMetroRunning ? 'Running Top 15...' : 'Run Top 15'}
          </button>
          <button
            onClick={() => setShowCreateForm(v => !v)}
            className="px-3 md:px-4 py-2 text-[10px] tracking-[0.15em] uppercase font-mono text-white bg-white/10 border border-zinc-600 hover:bg-white/20 hover:border-zinc-400 transition-colors"
          >
            {showCreateForm ? 'Cancel' : '+ Add'}
          </button>
          <button
            onClick={fetchData}
            disabled={loading}
            className="px-3 md:px-4 py-2 text-[10px] tracking-[0.15em] uppercase font-mono text-zinc-400 border border-zinc-700 hover:text-white hover:border-zinc-500 transition-colors disabled:opacity-50"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Banners */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-sm font-mono flex items-center justify-between gap-4">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-[10px] uppercase tracking-wider underline hover:text-red-300 shrink-0">Dismiss</button>
        </div>
      )}
      {notice && (
        <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-sm font-mono flex items-center justify-between gap-4">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="text-[10px] uppercase tracking-wider underline hover:text-emerald-200 shrink-0">Dismiss</button>
        </div>
      )}

      {(topMetroRunning || topMetroRows.length > 0 || topMetroSummary) && (
        <div className="border border-blue-500/20 bg-blue-500/[0.04]">
          <div className="px-4 py-3 border-b border-blue-500/20 space-y-2">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[10px] uppercase tracking-[0.2em] font-mono font-bold text-blue-300">
                Top-15 Metro Batch Check
              </div>
              <div className="text-[10px] font-mono text-blue-200">
                {(topMetroSummary?.total || topMetroRows.length) > 0
                  ? `${topMetroCompletedCount}/${topMetroSummary?.total || topMetroRows.length}`
                  : '0/15'}
              </div>
            </div>
            <div className="h-1 bg-zinc-900 border border-blue-500/20 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-blue-500/60 via-cyan-400/70 to-emerald-400/70 transition-all"
                style={{ width: `${Math.max(0, Math.min(100, topMetroGlobalPercent))}%` }}
              />
            </div>
            {topMetroSummary && (
              <div className="flex flex-wrap items-center gap-3 text-[10px] font-mono">
                <span className="text-emerald-300">{topMetroSummary.succeeded} complete</span>
                <span className="text-red-300">{topMetroSummary.failed} failed</span>
                <span className="text-amber-300">{topMetroSummary.low_confidence_total} below 95%</span>
              </div>
            )}
          </div>
          {topMetroRows.length > 0 && (
            <div className="max-h-72 overflow-y-auto divide-y divide-blue-500/10">
              {topMetroRows.map((row) => (
                <div key={`${row.city}-${row.state}`} className="px-4 py-3 space-y-1.5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-xs text-zinc-100 font-mono">{row.city}{row.state ? `, ${row.state}` : ''}</div>
                    <div className={`text-[9px] uppercase tracking-wider font-bold border px-1.5 py-0.5 ${
                      row.status === 'completed'
                        ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                        : row.status === 'failed'
                          ? 'bg-red-500/10 text-red-300 border-red-500/20'
                          : 'bg-blue-500/10 text-blue-300 border-blue-500/20'
                    }`}>
                      {row.status}
                    </div>
                  </div>
                  <div className="h-1 bg-zinc-900 border border-blue-500/10 overflow-hidden">
                    <div
                      className={`h-full transition-all ${
                        row.status === 'failed' ? 'bg-red-500/70' : 'bg-blue-400/70'
                      }`}
                      style={{ width: `${Math.max(0, Math.min(100, row.percent))}%` }}
                    />
                  </div>
                  <div className="text-[10px] text-zinc-400 font-mono truncate">
                    {row.message || row.phase}
                  </div>
                  {(row.newCount > 0 || row.updatedCount > 0 || row.alerts > 0 || row.lowConfidence > 0) && (
                    <div className="flex flex-wrap gap-3 text-[10px] font-mono">
                      {row.newCount > 0 && <span className="text-emerald-300">{row.newCount} new</span>}
                      {row.updatedCount > 0 && <span className="text-amber-300">{row.updatedCount} updated</span>}
                      {row.alerts > 0 && <span className="text-red-300">{row.alerts} alerts</span>}
                      {row.lowConfidence > 0 && <span className="text-amber-200">{row.lowConfidence} below 95%</span>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Create form */}
      {showCreateForm && (
        <div className="border border-white/10 bg-zinc-900/60 p-6 space-y-4">
          <div className="text-[9px] uppercase tracking-[0.2em] font-mono font-bold text-zinc-400">New Jurisdiction</div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-[9px] text-zinc-500 uppercase tracking-widest font-mono mb-1.5">City *</label>
              <input
                type="text"
                value={createForm.city}
                onChange={e => setCreateForm(f => ({ ...f, city: e.target.value }))}
                placeholder="e.g. manhattan"
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-sm text-white font-mono placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 transition-colors"
              />
            </div>
            <div>
              <label className="block text-[9px] text-zinc-500 uppercase tracking-widest font-mono mb-1.5">State *</label>
              <select
                value={createForm.state}
                onChange={e => setCreateForm(f => ({ ...f, state: e.target.value }))}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-sm text-white font-mono focus:outline-none focus:border-zinc-500 transition-colors"
              >
                <option value="">Select state</option>
                {US_STATES.map(s => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[9px] text-zinc-500 uppercase tracking-widest font-mono mb-1.5">County</label>
              <input
                type="text"
                value={createForm.county || ''}
                onChange={e => setCreateForm(f => ({ ...f, county: e.target.value }))}
                placeholder="optional"
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-sm text-white font-mono placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 transition-colors"
              />
            </div>
            <div>
              <label className="block text-[9px] text-zinc-500 uppercase tracking-widest font-mono mb-1.5">Parent</label>
              <select
                value={createForm.parent_id || ''}
                onChange={e => setCreateForm(f => ({ ...f, parent_id: e.target.value || undefined }))}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-sm text-white font-mono focus:outline-none focus:border-zinc-500 transition-colors"
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
        <div className="flex items-center justify-center py-32">
          <div className="flex items-center gap-3">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-zinc-400 opacity-30" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-zinc-500" />
            </span>
            <span className="text-xs text-zinc-500 uppercase tracking-widest font-mono">Loading</span>
          </div>
        </div>
      ) : (
        <>
          {/* Stats strip */}
          {totals && stats && (
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-px bg-white/[0.06] border border-white/[0.06]">
              {[
                { label: 'Jurisdictions', value: totals.total_jurisdictions, dim: false },
                { label: 'Requirements', value: totals.total_requirements, dim: false },
                { label: 'Legislation', value: totals.total_legislation, dim: false },
                { label: 'Checks (24h)', value: stats.overview.checks_24h, dim: false },
                { label: 'Failed (24h)', value: stats.overview.failed_24h, dim: false, alert: stats.overview.failed_24h > 0 },
              ].map((stat) => (
                <div key={stat.label} className="bg-zinc-950 px-5 py-4">
                  <div className="text-[9px] text-zinc-500 uppercase tracking-widest font-mono mb-2">{stat.label}</div>
                  <div className={`text-2xl font-bold font-mono tabular-nums ${'alert' in stat && stat.alert ? 'text-red-400' : 'text-white'}`}>
                    {stat.value}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Main two-column layout */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 items-start">

            {/* Jurisdictions list — 2/3 width on xl */}
            <div className="xl:col-span-2 space-y-3">
              <SectionLabel>
                Jurisdictions{jurisdictions.length > 0 ? ` (${jurisdictions.length})` : ''}
              </SectionLabel>

              {/* Search */}
              {jurisdictions.length > 0 && (
                <div className="flex items-center gap-3">
                  <div className="relative flex-1">
                    <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <input
                      type="text"
                      value={search}
                      onChange={e => setSearch(e.target.value)}
                      placeholder="Filter by city, state, or county..."
                      className="w-full pl-9 pr-3 py-2 bg-zinc-900 border border-zinc-800 text-xs text-white font-mono placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors"
                    />
                  </div>
                  {search && (
                    <span className="text-[10px] font-mono text-zinc-500 shrink-0">
                      {filteredJurisdictions.length}/{jurisdictions.length}
                    </span>
                  )}
                </div>
              )}

              {/* List */}
              {jurisdictions.length === 0 ? (
                <div className="border border-white/10 bg-zinc-900/30 p-8 text-center">
                  <div className="text-xs text-zinc-500 font-mono">No jurisdictions yet. They are created automatically when locations are added.</div>
                </div>
              ) : filteredJurisdictions.length === 0 ? (
                <div className="border border-white/10 bg-zinc-900/30 p-6 text-center">
                  <div className="text-xs text-zinc-500 font-mono">No jurisdictions match "{search}"</div>
                </div>
              ) : (
                <div className="border border-white/10 divide-y divide-white/[0.05]">
                  {/* Column header */}
                  <div className="hidden xl:flex items-center gap-2 px-4 py-2 bg-zinc-950/70 border-b border-white/[0.05]">
                    <div className="flex-1 min-w-0" />
                    <div className="flex items-center gap-4 shrink-0">
                      <div className="w-10 text-right text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Reqs</div>
                      <div className="w-10 text-right text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Leg</div>
                      <div className="w-10 text-right text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Locs</div>
                      <div className="w-16 text-right text-[9px] text-zinc-600 uppercase tracking-widest font-mono">Verified</div>
                    </div>
                    <div className="hidden sm:block w-[77px]" />
                    <div className="flex items-center gap-1.5 shrink-0">
                      <div className="w-[88px]" />
                      <div className="w-7" />
                    </div>
                  </div>
                  {groupedByState.map(([state, stateJurisdictions]) => (
                    <div key={state}>
                      {/* State group header */}
                      <div className="flex items-center gap-3 px-4 py-2 bg-zinc-900/80 border-b border-white/[0.05]">
                        <span className="text-[9px] uppercase tracking-[0.2em] font-mono font-bold text-zinc-400">{state}</span>
                        <span className="text-[9px] font-mono text-zinc-600">{stateJurisdictions.length}</span>
                      </div>
                      {stateJurisdictions.map((j) => {
                    const isExpanded = expanded === j.id;
                    const detail = detailCache[j.id];
                    const isLoading = detailLoading === j.id;
                    return (
                      <div key={j.id} className={isExpanded ? 'bg-white/[0.015]' : ''}>
                        {/* Row */}
                        <div className="flex items-center gap-2 px-4 py-3 hover:bg-white/[0.03] transition-colors group">
                          {/* Expand + main info */}
                          <button
                            onClick={() => handleExpand(j.id)}
                            className="flex-1 min-w-0 flex items-center gap-2.5 text-left"
                          >
                            <span className={`text-[9px] font-mono text-zinc-600 shrink-0 transition-transform duration-150 ${isExpanded ? 'rotate-90' : ''}`}>▶</span>
                            <div className="min-w-0 flex items-center gap-2 flex-wrap">
                              <span className="text-sm text-white font-medium">{displayCity(j.city)}, {j.state}</span>
                              {j.county && <span className="text-[9px] text-zinc-600 font-mono hidden md:inline">({j.county})</span>}
                              {j.parent_id && j.parent_city && (
                                <span className={`text-[8px] px-1.5 py-0.5 font-mono border hidden sm:inline ${
                                  j.inherits_from_parent
                                    ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                                    : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                                }`}>
                                  {j.inherits_from_parent
                                    ? `inherits ${formatInheritanceParent(displayCity(j.parent_city), j.parent_state)}`
                                    : `↳ ${displayCity(j.parent_city)}`}
                                </span>
                              )}
                              {j.children_count > 0 && (
                                <span className="text-[8px] px-1.5 py-0.5 font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20 hidden lg:inline">
                                  {j.children_count} {j.children_count === 1 ? 'child' : 'children'}
                                </span>
                              )}
                            </div>
                          </button>

                          {/* Stats — desktop only */}
                          <div className="hidden xl:flex items-center gap-4 shrink-0">
                            <div className="w-10 text-right text-xs text-zinc-300 font-mono font-bold tabular-nums">{j.requirement_count}</div>
                            <div className="w-10 text-right text-xs text-zinc-300 font-mono font-bold tabular-nums">{j.legislation_count}</div>
                            <div className="w-10 text-right text-xs text-zinc-300 font-mono font-bold tabular-nums">{j.location_count}</div>
                            <div className="w-16 text-right text-xs text-zinc-500 font-mono">{formatRelative(j.last_verified_at)}</div>
                          </div>

                          {/* Status badge */}
                          <span className={`hidden sm:inline text-[8px] px-1.5 py-0.5 uppercase tracking-wider font-bold border shrink-0 ${
                            j.requirement_count > 0
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                              : 'bg-zinc-800/40 text-zinc-600 border-zinc-700/30'
                          }`}>
                            {j.requirement_count > 0 ? 'Populated' : 'Empty'}
                          </span>

                          {/* Actions */}
                          <div className="flex items-center gap-1.5 shrink-0">
                            <button
                              onClick={(e) => { e.stopPropagation(); handleCheck(j.id); }}
                              disabled={topMetroRunning || checkingId !== null || deletingId !== null}
                              className={`relative px-2.5 py-1.5 text-[9px] tracking-[0.1em] uppercase font-mono border overflow-hidden transition-all duration-200 ${
                                checkingId === j.id
                                  ? 'text-blue-300 border-blue-500/40 bg-blue-500/5'
                                  : 'text-zinc-500 border-zinc-700/60 hover:text-white hover:border-zinc-500 disabled:opacity-30'
                              }`}
                            >
                              {checkingId === j.id && (
                                <span className="absolute inset-0 bg-gradient-to-r from-transparent via-blue-500/10 to-transparent" style={{ animation: 'scanX 1.5s ease-in-out infinite' }} />
                              )}
                              <span className="relative flex items-center gap-1.5">
                                {checkingId === j.id ? (
                                  <>
                                    <svg className="w-3 h-3 animate-spin" viewBox="0 0 16 16" fill="none">
                                      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" strokeDasharray="28" strokeDashoffset="8" strokeLinecap="round" />
                                    </svg>
                                    <span className="hidden sm:inline">Scanning</span>
                                  </>
                                ) : (
                                  <>
                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                    </svg>
                                    <span className="hidden sm:inline">Research</span>
                                  </>
                                )}
                              </span>
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); void handleDelete(j); }}
                              disabled={topMetroRunning || checkingId !== null || deletingId !== null}
                              className={`p-1.5 border transition-colors disabled:opacity-30 ${
                                deletingId === j.id
                                  ? 'text-red-300 border-red-500/40 bg-red-500/5'
                                  : 'text-zinc-700 border-zinc-800 hover:text-red-400 hover:border-red-700/60'
                              }`}
                              title="Delete jurisdiction"
                            >
                              {deletingId === j.id ? (
                                <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 16 16" fill="none">
                                  <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" strokeDasharray="28" strokeDashoffset="8" strokeLinecap="round" />
                                </svg>
                              ) : (
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                              )}
                            </button>
                          </div>
                        </div>

                        {/* Check progress panel */}
                        {isExpanded && checkTargetId === j.id && checkMessages.length > 0 && (() => {
                          const isActive = checkingId === j.id;
                          const completed = checkMessages.find(m => m.type === 'completed');
                          const hasError = checkMessages.some(m => m.type === 'error');
                          const resultCount = checkMessages.filter(m => m.type === 'result').length;
                          return (
                            <div className="border-t border-white/5 overflow-hidden">
                              {isActive && (
                                <div className="h-[2px] w-full bg-zinc-800 overflow-hidden">
                                  <div className="h-full w-1/3 bg-gradient-to-r from-transparent via-blue-400 to-transparent" style={{ animation: 'scanX 1.2s ease-in-out infinite' }} />
                                </div>
                              )}
                              {completed && !isActive && (
                                <div className="h-[2px] w-full bg-emerald-500/60" style={{ animation: 'fadeIn 0.4s ease-out' }} />
                              )}
                              {hasError && !isActive && (
                                <div className="h-[2px] w-full bg-red-500/60" style={{ animation: 'fadeIn 0.4s ease-out' }} />
                              )}

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

                              <div className="max-h-56 overflow-y-auto bg-zinc-950/30">
                                {checkMessages.map((msg, i) => {
                                  const isLast = i === checkMessages.length - 1;
                                  const isResult = msg.type === 'result';
                                  return (
                                    <div
                                      key={i}
                                      className="flex items-center gap-2.5 text-xs font-mono px-6 py-1.5 hover:bg-white/[0.02]"
                                      style={{ animation: `fadeSlideDown 0.25s ease-out ${Math.min(i * 0.04, 0.4)}s both` }}
                                    >
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

                                      {isResult && msg.status && (
                                        <span className={`text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 border flex-shrink-0 ${
                                          msg.status === 'new' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25' :
                                          msg.status === 'updated' ? 'bg-amber-500/15 text-amber-400 border-amber-500/25' :
                                          'bg-zinc-800/60 text-zinc-500 border-zinc-700/40'
                                        }`}>
                                          {msg.status === 'existing' ? 'same' : msg.status}
                                        </span>
                                      )}

                                      {!isResult && msg.type !== 'completed' && msg.type !== 'error' && msg.type !== 'started' && (
                                        <span className={`text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 border flex-shrink-0 ${
                                          msg.type === 'researching' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                          msg.type === 'scanning' ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                                          msg.type === 'verifying' ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' :
                                          msg.type === 'confidence_retry' ? 'bg-amber-500/10 text-amber-300 border-amber-500/20' :
                                          msg.type === 'confidence_gate' ? 'bg-amber-500/10 text-amber-300 border-amber-500/20' :
                                          msg.type === 'legislation' ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                                          'bg-zinc-800/60 text-zinc-500 border-zinc-700/40'
                                        }`}>
                                          {msg.type}
                                        </span>
                                      )}

                                      <span className={`truncate ${
                                        msg.type === 'error' ? 'text-red-400' :
                                        msg.type === 'completed' ? 'text-emerald-300 font-medium' :
                                        isResult && msg.status === 'new' ? 'text-emerald-300/80' :
                                        isResult && msg.status === 'updated' ? 'text-amber-300/80' :
                                        isActive && isLast ? 'text-zinc-200' :
                                        'text-zinc-500'
                                      }`}>
                                        {msg.type === 'completed'
                                          ? `Complete — ${msg.new ?? 0} requirements, ${msg.updated ?? 0} updated, ${msg.low_confidence ?? 0} below 95%`
                                          : msg.message || msg.location || ''}
                                      </span>
                                    </div>
                                  );
                                })}
                              </div>

                              {completed && !isActive && (
                                <div className="px-6 py-3 border-t border-emerald-500/10 bg-emerald-500/[0.03]" style={{ animation: 'fadeSlideDown 0.4s ease-out' }}>
                                  <div className="flex items-center gap-4">
                                    <div className="flex items-center gap-2">
                                      <span className="relative flex h-2 w-2">
                                        <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-40 animate-ping" style={{ animationDuration: '2s' }} />
                                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
                                      </span>
                                      <span className="text-[10px] uppercase tracking-widest font-mono font-bold text-emerald-400">Research Complete</span>
                                    </div>
                                    <div className="flex items-center gap-3 ml-auto text-[11px] font-mono">
                                      <span className="text-emerald-400">{completed.new ?? 0} <span className="text-zinc-600">reqs</span></span>
                                      <span className="text-amber-400">{completed.updated ?? 0} <span className="text-zinc-600">updated</span></span>
                                      <span className="text-zinc-500">{completed.alerts ?? 0} <span className="text-zinc-600">alerts</span></span>
                                      <span className="text-amber-200">{completed.low_confidence ?? 0} <span className="text-zinc-600">below 95%</span></span>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })()}

                        {/* Detail loading */}
                        {isExpanded && isLoading && (
                          <div className="border-t border-white/5 overflow-hidden">
                            <div className="h-[2px] w-full bg-zinc-800 overflow-hidden">
                              <div className="h-full w-1/4 bg-gradient-to-r from-transparent via-zinc-500 to-transparent" style={{ animation: 'scanX 1s ease-in-out infinite' }} />
                            </div>
                            <div className="px-6 py-5 flex items-center justify-center gap-2">
                              <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-zinc-400 opacity-30" />
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-zinc-500" />
                              </span>
                              <span className="text-xs text-zinc-500 uppercase tracking-wider font-mono">Loading detail</span>
                            </div>
                          </div>
                        )}

                        {/* Detail panel */}
                        {isExpanded && detail && (
                          <JurisdictionDetailPanel
                            detail={detail}
                            parentJurisdiction={detail.parent_id ? jurisdictions.find(p => p.id === detail.parent_id) : null}
                            onNavigate={handleNavigate}
                            inheritsFromParent={j.inherits_from_parent}
                          />
                        )}
                      </div>
                    );
                  })}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Right sidebar: Schedulers + Activity */}
            <div className="space-y-8">
              {/* Scheduled Jobs */}
              {schedulers.length > 0 && (
                <div>
                  <SectionLabel>Scheduled Jobs</SectionLabel>
                  <div className="border border-white/10 divide-y divide-white/[0.05]">
                    {schedulers.map((sched) => (
                      <div key={sched.task_key} className="p-4 space-y-3">
                        <div className="flex items-start gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs text-white font-medium leading-tight">{sched.display_name}</span>
                              <span className={`text-[8px] px-1.5 py-0.5 uppercase tracking-wider font-bold border shrink-0 ${
                                sched.enabled
                                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                  : 'bg-zinc-700/30 text-zinc-500 border-zinc-600/30'
                              }`}>
                                {sched.enabled ? 'On' : 'Off'}
                              </span>
                            </div>
                            <p className="text-[10px] text-zinc-600 font-mono leading-relaxed line-clamp-2">{sched.description}</p>
                          </div>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <button
                            onClick={() => handleToggle(sched.task_key, sched.enabled)}
                            disabled={toggling === sched.task_key}
                            className={`relative w-9 h-5 rounded-full transition-colors shrink-0 ${
                              sched.enabled ? 'bg-emerald-600' : 'bg-zinc-700'
                            } ${toggling === sched.task_key ? 'opacity-50' : ''}`}
                          >
                            <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                              sched.enabled ? 'translate-x-4' : 'translate-x-0.5'
                            }`} />
                          </button>
                          <button
                            onClick={() => handleTrigger(sched.task_key)}
                            disabled={triggering === sched.task_key}
                            className="flex-1 px-3 py-1.5 text-[9px] tracking-[0.12em] uppercase font-mono text-zinc-400 border border-zinc-700 hover:text-white hover:border-zinc-500 transition-colors disabled:opacity-50 text-center"
                          >
                            {triggering === sched.task_key ? 'Running...' : 'Run Now'}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recent Activity */}
              {stats && stats.recent_logs.length > 0 && (
                <div>
                  <SectionLabel>Recent Activity</SectionLabel>
                  <div className="border border-white/10 divide-y divide-white/[0.05]">
                    {stats.recent_logs.map((log: SchedulerLogEntry) => (
                      <div key={log.id} className="px-4 py-3 space-y-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[11px] text-zinc-300 font-mono truncate">
                            {log.location_name || log.location_id.slice(0, 8)}
                          </span>
                          <span className={`text-[8px] px-1.5 py-0.5 uppercase tracking-wider font-bold border shrink-0 ${statusColor(log.status)}`}>
                            {log.status}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 text-[10px] font-mono text-zinc-600 flex-wrap">
                          <span>{formatRelative(log.started_at)}</span>
                          {log.duration_seconds != null && <span>{Math.round(log.duration_seconds)}s</span>}
                          <span className="text-[8px] px-1 py-0.5 bg-zinc-900 border border-zinc-800 text-zinc-500">{log.check_type}</span>
                        </div>
                        {(log.new_count > 0 || log.updated_count > 0 || log.alert_count > 0) && (
                          <div className="flex items-center gap-3 text-[10px] font-mono">
                            {log.new_count > 0 && <span className="text-emerald-400">{log.new_count} new</span>}
                            {log.updated_count > 0 && <span className="text-amber-400">{log.updated_count} updated</span>}
                            {log.alert_count > 0 && <span className="text-red-400">{log.alert_count} alerts</span>}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

          </div>
        </>
      )}
    </div>
  );
}

export default Jurisdictions;
