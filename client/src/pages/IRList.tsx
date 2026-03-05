import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { irIncidents } from '../api/client';
import type { IRIncident, IRIncidentType, IRSeverity, IRStatus, IRAnalyticsSummary } from '../types';
import { Plus, Trash2, BarChart3, Shield, Copy, RefreshCw, X } from 'lucide-react';
import { FeatureGuideTrigger } from '../features/feature-guides';
import { LifecycleWizard } from '../components/LifecycleWizard';
import { useIsLightMode } from '../hooks/useIsLightMode';

// ─── theme ────────────────────────────────────────────────────────────────────

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  border: 'border-stone-200',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800 rounded-xl',
  btnSecondary: 'border border-stone-300 hover:border-stone-400 text-stone-600 hover:text-zinc-900 rounded-xl',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  statBg: 'bg-stone-200',
  statGap: 'bg-stone-300',
  tabActive: 'bg-zinc-900 border-zinc-900 text-zinc-50 rounded-xl',
  tabInactive: 'bg-transparent border-transparent text-stone-500 hover:text-zinc-900 hover:border-stone-300 rounded-xl',
  input: 'bg-white border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:border-stone-400',
  select: 'bg-white border border-stone-300 rounded-xl text-zinc-900 focus:border-stone-400',
  rowBg: 'bg-stone-100',
  rowHover: 'hover:bg-stone-50',
  emptyBg: 'border border-dashed border-stone-200 bg-stone-100 rounded-2xl',
  sevDots: { critical: 'bg-zinc-900', high: 'bg-stone-600', medium: 'bg-stone-400', low: 'bg-stone-300' } as Record<string, string>,
  statusColors: { reported: 'text-zinc-900', investigating: 'text-stone-600', action_required: 'text-stone-500', resolved: 'text-stone-400', closed: 'text-stone-300' } as Record<string, string>,
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  border: 'border-white/10',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600 rounded-xl',
  btnSecondary: 'border border-white/10 hover:border-white/20 text-zinc-500 hover:text-zinc-100 rounded-xl',
  btnGhost: 'text-zinc-600 hover:text-zinc-100',
  statBg: 'bg-zinc-900',
  statGap: 'bg-zinc-950',
  tabActive: 'bg-zinc-800 border-zinc-700 text-white rounded-xl',
  tabInactive: 'bg-transparent border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-800 rounded-xl',
  input: 'bg-zinc-800 border border-white/10 text-zinc-100 rounded-xl placeholder:text-zinc-600 focus:border-white/20',
  select: 'bg-zinc-800 border border-white/10 rounded-xl text-zinc-100 focus:border-white/20',
  rowBg: 'bg-zinc-900',
  rowHover: 'hover:bg-white/5',
  emptyBg: 'border border-dashed border-white/10 bg-white/5 rounded-2xl',
  sevDots: { critical: 'bg-zinc-100', high: 'bg-zinc-400', medium: 'bg-zinc-500', low: 'bg-zinc-600' } as Record<string, string>,
  statusColors: { reported: 'text-zinc-100', investigating: 'text-zinc-400', action_required: 'text-zinc-300', resolved: 'text-zinc-500', closed: 'text-zinc-600' } as Record<string, string>,
} as const;

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

const IR_CYCLE_STEPS = [
  {
    id: 1,
    icon: 'report' as const,
    title: 'Report Incident',
    description: 'Log safety, behavioral, or property incidents. Assign an initial severity level and description.',
    action: 'Click "Report" to log a new incident.',
  },
  {
    id: 2,
    icon: 'investigate' as const,
    title: 'Investigate',
    description: 'Gather evidence, interview witnesses, and document findings to build a complete case record.',
    action: 'Update status to "Investigating" to start your review.',
  },
  {
    id: 3,
    icon: 'analyze' as const,
    title: 'AI Analysis',
    description: 'AI detects risk patterns, root causes, and provides suggestions based on labor law compliance.',
    action: 'View "AI Analysis" in the incident detail view.',
  },
  {
    id: 4,
    icon: 'action' as const,
    title: 'Take Action',
    description: 'Assign resolution tasks, issue warnings, or implement new safety protocols based on findings.',
    action: 'Update status to "Action Required" for follow-up.',
  },
  {
    id: 5,
    icon: 'resolve' as const,
    title: 'Resolve & Close',
    description: 'Finalize the audit trail and close the record with a comprehensive summary of outcomes.',
    action: 'Review and transition to "Resolved" or "Closed".',
  },
];

