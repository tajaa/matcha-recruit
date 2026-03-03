import { useState, useMemo } from 'react';
import {
  Database, ChevronDown, ChevronRight, AlertTriangle, CheckCircle,
  XCircle, Loader2, RefreshCw, Layers, Globe2,
  Filter
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useJurisdictionData } from '../../hooks/useJurisdictionData';
import { useIsLightMode } from '../../hooks/useIsLightMode';
import type {
  JurisdictionDataState,
  JurisdictionDataCitySummary,
} from '../../api/client';

/* ───── Theme ───── */
const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  cardBg: 'bg-stone-100',
  innerEl: 'bg-stone-200 rounded-xl',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  divide: 'divide-stone-200',
  rowHover: 'hover:bg-stone-50',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  input: 'bg-white border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:border-stone-400',
  select: 'bg-white border border-stone-300 rounded-xl text-zinc-900 focus:border-stone-400',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  statusOk: 'text-emerald-600',
  statusWarn: 'text-amber-600',
  statusErr: 'text-red-600',
  dotOk: 'bg-emerald-500',
  dotMiss: 'bg-red-400',
  dotStale: 'bg-amber-400',
  barBg: 'bg-stone-300',
  barFill: 'bg-emerald-500',
  barTier1: 'bg-emerald-500',
  barTier2: 'bg-amber-400',
  barTier3: 'bg-red-400',
  kpi: 'bg-white rounded-2xl border border-stone-200',
  tabActive: 'bg-white text-zinc-900 shadow-sm',
  tabInactive: 'text-stone-500 hover:text-zinc-800',
  preemptOk: 'bg-emerald-100 text-emerald-700',
  preemptNo: 'bg-red-100 text-red-700',
  tooltip: 'bg-zinc-900 text-zinc-100',
};
const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900 rounded-2xl',
  cardBg: 'bg-zinc-900',
  innerEl: 'bg-zinc-800 rounded-xl',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  divide: 'divide-white/10',
  rowHover: 'hover:bg-white/5',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  input: 'bg-zinc-900 border border-white/10 text-zinc-100 rounded-xl placeholder:text-zinc-600 focus:border-white/20',
  select: 'bg-zinc-900 border border-white/10 rounded-xl text-zinc-100 focus:border-white/20',
  btnPrimary: 'bg-white text-black hover:bg-zinc-100',
  btnGhost: 'text-zinc-500 hover:text-zinc-100',
  statusOk: 'text-emerald-400',
  statusWarn: 'text-amber-400',
  statusErr: 'text-red-400',
  dotOk: 'bg-emerald-400',
  dotMiss: 'bg-red-500',
  dotStale: 'bg-amber-500',
  barBg: 'bg-zinc-700',
  barFill: 'bg-emerald-400',
  barTier1: 'bg-emerald-400',
  barTier2: 'bg-amber-400',
  barTier3: 'bg-red-400',
  kpi: 'bg-zinc-900 rounded-2xl border border-white/10',
  tabActive: 'bg-zinc-800 text-zinc-100 shadow-sm',
  tabInactive: 'text-zinc-500 hover:text-zinc-200',
  preemptOk: 'bg-emerald-500/20 text-emerald-400',
  preemptNo: 'bg-red-500/20 text-red-400',
  tooltip: 'bg-zinc-800 text-zinc-200',
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
  overtime: 'Overtime',
  sick_leave: 'Sick Leave',
  meal_breaks: 'Meal Breaks',
  pay_frequency: 'Pay Freq',
  final_pay: 'Final Pay',
  minor_work_permit: 'Minor Permit',
  scheduling_reporting: 'Scheduling',
};

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

