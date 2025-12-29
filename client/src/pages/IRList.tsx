import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, CardContent } from '../components';
import { irIncidents } from '../api/client';
import type { IRIncident, IRIncidentType, IRSeverity, IRStatus } from '../types';

const STATUS_TABS: { label: string; value: IRStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Reported', value: 'reported' },
  { label: 'Investigating', value: 'investigating' },
  { label: 'Action Required', value: 'action_required' },
  { label: 'Resolved', value: 'resolved' },
  { label: 'Closed', value: 'closed' },
];

const TYPE_OPTIONS: { label: string; value: IRIncidentType | '' }[] = [
  { label: 'All Types', value: '' },
  { label: 'Safety', value: 'safety' },
  { label: 'Behavioral', value: 'behavioral' },
  { label: 'Property', value: 'property' },
  { label: 'Near Miss', value: 'near_miss' },
  { label: 'Other', value: 'other' },
];

const SEVERITY_OPTIONS: { label: string; value: IRSeverity | '' }[] = [
  { label: 'All Severities', value: '' },
  { label: 'Critical', value: 'critical' },
  { label: 'High', value: 'high' },
  { label: 'Medium', value: 'medium' },
  { label: 'Low', value: 'low' },
];

const TYPE_LABELS: Record<string, string> = {
  safety: 'Safety',
  behavioral: 'Behavioral',
  property: 'Property',
  near_miss: 'Near Miss',
  other: 'Other',
};

const STATUS_COLORS: Record<string, string> = {
  reported: 'bg-blue-500/20 text-blue-400',
  investigating: 'bg-yellow-500/20 text-yellow-400',
  action_required: 'bg-orange-500/20 text-orange-400',
  resolved: 'bg-green-500/20 text-green-400',
  closed: 'bg-zinc-700 text-zinc-300',
};

const STATUS_LABELS: Record<string, string> = {
  reported: 'Reported',
  investigating: 'Investigating',
  action_required: 'Action Required',
  resolved: 'Resolved',
  closed: 'Closed',
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

  // Filters
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
    if (!confirm('Delete this incident? This action cannot be undone.')) return;
    try {
      await irIncidents.deleteIncident(id);
      fetchIncidents();
    } catch (err) {
      console.error('Failed to delete incident:', err);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">All Incidents</h1>
          <p className="text-zinc-400 mt-1">{total} total incidents</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate('/app/ir')}>
            Dashboard
          </Button>
          <Button onClick={() => navigate('/app/ir/incidents/new')}>Report Incident</Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4 mb-6">
        {/* Status Tabs */}
        <div className="flex gap-1 bg-zinc-900 p-1 rounded-lg">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setActiveTab(tab.value)}
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                activeTab === tab.value ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Type Filter */}
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as IRIncidentType | '')}
          className="px-3 py-1.5 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-white focus:outline-none focus:border-white"
        >
          {TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        {/* Severity Filter */}
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value as IRSeverity | '')}
          className="px-3 py-1.5 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-white focus:outline-none focus:border-white"
        >
          {SEVERITY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        {/* Search */}
        <div className="flex-1 min-w-[200px]">
          <input
            type="text"
            placeholder="Search incidents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-3 py-1.5 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-white"
          />
        </div>
      </div>

      {/* Incidents List */}
      {loading ? (
        <div className="text-center py-12 text-zinc-500">Loading...</div>
      ) : incidents.length === 0 ? (
        <Card>
          <CardContent className="text-center py-12">
            <svg className="mx-auto h-12 w-12 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <h3 className="mt-4 text-lg font-medium text-white">No incidents found</h3>
            <p className="mt-2 text-zinc-500">
              {activeTab !== 'all' || typeFilter || severityFilter || searchQuery
                ? 'Try adjusting your filters.'
                : 'Get started by reporting an incident.'}
            </p>
            <Button className="mt-4" onClick={() => navigate('/app/ir/incidents/new')}>
              Report Incident
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {incidents.map((incident) => (
            <Card
              key={incident.id}
              className="cursor-pointer hover:border-zinc-600 transition-colors"
              onClick={() => navigate(`/app/ir/incidents/${incident.id}`)}
            >
              <CardContent className="py-4">
                <div className="flex items-start gap-4">
                  {/* Severity Indicator */}
                  <div className={`w-3 h-3 rounded-full mt-1.5 ${SEVERITY_COLORS[incident.severity]}`} />

                  {/* Main Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm text-zinc-500 font-mono">{incident.incident_number}</span>
                      <span className={`px-2 py-0.5 text-xs rounded ${STATUS_COLORS[incident.status]}`}>
                        {STATUS_LABELS[incident.status]}
                      </span>
                      <span className="px-2 py-0.5 text-xs rounded bg-zinc-800 text-zinc-400">
                        {TYPE_LABELS[incident.incident_type]}
                      </span>
                    </div>

                    <h3 className="font-medium text-white mb-1">{incident.title}</h3>

                    {incident.description && (
                      <p className="text-sm text-zinc-500 mb-2 line-clamp-1">{incident.description}</p>
                    )}

                    <div className="flex items-center gap-4 text-sm text-zinc-500">
                      <span>{formatDate(incident.occurred_at)}</span>
                      {incident.location && <span>{incident.location}</span>}
                      <span>by {incident.reported_by_name}</span>
                      {incident.document_count > 0 && (
                        <span className="flex items-center gap-1">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                            />
                          </svg>
                          {incident.document_count}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => handleDelete(incident.id, e)}
                      className="text-xs text-zinc-500 hover:text-red-400 transition-colors px-2 py-1"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export default IRList;
