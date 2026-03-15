import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { getAccessToken, irIncidents, erCopilot } from '../api/client';
import type {
  IRIncident,
  IRDocument,
  IRIncidentUpdate,
  IRStatus,
  IRRootCauseAnalysis,
  IRRecommendationsAnalysis,
  IRPrecedentAnalysis,
  ERCaseCategory,
  InvestigationInterview,
} from '../types';
import { RootCauseAnalysisModal } from '../components/ir/RootCauseAnalysisModal';
import { RecommendationsAnalysisModal } from '../components/ir/RecommendationsAnalysisModal';
import { SimilarIncidentsAnalysisModal } from '../components/ir/SimilarIncidentsAnalysisModal';
import { ConsistencyGuidancePanel } from '../components/ir/ConsistencyGuidancePanel';
import { AnalysisTerminalModal } from '../components/ir/AnalysisTerminalModal';
import { ScheduleInterviewsModal } from '../components/ir/ScheduleInterviewsModal';
import { useIRAnalysisStream } from '../hooks/ir/useIRAnalysisStream';
import type { AnalysisType } from '../hooks/ir/useIRAnalysisStream';
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
  escalateBtn: 'text-emerald-700 hover:text-emerald-600',
  escalateGhost: 'text-stone-500 hover:text-zinc-900',
  modalBg: 'bg-stone-100 border border-stone-300 rounded-xl',
  modalInput: 'w-full px-2.5 py-1.5 bg-white border border-stone-300 rounded-xl text-sm text-zinc-900 focus:outline-none focus:border-stone-400',
  modalSelect: 'w-full px-2.5 py-1.5 bg-white border border-stone-300 rounded-xl text-sm text-zinc-900 focus:outline-none focus:border-stone-400 cursor-pointer',
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
  escalateBtn: 'text-emerald-400 hover:text-emerald-300',
  escalateGhost: 'text-zinc-600 hover:text-zinc-100',
  modalBg: 'bg-zinc-900 border border-zinc-800 rounded-xl',
  modalInput: 'w-full px-2.5 py-1.5 bg-transparent border border-zinc-800 rounded-xl text-sm text-white focus:outline-none focus:border-zinc-600',
  modalSelect: 'w-full px-2.5 py-1.5 bg-transparent border border-zinc-800 rounded-xl text-sm text-white focus:outline-none focus:border-zinc-600 cursor-pointer',
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

const IR_TYPE_TO_ER_CATEGORY: Record<string, ERCaseCategory> = {
  safety: 'safety',
  behavioral: 'misconduct',
  property: 'other',
  near_miss: 'safety',
  other: 'other',
};

const ER_CATEGORY_OPTIONS: { value: ERCaseCategory; label: string }[] = [
  { value: 'harassment', label: 'Harassment' },
  { value: 'discrimination', label: 'Discrimination' },
  { value: 'safety', label: 'Safety' },
  { value: 'retaliation', label: 'Retaliation' },
  { value: 'policy_violation', label: 'Policy Violation' },
  { value: 'misconduct', label: 'Misconduct' },
  { value: 'wage_hour', label: 'Wage & Hour' },
  { value: 'other', label: 'Other' },
];

