import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { irIncidents } from '../api/client';
import type { IRIncident, IRIncidentType, IRSeverity, IRStatus, IRAnalyticsSummary } from '../types';
import { Plus, Trash2, BarChart3 } from 'lucide-react';
import { FeatureGuideTrigger } from '../features/feature-guides';

const STATUS_TABS: { label: string; value: IRStatus | 'all' | 'needs_attention' }[] = [
  { label: 'Needs Attention', value: 'needs_attention' },
  { label: 'All', value: 'all' },
  { label: 'Reported', value: 'reported' },
  { label: 'Investigating', value: 'investigating' },
  { label: 'Action Req', value: 'action_required' },
  { label: 'Resolved', value: 'resolved' },
  { label: 'Closed', value: 'closed' },
];

const TYPE_LABELS: Record<string, string> = {
  safety: 'Safety',
  behavioral: 'Behavioral',
  property: 'Property',
  near_miss: 'Near Miss',
  other: 'Other',
};

const STATUS_COLORS: Record<string, string> = {
  reported: 'text-blue-400',
  investigating: 'text-amber-400',
  action_required: 'text-orange-400',
  resolved: 'text-emerald-400',
  closed: 'text-zinc-500',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-emerald-500',
};

// ─── Incident Lifecycle Wizard ────────────────────────────────────────────────

type IRStepIcon = 'report' | 'investigate' | 'analyze' | 'action' | 'resolve';

type IRWizardStep = {
  id: number;
  icon: IRStepIcon;
  title: string;
  description: string;
  action?: string;
};

const IR_CYCLE_STEPS: IRWizardStep[] = [
  {
    id: 1,
    icon: 'report',
    title: 'Report Incident',
    description: 'Log safety, behavioral, or property incidents. Assign an initial severity level and description.',
    action: 'Click "Report" to log a new incident.',
  },
  {
    id: 2,
    icon: 'investigate',
    title: 'Investigate',
    description: 'Gather evidence, interview witnesses, and document findings to build a complete case record.',
    action: 'Update status to "Investigating" to start your review.',
  },
  {
    id: 3,
    icon: 'analyze',
    title: 'AI Analysis',
    description: 'AI detects risk patterns, root causes, and provides suggestions based on labor law compliance.',
    action: 'View "AI Analysis" in the incident detail view.',
  },
  {
    id: 4,
    icon: 'action',
    title: 'Take Action',
    description: 'Assign resolution tasks, issue warnings, or implement new safety protocols based on findings.',
    action: 'Update status to "Action Required" for follow-up.',
  },
  {
    id: 5,
    icon: 'resolve',
    title: 'Resolve & Close',
    description: 'Finalize the audit trail and close the record with a comprehensive summary of outcomes.',
    action: 'Review and transition to "Resolved" or "Closed".',
  },
];