/* ═══════ Main Component ═══════ */
export default function JurisdictionData() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const { data, isLoading, refetch } = useJurisdictionData();
  const [activeTab, setActiveTab] = useState<Tab>('coverage');
  const [expandedStates, setExpandedStates] = useState<Set<string>>(new Set());

  // Missing Data tab filters
  const [filterState, setFilterState] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterStaleOnly, setFilterStaleOnly] = useState(false);

  const toggleState = (state: string) => {
    setExpandedStates(prev => {
      const next = new Set(prev);
      next.has(state) ? next.delete(state) : next.add(state);
      return next;
    });
  };

  // ── Missing data rows ──
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

  // ── Preemption matrix data ──
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
        <Loader2 className={`w-6 h-6 animate-spin ${t.textMuted}`} />
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
    <div className={`min-h-screen ${t.pageBg} p-6 md:p-10`}>
      <div className="max-w-[1400px] mx-auto space-y-6">

        {/* ── Header ── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className={`text-4xl tracking-tighter font-bold ${t.textMain}`}>
              JURISDICTION DATA
            </h1>
            <p className={`text-sm ${t.textMuted} mt-1`}>
              Compliance data repository overview
            </p>
          </div>
          <button
            onClick={() => refetch()}
            className={`flex items-center gap-2 px-4 py-2 text-sm rounded-xl transition ${t.btnGhost} ${t.innerEl}`}
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        </div>

        {/* ── KPI Bar ── */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <KpiCard t={t} label="States Covered" value={`${summary.total_states} / 50`}
            icon={<Globe2 className="w-4 h-4" />} />
          <KpiCard t={t} label="Cities with Data" value={summary.total_cities.toLocaleString()}
            icon={<Database className="w-4 h-4" />} />
          <KpiCard t={t} label="Category Coverage" value={`${summary.category_coverage_pct}%`}
            icon={<Layers className="w-4 h-4" />}
            accent={summary.category_coverage_pct >= 70 ? 'ok' : summary.category_coverage_pct >= 40 ? 'warn' : 'err'} />
          <KpiCard t={t} label="Tier 1 Data" value={`${summary.tier1_pct}%`}
            icon={<CheckCircle className="w-4 h-4" />}
            accent={summary.tier1_pct >= 50 ? 'ok' : summary.tier1_pct >= 20 ? 'warn' : 'err'} />
          <KpiCard t={t} label="Stale (>90d)" value={summary.stale_count.toString()}
            icon={<AlertTriangle className="w-4 h-4" />}
            accent={summary.stale_count === 0 ? 'ok' : summary.stale_count <= 10 ? 'warn' : 'err'} />
        </div>

        {/* ── Tabs ── */}
        <div className={`flex gap-1 p-1 rounded-xl ${t.innerEl} w-fit`}>
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-1.5 text-sm font-medium rounded-lg transition ${
                activeTab === tab.id ? t.tabActive : t.tabInactive
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* ── Tab Content ── */}
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.15 }}
          >
            {activeTab === 'coverage' && (
              <CoverageTab t={t} states={data.states} cats={cats}
                expandedStates={expandedStates} toggleState={toggleState} />
            )}
            {activeTab === 'missing' && (
              <MissingDataTab t={t} rows={missingRows} cats={cats} states={data.states}
                filterState={filterState} setFilterState={setFilterState}
                filterCategory={filterCategory} setFilterCategory={setFilterCategory}
                filterStaleOnly={filterStaleOnly} setFilterStaleOnly={setFilterStaleOnly} />
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
    </div>
  );
}

/* ───── KPI Card ───── */
function KpiCard({ t, label, value, icon, accent }: {
  t: typeof LT;
  label: string;
  value: string;
  icon: React.ReactNode;
  accent?: 'ok' | 'warn' | 'err';
}) {
  const accentColor = accent === 'ok' ? t.statusOk : accent === 'warn' ? t.statusWarn : accent === 'err' ? t.statusErr : t.textMain;
  return (
    <div className={`${t.kpi} p-4 flex flex-col gap-1`}>
      <div className={`flex items-center gap-1.5 ${t.label}`}>
        {icon}
        {label}
      </div>
      <div className={`text-2xl font-bold tracking-tight ${accentColor}`}>
        {value}
      </div>
    </div>
  );
}