const API_BASE = import.meta.env.VITE_API_URL || '/api';

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

  // Employee name map for resolving involved_employee_ids
  const [employeeNameMap, setEmployeeNameMap] = useState<Record<string, { first_name: string; last_name: string }>>({});

  const [rootCause, setRootCause] = useState<IRRootCauseAnalysis | null>(null);
  const [recommendations, setRecommendations] = useState<IRRecommendationsAnalysis | null>(null);
  const [similarIncidents, setSimilarIncidents] = useState<IRPrecedentAnalysis | null>(null);
  const [similarVersion, setSimilarVersion] = useState(0);
  const [showTerminalModal, setShowTerminalModal] = useState(false);

  const stream = useIRAnalysisStream();

  const [editingRootCause, setEditingRootCause] = useState(false);
  const [editingActions, setEditingActions] = useState(false);
  const [rootCauseText, setRootCauseText] = useState('');
  const [correctiveActionsText, setCorrectiveActionsText] = useState('');

  const [showRootCauseModal, setShowRootCauseModal] = useState(false);
  const [showRecommendationsModal, setShowRecommendationsModal] = useState(false);
  const [showSimilarModal, setShowSimilarModal] = useState(false);

  const [showEscalateModal, setShowEscalateModal] = useState(false);
  const [escalating, setEscalating] = useState(false);
  const [escalateForm, setEscalateForm] = useState({ title: '', description: '', category: 'other' as ERCaseCategory });

  const [investigationInterviews, setInvestigationInterviews] = useState<InvestigationInterview[]>([]);
  const [loadingInterviews, setLoadingInterviews] = useState(false);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [showAnalysisModal, setShowAnalysisModal] = useState<InvestigationInterview | null>(null);
  const [copiedLinkId, setCopiedLinkId] = useState<string | null>(null);

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

  const fetchInvestigationInterviews = useCallback(async () => {
    if (!id) return;
    setLoadingInterviews(true);
    try {
      const data = await irIncidents.listInvestigationInterviews(id);
      setInvestigationInterviews(data);
    } catch (e) {
      // silent fail - not critical
    } finally {
      setLoadingInterviews(false);
    }
  }, [id]);

  useEffect(() => {
    fetchIncident();
    fetchInvestigationInterviews();
  }, [fetchIncident, fetchInvestigationInterviews]);

  // Fetch employee names when incident has involved employees
  useEffect(() => {
    if (!incident?.involved_employee_ids?.length) return;
    const token = getAccessToken();
    if (!token) return;
    fetch(`${API_BASE}/employees`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => (res.ok ? res.json() : []))
      .then((employees: { id: string; first_name: string; last_name: string }[]) => {
        const map: Record<string, { first_name: string; last_name: string }> = {};
        for (const emp of employees) {
          map[emp.id] = { first_name: emp.first_name, last_name: emp.last_name };
        }
        setEmployeeNameMap(map);
      })
      .catch(() => {});
  }, [incident?.involved_employee_ids]);

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
      fetchIncident();
    } finally {
      setUpdating(false);
    }
  };

  const handleResendInvite = async (interviewId: string) => {
    if (!id) return;
    await irIncidents.resendInvestigationInvite(id, interviewId);
    await fetchInvestigationInterviews();
  };

  const handleCopyLink = async (inv: InvestigationInterview) => {
    if (!id) return;
    let token = inv.invite_token;
    if (!token) {
      const res = await irIncidents.generateInvestigationLink(id, inv.id);
      token = res.invite_token;
      await fetchInvestigationInterviews();
    }
    const url = `${window.location.origin}/investigation/${token}`;
    await navigator.clipboard.writeText(url);
    setCopiedLinkId(inv.id);
    setTimeout(() => setCopiedLinkId(null), 2000);
  };

  const handleCancelInterview = async (interviewId: string) => {
    if (!id) return;
    await irIncidents.cancelInvestigationInterview(id, interviewId);
    await fetchInvestigationInterviews();
  };

  const runAnalysis = (type: string) => {
    if (!id) return;
    stream.reset();
    setShowTerminalModal(true);
    stream.runAnalysis(id, type as AnalysisType);
  };

  // Sync stream results back to state for sidebar previews
  useEffect(() => {
    if (!stream.result || stream.streaming) return;
    switch (stream.analysisType) {
      case 'root_cause':
        setRootCause(stream.result as IRRootCauseAnalysis);
        break;
      case 'recommendations':
        setRecommendations(stream.result as IRRecommendationsAnalysis);
        break;
      case 'similar':
        setSimilarIncidents(stream.result as IRPrecedentAnalysis);
        setSimilarVersion((v) => v + 1);
        break;
    }
  }, [stream.result, stream.streaming, stream.analysisType]);

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const openEscalateModal = () => {
    if (!incident) return;
    const witnesses = incident.witnesses.length > 0
      ? `Witnesses: ${incident.witnesses.map(w => w.name).join(', ')}`
      : '';
    const lines = [
      `Escalated from IR incident ${incident.incident_number}`,
      '',
      `Type: ${TYPE_LABELS[incident.incident_type] || incident.incident_type}`,
      `Severity: ${incident.severity}`,
      `Occurred: ${formatDate(incident.occurred_at)}`,
      incident.location ? `Location: ${incident.location}` : '',
      `Reporter: ${incident.reported_by_name}`,
      '',
      incident.description || '',
      witnesses,
    ].filter(Boolean).join('\n');

    setEscalateForm({
      title: `[Escalated from ${incident.incident_number}] ${incident.title}`,
      description: lines,
      category: IR_TYPE_TO_ER_CATEGORY[incident.incident_type] || 'other',
    });
    setShowEscalateModal(true);
  };

  const handleEscalate = async () => {
    if (!incident || !id) return;
    setEscalating(true);
    try {
      const newCase = await erCopilot.createCase({
        title: escalateForm.title,
        description: escalateForm.description,
        category: escalateForm.category,
        intake_context: {
          assistance_requested: true,
          escalated_from_ir: {
            incident_id: incident.id,
            incident_number: incident.incident_number,
            incident_type: incident.incident_type,
            severity: incident.severity,
            occurred_at: incident.occurred_at,
          },
        } as any,
      });
      await irIncidents.updateIncident(id, {
        category_data: {
          ...incident.category_data,
          escalated_er_case_id: newCase.id,
          escalated_er_case_number: newCase.case_number,
        },
      });
      setShowEscalateModal(false);
      navigate(`/app/matcha/er-copilot/${newCase.id}`);
    } catch (err) {
      console.error('Failed to escalate to ER case:', err);
      setError(err instanceof Error ? err.message : 'Failed to escalate');
    } finally {
      setEscalating(false);
    }
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
    <div className="max-w-5xl mx-auto animate-in fade-in duration-500">
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

        <div className="flex items-center gap-4">
          {incident.category_data?.escalated_er_case_id ? (
            <button
              onClick={() => navigate(`/app/matcha/er-copilot/${incident.category_data.escalated_er_case_id}`)}
              className={`text-xs ${t.escalateBtn} uppercase tracking-wider font-bold`}
            >
              View ER Case &rarr;
            </button>
          ) : (
            <button
              onClick={openEscalateModal}
              className={`text-xs ${t.escalateGhost} uppercase tracking-wider font-bold`}
            >
              Escalate to ER Case
            </button>
          )}
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

            {incident.involved_employee_ids?.length > 0 && (
              <div className={`pt-4 border-t ${t.sectionBorder}`}>
                <div className={t.label}>Involved Employees</div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1">
                  {incident.involved_employee_ids.map((empId) => {
                    const emp = employeeNameMap[empId];
                    return (
                      <Link
                        key={empId}
                        to={`/app/matcha/employees/${empId}`}
                        className={`text-sm ${t.textMain} hover:underline`}
                      >
                        {emp ? `${emp.first_name} ${emp.last_name}` : empId}
                      </Link>
                    );
                  })}
                </div>
              </div>
            )}

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

          {/* Investigation Interviews */}
          {(incident.status === 'investigating' || incident.status === 'action_required' || investigationInterviews.length > 0) && (
            <div className={`${t.card} p-6`}>
              <div className="flex items-center justify-between mb-4">
                <div className={t.label}>Investigation Interviews</div>
                {(incident.status === 'investigating' || incident.status === 'action_required') && (
                  <button
                    onClick={() => setShowScheduleModal(true)}
                    className={`text-[10px] ${t.btnPrimary} px-3 py-1.5 uppercase tracking-wider font-bold`}
                  >
                    Schedule Interviews
                  </button>
                )}
              </div>

              {loadingInterviews ? (
                <p className={`text-xs ${t.textMuted}`}>Loading interviews...</p>
              ) : investigationInterviews.length === 0 ? (
                <p className={`text-xs ${t.textMuted}`}>No investigation interviews scheduled yet.</p>
              ) : (
                <div className="space-y-3">
                  {investigationInterviews.map((inv) => (
                    <div key={inv.id} className={`flex items-center justify-between gap-3 py-2 border-b ${t.border} last:border-0`}>
                      <div className="flex-1 min-w-0">
                        <div className={`text-xs font-medium ${t.textMain} truncate`}>{inv.interviewee_name}</div>
                        <div className={`text-[10px] ${t.textMuted} truncate`}>{inv.interviewee_email}</div>
                      </div>
                      <div className={`text-[10px] px-2 py-0.5 rounded-full border ${
                        inv.status === 'analyzed' ? 'border-blue-500/30 text-blue-400' :
                        inv.status === 'completed' ? 'border-green-500/30 text-green-400' :
                        inv.status === 'in_progress' ? 'border-yellow-500/30 text-yellow-400' :
                        inv.status === 'cancelled' ? 'border-red-500/30 text-red-400' :
                        'border-zinc-600 text-zinc-500'
                      } uppercase tracking-wider font-bold`}>
                        {inv.status}
                      </div>
                      <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">{inv.interviewee_role}</div>
                      <div className="flex gap-2 shrink-0">
                        {inv.status === 'analyzed' && (
                          <button
                            onClick={() => setShowAnalysisModal(inv)}
                            className={`text-[10px] ${t.btnGhost} uppercase tracking-wider font-bold`}
                          >
                            View Analysis
                          </button>
                        )}
                        {(inv.status === 'pending' || inv.status === 'in_progress') && (
                          <button
                            onClick={() => handleCopyLink(inv)}
                            className={`text-[10px] ${copiedLinkId === inv.id ? 'text-green-400' : t.btnGhost} uppercase tracking-wider font-bold`}
                          >
                            {copiedLinkId === inv.id ? 'Copied!' : 'Copy Link'}
                          </button>
                        )}
                        {inv.status === 'pending' && inv.invite_token && (
                          <button
                            onClick={() => handleResendInvite(inv.id)}
                            className={`text-[10px] ${t.btnGhost} uppercase tracking-wider font-bold`}
                          >
                            Resend
                          </button>
                        )}
                        {inv.status === 'pending' && (
                          <button
                            onClick={() => handleCancelInterview(inv.id)}
                            className={`text-[10px] text-red-500 hover:text-red-400 uppercase tracking-wider font-bold`}
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
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
          {/* Consistency Guidance - only for investigating/action_required */}
          {(incident.status === 'investigating' || incident.status === 'action_required') && (
            <ConsistencyGuidancePanel
              incidentId={id!}
              incidentStatus={incident.status}
              similarAnalysisVersion={similarVersion}
            />
          )}

          {/* AI Analysis */}
          <div className={`${t.card} p-6`}>
            <div className={`${t.label} mb-4`}>AI Analysis</div>
            <div className="space-y-3">
              {[
                { key: 'root_cause', label: 'Root Cause', data: rootCause, onClick: () => setShowRootCauseModal(true) },
                { key: 'recommendations', label: 'Actions', data: recommendations, onClick: () => setShowRecommendationsModal(true) },
                { key: 'similar', label: 'Precedents', data: similarIncidents, onClick: () => setShowSimilarModal(true) },
              ].map(({ key, label, data, onClick }) => (
                <div key={key} className={`py-2 border-b ${t.sectionBorder}`}>
                  <div className="flex justify-between items-center">
                    <span className={`text-xs ${t.textMuted}`}>{label}</span>
                    <button
                      onClick={() => runAnalysis(key)}
                      disabled={stream.streaming && stream.analysisType === key}
                      className={`text-[10px] ${t.btnGhost} uppercase tracking-wider font-bold disabled:opacity-50`}
                    >
                      {stream.streaming && stream.analysisType === key ? '...' : data ? 'Rerun' : 'Run'}
                    </button>
                  </div>
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
                        <span>{similarIncidents.precedents.length} precedent{similarIncidents.precedents.length !== 1 ? 's' : ''} found</span>
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

      {/* Analysis Terminal Modal */}
      <AnalysisTerminalModal
        isOpen={showTerminalModal}
        onClose={() => setShowTerminalModal(false)}
        messages={stream.messages}
        streaming={stream.streaming}
        result={stream.result}
        error={stream.error}
        analysisType={stream.analysisType}
      />

      {/* Investigation Analysis Modal */}
      {showAnalysisModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" onClick={() => setShowAnalysisModal(null)} />
          <div className={`relative ${t.modalBg} w-full max-w-2xl p-6 space-y-4 max-h-[80vh] overflow-y-auto`}>
            <div className="flex justify-between items-start">
              <h3 className={`text-sm font-medium ${t.textMain}`}>Interview Analysis — {showAnalysisModal.interviewee_name}</h3>
              <button onClick={() => setShowAnalysisModal(null)} className={`text-xs ${t.btnGhost}`}>✕</button>
            </div>
            {showAnalysisModal.investigation_analysis && (
              <div className="space-y-4 text-sm">
                {showAnalysisModal.investigation_analysis.key_facts.length > 0 && (
                  <div>
                    <div className={`${t.label} mb-2`}>Key Facts</div>
                    <ul className={`space-y-1 ${t.textSecondary}`}>
                      {showAnalysisModal.investigation_analysis.key_facts.map((f, i) => <li key={i} className="flex gap-2"><span className="shrink-0">•</span>{f}</li>)}
                    </ul>
                  </div>
                )}
                {showAnalysisModal.investigation_analysis.gaps_identified.length > 0 && (
                  <div>
                    <div className={`${t.label} mb-2`}>Gaps Identified</div>
                    <ul className={`space-y-1 ${t.textMuted}`}>
                      {showAnalysisModal.investigation_analysis.gaps_identified.map((g, i) => <li key={i} className="flex gap-2"><span className="shrink-0">•</span>{g}</li>)}
                    </ul>
                  </div>
                )}
                {showAnalysisModal.investigation_analysis.credibility_notes.length > 0 && (
                  <div>
                    <div className={`${t.label} mb-2`}>Credibility Notes</div>
                    <ul className={`space-y-1 ${t.textMuted}`}>
                      {showAnalysisModal.investigation_analysis.credibility_notes.map((n, i) => <li key={i} className="flex gap-2"><span className="shrink-0">•</span>{n}</li>)}
                    </ul>
                  </div>
                )}
                {showAnalysisModal.investigation_analysis.interview_summary && (
                  <div>
                    <div className={`${t.label} mb-2`}>Summary</div>
                    <p className={t.textMuted}>{showAnalysisModal.investigation_analysis.interview_summary}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Schedule Investigation Interviews Modal */}
      {incident && (
        <ScheduleInterviewsModal
          isOpen={showScheduleModal}
          onClose={() => setShowScheduleModal(false)}
          incidentId={id || ''}
          witnesses={incident.witnesses || []}
          onSuccess={(_count) => {
            setShowScheduleModal(false);
            fetchInvestigationInterviews();
          }}
        />
      )}

      {/* Escalate to ER Case Modal */}
      {showEscalateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" onClick={() => setShowEscalateModal(false)} />
          <div className={`relative ${t.modalBg} w-full max-w-lg p-6 space-y-4`}>
            <h3 className={`text-sm font-medium ${t.textMain}`}>Escalate to ER Case</h3>

            <div>
              <label className={`${t.label} block mb-1`}>Title</label>
              <input
                value={escalateForm.title}
                onChange={(e) => setEscalateForm(f => ({ ...f, title: e.target.value }))}
                className={t.modalInput}
              />
            </div>

            <div>
              <label className={`${t.label} block mb-1`}>Description</label>
              <textarea
                value={escalateForm.description}
                onChange={(e) => setEscalateForm(f => ({ ...f, description: e.target.value }))}
                rows={6}
                className={`${t.modalInput} resize-none`}
              />
            </div>

            <div>
              <label className={`${t.label} block mb-1`}>Category</label>
              <select
                value={escalateForm.category}
                onChange={(e) => setEscalateForm(f => ({ ...f, category: e.target.value as ERCaseCategory }))}
                className={t.modalSelect}
              >
                {ER_CATEGORY_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setShowEscalateModal(false)}
                className={`text-xs ${t.btnGhost} uppercase tracking-wider font-bold`}
              >
                Cancel
              </button>
              <button
                onClick={handleEscalate}
                disabled={escalating || !escalateForm.title.trim()}
                className={`px-3 py-1.5 ${t.btnPrimary} text-xs disabled:opacity-50 uppercase tracking-wider font-bold`}
              >
                {escalating ? 'Creating...' : 'Create ER Case'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
    </div>
  );
}

export default IRDetail;