function IRCycleIcon({ icon, className = '' }: { icon: IRStepIcon; className?: string }) {
  const common = { className, width: 16, height: 16, viewBox: '0 0 20 20', fill: 'none', 'aria-hidden': true as const };
  
  if (icon === 'report') {
    return (
      <svg {...common}>
        <path d="M10 5V15M5 10H15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  if (icon === 'investigate') {
    return (
      <svg {...common}>
        <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.6" />
        <path d="M10 10V6M10 10L13 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (icon === 'analyze') {
    return (
      <svg {...common}>
        <rect x="5" y="5" width="10" height="10" rx="1" stroke="currentColor" strokeWidth="1.6" />
        <path d="M10 8V12M8 10H12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (icon === 'action') {
    return (
      <svg {...common}>
        <path d="M16 5L4 10L10 11L11 17L16 5Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (icon === 'resolve') {
    return (
      <svg {...common}>
        <path d="M6 10.3L8.5 12.8L14 7.3" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  return null;
}

function IRCycleWizard({ incidentsCount, actionRequiredCount }: { incidentsCount: number, actionRequiredCount: number }) {
  const storageKey = 'ir-wizard-collapsed-v1';
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(storageKey) === 'true'; } catch { return false; }
  });

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem(storageKey, String(next)); } catch {}
  };

  const activeStep = incidentsCount > 20 ? 5 
                  : actionRequiredCount > 0 ? 4
                  : incidentsCount > 0 ? 2
                  : 1;

  return (
    <div className="border border-white/10 bg-zinc-950/60 mb-10">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500">Incident Cycle</span>
          <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-zinc-800 border border-zinc-700 text-zinc-400">
            Step {activeStep} of 5
          </span>
          <span className="text-[10px] text-zinc-600">
            {IR_CYCLE_STEPS[activeStep - 1].title}
          </span>
        </div>
        <ChevronDownIcon className={`text-zinc-600 transition-transform duration-200 ${collapsed ? '' : 'rotate-180'}`} />
      </button>

      {!collapsed && (
        <div className="border-t border-white/10">
          <div className="relative px-5 pt-5 pb-2 overflow-x-auto">
            <div className="flex items-start gap-0 min-w-max">
              {IR_CYCLE_STEPS.map((step, idx) => {
                const isComplete = step.id < activeStep;
                const isActive = step.id === activeStep;

                return (
                  <div key={step.id} className="flex items-start">
                    <div className="flex flex-col items-center w-28">
                      <div className={`relative w-9 h-9 rounded-full border-2 flex items-center justify-center text-sm transition-all ${
                        isComplete
                          ? 'bg-matcha-500/20 border-matcha-500/50 text-matcha-400'
                          : isActive
                          ? 'bg-white/10 border-white text-white shadow-[0_0_12px_rgba(255,255,255,0.15)]'
                          : 'bg-zinc-900 border-zinc-700 text-zinc-600'
                      }`}>
                        {isComplete ? '✓' : <IRCycleIcon icon={step.icon} className="w-4 h-4" />}
                      </div>
                      <div className={`mt-2 text-center text-[10px] font-bold uppercase tracking-wider leading-tight px-1 ${
                        isActive ? 'text-white' : isComplete ? 'text-matcha-400/70' : 'text-zinc-600'
                      }`}>
                        {step.title}
                      </div>
                    </div>
                    {idx < IR_CYCLE_STEPS.length - 1 && (
                      <div className={`w-10 h-0.5 mt-[18px] flex-shrink-0 transition-colors ${
                        step.id < activeStep ? 'bg-matcha-500/40' : 'bg-zinc-800'
                      }`} />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mx-5 mb-5 p-4 bg-white/[0.03] border border-white/10">
            <div className="flex items-start gap-3">
              <span className="text-xl flex-shrink-0 text-zinc-200">
                <IRCycleIcon icon={IR_CYCLE_STEPS[activeStep - 1].icon} className="w-5 h-5" />
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold text-white uppercase tracking-wider">
                    {IR_CYCLE_STEPS[activeStep - 1].title}
                  </span>
                  <span className="text-[9px] px-1.5 py-0.5 font-bold uppercase tracking-widest bg-white/10 text-zinc-400 border border-white/10">
                    Current Step
                  </span>
                </div>
                <p className="text-[11px] text-zinc-400 leading-relaxed mb-2">
                  {IR_CYCLE_STEPS[activeStep - 1].description}
                </p>
                {IR_CYCLE_STEPS[activeStep - 1].action && (
                  <p className="text-[11px] text-matcha-400/80 font-medium">
                    → {IR_CYCLE_STEPS[activeStep - 1].action}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ChevronDownIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={className}
      width="14"
      height="14"
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
    >
      <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IRList() {
  const navigate = useNavigate();
  const [incidents, setIncidents] = useState<IRIncident[]>([]);
  const [summary, setSummary] = useState<IRAnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [updatingIncidentId, setUpdatingIncidentId] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<IRStatus | 'all' | 'needs_attention'>('needs_attention');
  const [typeFilter, setTypeFilter] = useState<IRIncidentType | ''>('');
  const [severityFilter, setSeverityFilter] = useState<IRSeverity | ''>('');
  const [searchQuery, setSearchQuery] = useState('');

  const fetchIncidents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [response, summaryData] = await Promise.all([
        irIncidents.listIncidents({
          status: activeTab !== 'all' && activeTab !== 'needs_attention' ? activeTab : undefined,
          incident_type: typeFilter || undefined,
          severity: severityFilter || undefined,
          search: searchQuery || undefined,
          limit: 200,
        }),
        irIncidents.getAnalyticsSummary(),
      ]);

      const visibleIncidents = activeTab === 'needs_attention'
        ? response.incidents.filter((incident) =>
          ['reported', 'investigating', 'action_required'].includes(incident.status) ||
          incident.severity === 'critical'
        )
        : response.incidents;

      setIncidents(visibleIncidents);
      setTotal(activeTab === 'needs_attention' ? visibleIncidents.length : response.total);
      setSummary(summaryData);
    } catch (err) {
      console.error('Failed to fetch incidents:', err);
      setError(err instanceof Error ? err.message : 'Failed to load incidents');
    } finally {
      setLoading(false);
    }
  }, [activeTab, typeFilter, severityFilter, searchQuery]);

  useEffect(() => {
    fetchIncidents();
  }, [fetchIncidents]);

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this incident?')) return;
    try {
      await irIncidents.deleteIncident(id);
      fetchIncidents();
    } catch (err) {
      console.error('Failed to delete incident:', err);
      setError(err instanceof Error ? err.message : 'Failed to delete incident');
    }
  };

  const handleStatusUpdate = async (id: string, status: IRStatus, e: React.ChangeEvent<HTMLSelectElement>) => {
    e.stopPropagation();
    try {
      setUpdatingIncidentId(id);
      setError(null);
      const updated = await irIncidents.updateIncident(id, { status });
      setIncidents((prev) => prev.map((incident) => (incident.id === id ? updated : incident)));
      await fetchIncidents();
    } catch (err) {
      console.error('Failed to update incident status:', err);
      setError(err instanceof Error ? err.message : 'Failed to update status');
    } finally {
      setUpdatingIncidentId(null);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const openCount = (summary?.by_status?.reported || 0) +
    (summary?.by_status?.investigating || 0) +
    (summary?.by_status?.action_required || 0);
  const criticalCount = summary?.by_severity?.critical || 0;
  const actionRequiredCount = summary?.by_status?.action_required || 0;
  const recentCount = summary?.recent_count || 0;

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-start border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Incident Management</h1>
            <FeatureGuideTrigger guideId="ir-list" />
          </div>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">{total} Records in Current View</p>
        </div>
        <div className="flex gap-3">
          <button
            data-tour="ir-list-analytics-btn"
            onClick={() => navigate('/app/ir/dashboard')}
            className="flex items-center gap-2 px-4 py-2 border border-white/10 hover:bg-zinc-900 text-xs font-bold text-zinc-400 hover:text-white uppercase tracking-wider transition-colors"
          >
            <BarChart3 size={14} /> Analytics
          </button>
          <button
            data-tour="ir-list-report-btn"
            onClick={() => navigate('/app/ir/incidents/new')}
            className="flex items-center gap-2 px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
          >
            <Plus size={14} /> Report
          </button>
        </div>
      </div>

      <IRCycleWizard incidentsCount={incidents.length} actionRequiredCount={actionRequiredCount} />

      {/* Summary */}
      <div data-tour="ir-list-stats" className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/10 border border-white/10">
        <div className="bg-zinc-950 p-4">
          <div className="text-2xl font-light text-white font-mono">{openCount}</div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-1 font-bold">Open</div>
        </div>
        <div className="bg-zinc-950 p-4">
          <div className="text-2xl font-light text-orange-400 font-mono">{actionRequiredCount}</div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-1 font-bold">Action Required</div>
        </div>
        <div className="bg-zinc-950 p-4">
          <div className="text-2xl font-light text-red-400 font-mono">{criticalCount}</div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-1 font-bold">Critical</div>
        </div>
        <div className="bg-zinc-950 p-4">
          <div className="text-2xl font-light text-white font-mono">{recentCount}</div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-1 font-bold">Last 30d</div>
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 border border-red-500/40 bg-red-950/30 text-red-300 text-xs uppercase tracking-wider font-mono">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-6 pb-6 border-b border-white/10">
        {/* Status Tabs */}
        <div data-tour="ir-list-tabs" className="flex gap-2">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setActiveTab(tab.value)}
              className={`px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition-colors border ${
                activeTab === tab.value
                  ? 'bg-zinc-800 border-zinc-700 text-white'
                  : 'bg-transparent border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-800'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="w-px h-6 bg-zinc-800" />

        {/* Type */}
        <select
          data-tour="ir-list-type-filter"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as IRIncidentType | '')}
          className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 text-[10px] font-bold text-zinc-400 uppercase tracking-wider focus:outline-none focus:border-zinc-600 cursor-pointer"
        >
          <option value="">All Types</option>
          <option value="safety">Safety</option>
          <option value="behavioral">Behavioral</option>
          <option value="property">Property</option>
          <option value="near_miss">Near Miss</option>
          <option value="other">Other</option>
        </select>

        {/* Severity */}
        <select
          data-tour="ir-list-severity-filter"
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value as IRSeverity | '')}
          className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 text-[10px] font-bold text-zinc-400 uppercase tracking-wider focus:outline-none focus:border-zinc-600 cursor-pointer"
        >
          <option value="">All Severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>

        {/* Search */}
        <div data-tour="ir-list-search" className="flex-1 min-w-[200px]">
          <input
            type="text"
            placeholder="SEARCH INCIDENTS..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-3 py-1.5 bg-zinc-900 border border-zinc-800 text-[10px] font-bold text-white placeholder-zinc-600 focus:outline-none focus:border-zinc-600 tracking-wider"
          />
        </div>
      </div>

      {/* List */}
      {loading ? (
        <div className="text-center py-24 text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading...</div>
      ) : incidents.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-white/10 bg-white/5">
          <div className="text-xs text-zinc-500 mb-4 font-mono uppercase tracking-wider">No incidents found matching criteria</div>
          <button
            onClick={() => {
               setActiveTab('all');
               setTypeFilter('');
               setSeverityFilter('');
               setSearchQuery('');
            }}
            className="text-xs text-white hover:text-zinc-300 font-bold uppercase tracking-wider underline underline-offset-4"
          >
            Clear Filters
          </button>
        </div>
      ) : (
        <div data-tour="ir-list-rows" className="space-y-px bg-white/10 border border-white/10">
          {/* Header row */}
          <div className="flex items-center gap-4 py-3 px-6 bg-zinc-950 text-[10px] text-zinc-500 uppercase tracking-widest border-b border-white/10 font-bold">
            <div className="w-3" />
            <div className="w-24">ID</div>
            <div className="flex-1">Incident Details</div>
              <div className="w-24">Type</div>
              <div className="w-24">Status</div>
              <div className="w-40">Manager Update</div>
              <div className="w-24 text-right">Date</div>
              <div className="w-12" />
            </div>

          {incidents.map((incident) => (
            <div
              key={incident.id}
              onClick={() => navigate(`/app/ir/incidents/${incident.id}`)}
              className="flex items-center gap-4 py-4 px-6 bg-zinc-950 hover:bg-zinc-900 cursor-pointer group transition-colors"
            >
              <div className={`w-1.5 h-1.5 rounded-full ${SEVERITY_COLORS[incident.severity]}`} />
              <div className="text-[10px] text-zinc-500 font-mono w-24 group-hover:text-zinc-400">{incident.incident_number}</div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-bold text-zinc-300 truncate group-hover:text-white transition-colors uppercase tracking-wide">
                  {incident.title}
                </div>
                {incident.description && (
                  <div className="text-[10px] text-zinc-600 truncate mt-1 font-mono max-w-xl">{incident.description}</div>
                )}
              </div>
              <div className="text-[10px] text-zinc-500 w-24 uppercase tracking-wider font-bold">{TYPE_LABELS[incident.incident_type]}</div>
              <div className={`text-[10px] w-24 uppercase tracking-wider font-bold ${STATUS_COLORS[incident.status]}`}>
                {incident.status.replace('_', ' ')}
              </div>
              <div className="w-40">
                <select
                  data-tour="ir-list-status-dropdown"
                  value={incident.status}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => handleStatusUpdate(incident.id, e.target.value as IRStatus, e)}
                  disabled={updatingIncidentId === incident.id}
                  className="w-full px-2 py-1 bg-zinc-900 border border-zinc-800 text-[10px] font-bold text-zinc-300 uppercase tracking-wider focus:outline-none focus:border-zinc-600 disabled:opacity-50"
                >
                  <option value="reported">Reported</option>
                  <option value="investigating">Investigating</option>
                  <option value="action_required">Action Required</option>
                  <option value="resolved">Resolved</option>
                  <option value="closed">Closed</option>
                </select>
              </div>
              <div className="text-[10px] text-zinc-600 w-24 text-right font-mono">{formatDate(incident.occurred_at)}</div>
              <div className="w-12 text-right">
                <button
                  onClick={(e) => handleDelete(incident.id, e)}
                  className="p-2 text-zinc-600 hover:text-red-500 hover:bg-red-900/20 rounded transition-colors opacity-0 group-hover:opacity-100"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default IRList;
