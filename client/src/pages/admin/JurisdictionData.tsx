import { useState, useMemo, useCallback } from 'react';
import {
  Database, ChevronDown, ChevronRight, AlertTriangle, CheckCircle,
  XCircle, Loader2, RefreshCw, Layers, Globe2, Filter, Trash2, Check,
  X, ExternalLink, Settings2, ChevronUp, GripVertical, Eye, EyeOff, Plus, Info
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useQueryClient } from '@tanstack/react-query';
import { useJurisdictionData } from '../../hooks/useJurisdictionData';
import { useIndustryProfiles } from '../../hooks/useIndustryProfiles';
import { useIsLightMode } from '../../hooks/useIsLightMode';
import { api } from '../../api/client';
import type { JurisdictionDataState, JurisdictionDataCitySummary, JurisdictionDataOverview, JurisdictionDetail, IndustryProfile, CategoryEvidence } from '../../api/client';

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

const ALL_CATEGORIES = Object.keys(CAT_LABELS);
const VALID_RATE_TYPES = ['general', 'tipped', 'exempt_salary', 'hotel', 'fast_food', 'healthcare'];

function confidenceColor(confidence: number | undefined): 'green' | 'yellow' | 'red' | 'gray' {
  if (confidence == null) return 'gray';
  if (confidence >= 90) return 'green';
  if (confidence >= 70) return 'yellow';
  return 'red';
}

const CONF_DOT: Record<string, string> = {
  green: 'bg-emerald-500',
  yellow: 'bg-amber-400',
  red: 'bg-red-400',
  gray: 'bg-zinc-400',
};

