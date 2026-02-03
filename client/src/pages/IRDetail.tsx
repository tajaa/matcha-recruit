import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { irIncidents } from '../api/client';
import type {
  IRIncident,
  IRDocument,
  IRIncidentUpdate,
  IRStatus,
  IRCategorizationAnalysis,
  IRSeverityAnalysis,
  IRRootCauseAnalysis,
  IRRecommendationsAnalysis,
  IRSimilarIncidentsAnalysis,
} from '../types';

const STATUS_OPTIONS: { value: IRStatus; label: string }[] = [
  { value: 'reported', label: 'Reported' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'action_required', label: 'Action Required' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
];

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

const TYPE_LABELS: Record<string, string> = {
  safety: 'Safety',
  behavioral: 'Behavioral',
  property: 'Property',
  near_miss: 'Near Miss',
  other: 'Other',
};

export function IRDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [incident, setIncident] = useState<IRIncident | null>(null);
  const [documents, setDocuments] = useState<IRDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);

  const [categorization, setCategorization] = useState<IRCategorizationAnalysis | null>(null);
  const [severityAnalysis, setSeverityAnalysis] = useState<IRSeverityAnalysis | null>(null);
  const [rootCause, setRootCause] = useState<IRRootCauseAnalysis | null>(null);
  const [recommendations, setRecommendations] = useState<IRRecommendationsAnalysis | null>(null);
  const [similarIncidents, setSimilarIncidents] = useState<IRSimilarIncidentsAnalysis | null>(null);
  const [analyzingType, setAnalyzingType] = useState<string | null>(null);

  const [editingRootCause, setEditingRootCause] = useState(false);
  const [editingActions, setEditingActions] = useState(false);
  const [rootCauseText, setRootCauseText] = useState('');
  const [correctiveActionsText, setCorrectiveActionsText] = useState('');

  const fetchIncident = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true);
      const [incidentData, docsData] = await Promise.all([
        irIncidents.getIncident(id),
        irIncidents.listDocuments(id),
      ]);
      setIncident(incidentData);
      setDocuments(docsData);
      setRootCauseText(incidentData.root_cause || '');
      setCorrectiveActionsText(incidentData.corrective_actions || '');
    } catch (err) {
      console.error('Failed to fetch incident:', err);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchIncident();
  }, [fetchIncident]);

  const updateIncident = async (data: IRIncidentUpdate) => {
    if (!id) return;
    try {
      setUpdating(true);
      const updated = await irIncidents.updateIncident(id, data);
      setIncident(updated);
    } catch (err) {
      console.error('Failed to update incident:', err);
    } finally {
      setUpdating(false);
    }
  };

  const runAnalysis = async (type: string) => {
    if (!id) return;
    setAnalyzingType(type);
    try {
      switch (type) {
        case 'categorization':
          setCategorization(await irIncidents.analyzeCategorization(id));
          break;
        case 'severity':
          setSeverityAnalysis(await irIncidents.analyzeSeverity(id));
          break;
        case 'root_cause':
          setRootCause(await irIncidents.analyzeRootCause(id));
          break;
        case 'recommendations':
          setRecommendations(await irIncidents.analyzeRecommendations(id));
          break;
        case 'similar':
          setSimilarIncidents(await irIncidents.analyzeSimilarIncidents(id));
          break;
      }
    } catch (err) {
      console.error(`Failed to run ${type} analysis:`, err);
    } finally {
      setAnalyzingType(null);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const labelClass = 'text-[10px] uppercase tracking-wider text-zinc-600';

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-600 uppercase tracking-wider">Loading...</div>
      </div>
    );
  }

  if (!incident) {
    return (
      <div className="text-center py-16">
        <div className="text-xs text-zinc-600 mb-4">Incident not found</div>
        <button
          onClick={() => navigate('/app/ir/incidents')}
          className="text-xs text-zinc-500 hover:text-white uppercase tracking-wider"
        >
          Back to Incidents
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <button
            onClick={() => navigate(-1)}
            className="text-zinc-600 hover:text-white text-xs uppercase tracking-wider mb-4 flex items-center gap-1"
          >
            <span>←</span> Back
          </button>
          <div className="flex items-center gap-3 mb-2">
            <span className="text-[10px] text-zinc-600 font-mono">{incident.incident_number}</span>
            <div className={`w-2 h-2 rounded-full ${SEVERITY_COLORS[incident.severity]}`} />
            <span className={`text-xs ${STATUS_COLORS[incident.status]}`}>
              {incident.status.replace('_', ' ')}
            </span>
          </div>
          <h1 className="text-xl font-medium text-white">{incident.title}</h1>
        </div>

        <select
          value={incident.status}
          onChange={(e) => updateIncident({ status: e.target.value as IRStatus })}
          disabled={updating}
          className="px-2 py-1 bg-transparent border-b border-zinc-800 text-xs text-zinc-400 focus:outline-none focus:border-zinc-500 cursor-pointer"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-3 gap-12">
        {/* Main Content */}
        <div className="col-span-2 space-y-8">
          {/* Details */}
          <div className="space-y-4">
            <div className="grid grid-cols-4 gap-4">
              <div>
                <div className={labelClass}>Type</div>
                <div className="text-sm text-white mt-1">{TYPE_LABELS[incident.incident_type]}</div>
              </div>
              <div>
                <div className={labelClass}>When</div>
                <div className="text-sm text-white mt-1">{formatDate(incident.occurred_at)}</div>
              </div>
              <div>
                <div className={labelClass}>Where</div>
                <div className="text-sm text-white mt-1">{incident.location || '—'}</div>
              </div>
              <div>
                <div className={labelClass}>Reporter</div>
                <div className="text-sm text-white mt-1">{incident.reported_by_name}</div>
              </div>
            </div>

            {/* Company/Location Context */}
            {(incident.company_name || incident.location_city) && (
              <div className="grid grid-cols-2 gap-4 pt-4 border-t border-zinc-900">
                {incident.company_name && (
                  <div>
                    <div className={labelClass}>Company</div>
                    <div className="text-sm text-white mt-1">{incident.company_name}</div>
                  </div>
                )}
                {incident.location_city && (
                  <div>
                    <div className={labelClass}>Business Location</div>
                    <div className="text-sm text-white mt-1">
                      {incident.location_name ? `${incident.location_name} - ` : ''}
                      {incident.location_city}, {incident.location_state}
                    </div>
                  </div>
                )}
              </div>
            )}

            {incident.description && (
              <div>
                <div className={labelClass}>Description</div>
                <div className="text-sm text-zinc-300 mt-1 whitespace-pre-wrap">{incident.description}</div>
              </div>
            )}
          </div>

          {/* Category Data */}
          {Object.keys(incident.category_data).length > 0 && (
            <div className="pt-6 border-t border-zinc-900">
              <div className={`${labelClass} mb-3`}>Category Details</div>
              <div className="grid grid-cols-3 gap-4">
                {Object.entries(incident.category_data).map(([key, value]) => (
                  <div key={key}>
                    <div className="text-[10px] text-zinc-600 capitalize">{key.replace(/_/g, ' ')}</div>
                    <div className="text-xs text-white mt-0.5">
                      {Array.isArray(value)
                        ? value.join(', ')
                        : typeof value === 'boolean'
                        ? value ? 'Yes' : 'No'
                        : String(value)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Witnesses */}
          {incident.witnesses.length > 0 && (
            <div className="pt-6 border-t border-zinc-900">
              <div className={`${labelClass} mb-3`}>Witnesses</div>
              <div className="space-y-2">
                {incident.witnesses.map((witness, idx) => (
                  <div key={idx} className="flex items-center gap-4">
                    <span className="text-xs text-white">{witness.name}</span>
                    {witness.contact && <span className="text-[10px] text-zinc-600">{witness.contact}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Root Cause & Actions */}
          <div className="pt-6 border-t border-zinc-900 space-y-6">
            <div>
              <div className="flex justify-between items-center mb-2">
                <div className={labelClass}>Root Cause</div>
                {!editingRootCause && (
                  <button
                    onClick={() => setEditingRootCause(true)}
                    className="text-[10px] text-zinc-600 hover:text-white uppercase tracking-wider"
                  >
                    Edit
                  </button>
                )}
              </div>
              {editingRootCause ? (
                <div className="space-y-2">
                  <textarea
                    value={rootCauseText}
                    onChange={(e) => setRootCauseText(e.target.value)}
                    rows={2}
                    className="w-full px-2.5 py-1.5 bg-transparent border-b border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-500 resize-none"
                  />
                  <div className="flex justify-end gap-3">
                    <button
                      onClick={() => {
                        setRootCauseText(incident.root_cause || '');
                        setEditingRootCause(false);
                      }}
                      className="text-[10px] text-zinc-600 hover:text-white uppercase tracking-wider"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => {
                        updateIncident({ root_cause: rootCauseText });
                        setEditingRootCause(false);
                      }}
                      className="text-[10px] text-white uppercase tracking-wider"
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-zinc-400">{incident.root_cause || '—'}</div>
              )}
            </div>

            <div>
              <div className="flex justify-between items-center mb-2">
                <div className={labelClass}>Corrective Actions</div>
                {!editingActions && (
                  <button
                    onClick={() => setEditingActions(true)}
                    className="text-[10px] text-zinc-600 hover:text-white uppercase tracking-wider"
                  >
                    Edit
                  </button>
                )}
              </div>
              {editingActions ? (
                <div className="space-y-2">
                  <textarea
                    value={correctiveActionsText}
                    onChange={(e) => setCorrectiveActionsText(e.target.value)}
                    rows={2}
                    className="w-full px-2.5 py-1.5 bg-transparent border-b border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-500 resize-none"
                  />
                  <div className="flex justify-end gap-3">
                    <button
                      onClick={() => {
                        setCorrectiveActionsText(incident.corrective_actions || '');
                        setEditingActions(false);
                      }}
                      className="text-[10px] text-zinc-600 hover:text-white uppercase tracking-wider"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => {
                        updateIncident({ corrective_actions: correctiveActionsText });
                        setEditingActions(false);
                      }}
                      className="text-[10px] text-white uppercase tracking-wider"
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-zinc-400">{incident.corrective_actions || '—'}</div>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-8">
          {/* AI Analysis */}
          <div>
            <div className={`${labelClass} mb-4`}>AI Analysis</div>
            <div className="space-y-3">
              {[
                { key: 'categorization', label: 'Category', data: categorization },
                { key: 'severity', label: 'Severity', data: severityAnalysis },
                { key: 'root_cause', label: 'Root Cause', data: rootCause },
                { key: 'recommendations', label: 'Actions', data: recommendations },
                { key: 'similar', label: 'Similar', data: similarIncidents },
              ].map(({ key, label, data }) => (
                <div key={key} className="py-2 border-b border-zinc-900">
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-zinc-400">{label}</span>
                    <button
                      onClick={() => runAnalysis(key)}
                      disabled={analyzingType === key}
                      className="text-[10px] text-zinc-600 hover:text-white uppercase tracking-wider disabled:opacity-50"
                    >
                      {analyzingType === key ? '...' : data ? 'Rerun' : 'Run'}
                    </button>
                  </div>
                  {key === 'categorization' && categorization && (
                    <div className="mt-2 text-[10px] text-zinc-500">
                      {TYPE_LABELS[categorization.suggested_type]} ({(categorization.confidence * 100).toFixed(0)}%)
                      {categorization.from_cache && (
                        <div className="mt-1 text-amber-500/70 text-[9px]">⚠ Cached result</div>
                      )}
                    </div>
                  )}
                  {key === 'severity' && severityAnalysis && (
                    <div className="mt-2">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${SEVERITY_COLORS[severityAnalysis.suggested_severity]}`} />
                        <span className="text-[10px] text-zinc-500 capitalize">{severityAnalysis.suggested_severity}</span>
                      </div>
                      {severityAnalysis.from_cache && (
                        <div className="mt-1 text-amber-500/70 text-[9px]">⚠ Cached result</div>
                      )}
                    </div>
                  )}
                  {key === 'root_cause' && rootCause && (
                    <div className="mt-2">
                      <div className="text-[10px] text-zinc-500 line-clamp-2">{rootCause.primary_cause}</div>
                      {rootCause.from_cache && (
                        <div className="mt-1 text-amber-500/70 text-[9px]">⚠ Cached result</div>
                      )}
                    </div>
                  )}
                  {key === 'recommendations' && recommendations && (
                    <div className="mt-2 text-[10px] text-zinc-500">
                      {recommendations.recommendations.length} actions suggested
                      {recommendations.from_cache && (
                        <div className="mt-1 text-amber-500/70 text-[9px]">⚠ Cached result</div>
                      )}
                    </div>
                  )}
                  {key === 'similar' && similarIncidents && (
                    <div className="mt-2 text-[10px] text-zinc-500">
                      {similarIncidents.similar_incidents.length} similar found
                      {similarIncidents.from_cache && (
                        <div className="mt-1 text-amber-500/70 text-[9px]">⚠ Cached result</div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Documents */}
          <div>
            <div className={`${labelClass} mb-3`}>Documents</div>
            {documents.length === 0 ? (
              <div className="text-xs text-zinc-700">None</div>
            ) : (
              <div className="space-y-1">
                {documents.map((doc) => (
                  <div key={doc.id} className="flex items-center justify-between py-1">
                    <span className="text-xs text-zinc-400 truncate">{doc.filename}</span>
                    <span className="text-[10px] text-zinc-600">{doc.document_type}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Metadata */}
          <div>
            <div className={`${labelClass} mb-3`}>Info</div>
            <div className="space-y-1 text-[10px]">
              <div className="flex justify-between">
                <span className="text-zinc-600">Created</span>
                <span className="text-zinc-400">{formatDate(incident.created_at)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-600">Updated</span>
                <span className="text-zinc-400">{formatDate(incident.updated_at)}</span>
              </div>
              {incident.resolved_at && (
                <div className="flex justify-between">
                  <span className="text-zinc-600">Resolved</span>
                  <span className="text-zinc-400">{formatDate(incident.resolved_at)}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default IRDetail;