/* ───── Coverage Tab ───── */
function CoverageTab({ t, states, cats, expandedStates, toggleState }: {
  t: typeof LT;
  states: JurisdictionDataState[];
  cats: string[];
  expandedStates: Set<string>;
  toggleState: (s: string) => void;
}) {
  return (
    <div className={`${t.card} p-5 space-y-1`}>
      <div className={`${t.label} mb-3`}>State-by-State Coverage</div>
      {states.map(s => {
        const isOpen = expandedStates.has(s.state);
        return (
          <div key={s.state}>
            <button
              onClick={() => toggleState(s.state)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition ${t.rowHover}`}
            >
              {isOpen
                ? <ChevronDown className={`w-4 h-4 ${t.textMuted}`} />
                : <ChevronRight className={`w-4 h-4 ${t.textMuted}`} />}
              <span className={`font-mono font-bold text-sm w-8 ${t.textMain}`}>{s.state}</span>
              <span className={`text-xs ${t.textDim} w-20`}>{s.city_count} {s.city_count === 1 ? 'city' : 'cities'}</span>
              <div className="flex-1 flex items-center gap-2">
                <div className={`flex-1 h-2 rounded-full ${t.barBg} overflow-hidden`}>
                  <div
                    className={`h-full rounded-full ${t.barFill} transition-all`}
                    style={{ width: `${s.coverage_pct}%` }}
                  />
                </div>
                <span className={`text-xs font-mono ${t.textMuted} w-10 text-right`}>{s.coverage_pct}%</span>
              </div>
            </button>

            <AnimatePresence>
              {isOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className={`ml-8 mr-3 mb-2 ${t.innerEl} p-3 space-y-2`}>
                    {/* Category legend */}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 mb-2">
                      {cats.map(c => (
                        <span key={c} className={`text-[10px] font-mono ${t.textFaint}`}>
                          {CAT_LABELS[c] || c}
                        </span>
                      ))}
                    </div>
                    {/* City rows */}
                    {s.cities.map(city => (
                      <div key={city.city} className={`flex items-center gap-3 px-2 py-1.5 rounded-lg ${t.rowHover}`}>
                        <span className={`text-sm ${t.textMain} w-40 truncate`}>{city.city}</span>
                        <div className="flex gap-1.5">
                          {cats.map(c => (
                            <div
                              key={c}
                              className={`w-3 h-3 rounded-full ${city.categories_present.includes(c) ? t.dotOk : t.dotMiss}`}
                              title={`${CAT_LABELS[c] || c}: ${city.categories_present.includes(c) ? 'Present' : 'Missing'}`}
                            />
                          ))}
                        </div>
                        <span className={`text-[10px] font-mono ${t.textFaint} ml-auto`}>
                          {formatDate(city.last_verified_at)}
                        </span>
                        {city.is_stale && (
                          <AlertTriangle className={`w-3.5 h-3.5 ${t.statusWarn}`} />
                        )}
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
  );
}

/* ───── Missing Data Tab ───── */
function MissingDataTab({ t, rows, cats, states, filterState, setFilterState, filterCategory, setFilterCategory, filterStaleOnly, setFilterStaleOnly }: {
  t: typeof LT;
  rows: (JurisdictionDataCitySummary & { state: string })[];
  cats: string[];
  states: JurisdictionDataState[];
  filterState: string;
  setFilterState: (v: string) => void;
  filterCategory: string;
  setFilterCategory: (v: string) => void;
  filterStaleOnly: boolean;
  setFilterStaleOnly: (v: boolean) => void;
}) {
  const uniqueStates = useMemo(() => [...new Set(states.map(s => s.state))].sort(), [states]);

  return (
    <div className={`${t.card} p-5 space-y-4`}>
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className={`flex items-center gap-1.5 ${t.label}`}>
          <Filter className="w-3.5 h-3.5" />
          Filters
        </div>
        <select
          value={filterState}
          onChange={e => setFilterState(e.target.value)}
          className={`${t.select} text-sm px-3 py-1.5`}
        >
          <option value="">All States</option>
          {uniqueStates.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select
          value={filterCategory}
          onChange={e => setFilterCategory(e.target.value)}
          className={`${t.select} text-sm px-3 py-1.5`}
        >
          <option value="">All Categories</option>
          {cats.map(c => <option key={c} value={c}>{CAT_LABELS[c] || c}</option>)}
        </select>
        <label className={`flex items-center gap-2 text-sm cursor-pointer ${t.textDim}`}>
          <input
            type="checkbox"
            checked={filterStaleOnly}
            onChange={e => setFilterStaleOnly(e.target.checked)}
            className="rounded"
          />
          Stale only
        </label>
        <span className={`text-xs ${t.textFaint} ml-auto`}>{rows.length} jurisdictions</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className={`${t.label} border-b ${t.border}`}>
              <th className="text-left py-2 px-3">State</th>
              <th className="text-left py-2 px-3">City</th>
              <th className="text-left py-2 px-3">Missing Categories</th>
              <th className="text-left py-2 px-3">Gaps</th>
              <th className="text-left py-2 px-3">Last Verified</th>
            </tr>
          </thead>
          <tbody className={t.divide}>
            {rows.slice(0, 100).map((row, i) => (
              <tr key={`${row.state}-${row.city}-${i}`} className={t.rowHover}>
                <td className={`py-2 px-3 font-mono font-bold ${t.textMain}`}>{row.state}</td>
                <td className={`py-2 px-3 ${t.textMain}`}>{row.city}</td>
                <td className="py-2 px-3">
                  <div className="flex flex-wrap gap-1">
                    {row.categories_missing.map(c => (
                      <span key={c} className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${t.preemptNo}`}>
                        {CAT_LABELS[c] || c}
                      </span>
                    ))}
                  </div>
                </td>
                <td className={`py-2 px-3 font-mono ${row.categories_missing.length >= 4 ? t.statusErr : t.statusWarn}`}>
                  {row.categories_missing.length}/{cats.length}
                </td>
                <td className={`py-2 px-3 ${t.textFaint} flex items-center gap-1.5`}>
                  {formatDate(row.last_verified_at)}
                  {row.is_stale && <AlertTriangle className={`w-3 h-3 ${t.statusWarn}`} />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <div className={`text-center py-10 ${t.textMuted}`}>No missing data found with current filters.</div>
        )}
        {rows.length > 100 && (
          <div className={`text-center py-3 text-xs ${t.textFaint}`}>Showing first 100 of {rows.length} rows</div>
        )}
      </div>
    </div>
  );
}

