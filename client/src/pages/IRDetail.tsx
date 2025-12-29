import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Card, CardContent } from '../components';
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
  reported: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  investigating: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  action_required: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  resolved: 'bg-green-500/20 text-green-400 border-green-500/30',
  closed: 'bg-zinc-700/50 text-zinc-300 border-zinc-600',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-600',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-green-500',
};

const TYPE_LABELS: Record<string, string> = {
  safety: 'Safety / Injury',
  behavioral: 'Behavioral / HR',
  property: 'Property Damage',
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

  // Analysis states
  const [categorization, setCategorization] = useState<IRCategorizationAnalysis | null>(null);
  const [severityAnalysis, setSeverityAnalysis] = useState<IRSeverityAnalysis | null>(null);
  const [rootCause, setRootCause] = useState<IRRootCauseAnalysis | null>(null);
  const [recommendations, setRecommendations] = useState<IRRecommendationsAnalysis | null>(null);
  const [similarIncidents, setSimilarIncidents] = useState<IRSimilarIncidentsAnalysis | null>(null);
  const [analyzingType, setAnalyzingType] = useState<string | null>(null);

  // Edit states
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
          const catResult = await irIncidents.analyzeCategorization(id);
          setCategorization(catResult);
          break;
        case 'severity':
          const sevResult = await irIncidents.analyzeSeverity(id);
          setSeverityAnalysis(sevResult);
          break;
        case 'root_cause':
          const rcResult = await irIncidents.analyzeRootCause(id);
          setRootCause(rcResult);
          break;
        case 'recommendations':
          const recResult = await irIncidents.analyzeRecommendations(id);
          setRecommendations(recResult);
          break;
        case 'similar':
          const simResult = await irIncidents.analyzeSimilarIncidents(id);
          setSimilarIncidents(simResult);
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
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-zinc-500">Loading incident...</div>
      </div>
    );
  }

  if (!incident) {
    return (
      <div className="text-center py-12">
        <div className="text-zinc-500 mb-4">Incident not found</div>
        <Button onClick={() => navigate('/app/ir/incidents')}>Back to Incidents</Button>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate(-1)} className="text-zinc-400 hover:text-white transition-colors">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="text-sm text-zinc-500 font-mono">{incident.incident_number}</span>
              <span className={`px-2 py-0.5 text-xs rounded border ${STATUS_COLORS[incident.status]}`}>
                {STATUS_OPTIONS.find((s) => s.value === incident.status)?.label}
              </span>
              <div className={`w-3 h-3 rounded-full ${SEVERITY_COLORS[incident.severity]}`} title={incident.severity} />
            </div>
            <h1 className="text-2xl font-bold text-white">{incident.title}</h1>
          </div>
        </div>

        {/* Status Dropdown */}
        <select
          value={incident.status}
          onChange={(e) => updateIncident({ status: e.target.value as IRStatus })}
          disabled={updating}
          className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-white"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Basic Info */}
          <Card>
            <CardContent>
              <h2 className="text-lg font-medium text-white mb-4">Incident Details</h2>

              <div className="space-y-4">
                <div>
                  <div className="text-sm text-zinc-500 mb-1">Type</div>
                  <div className="text-white">{TYPE_LABELS[incident.incident_type]}</div>
                </div>

                {incident.description && (
                  <div>
                    <div className="text-sm text-zinc-500 mb-1">Description</div>
                    <div className="text-white whitespace-pre-wrap">{incident.description}</div>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-sm text-zinc-500 mb-1">Occurred At</div>
                    <div className="text-white">{formatDate(incident.occurred_at)}</div>
                  </div>
                  <div>
                    <div className="text-sm text-zinc-500 mb-1">Location</div>
                    <div className="text-white">{incident.location || '-'}</div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-sm text-zinc-500 mb-1">Reported By</div>
                    <div className="text-white">{incident.reported_by_name}</div>
                    {incident.reported_by_email && (
                      <div className="text-sm text-zinc-500">{incident.reported_by_email}</div>
                    )}
                  </div>
                  <div>
                    <div className="text-sm text-zinc-500 mb-1">Reported At</div>
                    <div className="text-white">{formatDate(incident.reported_at)}</div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Category-Specific Data */}
          {Object.keys(incident.category_data).length > 0 && (
            <Card>
              <CardContent>
                <h2 className="text-lg font-medium text-white mb-4">Category Details</h2>
                <div className="grid grid-cols-2 gap-4">
                  {Object.entries(incident.category_data).map(([key, value]) => (
                    <div key={key}>
                      <div className="text-sm text-zinc-500 mb-1 capitalize">
                        {key.replace(/_/g, ' ')}
                      </div>
                      <div className="text-white">
                        {Array.isArray(value)
                          ? value.join(', ')
                          : typeof value === 'boolean'
                          ? value
                            ? 'Yes'
                            : 'No'
                          : String(value)}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Witnesses */}
          {incident.witnesses.length > 0 && (
            <Card>
              <CardContent>
                <h2 className="text-lg font-medium text-white mb-4">Witnesses</h2>
                <div className="space-y-4">
                  {incident.witnesses.map((witness, idx) => (
                    <div key={idx} className="p-3 bg-zinc-800/50 rounded-lg">
                      <div className="flex justify-between items-start mb-2">
                        <div className="font-medium text-white">{witness.name}</div>
                        {witness.contact && <div className="text-sm text-zinc-500">{witness.contact}</div>}
                      </div>
                      {witness.statement && <div className="text-sm text-zinc-400">{witness.statement}</div>}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Root Cause & Corrective Actions */}
          <Card>
            <CardContent>
              <div className="space-y-6">
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <h3 className="text-lg font-medium text-white">Root Cause</h3>
                    {!editingRootCause && (
                      <button
                        onClick={() => setEditingRootCause(true)}
                        className="text-sm text-zinc-400 hover:text-white transition-colors"
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
                        rows={3}
                        className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-white"
                      />
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setRootCauseText(incident.root_cause || '');
                            setEditingRootCause(false);
                          }}
                        >
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => {
                            updateIncident({ root_cause: rootCauseText });
                            setEditingRootCause(false);
                          }}
                        >
                          Save
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="text-zinc-400">{incident.root_cause || 'Not analyzed yet'}</div>
                  )}
                </div>

                <div>
                  <div className="flex justify-between items-center mb-2">
                    <h3 className="text-lg font-medium text-white">Corrective Actions</h3>
                    {!editingActions && (
                      <button
                        onClick={() => setEditingActions(true)}
                        className="text-sm text-zinc-400 hover:text-white transition-colors"
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
                        rows={3}
                        className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-white"
                      />
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setCorrectiveActionsText(incident.corrective_actions || '');
                            setEditingActions(false);
                          }}
                        >
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => {
                            updateIncident({ corrective_actions: correctiveActionsText });
                            setEditingActions(false);
                          }}
                        >
                          Save
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="text-zinc-400">{incident.corrective_actions || 'Not defined yet'}</div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Sidebar - AI Analysis */}
        <div className="space-y-6">
          {/* AI Analysis Panel */}
          <Card>
            <CardContent>
              <h2 className="text-lg font-medium text-white mb-4">AI Analysis</h2>

              <div className="space-y-3">
                {/* Categorization */}
                <div className="p-3 bg-zinc-800/50 rounded-lg">
                  <div className="flex justify-between items-start mb-2">
                    <div className="text-sm font-medium text-white">Categorization</div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => runAnalysis('categorization')}
                      disabled={analyzingType === 'categorization'}
                    >
                      {analyzingType === 'categorization' ? 'Analyzing...' : 'Run'}
                    </Button>
                  </div>
                  {categorization && (
                    <div className="text-sm text-zinc-400">
                      <div>
                        Suggested: <span className="text-white">{TYPE_LABELS[categorization.suggested_type]}</span>
                      </div>
                      <div>Confidence: {(categorization.confidence * 100).toFixed(0)}%</div>
                      <div className="mt-1 text-xs">{categorization.reasoning}</div>
                    </div>
                  )}
                </div>

                {/* Severity */}
                <div className="p-3 bg-zinc-800/50 rounded-lg">
                  <div className="flex justify-between items-start mb-2">
                    <div className="text-sm font-medium text-white">Severity Assessment</div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => runAnalysis('severity')}
                      disabled={analyzingType === 'severity'}
                    >
                      {analyzingType === 'severity' ? 'Analyzing...' : 'Run'}
                    </Button>
                  </div>
                  {severityAnalysis && (
                    <div className="text-sm text-zinc-400">
                      <div className="flex items-center gap-2">
                        <span>Suggested:</span>
                        <span className={`px-2 py-0.5 rounded text-xs ${SEVERITY_COLORS[severityAnalysis.suggested_severity]} text-white`}>
                          {severityAnalysis.suggested_severity}
                        </span>
                      </div>
                      <div className="mt-2">
                        <div className="text-xs text-zinc-500 mb-1">Factors:</div>
                        <ul className="text-xs space-y-1">
                          {severityAnalysis.factors.map((f, i) => (
                            <li key={i}>• {f}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  )}
                </div>

                {/* Root Cause */}
                <div className="p-3 bg-zinc-800/50 rounded-lg">
                  <div className="flex justify-between items-start mb-2">
                    <div className="text-sm font-medium text-white">Root Cause</div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => runAnalysis('root_cause')}
                      disabled={analyzingType === 'root_cause'}
                    >
                      {analyzingType === 'root_cause' ? 'Analyzing...' : 'Run'}
                    </Button>
                  </div>
                  {rootCause && (
                    <div className="text-sm text-zinc-400">
                      <div className="text-white mb-1">{rootCause.primary_cause}</div>
                      <div className="text-xs text-zinc-500 mb-1">Contributing Factors:</div>
                      <ul className="text-xs space-y-1 mb-2">
                        {rootCause.contributing_factors.slice(0, 3).map((f, i) => (
                          <li key={i}>• {f}</li>
                        ))}
                      </ul>
                      <div className="text-xs text-zinc-500 mb-1">Prevention:</div>
                      <ul className="text-xs space-y-1">
                        {rootCause.prevention_suggestions.slice(0, 3).map((s, i) => (
                          <li key={i}>• {s}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {/* Recommendations */}
                <div className="p-3 bg-zinc-800/50 rounded-lg">
                  <div className="flex justify-between items-start mb-2">
                    <div className="text-sm font-medium text-white">Recommendations</div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => runAnalysis('recommendations')}
                      disabled={analyzingType === 'recommendations'}
                    >
                      {analyzingType === 'recommendations' ? 'Analyzing...' : 'Run'}
                    </Button>
                  </div>
                  {recommendations && (
                    <div className="text-sm text-zinc-400">
                      {recommendations.recommendations.map((rec, i) => (
                        <div key={i} className="mb-2 text-xs">
                          <div className="flex items-center gap-2 mb-1">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] ${
                                rec.priority === 'immediate'
                                  ? 'bg-red-500/20 text-red-400'
                                  : rec.priority === 'short_term'
                                  ? 'bg-yellow-500/20 text-yellow-400'
                                  : 'bg-blue-500/20 text-blue-400'
                              }`}
                            >
                              {rec.priority.replace('_', ' ')}
                            </span>
                          </div>
                          <div className="text-zinc-300">{rec.action}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Similar Incidents */}
                <div className="p-3 bg-zinc-800/50 rounded-lg">
                  <div className="flex justify-between items-start mb-2">
                    <div className="text-sm font-medium text-white">Similar Incidents</div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => runAnalysis('similar')}
                      disabled={analyzingType === 'similar'}
                    >
                      {analyzingType === 'similar' ? 'Analyzing...' : 'Run'}
                    </Button>
                  </div>
                  {similarIncidents && (
                    <div className="text-sm text-zinc-400">
                      {similarIncidents.similar_incidents.length === 0 ? (
                        <div className="text-xs">No similar incidents found</div>
                      ) : (
                        <div className="space-y-2">
                          {similarIncidents.similar_incidents.map((sim, i) => (
                            <div
                              key={i}
                              onClick={() => navigate(`/app/ir/incidents/${sim.incident_id}`)}
                              className="text-xs p-2 bg-zinc-900 rounded cursor-pointer hover:bg-zinc-800 transition-colors"
                            >
                              <div className="text-zinc-300">{sim.title}</div>
                              <div className="text-zinc-500 text-[10px]">
                                {sim.incident_number} • {(sim.similarity_score * 100).toFixed(0)}% match
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                      {similarIncidents.pattern_summary && (
                        <div className="mt-2 text-xs text-yellow-400">{similarIncidents.pattern_summary}</div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Documents */}
          <Card>
            <CardContent>
              <h2 className="text-lg font-medium text-white mb-4">Documents</h2>
              {documents.length === 0 ? (
                <div className="text-sm text-zinc-500">No documents uploaded</div>
              ) : (
                <div className="space-y-2">
                  {documents.map((doc) => (
                    <div key={doc.id} className="flex items-center justify-between p-2 bg-zinc-800/50 rounded-lg">
                      <div className="flex items-center gap-2">
                        <svg className="w-4 h-4 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                          />
                        </svg>
                        <span className="text-sm text-white truncate">{doc.filename}</span>
                      </div>
                      <span className="text-xs text-zinc-500">{doc.document_type}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Metadata */}
          <Card>
            <CardContent>
              <h2 className="text-lg font-medium text-white mb-4">Metadata</h2>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-zinc-500">Created</span>
                  <span className="text-white">{formatDate(incident.created_at)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Updated</span>
                  <span className="text-white">{formatDate(incident.updated_at)}</span>
                </div>
                {incident.resolved_at && (
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Resolved</span>
                    <span className="text-white">{formatDate(incident.resolved_at)}</span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default IRDetail;
