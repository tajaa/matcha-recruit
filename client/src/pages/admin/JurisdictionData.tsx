import { useState, useMemo, useEffect } from 'react';
import {
  Database, ChevronDown, ChevronRight, AlertTriangle, CheckCircle,
  XCircle, Loader2, RefreshCw, Layers, Globe2, Filter, Trash2, Check,
  X, ExternalLink
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useQueryClient } from '@tanstack/react-query';
import { useJurisdictionData } from '../../hooks/useJurisdictionData';
import { useIsLightMode } from '../../hooks/useIsLightMode';
import { api } from '../../api/client';
import type { JurisdictionDataState, JurisdictionDataCitySummary, JurisdictionDataOverview, JurisdictionDetail } from '../../api/client';

/* ───── Theme ───── */
const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-xl',
  innerEl: 'bg-stone-200 rounded-lg',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  divide: 'divide-stone-200',
  rowHover: 'hover:bg-stone-50',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  select: 'bg-white border border-stone-300 rounded-lg text-zinc-900 focus:border-stone-400',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  statusOk: 'text-emerald-600',
  statusWarn: 'text-amber-600',
  statusErr: 'text-red-600',
  dotOk: 'bg-emerald-500',
  dotMiss: 'bg-red-400',
  barBg: 'bg-stone-300',
  barFill: 'bg-emerald-500',
  barTier1: 'bg-emerald-500',
  barTier2: 'bg-amber-400',
  barTier3: 'bg-red-400',
  kpi: 'bg-white rounded-xl border border-stone-200',
  tabActive: 'bg-white text-zinc-900 shadow-sm',
  tabInactive: 'text-stone-500 hover:text-zinc-800',
  preemptOk: 'bg-emerald-100 text-emerald-700',
  preemptNo: 'bg-red-100 text-red-700',
  tooltip: 'bg-zinc-900 text-zinc-100',
  trashBtn: 'text-stone-300 hover:text-red-500',
  confirmBtn: 'text-red-500 hover:text-red-700',
};
const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900 rounded-xl',
  innerEl: 'bg-zinc-800 rounded-lg',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  divide: 'divide-white/10',
  rowHover: 'hover:bg-white/5',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  select: 'bg-zinc-900 border border-white/10 rounded-lg text-zinc-100 focus:border-white/20',
  btnGhost: 'text-zinc-500 hover:text-zinc-100',
  statusOk: 'text-emerald-400',
  statusWarn: 'text-amber-400',
  statusErr: 'text-red-400',
  dotOk: 'bg-emerald-400',
  dotMiss: 'bg-red-500',
  barBg: 'bg-zinc-700',
  barFill: 'bg-emerald-400',
  barTier1: 'bg-emerald-400',
  barTier2: 'bg-amber-400',
  barTier3: 'bg-red-400',
  kpi: 'bg-zinc-900 rounded-xl border border-white/10',
  tabActive: 'bg-zinc-800 text-zinc-100 shadow-sm',
  tabInactive: 'text-zinc-500 hover:text-zinc-200',
  preemptOk: 'bg-emerald-500/20 text-emerald-400',
  preemptNo: 'bg-red-500/20 text-red-400',
  tooltip: 'bg-zinc-800 text-zinc-200',
  trashBtn: 'text-zinc-700 hover:text-red-500',
  confirmBtn: 'text-red-400 hover:text-red-300',
};

type Tab = 'coverage' | 'missing' | 'quality' | 'preemption';
const TABS: { id: Tab; label: string }[] = [
  { id: 'coverage', label: 'Coverage' },
  { id: 'missing', label: 'Missing Data' },
  { id: 'quality', label: 'Data Quality' },
  { id: 'preemption', label: 'Preemption Rules' },
];

const CAT_LABELS: Record<string, string> = {
  minimum_wage: 'Min Wage',
  overtime: 'OT',
  sick_leave: 'Sick',
  meal_breaks: 'Meals',
  pay_frequency: 'Pay Freq',
  final_pay: 'Final Pay',
  minor_work_permit: 'Minor',
  scheduling_reporting: 'Sched',
};

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
}

