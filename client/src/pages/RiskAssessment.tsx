import { useState, useEffect, useCallback } from 'react';
import { HelpCircle, Plus, Check, X, ChevronDown, ChevronRight, User, Calendar, Clock, Play } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList, AreaChart, Area, Line, ReferenceArea } from 'recharts';
import type { RiskAssessmentResult, DimensionResult, ERCaseMetrics, RiskActionItem, AssignableUser, RiskHistoryEntry } from '../types';
import { riskAssessment, erCopilot, companies as companiesApi, ApiRequestError } from '../api/client';
import { useAuth } from '../context/AuthContext';

type Band = 'low' | 'moderate' | 'high' | 'critical';

const BAND_COLOR: Record<Band, { text: string; dot: string; badge: string; bar: string }> = {
  low:      { text: 'text-emerald-400', dot: 'bg-emerald-500',                          badge: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20', bar: 'bg-emerald-500' },
  moderate: { text: 'text-amber-400',   dot: 'bg-amber-500',                            badge: 'bg-amber-500/10  text-amber-400  border border-amber-500/20',  bar: 'bg-amber-500'   },
  high:     { text: 'text-orange-400',  dot: 'bg-orange-500',                           badge: 'bg-orange-500/10 text-orange-400 border border-orange-500/20', bar: 'bg-orange-500'  },
  critical: { text: 'text-red-400',     dot: 'bg-red-500 animate-pulse',                badge: 'bg-red-500/10    text-red-400    border border-red-500/20',    bar: 'bg-red-500'     },
};

const BAND_LABEL: Record<Band, string> = {
  low: 'Low', moderate: 'Moderate', high: 'High', critical: 'Critical',
};

const DIMENSION_META: Record<string, { label: string }> = {
  compliance:  { label: 'Compliance'  },
  incidents:   { label: 'Incidents'   },
  er_cases:    { label: 'ER Cases'    },
  workforce:   { label: 'Workforce'   },
  legislative: { label: 'Legislative' },
};

const DIMENSION_ORDER = ['compliance', 'incidents', 'er_cases', 'workforce', 'legislative'] as const;

const DIMENSION_HELP: Record<string, string> = {
  overall: 'The weighted composite of all five dimension scores. Higher means more exposure. Weights: Compliance 30%, Incidents 25%, ER Cases 25%, Workforce 15%, Legislative 5%.',
  compliance: 'Measures regulatory compliance gaps across your locations — minimum wage violations, missing postings, and jurisdiction-specific requirements. Contributes 30% of the overall score.',
  incidents: 'Tracks workplace safety and behavioral incident frequency, severity, and resolution time. Contributes 25% of the overall score.',
  er_cases: 'Evaluates open employee relations cases, escalation patterns, and unresolved disputes. Contributes 25% of the overall score.',
  workforce: 'Assesses workforce-level risks like turnover concentration, onboarding gaps, and headcount exposure. Contributes 15% of the overall score.',
  legislative: 'Monitors upcoming legislation and regulatory changes that could impact your operations. Contributes 5% of the overall score.',
};

const PRIORITY_COLOR: Record<string, { badge: string }> = {
  critical: { badge: 'bg-red-500/10 text-red-400 border border-red-500/20' },
  high:     { badge: 'bg-orange-500/10 text-orange-400 border border-orange-500/20' },
  medium:   { badge: 'bg-amber-500/10 text-amber-400 border border-amber-500/20' },
  low:      { badge: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' },
};

type ComplianceAlertLocation = {
  location_id: string;
  location_name: string | null;
  city: string | null;
  state: string | null;
  violation_count: number;
};

type ComplianceAlertMetrics = {
  total: number;
  hourly: number;
  salary: number;
  locations: number;
  topLocations: ComplianceAlertLocation[];
};

function getComplianceAlertMetrics(dim: DimensionResult): ComplianceAlertMetrics {
  const rawData = dim.raw_data;
  const toNumber = (key: string) => {
    const value = rawData[key];
    return typeof value === 'number' ? value : 0;
  };
  const topLocationsRaw = rawData.top_minimum_wage_violation_locations;
  const topLocations = Array.isArray(topLocationsRaw)
    ? topLocationsRaw.flatMap((item) => {
        if (!item || typeof item !== 'object') {
          return [];
        }

        const candidate = item as Record<string, unknown>;
        const locationId = typeof candidate.location_id === 'string' ? candidate.location_id : null;
        const violationCount = typeof candidate.violation_count === 'number' ? candidate.violation_count : null;

        if (!locationId || violationCount === null) {
          return [];
        }

        return [{
          location_id: locationId,
          location_name: typeof candidate.location_name === 'string' ? candidate.location_name : null,
          city: typeof candidate.city === 'string' ? candidate.city : null,
          state: typeof candidate.state === 'string' ? candidate.state : null,
          violation_count: violationCount,
        }];
      })
    : [];

  return {
    total: toNumber('minimum_wage_violation_employee_count'),
    hourly: toNumber('hourly_minimum_wage_violation_count'),
    salary: toNumber('salary_minimum_wage_violation_count'),
    locations: toNumber('locations_with_minimum_wage_violations'),
    topLocations,
  };
}

function formatComplianceLocation(location: ComplianceAlertLocation): string {
  if (location.location_name?.trim()) {
    return location.location_name;
  }
  if (location.city && location.state) {
    return `${location.city}, ${location.state}`;
  }
  if (location.state) {
    return location.state;
  }
  return 'Unlabeled location';
}

function hasEmployeeComplianceAlerts(dim: DimensionResult): boolean {
  const rawData = dim.raw_data;
  return (
    typeof rawData.minimum_wage_violation_employee_count === 'number'
    && rawData.minimum_wage_violation_employee_count > 0
  );
}

function HelpTooltip({ text }: { text: string }) {
  return (
    <span className="relative group/help inline-flex">
      <HelpCircle className="w-3 h-3 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity cursor-help" />
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 px-3 py-2 text-[10px] leading-relaxed text-zinc-300 bg-zinc-900 border border-white/10 shadow-xl opacity-0 group-hover/help:opacity-100 transition-opacity z-50">
        {text}
      </span>
    </span>
  );
}

function BandBadge({ band }: { band: Band }) {
  const c = BAND_COLOR[band];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${c.badge}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {BAND_LABEL[band]}
    </span>
  );
}

function ScoreBar({ score, band }: { score: number; band: Band }) {
  return (
    <div className="h-px w-full bg-white/10 relative overflow-hidden">
      <div
        className={`absolute inset-y-0 left-0 ${BAND_COLOR[band].bar} transition-all duration-700`}
        style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
      />
    </div>
  );
}

function DimensionCard({ dimensionKey, dim, weight }: { dimensionKey: string; dim: DimensionResult; weight?: string }) {
  const meta = DIMENSION_META[dimensionKey] ?? { label: dimensionKey };
  const c = BAND_COLOR[dim.band];
  const complianceMetrics = dimensionKey === 'compliance' ? getComplianceAlertMetrics(dim) : null;

  return (
    <div className="bg-zinc-900 border border-white/10 p-6 flex flex-col gap-5 rounded-2xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">{meta.label}</div>
          {weight && <div className="text-[9px] text-zinc-600 uppercase tracking-widest mt-0.5">{weight} weight</div>}
        </div>
        <BandBadge band={dim.band} />
      </div>

      {/* Score */}
      <div className="flex items-end gap-2">
        <span className={`text-4xl font-light font-mono ${c.text}`}>{dim.score}</span>
        <span className="text-sm text-zinc-600 mb-1 font-mono">/ 100</span>
      </div>

      <ScoreBar score={dim.score} band={dim.band} />

      {/* Factors */}
      <div className="flex flex-col gap-1.5">
        {dim.factors.map((factor, i) => (
          <div key={i} className="flex items-start gap-2 text-[11px] text-zinc-500">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-zinc-700 shrink-0" />
            {factor}
          </div>
        ))}
      </div>

      {complianceMetrics && (
        <div className="border border-white/10 bg-black/20 p-3 flex flex-col gap-3 rounded-xl">
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">Employee Compliance Alerts</div>

          <div className="grid grid-cols-2 gap-px bg-white/10 rounded-lg overflow-hidden">
            {[
              { label: 'Below Min Wage', value: complianceMetrics.total, tone: complianceMetrics.total > 0 ? 'text-red-400' : 'text-zinc-300' },
              { label: 'Hourly', value: complianceMetrics.hourly, tone: complianceMetrics.hourly > 0 ? 'text-red-400' : 'text-zinc-300' },
              { label: 'Salary', value: complianceMetrics.salary, tone: complianceMetrics.salary > 0 ? 'text-red-400' : 'text-zinc-300' },
              { label: 'Locations', value: complianceMetrics.locations, tone: complianceMetrics.locations > 0 ? 'text-amber-400' : 'text-zinc-300' },
            ].map((metric) => (
              <div key={metric.label} className="bg-zinc-950 px-3 py-2">
                <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{metric.label}</div>
                <div className={`mt-1 text-xl font-light font-mono ${metric.tone}`}>{metric.value}</div>
              </div>
            ))}
          </div>

          {complianceMetrics.topLocations.length > 0 ? (
            <div className="flex flex-col gap-1.5">
              {complianceMetrics.topLocations.map((location) => (
                <div key={location.location_id} className="flex items-center justify-between gap-3 text-[10px] text-zinc-400">
                  <span className="truncate">{formatComplianceLocation(location)}</span>
                  <span className="font-mono text-red-400">{location.violation_count}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[10px] text-zinc-600 font-mono">No employee pay alerts detected.</div>
          )}
        </div>
      )}
    </div>
  );
}

type EmployeeViolation = {
  employee_name: string;
  pay_rate: number;
  threshold: number;
  shortfall: number;
  pay_classification: string;
  location_city: string | null;
  location_state: string | null;
};

type OpenCase = {
  case_id: string;
  title: string;
  status: string;
  category: string | null;
  created_at: string | null;
};

function formatCurrency(value: number): string {
  return value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

function formatStatus(status: string): string {
  return status.replace(/_/g, ' ');
}

function ActionItems({ data, companyId }: { data: RiskAssessmentResult; companyId?: string }) {
  const [items, setItems] = useState<RiskActionItem[]>([]);
  const [closedItems, setClosedItems] = useState<RiskActionItem[]>([]);
  const [users, setUsers] = useState<AssignableUser[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);

  const violations: EmployeeViolation[] = (() => {
    const raw = data.dimensions.compliance?.raw_data?.employee_violations;
    if (!Array.isArray(raw)) return [];
    return raw.filter(
      (v): v is EmployeeViolation =>
        v && typeof v === 'object' && typeof v.employee_name === 'string' && typeof v.pay_rate === 'number',
    );
  })();

  const cases: OpenCase[] = (() => {
    const raw = data.dimensions.er_cases?.raw_data?.open_cases;
    if (!Array.isArray(raw)) return [];
    return raw.filter(
      (c): c is OpenCase => c && typeof c === 'object' && typeof c.title === 'string' && typeof c.status === 'string',
    );
  })();

  const fetchItems = useCallback(async () => {
    try {
      const [open, all] = await Promise.all([
        riskAssessment.listActionItems('open', companyId),
        riskAssessment.listActionItems('all', companyId),
      ]);
      setItems(open);
      setClosedItems(all.filter(i => i.status !== 'open'));
    } catch { /* silently fail */ }
  }, [companyId]);

  const fetchUsers = useCallback(async () => {
    try {
      setUsers(await riskAssessment.getAssignableUsers(companyId));
    } catch { /* silently fail */ }
  }, [companyId]);

  useEffect(() => { fetchItems(); fetchUsers(); }, [fetchItems, fetchUsers]);

  const trackedRefs = new Set(items.map(i => i.source_ref).filter(Boolean));
  const closedRefs = new Set(closedItems.map(i => i.source_ref).filter(Boolean));

  const suggestedViolations = violations.filter(v => !trackedRefs.has(v.employee_name) && !closedRefs.has(v.employee_name));
  const suggestedCases = cases.filter(c => !trackedRefs.has(c.case_id) && !closedRefs.has(c.case_id));

  const addItem = async (title: string, description: string, sourceType: 'wage_violation' | 'er_case', sourceRef: string) => {
    const key = `${sourceType}:${sourceRef}`;
    setAdding(key);
    try {
      await riskAssessment.createActionItem({ title, description, source_type: sourceType, source_ref: sourceRef });
      await fetchItems();
    } catch { /* silently fail */ }
    setAdding(null);
  };

  const updateItem = async (id: string, update: { assigned_to?: string | null; due_date?: string | null; status?: 'open' | 'completed' }) => {
    try {
      await riskAssessment.updateActionItem(id, update);
      await fetchItems();
    } catch { /* silently fail */ }
  };

  const hasSuggestions = suggestedViolations.length > 0 || suggestedCases.length > 0;
  const hasItems = items.length > 0;
  const hasHistory = closedItems.length > 0;

  if (!hasSuggestions && !hasItems && !hasHistory) return null;

  return (
    <div>
      <div className="text-[10px] text-stone-500 uppercase tracking-widest font-bold mb-4">Action Items</div>
      <div className="space-y-4">

        {/* Suggested (auto-detected) items */}
        {hasSuggestions && (
          <div className="bg-zinc-900 border border-white/10 rounded-2xl divide-y divide-white/10 overflow-hidden">
            {suggestedViolations.length > 0 && (
              <div className="p-5">
                <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-3">Suggested — Wage Compliance</div>
                <div className="flex flex-col gap-2">
                  {suggestedViolations.map((v, i) => {
                    const isLarge = v.shortfall >= 10000;
                    const location = v.location_city && v.location_state ? `${v.location_city}, ${v.location_state}` : v.location_state || 'Unknown';
                    const rateLabel = v.pay_classification === 'exempt' ? 'salary' : 'hourly rate';
                    const addKey = `wage_violation:${v.employee_name}`;
                    return (
                      <div key={i} className="flex items-center gap-3 text-[11px]">
                        <button
                          onClick={() => addItem(
                            `${v.employee_name} below minimum wage`,
                            `${v.employee_name}'s ${rateLabel} is ${formatCurrency(v.pay_rate)} but the minimum for ${location} is ${formatCurrency(v.threshold)} (gap: ${formatCurrency(v.shortfall)})`,
                            'wage_violation',
                            v.employee_name,
                          )}
                          disabled={adding === addKey}
                          className="shrink-0 w-5 h-5 flex items-center justify-center rounded bg-white/5 hover:bg-emerald-500/20 text-zinc-600 hover:text-emerald-400 transition-colors disabled:opacity-40"
                          title="Track this item"
                        >
                          <Plus size={12} />
                        </button>
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isLarge ? 'bg-red-500' : 'bg-amber-500'}`} />
                        <span className="text-zinc-400">
                          <span className="text-zinc-200">{v.employee_name}</span>
                          {`'s ${rateLabel} is `}
                          <span className="font-mono text-red-400">{formatCurrency(v.pay_rate)}</span>
                          {' — min '}
                          <span className="font-mono text-zinc-300">{formatCurrency(v.threshold)}</span>
                          <span className="text-zinc-600">{` (gap: ${formatCurrency(v.shortfall)})`}</span>
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {suggestedCases.length > 0 && (
              <div className="p-5">
                <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-3">Suggested — Open ER Cases</div>
                <div className="flex flex-col gap-2">
                  {suggestedCases.map((c) => {
                    const isPending = c.status === 'pending_determination';
                    const addKey = `er_case:${c.case_id}`;
                    return (
                      <div key={c.case_id} className="flex items-center gap-3 text-[11px]">
                        <button
                          onClick={() => addItem(
                            `ER case: ${c.title}`,
                            `Case '${c.title}' is ${formatStatus(c.status)}${c.category ? ` · ${formatStatus(c.category)}` : ''}`,
                            'er_case',
                            c.case_id,
                          )}
                          disabled={adding === addKey}
                          className="shrink-0 w-5 h-5 flex items-center justify-center rounded bg-white/5 hover:bg-emerald-500/20 text-zinc-600 hover:text-emerald-400 transition-colors disabled:opacity-40"
                          title="Track this item"
                        >
                          <Plus size={12} />
                        </button>
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isPending ? 'bg-red-500' : 'bg-amber-500'}`} />
                        <span className="text-zinc-400">
                          <span className="text-zinc-200">'{c.title}'</span>
                          {` is ${formatStatus(c.status)}`}
                          {c.category && <span className="text-zinc-600">{` · ${formatStatus(c.category)}`}</span>}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tracked (persisted) items */}
        {hasItems && (
          <div>
            <div className="text-[9px] text-stone-400 uppercase tracking-widest font-bold mb-3">Tracked ({items.length})</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {items.map((item) => {
                const isOverdue = item.due_date && new Date(item.due_date) < new Date(new Date().toDateString());
                return (
                  <div key={item.id} className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden group">
                    {/* Top: type badge stripe */}
                    <div className={`h-0.5 ${item.source_type === 'wage_violation' ? 'bg-red-500' : 'bg-amber-500'}`} />

                    <div className="p-5 flex flex-col gap-4">
                      {/* Title + description */}
                      <div>
                        <div className="flex items-start justify-between gap-3">
                          <div className="text-[12px] text-zinc-200 font-medium leading-snug">{item.title}</div>
                          <span className={`shrink-0 text-[8px] uppercase tracking-widest font-bold px-1.5 py-0.5 rounded ${
                            item.source_type === 'wage_violation'
                              ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                              : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                          }`}>
                            {item.source_type === 'wage_violation' ? 'Wage' : 'ER'}
                          </span>
                        </div>
                        {item.description && (
                          <div className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">{item.description}</div>
                        )}
                      </div>

                      {/* Controls row */}
                      <div className="flex items-center gap-2">
                        <div className="relative flex-1 min-w-0">
                          <User size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none" />
                          <select
                            value={item.assigned_to ?? ''}
                            onChange={(e) => updateItem(item.id, { assigned_to: e.target.value || null })}
                            className="w-full bg-zinc-800/80 border border-white/5 rounded-lg pl-6 pr-2 py-1.5 text-[10px] text-zinc-300 outline-none hover:border-white/10 transition-colors appearance-none cursor-pointer truncate"
                          >
                            <option value="">Unassigned</option>
                            {users.map(u => (
                              <option key={u.id} value={u.id}>{u.name}</option>
                            ))}
                          </select>
                        </div>
                        <div className="relative shrink-0">
                          <Calendar size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none" />
                          <input
                            type="date"
                            value={item.due_date ?? ''}
                            onChange={(e) => updateItem(item.id, { due_date: e.target.value || null })}
                            className={`bg-zinc-800/80 border rounded-lg pl-6 pr-2 py-1.5 text-[10px] outline-none hover:border-white/10 transition-colors w-[120px] cursor-pointer ${
                              isOverdue
                                ? 'border-red-500/30 text-red-400'
                                : 'border-white/5 text-zinc-300'
                            }`}
                          />
                        </div>
                      </div>

                      {/* Overdue warning */}
                      {isOverdue && (
                        <div className="flex items-center gap-1.5 text-[9px] text-red-400 font-mono">
                          <Clock size={10} />
                          Overdue
                        </div>
                      )}

                      {/* Action buttons */}
                      <div className="flex items-center gap-2 pt-2 border-t border-white/5">
                        <button
                          onClick={() => updateItem(item.id, { status: 'completed' })}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] font-bold uppercase tracking-widest hover:bg-emerald-500/20 transition-colors"
                        >
                          <Check size={11} />
                          Resolve
                        </button>
                        {item.assigned_to_name && (
                          <span className="ml-auto text-[9px] text-zinc-600 font-mono truncate">
                            {item.assigned_to_name}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* History (completed & dismissed) */}
        {hasHistory && (
          <div>
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="flex items-center gap-1.5 text-[10px] text-stone-400 uppercase tracking-widest font-bold hover:text-zinc-900 transition-colors mb-3"
            >
              {showHistory ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              History ({closedItems.length})
            </button>
            {showHistory && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {closedItems.map((item) => (
                  <div key={item.id} className="bg-zinc-900/60 border border-white/5 rounded-2xl overflow-hidden opacity-50 hover:opacity-75 transition-opacity">
                    <div className={`h-0.5 ${item.status === 'completed' ? 'bg-emerald-500/40' : 'bg-zinc-600/40'}`} />
                    <div className="p-4 flex items-start gap-3">
                      <span className={`mt-0.5 shrink-0 w-4 h-4 rounded-full flex items-center justify-center ${
                        item.status === 'completed'
                          ? 'bg-emerald-500/20 text-emerald-500'
                          : 'bg-zinc-700/50 text-zinc-500'
                      }`}>
                        {item.status === 'completed' ? <Check size={10} /> : <X size={10} />}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-[11px] text-zinc-400 line-through">{item.title}</div>
                        <div className="flex items-center gap-2 mt-1 text-[9px] text-zinc-600 font-mono">
                          <span className="uppercase tracking-widest font-bold">{item.status}</span>
                          {item.assigned_to_name && <span>· {item.assigned_to_name}</span>}
                          {item.closed_at && <span>· {new Date(item.closed_at).toLocaleDateString()}</span>}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const TREND_DIMENSION_COLORS: Record<string, string> = {
  compliance: '#f59e0b',
  incidents: '#ef4444',
  er_cases: '#3b82f6',
  workforce: '#a855f7',
  legislative: '#06b6d4',
};

function formatShortDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function TrendTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ dataKey: string; value: number; color: string }>; label?: string }) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="bg-zinc-900 border border-white/10 px-4 py-3 shadow-xl text-xs">
      <div className="text-zinc-500 font-mono text-[9px] uppercase tracking-widest mb-2">{label}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex items-center justify-between gap-6">
          <span className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
            <span className="text-zinc-400 capitalize">{entry.dataKey.replace('_', ' ')}</span>
          </span>
          <span className="font-mono text-zinc-200">{entry.value}</span>
        </div>
      ))}
    </div>
  );
}

function RiskTrendChart({ companyId }: { companyId?: string }) {
  const [history, setHistory] = useState<RiskHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [months, setMonths] = useState(12);
  const [visibleDimensions, setVisibleDimensions] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    riskAssessment.getHistory(months, companyId)
      .then((data) => {
        if (!cancelled) setHistory(data);
      })
      .catch(() => {
        if (!cancelled) setHistory([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [months, companyId]);

  const toggleDimension = (dim: string) => {
    setVisibleDimensions(prev => {
      const next = new Set(prev);
      if (next.has(dim)) next.delete(dim);
      else next.add(dim);
      return next;
    });
  };

  const chartData = history
    .slice()
    .sort((a, b) => new Date(a.computed_at).getTime() - new Date(b.computed_at).getTime())
    .map(entry => ({
      date: formatShortDate(entry.computed_at),
      overall_score: entry.overall_score,
      ...entry.dimensions,
    }));

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-[10px] text-stone-500 uppercase tracking-widest font-bold">Risk Trend</div>
        <div className="flex gap-0 border border-stone-300 rounded-lg overflow-hidden">
          {([3, 6, 12] as const).map(m => (
            <button
              key={m}
              onClick={() => setMonths(m)}
              className={`px-3 py-1.5 text-[10px] uppercase tracking-widest font-mono transition-colors ${
                months === m
                  ? 'bg-zinc-900 text-zinc-50'
                  : 'bg-stone-200 text-stone-500 hover:text-zinc-900'
              }`}
            >
              {m}m
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="bg-stone-200 rounded-2xl p-8 text-center">
          <div className="text-xs text-stone-500 uppercase tracking-wider animate-pulse">Loading trend data…</div>
        </div>
      )}

      {!loading && chartData.length === 0 && (
        <div className="bg-stone-200 rounded-2xl p-8 text-center">
          <div className="text-xs text-stone-500 uppercase tracking-wider">No history yet</div>
          <div className="text-[10px] text-stone-400 mt-2 font-mono">Risk assessments will be recorded automatically</div>
        </div>
      )}

      {!loading && chartData.length > 0 && (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6">
          {/* Dimension toggles */}
          <div className="flex flex-wrap gap-2 mb-5">
            {DIMENSION_ORDER.map(dim => {
              const active = visibleDimensions.has(dim);
              const color = TREND_DIMENSION_COLORS[dim];
              return (
                <button
                  key={dim}
                  onClick={() => toggleDimension(dim)}
                  className={`px-2.5 py-1 text-[9px] uppercase tracking-widest font-bold rounded-lg border transition-colors ${
                    active
                      ? 'border-white/20 text-zinc-200'
                      : 'border-white/5 text-zinc-600 hover:text-zinc-400 hover:border-white/10'
                  }`}
                  style={active ? { backgroundColor: `${color}20`, borderColor: `${color}40` } : undefined}
                >
                  <span className="inline-block w-1.5 h-1.5 rounded-full mr-1.5" style={{ backgroundColor: active ? color : '#52525b' }} />
                  {DIMENSION_META[dim]?.label ?? dim}
                </button>
              );
            })}
          </div>

          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={chartData} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
              {/* Risk zone reference bands */}
              <ReferenceArea y1={0} y2={25} fill="#10b981" fillOpacity={0.04} />
              <ReferenceArea y1={25} y2={50} fill="#f59e0b" fillOpacity={0.04} />
              <ReferenceArea y1={50} y2={75} fill="#f97316" fillOpacity={0.04} />
              <ReferenceArea y1={75} y2={100} fill="#ef4444" fillOpacity={0.04} />

              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#71717a' }}
                axisLine={{ stroke: 'rgba(255,255,255,0.05)' }}
                tickLine={false}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fontSize: 10, fill: '#71717a' }}
                axisLine={{ stroke: 'rgba(255,255,255,0.05)' }}
                tickLine={false}
                width={32}
              />
              <Tooltip content={<TrendTooltip />} />

              {/* Overall score — always visible */}
              <Area
                type="monotone"
                dataKey="overall_score"
                stroke="#e4e4e7"
                strokeWidth={2}
                fill="url(#overallGradient)"
                dot={{ r: 3, fill: '#e4e4e7', stroke: '#18181b', strokeWidth: 2 }}
                activeDot={{ r: 5, fill: '#e4e4e7', stroke: '#18181b', strokeWidth: 2 }}
                name="Overall"
              />

              {/* Dimension lines — toggleable */}
              {DIMENSION_ORDER.map(dim => {
                if (!visibleDimensions.has(dim)) return null;
                const color = TREND_DIMENSION_COLORS[dim];
                return (
                  <Line
                    key={dim}
                    type="monotone"
                    dataKey={dim}
                    stroke={color}
                    strokeWidth={1.5}
                    strokeDasharray="4 2"
                    dot={{ r: 2, fill: color, stroke: '#18181b', strokeWidth: 1 }}
                    activeDot={{ r: 4, fill: color, stroke: '#18181b', strokeWidth: 2 }}
                    name={DIMENSION_META[dim]?.label ?? dim}
                  />
                );
              })}

              <defs>
                <linearGradient id="overallGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#e4e4e7" stopOpacity={0.15} />
                  <stop offset="100%" stopColor="#e4e4e7" stopOpacity={0} />
                </linearGradient>
              </defs>
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function isEmptyResult(data: RiskAssessmentResult): boolean {
  if (data.overall_score !== 0) return false;
  if (hasEmployeeComplianceAlerts(data.dimensions.compliance)) return false;
  return DIMENSION_ORDER.every(k => data.dimensions[k].score === 0);
}

export default function RiskAssessment() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [data, setData] = useState<RiskAssessmentResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notAssessed, setNotAssessed] = useState(false);
  const [running, setRunning] = useState(false);
  const [adminCompanies, setAdminCompanies] = useState<Array<{ id: string; name: string }>>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState<string>('');
  const [metrics, setMetrics] = useState<ERCaseMetrics | null>(null);
  const [metricsDays, setMetricsDays] = useState(30);
  const [metricsLoading, setMetricsLoading] = useState(false);

  const fetchMetrics = useCallback(async (days: number) => {
    setMetricsLoading(true);
    try {
      setMetrics(await erCopilot.getMetrics(days));
    } catch {
      // Silently fail — metrics are supplementary
    } finally {
      setMetricsLoading(false);
    }
  }, []);

  const adminCompanyId = isAdmin ? selectedCompanyId : undefined;

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNotAssessed(false);
    try {
      setData(await riskAssessment.get(adminCompanyId));
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        setNotAssessed(true);
      } else {
        setError(err instanceof Error ? err.message : 'Failed to load risk assessment.');
      }
    } finally {
      setLoading(false);
    }
  }, [adminCompanyId]);

  // Load companies list for admin company selector
  useEffect(() => {
    if (!isAdmin) return;
    companiesApi.list().then((list) => {
      setAdminCompanies(list.map((c: { id: string; name: string }) => ({ id: c.id, name: c.name })));
      if (list.length > 0 && !selectedCompanyId) setSelectedCompanyId(list[0].id);
    }).catch(() => {});
  }, [isAdmin]);

  const handleAdminRun = useCallback(async () => {
    if (!selectedCompanyId) return;
    setRunning(true);
    setError(null);
    try {
      const result = await riskAssessment.adminRun(selectedCompanyId);
      setData(result);
      setNotAssessed(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run assessment.');
    } finally {
      setRunning(false);
    }
  }, [selectedCompanyId]);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { fetchMetrics(metricsDays); }, [fetchMetrics, metricsDays]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-stone-500 uppercase tracking-wider animate-pulse">Loading risk assessment…</div>
      </div>
    );
  }

  return (
    <div className="-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-6 sm:px-8 lg:px-10 py-10 min-h-screen bg-stone-300">
    <div className="max-w-5xl mx-auto space-y-12">

      {/* Header */}
      <div className="flex justify-between items-start border-b border-stone-200 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-zinc-900 uppercase">Risk Assessment</h1>
          <p className="text-xs text-stone-500 mt-2 font-mono tracking-wide uppercase">
            {isAdmin ? 'Admin risk assessment console' : 'Snapshot computed by your account manager'}
          </p>
        </div>
        {isAdmin && (
          <div className="flex items-center gap-3">
            {adminCompanies.length > 1 && (
              <select
                value={selectedCompanyId}
                onChange={(e) => setSelectedCompanyId(e.target.value)}
                className="px-3 py-2 text-xs bg-stone-200 border border-stone-300 rounded-lg text-zinc-900 font-mono"
              >
                {adminCompanies.map(c => (
                  <option key={c.id} value={c.id}>{c.name || c.id.slice(0, 8)}</option>
                ))}
              </select>
            )}
            <button
              onClick={handleAdminRun}
              disabled={running || !selectedCompanyId}
              className="flex items-center gap-2 px-4 py-2 text-xs font-bold uppercase tracking-widest bg-zinc-900 text-zinc-50 rounded-xl hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Play className="w-3 h-3" />
              {running ? 'Running…' : 'Run Assessment'}
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="border border-red-300 bg-red-50 px-4 py-3 text-xs text-red-700 uppercase tracking-wider rounded-xl">
          {error}
        </div>
      )}

      {notAssessed && (
        <div className="bg-stone-200 rounded-2xl p-12 text-center">
          <div className="text-xs text-stone-500 uppercase tracking-wider">Not yet assessed</div>
          <div className="text-[10px] text-stone-400 mt-2 font-mono">
            {isAdmin
              ? 'Click "Run Assessment" above to compute the first risk snapshot.'
              : 'Your account manager will run a risk assessment for your company. Check back soon.'}
          </div>
        </div>
      )}

      {!error && !notAssessed && data && isEmptyResult(data) && (
        <div className="bg-stone-200 rounded-2xl p-12 text-center">
          <div className="text-xs text-stone-500 uppercase tracking-wider">No risk data yet</div>
          <div className="text-[10px] text-stone-400 mt-2 font-mono">Add locations, employees, or run a compliance check to see your risk profile.</div>
        </div>
      )}

      {!error && !notAssessed && data && !isEmptyResult(data) && (
        <>
          {/* Overall score */}
          <div className="grid grid-cols-5 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
            {/* Big number */}
            <div className="col-span-2 bg-zinc-900 p-8 flex flex-col justify-between group">
              <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold flex items-center gap-1.5">
                Overall Risk Score
                <HelpTooltip text={DIMENSION_HELP.overall} />
              </div>
              <div className="flex items-end gap-4 mt-4">
                <span className={`text-8xl font-light font-mono ${BAND_COLOR[data.overall_band].text}`}>
                  {data.overall_score}
                </span>
                <div className="mb-2 flex flex-col gap-2">
                  <BandBadge band={data.overall_band} />
                  <span className="text-[9px] text-zinc-600 font-mono">/100</span>
                </div>
              </div>
              <div className="mt-6">
                <ScoreBar score={data.overall_score} band={data.overall_band} />
              </div>
            </div>

            {/* Dimension mini-stats */}
            {DIMENSION_ORDER.map(key => {
              const dim = data.dimensions[key];
              const meta = DIMENSION_META[key];
              const c = BAND_COLOR[dim.band];
              const weightPct = data.weights?.[key] != null ? `${Math.round(data.weights?.[key] * 100)}%` : null;
              return (
                <div key={key} className="bg-zinc-900 p-6 flex flex-col justify-between group">
                  <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold flex items-center gap-1.5">
                    {meta.label}
                    <HelpTooltip text={DIMENSION_HELP[key]} />
                  </div>
                  <div className={`text-3xl font-light font-mono mt-2 ${c.text}`}>{dim.score}</div>
                  <div className="mt-3 space-y-2">
                    {weightPct && <div className="text-[9px] text-zinc-600 uppercase tracking-widest">{weightPct} weight</div>}
                    <BandBadge band={dim.band} />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Timestamp */}
          <div className="text-[10px] text-stone-400 font-mono uppercase tracking-wider -mt-8">
            Computed {new Date(data.computed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
          </div>

          {/* Risk Trend Chart */}
          <RiskTrendChart companyId={adminCompanyId} />

          {/* Dimension detail cards */}
          <div>
            <div className="text-[10px] text-stone-500 uppercase tracking-widest font-bold mb-4">Dimension Breakdown</div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {DIMENSION_ORDER.map(key => (
                <DimensionCard
                  key={key}
                  dimensionKey={key}
                  dim={data.dimensions[key]}
                  weight={data.weights?.[key] != null ? `${Math.round(data.weights?.[key] * 100)}%` : undefined}
                />
              ))}
            </div>
          </div>

          {/* Action Items */}
          <ActionItems data={data} companyId={adminCompanyId} />

          {/* ER Case Metrics */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="text-[10px] text-stone-500 uppercase tracking-widest font-bold">ER Case Metrics</div>
              <div className="flex gap-0 border border-stone-300 rounded-lg overflow-hidden">
                {([30, 60, 90] as const).map(d => (
                  <button
                    key={d}
                    onClick={() => setMetricsDays(d)}
                    className={`px-3 py-1.5 text-[10px] uppercase tracking-widest font-mono transition-colors ${
                      metricsDays === d
                        ? 'bg-zinc-900 text-zinc-50'
                        : 'bg-stone-200 text-stone-500 hover:text-zinc-900'
                    }`}
                  >
                    {d}d
                  </button>
                ))}
              </div>
            </div>

            {metricsLoading && (
              <div className="bg-stone-200 rounded-2xl p-8 text-center">
                <div className="text-xs text-stone-500 uppercase tracking-wider animate-pulse">Loading metrics…</div>
              </div>
            )}

            {!metricsLoading && metrics && (
              <div className="space-y-4">
                {/* Stat cards */}
                <div className="grid grid-cols-4 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
                  {[
                    { label: 'Total Cases', value: metrics.total_cases },
                    { label: 'Open', value: metrics.by_status['open'] || 0 },
                    { label: 'In Review', value: metrics.by_status['in_review'] || 0 },
                    { label: 'Closed', value: metrics.by_status['closed'] || 0 },
                  ].map(s => (
                    <div key={s.label} className="bg-zinc-900 p-5 flex flex-col">
                      <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{s.label}</div>
                      <div className="text-3xl font-light font-mono text-zinc-200 mt-2">{s.value}</div>
                    </div>
                  ))}
                </div>

                {/* Charts row */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Category breakdown */}
                  <div className="bg-zinc-900 border border-white/10 rounded-2xl p-5">
                    <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-4">By Category</div>
                    {Object.keys(metrics.by_category).length === 0 ? (
                      <div className="text-[10px] text-zinc-600 font-mono">No categorized cases yet</div>
                    ) : (
                      <ResponsiveContainer width="100%" height={Math.max(120, Object.keys(metrics.by_category).length * 28)}>
                        <BarChart
                          data={Object.entries(metrics.by_category).map(([name, value]) => ({ name: name.replace('_', ' '), value }))}
                          layout="vertical"
                          margin={{ top: 0, right: 30, bottom: 0, left: 0 }}
                        >
                          <XAxis type="number" hide />
                          <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 10, fill: '#71717a' }} axisLine={false} tickLine={false} />
                          <Tooltip
                            contentStyle={{ background: '#18181b', border: '1px solid rgba(255,255,255,0.1)', fontSize: 11, color: '#e4e4e7' }}
                            cursor={{ fill: 'rgba(255,255,255,0.03)' }}
                          />
                          <Bar dataKey="value" radius={[0, 2, 2, 0]} maxBarSize={14}>
                            {Object.entries(metrics.by_category).map((_, i) => (
                              <Cell key={i} fill={['#f59e0b', '#ef4444', '#3b82f6', '#10b981', '#a855f7', '#f97316', '#06b6d4', '#6366f1'][i % 8]} />
                            ))}
                            <LabelList dataKey="value" position="right" style={{ fontSize: 10, fill: '#a1a1aa', fontFamily: 'monospace' }} />
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                  </div>

                  {/* Outcome breakdown */}
                  <div className="bg-zinc-900 border border-white/10 rounded-2xl p-5">
                    <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold mb-4">By Outcome</div>
                    {Object.keys(metrics.by_outcome).length === 0 ? (
                      <div className="text-[10px] text-zinc-600 font-mono">No outcomes recorded yet</div>
                    ) : (
                      <ResponsiveContainer width="100%" height={Math.max(120, Object.keys(metrics.by_outcome).length * 28)}>
                        <BarChart
                          data={Object.entries(metrics.by_outcome).map(([name, value]) => ({ name: name.replace('_', ' '), value }))}
                          layout="vertical"
                          margin={{ top: 0, right: 30, bottom: 0, left: 0 }}
                        >
                          <XAxis type="number" hide />
                          <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10, fill: '#71717a' }} axisLine={false} tickLine={false} />
                          <Tooltip
                            contentStyle={{ background: '#18181b', border: '1px solid rgba(255,255,255,0.1)', fontSize: 11, color: '#e4e4e7' }}
                            cursor={{ fill: 'rgba(255,255,255,0.03)' }}
                          />
                          <Bar dataKey="value" radius={[0, 2, 2, 0]} maxBarSize={14}>
                            {Object.entries(metrics.by_outcome).map((_, i) => (
                              <Cell key={i} fill={['#10b981', '#f59e0b', '#3b82f6', '#ef4444', '#a855f7', '#6366f1'][i % 6]} />
                            ))}
                            <LabelList dataKey="value" position="right" style={{ fontSize: 10, fill: '#a1a1aa', fontFamily: 'monospace' }} />
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                </div>
              </div>
            )}

            {!metricsLoading && metrics && metrics.total_cases === 0 && (
              <div className="bg-stone-200 rounded-2xl p-8 text-center">
                <div className="text-xs text-stone-500 uppercase tracking-wider">No cases in the last {metricsDays} days</div>
              </div>
            )}
          </div>

          {/* Consultation Analysis — included with snapshot when admin runs assessment */}
          {(data.report || (data.recommendations && data.recommendations.length > 0)) && (
            <div>
              <div className="text-[10px] text-stone-500 uppercase tracking-widest font-bold mb-4">Consultation Analysis</div>

              {data.report && (
                <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 mb-4">
                  <div className="text-sm text-zinc-300 leading-relaxed whitespace-pre-line">{data.report}</div>
                </div>
              )}

              {data.recommendations && data.recommendations.length > 0 && (
                <div className="bg-zinc-900 border border-white/10 rounded-2xl divide-y divide-white/10 overflow-hidden">
                  {data.recommendations.map((rec, i) => (
                    <div key={i} className="px-6 py-5 flex items-start gap-4">
                      <span className={`shrink-0 inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${PRIORITY_COLOR[rec.priority]?.badge ?? ''}`}>
                        {rec.priority}
                      </span>
                      <div className="flex flex-col gap-2 min-w-0">
                        <span className="text-[10px] text-zinc-600 uppercase tracking-widest font-bold">
                          {DIMENSION_META[rec.dimension]?.label ?? rec.dimension}
                        </span>
                        <span className="text-sm text-zinc-200 font-medium leading-snug">{rec.title}</span>
                        <span className="text-sm text-zinc-400 leading-relaxed">{rec.guidance}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Score bands legend */}
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6">
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-4">Score Bands</div>
            <div className="grid grid-cols-4 gap-px bg-white/10 rounded-lg overflow-hidden">
              {(['low', 'moderate', 'high', 'critical'] as Band[]).map(band => (
                <div key={band} className="bg-zinc-800 px-4 py-3">
                  <div className={`text-[10px] font-bold uppercase tracking-widest ${BAND_COLOR[band].text}`}>{BAND_LABEL[band]}</div>
                  <div className="text-[9px] text-zinc-600 mt-1 font-mono">
                    {band === 'low' ? '0 – 25' : band === 'moderate' ? '26 – 50' : band === 'high' ? '51 – 75' : '76 – 100'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
    </div>
  );
}
