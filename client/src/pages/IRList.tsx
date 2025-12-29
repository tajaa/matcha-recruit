import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { irIncidents } from '../api/client';
import type { IRIncident, IRIncidentType, IRSeverity, IRStatus } from '../types';

const STATUS_TABS: { label: string; value: IRStatus | 'all' }[] = [
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
  investigating: 'text-yellow-400',
  action_required: 'text-orange-400',
  resolved: 'text-green-400',
  closed: 'text-zinc-500',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-600',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-green-500',
};

export function IRList() {
  const navigate = useNavigate();
  const [incidents, setIncidents] = useState<IRIncident[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);

  const [activeTab, setActiveTab] = useState<IRStatus | 'all'>('all');
  const [typeFilter, setTypeFilter] = useState<IRIncidentType | ''>('');
  const [severityFilter, setSeverityFilter] = useState<IRSeverity | ''>('');
  const [searchQuery, setSearchQuery] = useState('');

  const fetchIncidents = useCallback(async () => {
    try {
      setLoading(true);
      const response = await irIncidents.listIncidents({
        status: activeTab !== 'all' ? activeTab : undefined,
        incident_type: typeFilter || undefined,
        severity: severityFilter || undefined,
        search: searchQuery || undefined,
        limit: 50,
      });
      setIncidents(response.incidents);
      setTotal(response.total);
    } catch (err) {
      console.error('Failed to fetch incidents:', err);
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
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex justify-between items-start mb-8">
        <div>
          <h1 className="text-xl font-medium text-white">All Incidents</h1>
          <p className="text-xs text-zinc-600 mt-1">{total} total</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => navigate('/app/ir')}
            className="text-xs text-zinc-500 hover:text-white uppercase tracking-wider"
          >
            Dashboard
          </button>
          <button
            onClick={() => navigate('/app/ir/incidents/new')}
            className="px-3 py-1.5 bg-white text-black text-xs font-medium rounded hover:bg-zinc-200 uppercase tracking-wider"
          >
            Report
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4 mb-8">
        {/* Status Tabs */}
        <div className="flex gap-1">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setActiveTab(tab.value)}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                activeTab === tab.value
                  ? 'bg-white text-black'
                  : 'text-zinc-500 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-zinc-800" />

        {/* Type */}
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as IRIncidentType | '')}
          className="px-2 py-1 bg-transparent border-b border-zinc-800 text-xs text-zinc-400 focus:outline-none focus:border-zinc-500 cursor-pointer"
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
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value as IRSeverity | '')}
          className="px-2 py-1 bg-transparent border-b border-zinc-800 text-xs text-zinc-400 focus:outline-none focus:border-zinc-500 cursor-pointer"
        >
          <option value="">All Severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>

        {/* Search */}
        <div className="flex-1 min-w-[150px]">
          <input
            type="text"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-2 py-1 bg-transparent border-b border-zinc-800 text-xs text-white placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
          />
        </div>
      </div>

      {/* List */}
      {loading ? (
        <div className="text-center py-12 text-xs text-zinc-600 uppercase tracking-wider">Loading...</div>
      ) : incidents.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-xs text-zinc-600 mb-4">No incidents found</div>
          <button
            onClick={() => navigate('/app/ir/incidents/new')}
            className="text-xs text-zinc-500 hover:text-white uppercase tracking-wider"
          >
            Report Incident
          </button>
        </div>
      ) : (
        <div className="space-y-1">
          {/* Header row */}
          <div className="flex items-center gap-4 py-2 text-[10px] text-zinc-600 uppercase tracking-wider border-b border-zinc-900">
            <div className="w-3" />
            <div className="w-24">ID</div>
            <div className="flex-1">Title</div>
            <div className="w-20">Type</div>
            <div className="w-20">Status</div>
            <div className="w-16 text-right">Date</div>
            <div className="w-12" />
          </div>

          {incidents.map((incident) => (
            <div
              key={incident.id}
              onClick={() => navigate(`/app/ir/incidents/${incident.id}`)}
              className="flex items-center gap-4 py-3 cursor-pointer group border-b border-zinc-900/50 hover:bg-zinc-900/30 transition-colors"
            >
              <div className={`w-2 h-2 rounded-full ${SEVERITY_COLORS[incident.severity]}`} />
              <div className="text-[10px] text-zinc-600 font-mono w-24">{incident.incident_number}</div>
              <div className="flex-1 min-w-0">
                <div className="text-xs text-zinc-300 truncate group-hover:text-white transition-colors">
                  {incident.title}
                </div>
                {incident.description && (
                  <div className="text-[10px] text-zinc-600 truncate mt-0.5">{incident.description}</div>
                )}
              </div>
              <div className="text-[10px] text-zinc-500 w-20">{TYPE_LABELS[incident.incident_type]}</div>
              <div className={`text-[10px] w-20 ${STATUS_COLORS[incident.status]}`}>
                {incident.status.replace('_', ' ')}
              </div>
              <div className="text-[10px] text-zinc-600 w-16 text-right">{formatDate(incident.occurred_at)}</div>
              <div className="w-12 text-right">
                <button
                  onClick={(e) => handleDelete(incident.id, e)}
                  className="text-[10px] text-zinc-700 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                >
                  Delete
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