/* ═══════ Main Component ═══════ */
export default function JurisdictionData() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const { data, isLoading, hardRefresh } = useJurisdictionData();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>('coverage');
  const [expandedStates, setExpandedStates] = useState<Set<string>>(new Set());
  const [filterState, setFilterState] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterStaleOnly, setFilterStaleOnly] = useState(false);
  const [selectedCityId, setSelectedCityId] = useState<string | null>(null);
  const [cityDetail, setCityDetail] = useState<JurisdictionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const openCity = async (id: string) => {
    if (!id) return;
    setSelectedCityId(id);
    setLoadingDetail(true);
    setCityDetail(null);
    try {
      const detail = await api.adminJurisdictions.get(id);
      setCityDetail(detail);
    } catch { /* silently fail */ }
    setLoadingDetail(false);
  };

  const closeCity = () => {
    setSelectedCityId(null);
    setCityDetail(null);
  };

  const toggleState = (state: string) => {
    setExpandedStates(prev => {
      const next = new Set(prev);
      next.has(state) ? next.delete(state) : next.add(state);
      return next;
    });
  };

  const handleDelete = async (id: string) => {
    await api.adminJurisdictions.delete(id);
    queryClient.invalidateQueries({ queryKey: ['jurisdiction-data-overview'] });
  };

  const missingRows = useMemo(() => {
    if (!data) return [];
    const rows: (JurisdictionDataCitySummary & { state: string })[] = [];
    for (const s of data.states) {
      for (const c of s.cities) {
        if (c.categories_missing.length === 0) continue;
        if (filterState && s.state !== filterState) continue;
        if (filterCategory && !c.categories_missing.includes(filterCategory)) continue;
        if (filterStaleOnly && !c.is_stale) continue;
        rows.push({ ...c, state: s.state });
      }
    }
    return rows.sort((a, b) => b.categories_missing.length - a.categories_missing.length);
  }, [data, filterState, filterCategory, filterStaleOnly]);

  const preemptionMatrix = useMemo(() => {
    if (!data) return { states: [] as string[], matrix: {} as Record<string, Record<string, { allows: boolean; notes: string | null }>> };
    const matrix: Record<string, Record<string, { allows: boolean; notes: string | null }>> = {};
    const stateSet = new Set<string>();
    for (const r of data.preemption_rules) {
      stateSet.add(r.state);
      if (!matrix[r.state]) matrix[r.state] = {};
      matrix[r.state][r.category] = { allows: r.allows_local_override, notes: r.notes };
    }
    return { states: [...stateSet].sort(), matrix };
  }, [data]);

  if (isLoading) {
    return (
      <div className={`min-h-screen ${t.pageBg} flex items-center justify-center`}>
        <Loader2 className={`w-5 h-5 animate-spin ${t.textMuted}`} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className={`min-h-screen ${t.pageBg} flex items-center justify-center`}>
        <p className={t.textMuted}>Failed to load data.</p>
      </div>
    );
  }

  const { summary } = data;
  const cats = summary.required_categories;

  return (
    <div className={`min-h-screen ${t.pageBg} p-5 md:p-8`}>
      <div className="max-w-[1400px] mx-auto space-y-5">

        {/* ── Header ── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className={`text-4xl tracking-tighter font-bold ${t.textMain}`}>JURISDICTION DATA</h1>
            <p className={`text-sm ${t.textMuted} mt-1`}>Compliance data repository overview</p>
          </div>
          <button
            onClick={() => hardRefresh()}
            className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition ${t.btnGhost} ${t.innerEl}`}
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        </div>

        {/* ── KPI Bar ── */}
        <div className="grid grid-cols-5 gap-3">
          <KpiCard t={t} label="States" value={`${summary.total_states}/50`} icon={<Globe2 className="w-4 h-4" />} />
          <KpiCard t={t} label="Cities" value={summary.total_cities.toLocaleString()} icon={<Database className="w-4 h-4" />} />
          <KpiCard t={t} label="Coverage" value={`${summary.category_coverage_pct}%`} icon={<Layers className="w-4 h-4" />}
            accent={summary.category_coverage_pct >= 70 ? 'ok' : summary.category_coverage_pct >= 40 ? 'warn' : 'err'} />
          <KpiCard t={t} label="Tier 1" value={`${summary.tier1_pct}%`} icon={<CheckCircle className="w-4 h-4" />}
            accent={summary.tier1_pct >= 50 ? 'ok' : summary.tier1_pct >= 20 ? 'warn' : 'err'} />
          <KpiCard t={t} label="Stale >90d" value={summary.stale_count.toString()} icon={<AlertTriangle className="w-4 h-4" />}
            accent={summary.stale_count === 0 ? 'ok' : summary.stale_count <= 10 ? 'warn' : 'err'} />
        </div>

        {/* ── Tabs ── */}
        <div className={`flex gap-1 p-1 rounded-xl ${t.innerEl} w-fit`}>
          {TABS.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-1.5 text-sm font-medium rounded-lg transition ${activeTab === tab.id ? t.tabActive : t.tabInactive}`}>
              {tab.label}
            </button>
          ))}
        </div>

        {/* ── Tab Content ── */}
        <AnimatePresence mode="wait">
          <motion.div key={activeTab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.12 }}>
            {activeTab === 'coverage' && (
              <CoverageTab t={t} states={data.states} cats={cats}
                expandedStates={expandedStates} toggleState={toggleState} onDelete={handleDelete}
                onCityClick={openCity} />
            )}
            {activeTab === 'missing' && (
              <MissingDataTab t={t} rows={missingRows} cats={cats} states={data.states}
                filterState={filterState} setFilterState={setFilterState}
                filterCategory={filterCategory} setFilterCategory={setFilterCategory}
                filterStaleOnly={filterStaleOnly} setFilterStaleOnly={setFilterStaleOnly}
                onDelete={handleDelete} onCityClick={openCity} />
            )}
            {activeTab === 'quality' && (
              <DataQualityTab t={t} summary={summary} sources={data.structured_sources} />
            )}
            {activeTab === 'preemption' && (
              <PreemptionTab t={t} cats={cats} matrix={preemptionMatrix.matrix} states={preemptionMatrix.states} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* ── City Detail Drawer ── */}
      <AnimatePresence>
        {selectedCityId && (
          <CityDetailDrawer t={t} detail={cityDetail} loading={loadingDetail} onClose={closeCity} />
        )}
      </AnimatePresence>
    </div>
  );
}

/* ───── KPI Card ───── */
function KpiCard({ t, label, value, icon, accent }: {
  t: typeof LT; label: string; value: string; icon: React.ReactNode; accent?: 'ok' | 'warn' | 'err';
}) {
  const color = accent === 'ok' ? t.statusOk : accent === 'warn' ? t.statusWarn : accent === 'err' ? t.statusErr : t.textMain;
  return (
    <div className={`${t.kpi} p-3.5 flex flex-col gap-1`}>
      <div className={`flex items-center gap-1.5 ${t.label}`}>{icon}{label}</div>
      <div className={`text-2xl font-bold tracking-tight ${color}`}>{value}</div>
    </div>
  );
}

/* ───── Delete Button (two-step confirm) ───── */
function DeleteBtn({ t, onDelete }: { t: typeof LT; onDelete: () => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  if (deleting) return <Loader2 className="w-3.5 h-3.5 animate-spin text-red-500" />;

  if (confirming) {
    return (
      <span className="flex items-center gap-1">
        <button onClick={async (e) => { e.stopPropagation(); setDeleting(true); await onDelete(); }}
          className={`${t.confirmBtn} transition`} title="Confirm delete">
          <Check className="w-3.5 h-3.5" />
        </button>
        <button onClick={(e) => { e.stopPropagation(); setConfirming(false); }}
          className={`${t.trashBtn} transition`}>
          <XCircle className="w-3.5 h-3.5" />
        </button>
      </span>
    );
  }

  return (
    <button onClick={(e) => { e.stopPropagation(); setConfirming(true); }}
      className={`${t.trashBtn} transition opacity-0 group-hover:opacity-100`} title="Delete city">
      <Trash2 className="w-3.5 h-3.5" />
    </button>
  );
}

/* ───── Coverage Tab ───── */
function CoverageTab({ t, states, cats, expandedStates, toggleState, onDelete, onCityClick }: {
  t: typeof LT; states: JurisdictionDataState[]; cats: string[];
  expandedStates: Set<string>; toggleState: (s: string) => void;
  onDelete: (id: string) => Promise<void>;
  onCityClick: (id: string) => void;
}) {
  return (
    <div className={`${t.card} p-5`}>
      <div className={`${t.label} mb-3`}>State-by-State Coverage</div>
      <div className="space-y-0.5">
        {states.map(s => {
          const isOpen = expandedStates.has(s.state);
          return (
            <div key={s.state}>
              <button onClick={() => toggleState(s.state)}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-xl transition ${t.rowHover}`}>
                {isOpen ? <ChevronDown className={`w-4 h-4 ${t.textMuted} flex-shrink-0`} />
                  : <ChevronRight className={`w-4 h-4 ${t.textMuted} flex-shrink-0`} />}
                <span className={`font-mono font-bold text-sm w-8 ${t.textMain}`}>{s.state}</span>
                <span className={`text-xs ${t.textFaint} w-16`}>{s.city_count} {s.city_count === 1 ? 'city' : 'cities'}</span>
                <div className="flex-1 flex items-center gap-2">
                  <div className={`flex-1 h-2 rounded-full ${t.barBg} overflow-hidden`}>
                    <div className={`h-full rounded-full ${t.barFill}`} style={{ width: `${s.coverage_pct}%` }} />
                  </div>
                  <span className={`text-xs font-mono ${t.textFaint} w-10 text-right`}>{s.coverage_pct}%</span>
                </div>
              </button>

              <AnimatePresence>
                {isOpen && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.15 }} className="overflow-hidden">
                    <div className={`ml-7 mr-3 mb-2 ${t.innerEl} p-3`}>
                      {/* legend */}
                      <div className="flex gap-3 mb-2 px-1">
                        {cats.map(c => (
                          <span key={c} className={`text-[10px] font-mono ${t.textFaint}`}>{CAT_LABELS[c] || c}</span>
                        ))}
                      </div>
                      {/* city rows */}
                      {s.cities.map(city => (
                        <div key={city.city} onClick={() => onCityClick(city.id)}
                          className={`group flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer ${t.rowHover}`}>
                          <span className={`text-sm ${t.textMain} w-40 truncate`}>{city.city}</span>
                          <div className="flex gap-1.5">
                            {cats.map(c => (
                              <div key={c} className={`w-3 h-3 rounded-full ${city.categories_present.includes(c) ? t.dotOk : t.dotMiss}`}
                                title={`${CAT_LABELS[c] || c}: ${city.categories_present.includes(c) ? 'Present' : 'Missing'}`} />
                            ))}
                          </div>
                          <span className={`text-[11px] font-mono ${t.textFaint} ml-auto`}>{formatDate(city.last_verified_at)}</span>
                          {city.is_stale && <AlertTriangle className={`w-3.5 h-3.5 ${t.statusWarn} flex-shrink-0`} />}
                          <DeleteBtn t={t} onDelete={() => onDelete(city.id!)} />
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ───── Missing Data Tab ───── */
function MissingDataTab({ t, rows, cats, states, filterState, setFilterState, filterCategory, setFilterCategory, filterStaleOnly, setFilterStaleOnly, onDelete, onCityClick }: {
  t: typeof LT;
  rows: (JurisdictionDataCitySummary & { state: string })[];
  cats: string[];
  states: JurisdictionDataState[];
  filterState: string; setFilterState: (v: string) => void;
  filterCategory: string; setFilterCategory: (v: string) => void;
  filterStaleOnly: boolean; setFilterStaleOnly: (v: boolean) => void;
  onDelete: (id: string) => Promise<void>;
  onCityClick: (id: string) => void;
}) {
  const uniqueStates = useMemo(() => [...new Set(states.map(s => s.state))].sort(), [states]);

  return (
    <div className={`${t.card} p-5 space-y-4`}>
      <div className="flex flex-wrap items-center gap-3">
        <div className={`flex items-center gap-1.5 ${t.label}`}><Filter className="w-3.5 h-3.5" />Filters</div>
        <select value={filterState} onChange={e => setFilterState(e.target.value)}
          className={`${t.select} text-sm px-3 py-1.5`}>
          <option value="">All States</option>
          {uniqueStates.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)}
          className={`${t.select} text-sm px-3 py-1.5`}>
          <option value="">All Categories</option>
          {cats.map(c => <option key={c} value={c}>{CAT_LABELS[c] || c}</option>)}
        </select>
        <label className={`flex items-center gap-2 text-sm cursor-pointer ${t.textDim}`}>
          <input type="checkbox" checked={filterStaleOnly} onChange={e => setFilterStaleOnly(e.target.checked)} className="rounded" />
          Stale only
        </label>
        <span className={`text-xs ${t.textFaint} ml-auto`}>{rows.length} jurisdictions</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className={`${t.label} border-b ${t.border}`}>
              <th className="text-left py-2 px-2">ST</th>
              <th className="text-left py-2 px-2">City</th>
              <th className="text-left py-2 px-2">Missing</th>
              <th className="text-left py-2 px-2">Gaps</th>
              <th className="text-left py-2 px-2">Verified</th>
              <th className="py-2 px-2" />
            </tr>
          </thead>
          <tbody className={`divide-y ${t.divide}`}>
            {rows.slice(0, 100).map((row, i) => (
              <tr key={`${row.state}-${row.city}-${i}`} className={`group ${t.rowHover}`}>
                <td className={`py-2 px-2 font-mono font-bold ${t.textMain}`}>{row.state}</td>
                <td className={`py-2 px-2 ${t.textMain} cursor-pointer hover:underline`}
                  onClick={() => onCityClick(row.id)}>{row.city}</td>
                <td className="py-2 px-2">
                  <div className="flex flex-wrap gap-1">
                    {row.categories_missing.map(c => (
                      <span key={c} className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${t.preemptNo}`}>{CAT_LABELS[c] || c}</span>
                    ))}
                  </div>
                </td>
                <td className={`py-2 px-2 font-mono ${row.categories_missing.length >= 4 ? t.statusErr : t.statusWarn}`}>
                  {row.categories_missing.length}/{cats.length}
                </td>
                <td className={`py-2 px-2 ${t.textFaint} whitespace-nowrap`}>
                  <span className="flex items-center gap-1.5">
                    {formatDate(row.last_verified_at)}
                    {row.is_stale && <AlertTriangle className={`w-3 h-3 ${t.statusWarn}`} />}
                  </span>
                </td>
                <td className="py-2 px-2 text-right">
                  <DeleteBtn t={t} onDelete={() => onDelete(row.id!)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <div className={`text-center py-8 text-xs ${t.textMuted}`}>No missing data found.</div>
        )}
        {rows.length > 100 && (
          <div className={`text-center py-2 text-[10px] ${t.textFaint}`}>Showing 100 of {rows.length}</div>
        )}
      </div>
    </div>
  );
}

/* ───── Data Quality Tab ───── */
function DataQualityTab({ t, summary, sources }: {
  t: typeof LT; summary: JurisdictionDataOverview['summary']; sources: JurisdictionDataOverview['structured_sources'];
}) {
  const tierTotal = Object.values(summary.tier_breakdown).reduce((a, b) => a + b, 0);
  const freshTotal = Object.values(summary.freshness).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-4">
      <div className={`${t.card} p-5 space-y-3`}>
        <div className={t.label}>Tier Breakdown</div>
        {([
          { tier: '1', label: 'Tier 1 — Structured', color: t.barTier1, count: summary.tier_breakdown['1'] || 0 },
          { tier: '2', label: 'Tier 2 — Repository', color: t.barTier2, count: summary.tier_breakdown['2'] || 0 },
          { tier: '3', label: 'Tier 3 — AI Research', color: t.barTier3, count: summary.tier_breakdown['3'] || 0 },
        ] as const).map(row => {
          const pct = tierTotal > 0 ? Math.round(row.count / tierTotal * 100) : 0;
          return (
            <div key={row.tier} className="flex items-center gap-2">
              <span className={`text-xs w-32 ${t.textDim}`}>{row.label}</span>
              <div className={`flex-1 h-2 rounded-full ${t.barBg} overflow-hidden`}>
                <div className={`h-full rounded-full ${row.color}`} style={{ width: `${pct}%` }} />
              </div>
              <span className={`text-[11px] font-mono w-20 text-right ${t.textMuted}`}>{row.count.toLocaleString()} ({pct}%)</span>
            </div>
          );
        })}
      </div>

      <div className={`${t.card} p-5 space-y-3`}>
        <div className={t.label}>Freshness</div>
        <div className="grid grid-cols-4 gap-3">
          {([
            { key: '7d', label: '≤7 days', accent: 'ok' as const },
            { key: '30d', label: '8–30 days', accent: 'ok' as const },
            { key: '90d', label: '31–90 days', accent: 'warn' as const },
            { key: 'stale', label: '>90 days', accent: 'err' as const },
          ]).map(b => {
            const count = summary.freshness[b.key] || 0;
            const pct = freshTotal > 0 ? Math.round(count / freshTotal * 100) : 0;
            const color = b.accent === 'ok' ? t.statusOk : b.accent === 'warn' ? t.statusWarn : t.statusErr;
            return (
              <div key={b.key} className={`${t.innerEl} p-3`}>
                <div className={`${t.label} mb-1`}>{b.label}</div>
                <div className={`text-lg font-bold font-mono ${color}`}>{count.toLocaleString()}</div>
                <div className={`text-[10px] font-mono ${t.textFaint}`}>{pct}%</div>
              </div>
            );
          })}
        </div>
      </div>

      <div className={`${t.card} p-5 space-y-3`}>
        <div className={t.label}>Structured Sources</div>
        {sources.length === 0 ? (
          <div className={`text-xs ${t.textMuted}`}>No structured sources configured.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className={`${t.label} border-b ${t.border}`}>
                <th className="text-left py-2 px-3">Source</th>
                <th className="text-left py-2 px-3">Type</th>
                <th className="text-left py-2 px-3">Categories</th>
                <th className="text-left py-2 px-3">Records</th>
                <th className="text-left py-2 px-3">Last Fetch</th>
                <th className="text-left py-2 px-3">Status</th>
              </tr>
            </thead>
            <tbody className={`divide-y ${t.divide}`}>
              {sources.map((src, i) => (
                <tr key={i} className={t.rowHover}>
                  <td className={`py-2 px-3 ${t.textMain} font-medium`}>{src.source_name}</td>
                  <td className={`py-2 px-3 ${t.textFaint} font-mono text-xs`}>{src.source_type}</td>
                  <td className="py-2 px-3">
                    <div className="flex flex-wrap gap-1">
                      {src.categories.map(c => (
                        <span key={c} className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${t.preemptOk}`}>{CAT_LABELS[c] || c}</span>
                      ))}
                    </div>
                  </td>
                  <td className={`py-2 px-3 font-mono ${t.textDim}`}>{src.record_count.toLocaleString()}</td>
                  <td className={`py-2 px-3 ${t.textFaint}`}>{formatDate(src.last_fetched_at)}</td>
                  <td className="py-2 px-3">
                    {src.is_active
                      ? <span className={`flex items-center gap-1 text-xs ${t.statusOk}`}><CheckCircle className="w-3 h-3" />Active</span>
                      : <span className={`flex items-center gap-1 text-xs ${t.statusErr}`}><XCircle className="w-3 h-3" />Inactive</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ───── Preemption Tab ───── */
function PreemptionTab({ t, cats, matrix, states }: {
  t: typeof LT; cats: string[];
  matrix: Record<string, Record<string, { allows: boolean; notes: string | null }>>;
  states: string[];
}) {
  const [hoveredCell, setHoveredCell] = useState<{ state: string; cat: string } | null>(null);

  if (states.length === 0) {
    return <div className={`${t.card} p-8 text-center text-xs ${t.textMuted}`}>No preemption rules in the database yet.</div>;
  }

  return (
    <div className={`${t.card} p-5 space-y-3`}>
      <div className={t.label}>State × Category Preemption Matrix</div>
      <p className={`text-xs ${t.textFaint}`}>Green = allows local override · Red = preempted · Hover for notes</p>
      <div className="overflow-x-auto">
        <table className="text-xs">
          <thead>
            <tr>
              <th className={`py-1.5 px-2 text-left ${t.label}`}>State</th>
              {cats.map(c => (
                <th key={c} className={`py-1.5 px-1.5 text-center ${t.label} whitespace-nowrap`}>{CAT_LABELS[c] || c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {states.map(state => (
              <tr key={state} className={t.rowHover}>
                <td className={`py-1 px-2 font-mono font-bold ${t.textMain}`}>{state}</td>
                {cats.map(cat => {
                  const cell = matrix[state]?.[cat];
                  if (!cell) return <td key={cat} className={`py-1 px-1.5 text-center text-xs ${t.textFaint}`}>—</td>;
                  const isHovered = hoveredCell?.state === state && hoveredCell?.cat === cat;
                  return (
                    <td key={cat} className="py-1 px-1.5 text-center relative"
                      onMouseEnter={() => setHoveredCell({ state, cat })}
                      onMouseLeave={() => setHoveredCell(null)}>
                      <span className={`inline-flex items-center justify-center w-6 h-6 rounded text-[11px] font-bold ${cell.allows ? t.preemptOk : t.preemptNo}`}>
                        {cell.allows ? '✓' : '✗'}
                      </span>
                      {isHovered && cell.notes && (
                        <div className={`absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2.5 py-1.5 rounded-lg text-[10px] max-w-[220px] ${t.tooltip} shadow-lg whitespace-normal`}>
                          {cell.notes}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ───── City Detail Drawer ───── */
function CityDetailDrawer({ t, detail, loading, onClose }: {
  t: typeof LT; detail: JurisdictionDetail | null; loading: boolean; onClose: () => void;
}) {
  const grouped = useMemo(() => {
    if (!detail) return {};
    const map: Record<string, JurisdictionDetail['requirements']> = {};
    for (const req of detail.requirements) {
      const cat = req.category || 'other';
      if (!map[cat]) map[cat] = [];
      map[cat].push(req);
    }
    return map;
  }, [detail]);

  return (
    <>
      {/* backdrop */}
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/40 z-40" onClick={onClose}
      />
      {/* panel */}
      <motion.div
        initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        className={`fixed inset-y-0 right-0 w-full max-w-2xl z-50 ${t.pageBg} shadow-2xl overflow-y-auto`}
      >
        <div className="p-6 space-y-5">
          {/* header */}
          <div className="flex items-start justify-between">
            <div>
              {detail ? (
                <>
                  <h2 className={`text-2xl font-bold tracking-tight ${t.textMain}`}>{detail.city}</h2>
                  <p className={`text-sm ${t.textMuted} mt-0.5`}>
                    {detail.state}{detail.county ? ` · ${detail.county} County` : ''}
                    {' · '}{detail.requirements.length} requirement{detail.requirements.length !== 1 ? 's' : ''}
                  </p>
                </>
              ) : (
                <div className={`h-8 w-48 rounded ${t.innerEl} animate-pulse`} />
              )}
            </div>
            <button onClick={onClose} className={`p-1.5 rounded-lg transition ${t.btnGhost} ${t.rowHover}`}>
              <X className="w-5 h-5" />
            </button>
          </div>

          {loading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 className={`w-5 h-5 animate-spin ${t.textMuted}`} />
            </div>
          )}

          {detail && !loading && detail.requirements.length === 0 && (
            <div className={`${t.card} p-8 text-center`}>
              <p className={`text-sm ${t.textMuted}`}>No requirements data for this jurisdiction yet.</p>
            </div>
          )}

          {detail && !loading && Object.entries(grouped).map(([category, reqs]) => (
            <div key={category} className={`${t.card} p-4 space-y-2`}>
              <div className={`${t.label} flex items-center gap-2`}>
                <span className={`w-2.5 h-2.5 rounded-full ${t.dotOk}`} />
                {CAT_LABELS[category] || category.replace(/_/g, ' ')}
                <span className={`${t.textFaint} font-normal`}>({reqs.length})</span>
              </div>

              <div className="space-y-1.5">
                {reqs.map(req => (
                  <div key={req.id} className={`${t.innerEl} p-3 space-y-1.5`}>
                    <div className="flex items-start justify-between gap-2">
                      <h4 className={`text-sm font-medium ${t.textMain}`}>{req.title}</h4>
                      {req.source_url && (
                        <a href={req.source_url} target="_blank" rel="noopener noreferrer"
                          className={`flex-shrink-0 ${t.btnGhost} transition`} title="View source">
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </div>

                    {req.current_value && (
                      <div className={`text-sm ${t.textDim}`}>{req.current_value}</div>
                    )}

                    {req.description && (
                      <p className={`text-xs ${t.textFaint} leading-relaxed`}>{req.description}</p>
                    )}

                    <div className={`flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono ${t.textFaint} pt-1`}>
                      {req.effective_date && <span>Effective: {formatDate(req.effective_date)}</span>}
                      {req.last_verified_at && <span>Verified: {formatDate(req.last_verified_at)}</span>}
                      {req.source_name && <span>Source: {req.source_name}</span>}
                      {req.jurisdiction_level && <span>Level: {req.jurisdiction_level}</span>}
                      {req.previous_value && <span>Prev: {req.previous_value}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* legislation section */}
          {detail && !loading && detail.legislation.length > 0 && (
            <div className={`${t.card} p-4 space-y-2`}>
              <div className={t.label}>Pending Legislation ({detail.legislation.length})</div>
              <div className="space-y-1.5">
                {detail.legislation.map(leg => (
                  <div key={leg.id} className={`${t.innerEl} p-3 space-y-1`}>
                    <div className="flex items-start justify-between gap-2">
                      <h4 className={`text-sm font-medium ${t.textMain}`}>{leg.title}</h4>
                      {leg.source_url && (
                        <a href={leg.source_url} target="_blank" rel="noopener noreferrer"
                          className={`flex-shrink-0 ${t.btnGhost} transition`}>
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </div>
                    <div className={`flex items-center gap-2 text-xs`}>
                      <span className={`px-1.5 py-0.5 rounded font-mono text-[10px] ${
                        leg.current_status === 'enacted' ? t.preemptOk : t.preemptNo
                      }`}>{leg.current_status}</span>
                      {leg.category && <span className={t.textFaint}>{CAT_LABELS[leg.category] || leg.category}</span>}
                    </div>
                    {leg.impact_summary && (
                      <p className={`text-xs ${t.textFaint} leading-relaxed`}>{leg.impact_summary}</p>
                    )}
                    <div className={`flex gap-4 text-[10px] font-mono ${t.textFaint}`}>
                      {leg.expected_effective_date && <span>Expected: {formatDate(leg.expected_effective_date)}</span>}
                      {leg.source_name && <span>Source: {leg.source_name}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </>
  );
}