const CONF_BADGE_BG: Record<string, string> = {
  green: 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400',
  yellow: 'bg-amber-400/20 text-amber-700 dark:text-amber-400',
  red: 'bg-red-400/20 text-red-600 dark:text-red-400',
  gray: 'bg-zinc-400/20 text-zinc-500',
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
  const { profiles, create: createProfile, update: updateProfile, remove: removeProfile } = useIndustryProfiles();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>('coverage');
  const [expandedStates, setExpandedStates] = useState<Set<string>>(new Set());
  const [filterState, setFilterState] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterStaleOnly, setFilterStaleOnly] = useState(false);
  const [selectedCityId, setSelectedCityId] = useState<string | null>(null);
  const [cityDetail, setCityDetail] = useState<JurisdictionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [profileEditorOpen, setProfileEditorOpen] = useState(false);
  const [editingProfile, setEditingProfile] = useState<IndustryProfile | null>(null);

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
    try {
      await api.adminJurisdictions.delete(id);
    } catch (err: any) {
      alert(err?.status === 409 ? 'Cannot delete — linked business locations exist.' : (err?.message || 'Delete failed'));
      throw err;
    }
    const fresh = await api.adminJurisdictionData.overview(true);
    queryClient.setQueryData(['jurisdiction-data-overview'], fresh);
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

  return (
    <div className={`min-h-screen ${t.pageBg} p-5 md:p-8`}>
      <div className="max-w-[1400px] mx-auto space-y-5">

        {/* ── Header ── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className={`text-4xl tracking-tighter font-bold ${t.textMain}`}>JURISDICTION DATA</h1>
            <p className={`text-sm ${t.textMuted} mt-1`}>Compliance data repository overview</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setEditingProfile(null); setProfileEditorOpen(true); }}
              className={`p-1.5 rounded-lg transition ${t.btnGhost} ${t.innerEl}`}
              title="Manage industry profiles"
            >
              <Settings2 className="w-3.5 h-3.5" />
            </button>

            <button
              onClick={() => hardRefresh()}
              className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg transition ${t.btnGhost} ${t.innerEl}`}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh
            </button>
          </div>
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
              <CoverageTab t={t} states={data.states} cats={summary.required_categories}
                expandedStates={expandedStates} toggleState={toggleState} onDelete={handleDelete}
                onCityClick={openCity} />
            )}
            {activeTab === 'missing' && (
              <MissingDataTab t={t} rows={missingRows} cats={summary.required_categories} states={data.states}
                filterState={filterState} setFilterState={setFilterState}
                filterCategory={filterCategory} setFilterCategory={setFilterCategory}
                filterStaleOnly={filterStaleOnly} setFilterStaleOnly={setFilterStaleOnly}
                onDelete={handleDelete} onCityClick={openCity} />
            )}
            {activeTab === 'quality' && (
              <DataQualityTab t={t} summary={summary} sources={data.structured_sources} />
            )}
            {activeTab === 'preemption' && (
              <PreemptionTab t={t} cats={summary.required_categories} matrix={preemptionMatrix.matrix} states={preemptionMatrix.states} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* ── City Detail Drawer ── */}
      <AnimatePresence>
        {selectedCityId && (
          <CityDetailDrawer t={t} detail={cityDetail} loading={loadingDetail} onClose={closeCity}
            profiles={profiles} onOpenProfileEditor={() => { setEditingProfile(null); setProfileEditorOpen(true); }} />
        )}
      </AnimatePresence>

      {/* ── Profile Editor Modal ── */}
      <AnimatePresence>
        {profileEditorOpen && (
          <ProfileEditorModal
            t={t}
            profiles={profiles}
            editingProfile={editingProfile}
            onClose={() => { setProfileEditorOpen(false); setEditingProfile(null); }}
            onEdit={(p) => setEditingProfile(p)}
            onCreate={createProfile}
            onUpdate={updateProfile}
            onDelete={removeProfile}
          />
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
        <button onClick={async (e) => { e.stopPropagation(); setDeleting(true); try { await onDelete(); } catch { setDeleting(false); setConfirming(false); } }}
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
                          <span key={c} className={`text-[10px] font-mono ${t.textFaint}`}>
                            {CAT_LABELS[c] || c}
                          </span>
                        ))}
                      </div>
                      {/* city rows */}
                      {s.cities.map(city => (
                        <div key={city.city} onClick={() => onCityClick(city.id)}
                          className={`group flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer ${t.rowHover}`}>
                          <span className={`text-sm ${t.textMain} w-40 truncate`}>{city.city}</span>
                          <div className="flex gap-1.5">
                            {cats.map(c => (
                              <div key={c}
                                className={`w-3 h-3 rounded-full ${city.categories_present.includes(c) ? t.dotOk : t.dotMiss}`}
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
function CityDetailDrawer({ t, detail, loading, onClose, profiles, onOpenProfileEditor }: {
  t: typeof LT; detail: JurisdictionDetail | null; loading: boolean; onClose: () => void;
  profiles: IndustryProfile[]; onOpenProfileEditor: () => void;
}) {
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);

  const selectedProfile = useMemo(
    () => profiles.find(p => p.id === selectedProfileId) ?? null,
    [profiles, selectedProfileId]
  );

  const grouped = useMemo(() => {
    if (!detail) return {} as Record<string, JurisdictionDetail['requirements']>;
    const map: Record<string, JurisdictionDetail['requirements']> = {};
    for (const req of detail.requirements) {
      const cat = req.category || 'other';
      if (!map[cat]) map[cat] = [];
      map[cat].push(req);
    }

    if (!selectedProfile) return map;

    // Sort entries by profile's category_order
    const focusedSet = new Set(selectedProfile.focused_categories);
    const orderIndex = new Map(selectedProfile.category_order.map((c, i) => [c, i]));
    const sorted: Record<string, JurisdictionDetail['requirements']> = {};
    const entries = Object.entries(map);

    entries.sort((a, b) => {
      const aFocused = focusedSet.has(a[0]);
      const bFocused = focusedSet.has(b[0]);
      const aInOrder = orderIndex.has(a[0]);
      const bInOrder = orderIndex.has(b[0]);

      // Focused categories first (in category_order), then non-focused in order, then unknown
      if (aFocused !== bFocused) return aFocused ? -1 : 1;
      if (aInOrder && bInOrder) return (orderIndex.get(a[0])!) - (orderIndex.get(b[0])!);
      if (aInOrder !== bInOrder) return aInOrder ? -1 : 1;
      return 0;
    });

    for (const [k, v] of entries) sorted[k] = v;
    return sorted;
  }, [detail, selectedProfile]);

  const focusedSet = useMemo(
    () => selectedProfile ? new Set(selectedProfile.focused_categories) : null,
    [selectedProfile]
  );

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
                  {/* Profile selector */}
                  <div className="flex items-center gap-1.5 mt-2">
                    <select
                      value={selectedProfileId ?? ''}
                      onChange={e => setSelectedProfileId(e.target.value || null)}
                      className={`${t.select} text-xs px-2.5 py-1`}
                    >
                      <option value="">All Categories</option>
                      {profiles.map(p => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                    <button
                      onClick={onOpenProfileEditor}
                      className={`p-1 rounded-lg transition ${t.btnGhost}`}
                      title="Manage industry profiles"
                    >
                      <Settings2 className="w-3 h-3" />
                    </button>
                  </div>
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

          {detail && !loading && Object.entries(grouped).map(([category, reqs]) => {
            const dimmed = focusedSet && !focusedSet.has(category);
            const evidence = selectedProfile?.category_evidence?.[category];
            const confColor = confidenceColor(evidence?.confidence);
            return (
            <div key={category} className={`${t.card} p-4 space-y-2 transition-opacity ${dimmed ? 'opacity-40' : ''}`}>
              <div className={`${t.label} flex items-center gap-2`}>
                {evidence ? (
                  <span className={`w-2.5 h-2.5 rounded-full ${CONF_DOT[confColor]}`} title={`Confidence: ${evidence.confidence}%`} />
                ) : (
                  <span className={`w-2.5 h-2.5 rounded-full ${t.dotOk}`} />
                )}
                {CAT_LABELS[category] || category.replace(/_/g, ' ')}
                <span className={`${t.textFaint} font-normal`}>({reqs.length})</span>
                {evidence && evidence.confidence < 70 && (
                  <span className="text-[9px] font-normal text-red-400 ml-1">needs review</span>
                )}
              </div>
              {evidence?.reason && (
                <p className={`text-[10px] italic ${t.textFaint} -mt-0.5 leading-relaxed`}>{evidence.reason}</p>
              )}

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
            );
          })}

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

/* ───── Profile Editor Modal ───── */
function ProfileEditorModal({ t, profiles, editingProfile, onClose, onEdit, onCreate, onUpdate, onDelete }: {
  t: typeof LT;
  profiles: IndustryProfile[];
  editingProfile: IndustryProfile | null;
  onClose: () => void;
  onEdit: (p: IndustryProfile | null) => void;
  onCreate: (data: { name: string; description?: string; focused_categories: string[]; rate_types: string[]; category_order: string[]; category_evidence?: Record<string, CategoryEvidence> }) => Promise<unknown>;
  onUpdate: (args: { id: string; data: { name?: string; description?: string; focused_categories?: string[]; rate_types?: string[]; category_order?: string[]; category_evidence?: Record<string, CategoryEvidence> } }) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
}) {
  const [formName, setFormName] = useState(editingProfile?.name ?? '');
  const [formDesc, setFormDesc] = useState(editingProfile?.description ?? '');
  const [formFocused, setFormFocused] = useState<Set<string>>(new Set(editingProfile?.focused_categories ?? ALL_CATEGORIES.slice(0, 4)));
  const [formOrder, setFormOrder] = useState<string[]>(editingProfile?.category_order ?? [...ALL_CATEGORIES]);
  const [formRateTypes, setFormRateTypes] = useState<Set<string>>(new Set(editingProfile?.rate_types ?? []));
  const [formEvidence, setFormEvidence] = useState<Record<string, CategoryEvidence>>(editingProfile?.category_evidence ?? {});
  const [expandedCat, setExpandedCat] = useState<string | null>(null);
  const [newSource, setNewSource] = useState('');
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const isNew = !editingProfile;

  const today = new Date().toISOString().slice(0, 10);

  const resetForm = useCallback((p: IndustryProfile | null) => {
    setFormName(p?.name ?? '');
    setFormDesc(p?.description ?? '');
    setFormFocused(new Set(p?.focused_categories ?? ALL_CATEGORIES.slice(0, 4)));
    setFormOrder(p?.category_order ?? [...ALL_CATEGORIES]);
    setFormRateTypes(new Set(p?.rate_types ?? []));
    setFormEvidence(p?.category_evidence ?? {});
    setExpandedCat(null);
    setConfirmDelete(false);
  }, []);

  const updateEvidence = (cat: string, patch: Partial<CategoryEvidence>) => {
    setFormEvidence(prev => {
      const existing = prev[cat] ?? { reason: '', confidence: 50, sources: [], last_reviewed: null };
      return { ...prev, [cat]: { ...existing, ...patch, last_reviewed: today } };
    });
  };

  const addSource = (cat: string) => {
    const trimmed = newSource.trim();
    if (!trimmed) return;
    const existing = formEvidence[cat];
    if (existing?.sources?.includes(trimmed)) return;
    updateEvidence(cat, { sources: [...(existing?.sources ?? []), trimmed] });
    setNewSource('');
  };

  const removeSource = (cat: string, idx: number) => {
    const sources = [...(formEvidence[cat]?.sources ?? [])];
    sources.splice(idx, 1);
    updateEvidence(cat, { sources });
  };

  // Profile-level confidence summary
  const focusedConfidence = useMemo(() => {
    const focused = formOrder.filter(c => formFocused.has(c));
    if (focused.length === 0) return null;
    const withEvidence = focused.filter(c => formEvidence[c]?.confidence != null);
    if (withEvidence.length === 0) return null;
    const avg = Math.round(withEvidence.reduce((sum, c) => sum + (formEvidence[c]?.confidence ?? 0), 0) / withEvidence.length);
    const weak = focused.filter(c => (formEvidence[c]?.confidence ?? 0) < 70).length;
    const missing = focused.length - withEvidence.length;
    return { avg, weak, missing, total: focused.length };
  }, [formOrder, formFocused, formEvidence]);

  const handleSave = async () => {
    if (!formName.trim()) return;
    setSaving(true);
    try {
      const payload = {
        name: formName.trim(),
        description: formDesc.trim() || undefined,
        focused_categories: formOrder.filter(c => formFocused.has(c)),
        rate_types: [...formRateTypes],
        category_order: formOrder,
        category_evidence: Object.keys(formEvidence).length > 0 ? formEvidence : undefined,
      };
      if (editingProfile) {
        await onUpdate({ id: editingProfile.id, data: payload });
      } else {
        await onCreate(payload);
      }
      onClose();
    } catch (e: any) {
      alert(e?.message || 'Save failed');
    }
    setSaving(false);
  };

  const handleDeleteProfile = async () => {
    if (!editingProfile) return;
    setDeleting(true);
    try {
      await onDelete(editingProfile.id);
      onClose();
    } catch (e: any) {
      alert(e?.message || 'Delete failed');
    }
    setDeleting(false);
  };

  const moveCategory = (idx: number, dir: -1 | 1) => {
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= formOrder.length) return;
    const next = [...formOrder];
    [next[idx], next[newIdx]] = [next[newIdx], next[idx]];
    setFormOrder(next);
  };

  const toggleFocused = (cat: string) => {
    setFormFocused(prev => {
      const next = new Set(prev);
      next.has(cat) ? next.delete(cat) : next.add(cat);
      return next;
    });
  };

  const toggleRateType = (rt: string) => {
    setFormRateTypes(prev => {
      const next = new Set(prev);
      next.has(rt) ? next.delete(rt) : next.add(rt);
      return next;
    });
  };

  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/40 z-40" onClick={onClose} />
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.15 }}
        className={`fixed inset-0 z-50 flex items-center justify-center p-4`}>
        <div className={`${t.card} w-full max-w-2xl max-h-[85vh] overflow-y-auto shadow-2xl`} onClick={e => e.stopPropagation()}>
          <div className="p-5 space-y-4">
            {/* Modal header */}
            <div className="flex items-center justify-between">
              <h2 className={`text-lg font-bold ${t.textMain}`}>
                {isNew ? 'New Industry Profile' : `Edit: ${editingProfile.name}`}
              </h2>
              <button onClick={onClose} className={`p-1 rounded-lg ${t.btnGhost}`}><X className="w-4 h-4" /></button>
            </div>

            {/* Profile list (when not editing a specific one and it's "new" mode) */}
            {isNew && profiles.length > 0 && (
              <div className="space-y-1">
                <div className={t.label}>Existing Profiles</div>
                <div className="space-y-1">
                  {profiles.map(p => (
                    <button key={p.id} onClick={() => { onEdit(p); resetForm(p); }}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm ${t.rowHover} ${t.textMain} flex items-center justify-between`}>
                      <span>{p.name}</span>
                      <span className={`text-[10px] ${t.textFaint}`}>{p.focused_categories.length} focused</span>
                    </button>
                  ))}
                </div>
                <div className={`border-t ${t.border} my-3`} />
                <div className={t.label}>Create New</div>
              </div>
            )}

            {/* Form */}
            <div className="space-y-3">
              <div>
                <label className={`${t.label} block mb-1`}>Name</label>
                <input value={formName} onChange={e => setFormName(e.target.value)}
                  className={`w-full ${t.select} px-3 py-2 text-sm`} placeholder="e.g. Restaurant / Hospitality" />
              </div>
              <div>
                <label className={`${t.label} block mb-1`}>Description</label>
                <textarea value={formDesc} onChange={e => setFormDesc(e.target.value)}
                  className={`w-full ${t.select} px-3 py-2 text-sm resize-none`} rows={2} placeholder="Optional notes" />
              </div>

              {/* Profile confidence summary */}
              {focusedConfidence && (
                <div className={`${t.innerEl} px-3 py-2 flex items-center gap-3`}>
                  <Info className={`w-3.5 h-3.5 flex-shrink-0 ${t.textFaint}`} />
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-xs font-medium ${t.textDim}`}>Profile confidence:</span>
                    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${CONF_BADGE_BG[confidenceColor(focusedConfidence.avg)]}`}>
                      {focusedConfidence.avg}%
                    </span>
                    {focusedConfidence.weak > 0 && (
                      <span className="text-[10px] text-red-400">{focusedConfidence.weak} category{focusedConfidence.weak !== 1 ? 'ies' : 'y'} below 70%</span>
                    )}
                    {focusedConfidence.missing > 0 && (
                      <span className={`text-[10px] ${t.textFaint}`}>{focusedConfidence.missing} without evidence</span>
                    )}
                  </div>
                </div>
              )}

              {/* Category order + focus toggles + evidence */}
              <div>
                <label className={`${t.label} block mb-1`}>Categories (reorder, toggle focus, expand for evidence)</label>
                <div className={`${t.innerEl} p-2 space-y-0.5`}>
                  {formOrder.map((cat, idx) => {
                    const ev = formEvidence[cat];
                    const confColor = confidenceColor(ev?.confidence);
                    const isExpanded = expandedCat === cat;
                    return (
                      <div key={cat}>
                        <div className={`flex items-center gap-2 px-2 py-1.5 rounded-lg ${t.rowHover}`}>
                          <div className="flex flex-col gap-0.5">
                            <button onClick={() => moveCategory(idx, -1)} disabled={idx === 0}
                              className={`${t.btnGhost} disabled:opacity-20`}><ChevronUp className="w-3 h-3" /></button>
                            <button onClick={() => moveCategory(idx, 1)} disabled={idx === formOrder.length - 1}
                              className={`${t.btnGhost} disabled:opacity-20`}><ChevronDown className="w-3 h-3" /></button>
                          </div>
                          <GripVertical className={`w-3.5 h-3.5 ${t.textFaint}`} />
                          <span className={`text-sm flex-1 ${formFocused.has(cat) ? t.textMain : t.textFaint}`}>
                            {CAT_LABELS[cat] || cat}
                          </span>
                          {/* confidence badge */}
                          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${CONF_BADGE_BG[confColor]}`}>
                            {ev?.confidence != null ? `${ev.confidence}%` : '—'}
                          </span>
                          <button onClick={() => toggleFocused(cat)}
                            className={`p-1 rounded transition ${formFocused.has(cat) ? t.statusOk : t.textFaint + ' opacity-40'}`}
                            title={formFocused.has(cat) ? 'Focused (click to unfocus)' : 'Not focused (click to focus)'}>
                            {formFocused.has(cat) ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                          </button>
                          <button onClick={() => setExpandedCat(isExpanded ? null : cat)}
                            className={`p-1 rounded transition ${t.btnGhost}`} title="Evidence">
                            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                          </button>
                        </div>
                        {/* Expanded evidence panel */}
                        <AnimatePresence>
                          {isExpanded && (
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: 'auto', opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              transition={{ duration: 0.15 }}
                              className="overflow-hidden"
                            >
                              <div className={`mx-2 mb-2 p-3 rounded-lg border ${t.border} space-y-2.5`}>
                                {/* Reason */}
                                <div>
                                  <label className={`text-[10px] ${t.textFaint} block mb-0.5`}>Reason</label>
                                  <textarea
                                    value={ev?.reason ?? ''}
                                    onChange={e => updateEvidence(cat, { reason: e.target.value })}
                                    className={`w-full ${t.select} px-2 py-1.5 text-xs resize-none`}
                                    rows={2}
                                    placeholder="Why this category ranks here..."
                                  />
                                </div>
                                {/* Confidence slider */}
                                <div>
                                  <label className={`text-[10px] ${t.textFaint} block mb-0.5`}>Confidence</label>
                                  <div className="flex items-center gap-2">
                                    <input
                                      type="range" min={0} max={100}
                                      value={ev?.confidence ?? 50}
                                      onChange={e => updateEvidence(cat, { confidence: parseInt(e.target.value) })}
                                      className="flex-1 h-1.5 accent-emerald-500"
                                      style={{
                                        background: `linear-gradient(to right, ${
                                          (ev?.confidence ?? 50) >= 90 ? '#10b981' :
                                          (ev?.confidence ?? 50) >= 70 ? '#f59e0b' : '#ef4444'
                                        } ${ev?.confidence ?? 50}%, transparent ${ev?.confidence ?? 50}%)`,
                                      }}
                                    />
                                    <span className={`text-xs font-mono w-8 text-right font-bold ${
                                      confColor === 'green' ? 'text-emerald-500' :
                                      confColor === 'yellow' ? 'text-amber-500' :
                                      confColor === 'red' ? 'text-red-400' : t.textFaint
                                    }`}>{ev?.confidence ?? 50}</span>
                                  </div>
                                </div>
                                {/* Sources */}
                                <div>
                                  <label className={`text-[10px] ${t.textFaint} block mb-0.5`}>Sources</label>
                                  <div className="flex flex-wrap gap-1 mb-1.5">
                                    {(ev?.sources ?? []).map((src, si) => (
                                      <span key={si} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] ${t.preemptOk}`}>
                                        {src}
                                        <button onClick={() => removeSource(cat, si)} className="hover:opacity-70"><X className="w-2.5 h-2.5" /></button>
                                      </span>
                                    ))}
                                  </div>
                                  <div className="flex gap-1">
                                    <input
                                      value={newSource}
                                      onChange={e => setNewSource(e.target.value)}
                                      onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addSource(cat); } }}
                                      className={`flex-1 ${t.select} px-2 py-1 text-[10px]`}
                                      placeholder="Add source..."
                                    />
                                    <button onClick={() => addSource(cat)}
                                      className={`p-1 rounded transition ${t.btnGhost}`}><Plus className="w-3 h-3" /></button>
                                  </div>
                                </div>
                                {/* Last reviewed */}
                                {ev?.last_reviewed && (
                                  <div className={`text-[10px] ${t.textFaint}`}>
                                    Last reviewed: {ev.last_reviewed}
                                  </div>
                                )}
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Rate types */}
              <div>
                <label className={`${t.label} block mb-1`}>Rate Types</label>
                <div className="flex flex-wrap gap-1.5">
                  {VALID_RATE_TYPES.map(rt => (
                    <button key={rt} onClick={() => toggleRateType(rt)}
                      className={`px-2.5 py-1 text-xs font-mono rounded-lg transition ${formRateTypes.has(rt) ? t.preemptOk : t.innerEl + ' ' + t.textFaint}`}>
                      {rt}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between pt-2">
              <div>
                {editingProfile && !confirmDelete && (
                  <button onClick={() => setConfirmDelete(true)}
                    className={`text-xs ${t.statusErr} hover:underline`}>Delete profile</button>
                )}
                {editingProfile && confirmDelete && (
                  <span className="flex items-center gap-2">
                    <span className={`text-xs ${t.statusErr}`}>Confirm?</span>
                    <button onClick={handleDeleteProfile} disabled={deleting}
                      className={`text-xs ${t.confirmBtn} font-bold`}>{deleting ? 'Deleting...' : 'Yes, delete'}</button>
                    <button onClick={() => setConfirmDelete(false)}
                      className={`text-xs ${t.btnGhost}`}>Cancel</button>
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                <button onClick={onClose} className={`px-3 py-1.5 text-sm rounded-lg ${t.btnGhost} ${t.innerEl}`}>Cancel</button>
                <button onClick={handleSave} disabled={saving || !formName.trim()}
                  className={`px-4 py-1.5 text-sm rounded-lg font-medium transition bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40`}>
                  {saving ? 'Saving...' : isNew ? 'Create' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </>
  );
}