export function IRList() {
  const navigate = useNavigate();
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
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

  // Anonymous reporting
  const [anonLink, setAnonLink] = useState<string | null>(null);
  const [anonEnabled, setAnonEnabled] = useState(false);
  const [anonUsed, setAnonUsed] = useState(false);
  const [anonLoading, setAnonLoading] = useState(false);
  const [anonCopied, setAnonCopied] = useState(false);

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

  // Load anonymous reporting status
  useEffect(() => {
    irIncidents.getAnonymousReportingStatus().then((res: any) => {
      setAnonLink(res.token ? `${window.location.origin}/report/${res.token}` : null);
      setAnonEnabled(res.enabled);
      setAnonUsed(res.used ?? false);
    }).catch(() => {});
  }, []);

  const handleEnableAnon = async () => {
    setAnonLoading(true);
    try {
      const res = await irIncidents.generateAnonymousReportingToken();
      setAnonLink(`${window.location.origin}/report/${res.token}`);
      setAnonEnabled(true);
      setAnonUsed(false);
    } catch { /* ignore */ }
    setAnonLoading(false);
  };

  const handleRegenerateAnon = async () => {
    if (!confirm('Regenerate link? The old link will stop working.')) return;
    setAnonLoading(true);
    try {
      const res = await irIncidents.generateAnonymousReportingToken();
      setAnonLink(`${window.location.origin}/report/${res.token}`);
      setAnonEnabled(true);
      setAnonUsed(false);
    } catch { /* ignore */ }
    setAnonLoading(false);
  };

  const handleDisableAnon = async () => {
    if (!confirm('Disable anonymous reporting? The current link will stop working.')) return;
    setAnonLoading(true);
    try {
      await irIncidents.disableAnonymousReporting();
      setAnonLink(null);
      setAnonEnabled(false);
    } catch { /* ignore */ }
    setAnonLoading(false);
  };

  const handleCopyAnon = () => {
    if (anonLink) {
      navigator.clipboard.writeText(anonLink);
      setAnonCopied(true);
      setTimeout(() => setAnonCopied(false), 2000);
    }
  };

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
    <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-start mb-12 pb-8">
        <div>
          <div className="flex items-center gap-3">
            <h1 className={`text-4xl font-bold tracking-tighter ${t.textMain} uppercase`}>Incident Management</h1>
            <FeatureGuideTrigger guideId="ir-list" />
          </div>
          <p className={`text-xs ${t.textMuted} mt-2 font-mono tracking-wide uppercase`}>{total} Records in Current View</p>
        </div>
        <div className="flex gap-3">
          <button
            data-tour="ir-list-analytics-btn"
            onClick={() => navigate('/app/ir/dashboard')}
            className={`flex items-center gap-2 px-5 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${t.btnSecondary}`}
          >
            <BarChart3 size={14} /> Analytics
          </button>
          <button
            data-tour="ir-list-report-btn"
            onClick={() => navigate('/app/ir/incidents/new')}
            className={`flex items-center gap-2 px-5 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${t.btnPrimary}`}
          >
            <Plus size={14} /> Report
          </button>
        </div>
      </div>

      <LifecycleWizard
        steps={IR_CYCLE_STEPS}
        activeStep={incidents.length > 20 ? 5
                  : actionRequiredCount > 0 ? 4
                  : incidents.length > 0 ? 2
                  : 1}
        title="Incident Cycle"
        storageKey="ir-wizard-collapsed-v1"
      />

      {/* Anonymous Reporting */}
      <div className={`${t.card} p-4`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield size={14} className={t.textMuted} />
            <span className={`${t.label}`}>Anonymous Reporting</span>
            {anonUsed && (
              <span className="px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-orange-500/10 text-orange-400 border border-orange-500/20 rounded">
                Used
              </span>
            )}
          </div>
          {!anonEnabled ? (
            <button
              onClick={handleEnableAnon}
              disabled={anonLoading}
              className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider transition-colors disabled:opacity-50 ${t.btnPrimary}`}
            >
              Enable
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={handleRegenerateAnon}
                disabled={anonLoading}
                className={`p-1.5 ${t.btnGhost} transition-colors disabled:opacity-50`}
                title="Regenerate link"
              >
                <RefreshCw size={12} />
              </button>
              <button
                onClick={handleDisableAnon}
                disabled={anonLoading}
                className="p-1.5 text-zinc-500 hover:text-red-400 hover:bg-red-900/20 rounded-xl transition-colors disabled:opacity-50"
                title="Disable"
              >
                <X size={12} />
              </button>
            </div>
          )}
        </div>
        {anonEnabled && anonLink && (
          <div className="mt-3 flex items-center gap-2">
            <code className={`flex-1 px-3 py-1.5 ${t.input} text-xs font-mono truncate`}>
              {anonLink}
            </code>
            <button
              onClick={handleCopyAnon}
              className={`px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition-colors ${t.btnSecondary}`}
            >
              {anonCopied ? 'Copied' : <Copy size={12} />}
            </button>
          </div>
        )}
        <p className={`text-[10px] ${t.textFaint} mt-2 font-mono`}>
          {!anonEnabled
            ? 'Allow employees to report incidents anonymously via a shareable link.'
            : anonUsed
              ? 'This link has been used. Regenerate to create a new single-use link.'
              : 'Share this link — it can only be used once. Reporter identity is never stored.'}
        </p>
      </div>

      {/* Summary */}
      <div data-tour="ir-list-stats" className={`grid grid-cols-2 md:grid-cols-4 gap-px ${t.statGap} rounded-2xl overflow-hidden`}>
        {[
          { label: 'Open', value: openCount },
          { label: 'Action Required', value: actionRequiredCount },
          { label: 'Critical', value: criticalCount },
          { label: 'Last 30d', value: recentCount },
        ].map((stat) => (
          <div key={stat.label} className={`${t.statBg} p-4`}>
            <div className={`text-2xl font-light ${t.textMain} font-mono tabular-nums`}>{stat.value}</div>
            <div className={`${t.label} mt-1`}>{stat.label}</div>
          </div>
        ))}
      </div>

      {error && (
        <div className="px-4 py-3 border border-red-500/40 bg-red-950/30 text-red-300 text-xs uppercase tracking-wider font-mono rounded-xl">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className={`flex flex-wrap items-center gap-6 pb-6 border-b ${t.border}`}>
        {/* Status Tabs */}
        <div data-tour="ir-list-tabs" className="flex gap-2">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setActiveTab(tab.value)}
              className={`px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider transition-colors border ${
                activeTab === tab.value ? t.tabActive : t.tabInactive
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className={`w-px h-6 ${isLight ? 'bg-stone-300' : 'bg-zinc-800'}`} />

        {/* Type */}
        <select
          data-tour="ir-list-type-filter"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as IRIncidentType | '')}
          className={`px-3 py-1.5 ${t.select} text-[10px] font-bold uppercase tracking-wider focus:outline-none cursor-pointer`}
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
          className={`px-3 py-1.5 ${t.select} text-[10px] font-bold uppercase tracking-wider focus:outline-none cursor-pointer`}
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
            className={`w-full px-3 py-1.5 ${t.input} text-[10px] font-bold focus:outline-none tracking-wider`}
          />
        </div>
      </div>

      {/* List */}
      {loading ? (
        <div className={`text-center py-24 text-xs ${t.textFaint} uppercase tracking-wider animate-pulse`}>Loading...</div>
      ) : incidents.length === 0 ? (
        <div className={`text-center py-24 ${t.emptyBg}`}>
          <div className={`text-xs ${t.textMuted} mb-4 font-mono uppercase tracking-wider`}>No incidents found matching criteria</div>
          <button
            onClick={() => {
               setActiveTab('all');
               setTypeFilter('');
               setSeverityFilter('');
               setSearchQuery('');
            }}
            className={`text-xs ${t.textMain} font-bold uppercase tracking-wider underline underline-offset-4`}
          >
            Clear Filters
          </button>
        </div>
      ) : (
        <div data-tour="ir-list-rows" className="bg-zinc-900 rounded-2xl overflow-hidden">
          {/* Header row */}
          <div className="flex items-center gap-4 py-3 px-6 text-[10px] text-zinc-600 uppercase tracking-widest font-bold border-b border-zinc-800">
            <div className="w-3" />
            <div className="w-24">ID</div>
            <div className="flex-1">Incident Details</div>
            <div className="w-24">Type</div>
            <div className="w-24">Status</div>
            <div className="w-40">Manager Update</div>
            <div className="w-24 text-right">Date</div>
            <div className="w-12" />
          </div>

          <div className="divide-y divide-zinc-800">
          {incidents.map((incident) => (
            <div
              key={incident.id}
              onClick={() => navigate(`/app/ir/incidents/${incident.id}`)}
              className="flex items-center gap-4 py-4 px-6 hover:bg-white/5 cursor-pointer group transition-colors"
            >
              <div className={`w-1.5 h-1.5 rounded-full ${t.sevDots[incident.severity]}`} />
              <div className="text-[10px] text-zinc-500 font-mono w-24">{incident.incident_number}</div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-bold text-zinc-300 group-hover:text-white truncate transition-colors uppercase tracking-wide">
                  {incident.title}
                </div>
                {incident.description && (
                  <div className="text-[10px] text-zinc-600 truncate mt-1 font-mono max-w-xl">{incident.description}</div>
                )}
              </div>
              <div className="text-[10px] text-zinc-500 w-24 uppercase tracking-wider font-bold">{TYPE_LABELS[incident.incident_type]}</div>
              <div className={`text-[10px] w-24 uppercase tracking-wider font-bold ${t.statusColors[incident.status]}`}>
                {incident.status.replace('_', ' ')}
              </div>
              <div className="w-40">
                <select
                  data-tour="ir-list-status-dropdown"
                  value={incident.status}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => handleStatusUpdate(incident.id, e.target.value as IRStatus, e)}
                  disabled={updatingIncidentId === incident.id}
                  className="w-full px-2 py-1 bg-zinc-800 border border-white/10 rounded-xl text-zinc-100 text-[10px] font-bold uppercase tracking-wider focus:outline-none disabled:opacity-50"
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
                  className="p-2 text-zinc-600 hover:text-red-400 hover:bg-red-900/20 rounded-xl transition-colors opacity-0 group-hover:opacity-100"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
          </div>
        </div>
      )}
    </div>
    </div>
  );
}

export default IRList;