/* ───── Data Quality Tab ───── */
function DataQualityTab({ t, summary, sources }: {
  t: typeof LT;
  summary: JurisdictionDataOverview['summary'];
  sources: JurisdictionDataOverview['structured_sources'];
}) {
  const tierTotal = Object.values(summary.tier_breakdown).reduce((a, b) => a + b, 0);
  const freshTotal = Object.values(summary.freshness).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-4">
      {/* Tier Breakdown */}
      <div className={`${t.card} p-5 space-y-3`}>
        <div className={`${t.label}`}>Data Tier Breakdown</div>
        <div className="space-y-2">
          {([
            { tier: '1', label: 'Tier 1 (Structured)', color: t.barTier1, count: summary.tier_breakdown['1'] || 0 },
            { tier: '2', label: 'Tier 2 (Repository)', color: t.barTier2, count: summary.tier_breakdown['2'] || 0 },
            { tier: '3', label: 'Tier 3 (AI Research)', color: t.barTier3, count: summary.tier_breakdown['3'] || 0 },
          ] as const).map(row => {
            const pct = tierTotal > 0 ? Math.round(row.count / tierTotal * 100) : 0;
            return (
              <div key={row.tier} className="flex items-center gap-3">
                <span className={`text-xs w-36 ${t.textDim}`}>{row.label}</span>
                <div className={`flex-1 h-3 rounded-full ${t.barBg} overflow-hidden`}>
                  <div className={`h-full rounded-full ${row.color} transition-all`} style={{ width: `${pct}%` }} />
                </div>
                <span className={`text-xs font-mono w-20 text-right ${t.textMuted}`}>
                  {row.count.toLocaleString()} ({pct}%)
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Freshness */}
      <div className={`${t.card} p-5 space-y-3`}>
        <div className={`${t.label}`}>Data Freshness</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {([
            { key: '7d', label: 'Last 7 days', accent: 'ok' as const },
            { key: '30d', label: '8–30 days', accent: 'ok' as const },
            { key: '90d', label: '31–90 days', accent: 'warn' as const },
            { key: 'stale', label: '>90 days (stale)', accent: 'err' as const },
          ]).map(bucket => {
            const count = summary.freshness[bucket.key] || 0;
            const pct = freshTotal > 0 ? Math.round(count / freshTotal * 100) : 0;
            const color = bucket.accent === 'ok' ? t.statusOk : bucket.accent === 'warn' ? t.statusWarn : t.statusErr;
            return (
              <div key={bucket.key} className={`${t.innerEl} p-3`}>
                <div className={`${t.label} mb-1`}>{bucket.label}</div>
                <div className={`text-lg font-bold font-mono ${color}`}>{count.toLocaleString()}</div>
                <div className={`text-[10px] font-mono ${t.textFaint}`}>{pct}%</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Structured Sources */}
      <div className={`${t.card} p-5 space-y-3`}>
        <div className={`${t.label}`}>Structured Data Sources</div>
        {sources.length === 0 ? (
          <div className={`text-sm ${t.textMuted}`}>No structured sources configured.</div>
        ) : (
          <div className="overflow-x-auto">
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
              <tbody className={t.divide}>
                {sources.map((src, i) => (
                  <tr key={i} className={t.rowHover}>
                    <td className={`py-2 px-3 ${t.textMain} font-medium`}>{src.source_name}</td>
                    <td className={`py-2 px-3 ${t.textDim} font-mono text-xs`}>{src.source_type}</td>
                    <td className="py-2 px-3">
                      <div className="flex flex-wrap gap-1">
                        {src.categories.map(c => (
                          <span key={c} className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${t.preemptOk}`}>
                            {CAT_LABELS[c] || c}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className={`py-2 px-3 font-mono ${t.textDim}`}>{src.record_count.toLocaleString()}</td>
                    <td className={`py-2 px-3 ${t.textFaint}`}>{formatDate(src.last_fetched_at)}</td>
                    <td className="py-2 px-3">
                      {src.is_active ? (
                        <span className={`flex items-center gap-1 text-xs ${t.statusOk}`}>
                          <CheckCircle className="w-3 h-3" /> Active
                        </span>
                      ) : (
                        <span className={`flex items-center gap-1 text-xs ${t.statusErr}`}>
                          <XCircle className="w-3 h-3" /> Inactive
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ───── Preemption Tab ───── */
function PreemptionTab({ t, cats, matrix, states }: {
  t: typeof LT;
  cats: string[];
  matrix: Record<string, Record<string, { allows: boolean; notes: string | null }>>;
  states: string[];
}) {
  const [hoveredCell, setHoveredCell] = useState<{ state: string; cat: string } | null>(null);

  if (states.length === 0) {
    return (
      <div className={`${t.card} p-10 text-center ${t.textMuted}`}>
        No preemption rules in the database yet.
      </div>
    );
  }

  return (
    <div className={`${t.card} p-5 space-y-3`}>
      <div className={`${t.label}`}>State × Category Preemption Matrix</div>
      <p className={`text-xs ${t.textFaint}`}>
        Green = allows local override, Red = preempted by state law. Hover for notes.
      </p>
      <div className="overflow-x-auto">
        <table className="text-sm">
          <thead>
            <tr>
              <th className={`py-2 px-3 text-left ${t.label}`}>State</th>
              {cats.map(c => (
                <th key={c} className={`py-2 px-2 text-center ${t.label}`}>
                  <span className="block whitespace-nowrap">{CAT_LABELS[c] || c}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {states.map(state => (
              <tr key={state} className={t.rowHover}>
                <td className={`py-1.5 px-3 font-mono font-bold ${t.textMain}`}>{state}</td>
                {cats.map(cat => {
                  const cell = matrix[state]?.[cat];
                  if (!cell) {
                    return <td key={cat} className="py-1.5 px-2 text-center">
                      <span className={`text-xs ${t.textFaint}`}>—</span>
                    </td>;
                  }
                  const isHovered = hoveredCell?.state === state && hoveredCell?.cat === cat;
                  return (
                    <td
                      key={cat}
                      className="py-1.5 px-2 text-center relative"
                      onMouseEnter={() => setHoveredCell({ state, cat })}
                      onMouseLeave={() => setHoveredCell(null)}
                    >
                      <span className={`inline-flex items-center justify-center w-7 h-7 rounded-lg text-xs font-bold ${
                        cell.allows ? t.preemptOk : t.preemptNo
                      }`}>
                        {cell.allows ? '✓' : '✗'}
                      </span>
                      {isHovered && cell.notes && (
                        <div className={`absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 rounded-lg text-xs max-w-[250px] ${t.tooltip} shadow-lg`}>
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

/* ── Type re-export for inline usage ── */
import type { JurisdictionDataOverview } from '../../api/client';
