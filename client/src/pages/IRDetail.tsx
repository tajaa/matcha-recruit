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
import { CategorizationAnalysisModal } from '../components/ir/CategorizationAnalysisModal';
import { SeverityAnalysisModal } from '../components/ir/SeverityAnalysisModal';
import { RootCauseAnalysisModal } from '../components/ir/RootCauseAnalysisModal';
import { RecommendationsAnalysisModal } from '../components/ir/RecommendationsAnalysisModal';
import { SimilarIncidentsAnalysisModal } from '../components/ir/SimilarIncidentsAnalysisModal';
import { useIsLightMode } from '../hooks/useIsLightMode';

// ─── theme ────────────────────────────────────────────────────────────────────

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  textMain: 'text-zinc-900',
  textSecondary: 'text-zinc-700',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  border: 'border-stone-200',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800 rounded-xl',
  select: 'px-3 py-1.5 bg-white border border-stone-300 text-zinc-900 text-xs rounded-xl focus:outline-none focus:border-stone-400 cursor-pointer',
  textarea: 'w-full px-3 py-2 bg-white border border-stone-300 text-zinc-900 text-sm focus:outline-none focus:border-stone-400 rounded-xl resize-none',
  sectionBorder: 'border-stone-200',
  sidebarHover: 'hover:bg-stone-200 rounded-xl',
  sevDots: { critical: 'bg-zinc-900', high: 'bg-stone-600', medium: 'bg-stone-400', low: 'bg-stone-300' } as Record<string, string>,
  statusColors: { reported: 'text-zinc-900', investigating: 'text-stone-600', action_required: 'text-stone-500', resolved: 'text-stone-400', closed: 'text-stone-300' } as Record<string, string>,
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  textMain: 'text-zinc-100',
  textSecondary: 'text-zinc-300',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  border: 'border-white/10',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  btnGhost: 'text-zinc-600 hover:text-zinc-100',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600 rounded-xl',
  select: 'px-3 py-1.5 bg-zinc-800 border border-white/10 text-zinc-100 text-xs rounded-xl focus:outline-none focus:border-white/20 cursor-pointer',
  textarea: 'w-full px-3 py-2 bg-zinc-800 border border-white/10 text-zinc-100 text-sm focus:outline-none focus:border-white/20 rounded-xl resize-none',
  sectionBorder: 'border-zinc-800',
  sidebarHover: 'hover:bg-zinc-800 rounded-xl',
  sevDots: { critical: 'bg-zinc-100', high: 'bg-zinc-400', medium: 'bg-zinc-500', low: 'bg-zinc-600' } as Record<string, string>,
  statusColors: { reported: 'text-zinc-100', investigating: 'text-zinc-400', action_required: 'text-zinc-300', resolved: 'text-zinc-500', closed: 'text-zinc-600' } as Record<string, string>,
} as const;

