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