const STATUS_OPTIONS: { value: IRStatus; label: string }[] = [
  { value: 'reported', label: 'Reported' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'action_required', label: 'Action Required' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
];

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
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  const [incident, setIncident] = useState<IRIncident | null>(null);
  const [documents, setDocuments] = useState<IRDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const [showCategorizationModal, setShowCategorizationModal] = useState(false);
  const [showSeverityModal, setShowSeverityModal] = useState(false);
  const [showRootCauseModal, setShowRootCauseModal] = useState(false);
  const [showRecommendationsModal, setShowRecommendationsModal] = useState(false);
  const [showSimilarModal, setShowSimilarModal] = useState(false);

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
    setError(null);
    try {
      setUpdating(true);
      const updated = await irIncidents.updateIncident(id, data);
      setIncident(updated);
    } catch (err) {
      console.error('Failed to update incident:', err);
      setError(err instanceof Error ? err.message : 'Failed to update incident');
      // Re-fetch to ensure UI is in sync with server
      fetchIncident();
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

  if (loading) {
    return (
      <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
        <div className="flex items-center justify-center min-h-[50vh]">
          <div className={`text-xs ${t.textFaint} uppercase tracking-wider animate-pulse`}>Loading...</div>
        </div>
      </div>
    );
  }

  if (!incident) {
    return (
      <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
        <div className="text-center py-16">
          <div className={`text-xs ${t.textFaint} mb-4`}>Incident not found</div>
          <button
            onClick={() => navigate('/app/ir/incidents')}
            className={`text-xs ${t.btnGhost} uppercase tracking-wider font-bold`}
          >
            Back to Incidents
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-12 pb-8">
        <div>
          <button
            onClick={() => navigate(-1)}
            className={`${t.btnGhost} text-xs uppercase tracking-wider mb-4 flex items-center gap-1 font-bold`}
          >
            <span>&larr;</span> Back
          </button>
          <div className="flex items-center gap-3 mb-2">
            <span className={`text-[10px] ${t.textFaint} font-mono`}>{incident.incident_number}</span>
            <div className={`w-2 h-2 rounded-full ${t.sevDots[incident.severity]}`} />
            <span className={`text-xs font-bold uppercase tracking-wider ${t.statusColors[incident.status]}`}>
              {incident.status.replace('_', ' ')}
            </span>
          </div>
          <h1 className={`text-4xl font-bold tracking-tighter ${t.textMain} uppercase`}>{incident.title}</h1>
        </div>

        <div>
          <select
            value={incident.status}
            onChange={(e) => updateIncident({ status: e.target.value as IRStatus })}
            disabled={updating}
            className={`${t.select} ${updating ? 'opacity-50' : ''} font-bold uppercase tracking-wider`}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          {error && (
            <div className="text-xs text-red-400 mt-1">{error}</div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-12">
        {/* Main Content */}
        <div className="col-span-2 space-y-8">
          {/* Details */}
          <div className={`${t.card} p-6 space-y-4`}>
            <div className="grid grid-cols-4 gap-4">
              <div>
                <div className={t.label}>Type</div>
                <div className={`text-sm ${t.textMain} mt-1`}>{TYPE_LABELS[incident.incident_type]}</div>
              </div>
              <div>
                <div className={t.label}>When</div>
                <div className={`text-sm ${t.textMain} mt-1`}>{formatDate(incident.occurred_at)}</div>
              </div>
              <div>
                <div className={t.label}>Where</div>
                <div className={`text-sm ${t.textMain} mt-1`}>{incident.location || '—'}</div>
              </div>
              <div>
                <div className={t.label}>Reporter</div>
                <div className={`text-sm ${t.textMain} mt-1`}>{incident.reported_by_name}</div>
              </div>
            </div>

            {/* Company/Location Context */}
            {(incident.company_name || incident.location_city) && (
              <div className={`grid grid-cols-2 gap-4 pt-4 border-t ${t.sectionBorder}`}>
                {incident.company_name && (
                  <div>
                    <div className={t.label}>Company</div>
                    <div className={`text-sm ${t.textMain} mt-1`}>{incident.company_name}</div>
                  </div>
                )}
                {incident.location_city && (
                  <div>
                    <div className={t.label}>Business Location</div>
                    <div className={`text-sm ${t.textMain} mt-1`}>
                      {incident.location_name ? `${incident.location_name} - ` : ''}
                      {incident.location_city}, {incident.location_state}
                    </div>
                  </div>
                )}
              </div>
            )}

            {incident.description && (
              <div className={`pt-4 border-t ${t.sectionBorder}`}>
                <div className={t.label}>Description</div>
                <div className={`text-sm ${t.textSecondary} mt-1 whitespace-pre-wrap`}>{incident.description}</div>
              </div>
            )}
          </div>

          {/* Category Data */}
          {Object.keys(incident.category_data).length > 0 && (
            <div className={`${t.card} p-6`}>
              <div className={`${t.label} mb-3`}>Category Details</div>
              <div className="grid grid-cols-3 gap-4">
                {Object.entries(incident.category_data).map(([key, value]) => (
                  <div key={key}>
                    <div className={`text-[10px] ${t.textFaint} capitalize`}>{key.replace(/_/g, ' ')}</div>
                    <div className={`text-xs ${t.textMain} mt-0.5`}>
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
            <div className={`${t.card} p-6`}>
              <div className={`${t.label} mb-3`}>Witnesses</div>
              <div className="space-y-2">
                {incident.witnesses.map((witness, idx) => (
                  <div key={idx} className="flex items-center gap-4">
                    <span className={`text-xs ${t.textMain}`}>{witness.name}</span>
                    {witness.contact && <span className={`text-[10px] ${t.textFaint}`}>{witness.contact}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Root Cause & Actions */}
          <div className={`${t.card} p-6 space-y-6`}>
            <div>
              <div className="flex justify-between items-center mb-2">
                <div className={t.label}>Root Cause</div>
                {!editingRootCause && (
                  <button
                    onClick={() => setEditingRootCause(true)}
                    className={`text-[10px] ${t.btnGhost} uppercase tracking-wider font-bold`}
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
                    className={t.textarea}
                  />
                  <div className="flex justify-end gap-3">
                    <button
                      onClick={() => {
                        setRootCauseText(incident.root_cause || '');
                        setEditingRootCause(false);
                      }}
                      className={`text-[10px] ${t.btnGhost} uppercase tracking-wider font-bold`}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => {
                        updateIncident({ root_cause: rootCauseText });
                        setEditingRootCause(false);
                      }}
                      className={`text-[10px] ${t.textMain} uppercase tracking-wider font-bold`}
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <div className={`text-sm ${t.textMuted}`}>{incident.root_cause || '—'}</div>
              )}
            </div>

            <div className={`pt-6 border-t ${t.sectionBorder}`}>
              <div className="flex justify-between items-center mb-2">
                <div className={t.label}>Corrective Actions</div>
                {!editingActions && (
                  <button
                    onClick={() => setEditingActions(true)}
                    className={`text-[10px] ${t.btnGhost} uppercase tracking-wider font-bold`}
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
                    className={t.textarea}
                  />
                  <div className="flex justify-end gap-3">
                    <button
                      onClick={() => {
                        setCorrectiveActionsText(incident.corrective_actions || '');
                        setEditingActions(false);
                      }}
                      className={`text-[10px] ${t.btnGhost} uppercase tracking-wider font-bold`}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => {
                        updateIncident({ corrective_actions: correctiveActionsText });
                        setEditingActions(false);
                      }}
                      className={`text-[10px] ${t.textMain} uppercase tracking-wider font-bold`}
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <div className={`text-sm ${t.textMuted}`}>{incident.corrective_actions || '—'}</div>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-8">
          {/* AI Analysis */}
          <div className={`${t.card} p-6`}>
            <div className={`${t.label} mb-4`}>AI Analysis</div>
            <div className="space-y-3">
              {[
                { key: 'categorization', label: 'Category', data: categorization, onClick: () => setShowCategorizationModal(true) },
                { key: 'severity', label: 'Severity', data: severityAnalysis, onClick: () => setShowSeverityModal(true) },
                { key: 'root_cause', label: 'Root Cause', data: rootCause, onClick: () => setShowRootCauseModal(true) },
                { key: 'recommendations', label: 'Actions', data: recommendations, onClick: () => setShowRecommendationsModal(true) },
                { key: 'similar', label: 'Similar', data: similarIncidents, onClick: () => setShowSimilarModal(true) },
              ].map(({ key, label, data, onClick }) => (
                <div key={key} className={`py-2 border-b ${t.sectionBorder}`}>
                  <div className="flex justify-between items-center">
                    <span className={`text-xs ${t.textMuted}`}>{label}</span>
                    <button
                      onClick={() => runAnalysis(key)}
                      disabled={analyzingType === key}
                      className={`text-[10px] ${t.btnGhost} uppercase tracking-wider font-bold disabled:opacity-50`}
                    >
                      {analyzingType === key ? '...' : data ? 'Rerun' : 'Run'}
                    </button>
                  </div>
                  {key === 'categorization' && categorization && (
                    <div
                      onClick={onClick}
                      className={`mt-2 text-[10px] ${t.textMuted} cursor-pointer ${t.sidebarHover} p-2 -m-2 transition-colors`}
                    >
                      <div className="flex items-center justify-between">
                        <span>{TYPE_LABELS[categorization.suggested_type]} ({(categorization.confidence * 100).toFixed(0)}%)</span>
                        <span className={t.textFaint}>&rarr;</span>
                      </div>
                      {categorization.from_cache && (
                        <div className="mt-1 text-amber-500/70 text-[9px]">Cached result</div>
                      )}
                    </div>
                  )}
                  {key === 'severity' && severityAnalysis && (
                    <div
                      onClick={onClick}
                      className={`mt-2 cursor-pointer ${t.sidebarHover} p-2 -m-2 transition-colors`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${t.sevDots[severityAnalysis.suggested_severity]}`} />
                          <span className={`text-[10px] ${t.textMuted} capitalize`}>{severityAnalysis.suggested_severity}</span>
                        </div>
                        <span className={t.textFaint}>&rarr;</span>
                      </div>
                      {severityAnalysis.from_cache && (
                        <div className="mt-1 text-amber-500/70 text-[9px]">Cached result</div>
                      )}
                    </div>
                  )}
                  {key === 'root_cause' && rootCause && (
                    <div
                      onClick={onClick}
                      className={`mt-2 cursor-pointer ${t.sidebarHover} p-2 -m-2 transition-colors`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className={`text-[10px] ${t.textMuted} line-clamp-2 flex-1`}>{rootCause.primary_cause}</div>
                        <span className={t.textFaint}>&rarr;</span>
                      </div>
                      {rootCause.from_cache && (
                        <div className="mt-1 text-amber-500/70 text-[9px]">Cached result</div>
                      )}
                    </div>
                  )}
                  {key === 'recommendations' && recommendations && (
                    <div
                      onClick={onClick}
                      className={`mt-2 text-[10px] ${t.textMuted} cursor-pointer ${t.sidebarHover} p-2 -m-2 transition-colors`}
                    >
                      <div className="flex items-center justify-between">
                        <span>{recommendations.recommendations.length} actions suggested</span>
                        <span className={t.textFaint}>&rarr;</span>
                      </div>
                      {recommendations.from_cache && (
                        <div className="mt-1 text-amber-500/70 text-[9px]">Cached result</div>
                      )}
                    </div>
                  )}
                  {key === 'similar' && similarIncidents && (
                    <div
                      onClick={onClick}
                      className={`mt-2 text-[10px] ${t.textMuted} cursor-pointer ${t.sidebarHover} p-2 -m-2 transition-colors`}
                    >
                      <div className="flex items-center justify-between">
                        <span>{similarIncidents.similar_incidents.length} similar found</span>
                        <span className={t.textFaint}>&rarr;</span>
                      </div>
                      {similarIncidents.from_cache && (
                        <div className="mt-1 text-amber-500/70 text-[9px]">Cached result</div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Documents */}
          <div className={`${t.card} p-6`}>
            <div className={`${t.label} mb-3`}>Documents</div>
            {documents.length === 0 ? (
              <div className={`text-xs ${t.textFaint}`}>None</div>
            ) : (
              <div className="space-y-1">
                {documents.map((doc) => (
                  <div key={doc.id} className="flex items-center justify-between py-1">
                    <span className={`text-xs ${t.textMuted} truncate`}>{doc.filename}</span>
                    <span className={`text-[10px] ${t.textFaint}`}>{doc.document_type}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Metadata */}
          <div className={`${t.card} p-6`}>
            <div className={`${t.label} mb-3`}>Info</div>
            <div className="space-y-1 text-[10px]">
              <div className="flex justify-between">
                <span className={t.textFaint}>Created</span>
                <span className={t.textMuted}>{formatDate(incident.created_at)}</span>
              </div>
              <div className="flex justify-between">
                <span className={t.textFaint}>Updated</span>
                <span className={t.textMuted}>{formatDate(incident.updated_at)}</span>
              </div>
              {incident.resolved_at && (
                <div className="flex justify-between">
                  <span className={t.textFaint}>Resolved</span>
                  <span className={t.textMuted}>{formatDate(incident.resolved_at)}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Analysis Detail Modals */}
      <CategorizationAnalysisModal
        isOpen={showCategorizationModal}
        onClose={() => setShowCategorizationModal(false)}
        analysis={categorization}
      />
      <SeverityAnalysisModal
        isOpen={showSeverityModal}
        onClose={() => setShowSeverityModal(false)}
        analysis={severityAnalysis}
      />
      <RootCauseAnalysisModal
        isOpen={showRootCauseModal}
        onClose={() => setShowRootCauseModal(false)}
        analysis={rootCause}
      />
      <RecommendationsAnalysisModal
        isOpen={showRecommendationsModal}
        onClose={() => setShowRecommendationsModal(false)}
        analysis={recommendations}
      />
      <SimilarIncidentsAnalysisModal
        isOpen={showSimilarModal}
        onClose={() => setShowSimilarModal(false)}
        analysis={similarIncidents}
      />
    </div>
    </div>
  );
}

export default IRDetail;
