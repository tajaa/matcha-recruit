import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Button, FileUpload } from '../components';
import { erCopilot } from '../api/client';
import type {
  ERCase,
  ERCaseStatus,
  ERCaseNote,
  ERDocument,
  ERDocumentType,
  ERCaseIntakeContext,
  ERGuidanceCard,
  ERGuidancePriority,
  ERSuggestedGuidanceResponse,
  OutcomeAnalysisResponse,
  TimelineEvent,
  Discrepancy,
  PolicyViolation,
  EvidenceSearchResult,
} from '../types';
import {
  ChevronLeft, Upload, Trash2, Search,
  AlertTriangle, CheckCircle, Clock, X, RefreshCw, Download
} from 'lucide-react';

function normalizeDiscrepancyStatement(
  value: unknown,
  fallbackSpeaker: string
): Discrepancy['statement_1'] {
  if (!value || typeof value !== 'object') {
    return {
      source_document_id: '',
      speaker: fallbackSpeaker,
      quote: 'No quote provided.',
      location: '',
    };
  }

  const statement = value as Record<string, unknown>;
  const speaker = typeof statement.speaker === 'string' && statement.speaker.trim()
    ? statement.speaker
    : fallbackSpeaker;
  const quote = typeof statement.quote === 'string' && statement.quote.trim()
    ? statement.quote
    : 'No quote provided.';

  return {
    source_document_id: typeof statement.source_document_id === 'string' ? statement.source_document_id : '',
    speaker,
    quote,
    location: typeof statement.location === 'string' ? statement.location : '',
  };
}

function normalizeDiscrepancies(payload: unknown): Discrepancy[] {
  if (!Array.isArray(payload)) return [];

  return payload
    .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
    .map((item) => ({
      type: typeof item.type === 'string' ? item.type : 'inconsistency',
      severity:
        item.severity === 'high' || item.severity === 'medium' || item.severity === 'low'
          ? item.severity
          : 'low',
      description:
        typeof item.description === 'string' && item.description.trim()
          ? item.description
          : 'Potential inconsistency detected in witness accounts.',
      statement_1: normalizeDiscrepancyStatement(item.statement_1, 'Source 1'),
      statement_2: normalizeDiscrepancyStatement(item.statement_2, 'Source 2'),
      analysis:
        typeof item.analysis === 'string' && item.analysis.trim()
          ? item.analysis
          : 'No additional analysis provided.',
    }));
}

function normalizeTimelineEvents(payload: unknown): TimelineEvent[] {
  if (!Array.isArray(payload)) return [];

  return payload
    .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
    .map((item) => {
      const participants = Array.isArray(item.participants)
        ? item.participants.filter((participant): participant is string => typeof participant === 'string')
        : [];
      const confidence =
        item.confidence === 'high' || item.confidence === 'medium' || item.confidence === 'low'
          ? item.confidence
          : 'low';

      return {
        date: typeof item.date === 'string' ? item.date : '',
        time: typeof item.time === 'string' ? item.time : null,
        description: typeof item.description === 'string' ? item.description : '',
        participants,
        source_document_id: typeof item.source_document_id === 'string' ? item.source_document_id : '',
        source_location: typeof item.source_location === 'string' ? item.source_location : '',
        confidence,
        evidence_quote: typeof item.evidence_quote === 'string' ? item.evidence_quote : '',
      };
    });
}

function normalizePolicyViolations(payload: unknown): PolicyViolation[] {
  if (!Array.isArray(payload)) return [];

  return payload
    .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
    .map((item) => {
      const evidence = Array.isArray(item.evidence)
        ? item.evidence
            .filter((entry): entry is Record<string, unknown> => !!entry && typeof entry === 'object')
            .map((entry) => ({
              source_document_id:
                typeof entry.source_document_id === 'string' ? entry.source_document_id : '',
              quote: typeof entry.quote === 'string' ? entry.quote : '',
              location: typeof entry.location === 'string' ? entry.location : '',
              how_it_violates: typeof entry.how_it_violates === 'string' ? entry.how_it_violates : '',
            }))
        : [];

      return {
        policy_section: typeof item.policy_section === 'string' ? item.policy_section : '',
        policy_text: typeof item.policy_text === 'string' ? item.policy_text : '',
        severity: item.severity === 'major' || item.severity === 'minor' ? item.severity : 'minor',
        evidence,
        analysis: typeof item.analysis === 'string' ? item.analysis : '',
      };
    });
}

function normalizeTimelineGaps(payload: unknown): string[] {
  if (!Array.isArray(payload)) return [];
  return payload.filter((gap): gap is string => typeof gap === 'string');
}

function normalizeIntakeContext(payload: unknown): ERCaseIntakeContext | null {
  if (!payload) return null;
  if (typeof payload === 'string') {
    try {
      const parsed = JSON.parse(payload);
      if (parsed && typeof parsed === 'object') {
        return parsed as ERCaseIntakeContext;
      }
    } catch {
      return null;
    }
    return null;
  }
  if (typeof payload === 'object') {
    return payload as ERCaseIntakeContext;
  }
  return null;
}

function formatIntakeObjective(value?: string): string {
  if (value === 'timeline') return 'Timeline reconstruction';
  if (value === 'discrepancies') return 'Discrepancy detection';
  if (value === 'policy') return 'Policy risk review';
  return 'General guidance';
}

function formatCaseNoteType(value: ERCaseNote['note_type']): string {
  if (value === 'question') return 'Question';
  if (value === 'answer') return 'Answer';
  if (value === 'guidance') return 'Guidance';
  if (value === 'system') return 'System';
  return 'General';
}

function normalizeGuidancePriority(value: unknown): ERGuidancePriority {
  if (value === 'high' || value === 'medium' || value === 'low') return value;
  return 'medium';
}

function normalizeGuidanceAction(value: unknown): ERGuidanceCard['action'] {
  if (!value || typeof value !== 'object') {
    return {
      type: 'open_tab',
      label: 'Open Timeline',
      tab: 'timeline',
      analysis_type: null,
      search_query: null,
    };
  }

  const action = value as Record<string, unknown>;
  const type = action.type;
  const tab = action.tab;
  const analysisType = action.analysis_type;
  const searchQuery = action.search_query;

  return {
    type:
      type === 'run_analysis' || type === 'open_tab' || type === 'search_evidence' || type === 'upload_document'
        ? type
        : 'open_tab',
    label: typeof action.label === 'string' && action.label.trim() ? action.label : 'Open Guidance',
    tab: tab === 'timeline' || tab === 'discrepancies' || tab === 'policy' || tab === 'search' ? tab : null,
    analysis_type: analysisType === 'timeline' || analysisType === 'discrepancies' || analysisType === 'policy'
      ? analysisType
      : null,
    search_query: typeof searchQuery === 'string' && searchQuery.trim() ? searchQuery : null,
  };
}

function normalizeGuidanceCards(value: unknown): ERGuidanceCard[] {
  if (!Array.isArray(value)) return [];

  return value
    .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
    .map((item, idx) => {
      const title = typeof item.title === 'string' && item.title.trim()
        ? item.title.trim()
        : `Suggested Action ${idx + 1}`;

      const recommendation = typeof item.recommendation === 'string' && item.recommendation.trim()
        ? item.recommendation.trim()
        : 'Review available evidence and proceed with the next analysis step.';

      const rationale = typeof item.rationale === 'string' && item.rationale.trim()
        ? item.rationale.trim()
        : 'This action helps improve investigation confidence.';

      const blockers = Array.isArray(item.blockers)
        ? item.blockers
            .filter((blocker): blocker is string => typeof blocker === 'string' && blocker.trim().length > 0)
            .map((blocker) => blocker.trim())
        : [];

      return {
        id: typeof item.id === 'string' && item.id.trim() ? item.id.trim() : `guidance-${idx + 1}`,
        title,
        recommendation,
        rationale,
        priority: normalizeGuidancePriority(item.priority),
        blockers,
        action: normalizeGuidanceAction(item.action),
      };
    });
}

function getSuggestedGuidancePayload(note: ERCaseNote | null): ERSuggestedGuidanceResponse | null {
  if (!note?.metadata || typeof note.metadata !== 'object') return null;
  const metadata = note.metadata as Record<string, unknown>;
  const payload = metadata.guidance_payload;
  if (!payload || typeof payload !== 'object') return null;

  const raw = payload as Record<string, unknown>;
  return {
    summary:
      typeof raw.summary === 'string' && raw.summary.trim()
        ? raw.summary.trim()
        : 'Suggested guidance is available.',
    cards: normalizeGuidanceCards(raw.cards),
    generated_at:
      typeof raw.generated_at === 'string' && raw.generated_at.trim()
        ? raw.generated_at
        : note.created_at,
    model:
      typeof raw.model === 'string' && raw.model.trim()
        ? raw.model
        : 'unknown',
    fallback_used: raw.fallback_used === true,
    determination_suggested: raw.determination_suggested === true,
    determination_confidence: typeof raw.determination_confidence === 'number' ? raw.determination_confidence : undefined,
    determination_signals: Array.isArray(raw.determination_signals) ? (raw.determination_signals as string[]) : undefined,
  };
}

function buildSuggestedGuidanceNoteContent(payload: ERSuggestedGuidanceResponse): string {
  const lines = [payload.summary];
  payload.cards.forEach((card, idx) => {
    lines.push(`${idx + 1}. ${card.title}: ${card.recommendation}`);
  });
  return lines.join('\n');
}

function guidancePriorityStyle(priority: ERGuidancePriority): string {
  if (priority === 'high') return 'text-red-700 bg-red-100';
  if (priority === 'low') return 'text-zinc-600 bg-zinc-100';
  return 'text-amber-700 bg-amber-100';
}

function getCaseNotePurpose(note: ERCaseNote): string | null {
  const metadata = note.metadata;
  if (!metadata || typeof metadata !== 'object') return null;
  const purpose = metadata.note_purpose;
  return typeof purpose === 'string' ? purpose : null;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

function buildNotificationsWsUrl(apiBase: string): string {
  if (typeof window === 'undefined') {
    return 'ws://localhost/ws/notifications';
  }

  if (/^https?:\/\//i.test(apiBase)) {
    const base = new URL(apiBase);
    const protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${base.host}/ws/notifications`;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/notifications`;
}

const STATUS_COLORS: Record<ERCaseStatus, string> = {
  open: 'text-zinc-900',
  in_review: 'text-amber-600',
  pending_determination: 'text-orange-600',
  closed: 'text-zinc-400',
};

const STATUS_OPTIONS: { value: ERCaseStatus; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'in_review', label: 'In Review' },
  { value: 'pending_determination', label: 'Pending Determination' },
  { value: 'closed', label: 'Closed' },
];

const DOC_TYPE_OPTIONS: { value: ERDocumentType; label: string }[] = [
  { value: 'transcript', label: 'Interview Transcript' },
  { value: 'policy', label: 'Policy Document' },
  { value: 'email', label: 'Email/Communication' },
  { value: 'other', label: 'Other Evidence' },
];

const DOC_TYPE_COLORS: Record<ERDocumentType, string> = {
  transcript: 'text-blue-600',
  policy: 'text-purple-600',
  email: 'text-amber-600',
  other: 'text-zinc-500',
};

type AnalysisTab = 'timeline' | 'discrepancies' | 'policy' | 'search';
type GuidanceCardState = 'pending' | 'done' | 'dismissed';

export function ERCaseDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  // State
  const [erCase, setCase] = useState<ERCase | null>(null);
  const [documents, setDocuments] = useState<ERDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<AnalysisTab>('timeline');
  const [statusUpdating, setStatusUpdating] = useState(false);

  // Upload state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadDocType, setUploadDocType] = useState<ERDocumentType>('transcript');
  const [uploading, setUploading] = useState(false);

  // Analysis state
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [timelineSummary, setTimelineSummary] = useState<string>('');
  const [timelineGaps, setTimelineGaps] = useState<string[]>([]);
  const [discrepancies, setDiscrepancies] = useState<Discrepancy[]>([]);
  const [discrepancySummary, setDiscrepancySummary] = useState<string>('');
  const [violations, setViolations] = useState<PolicyViolation[]>([]);
  const [policiesChecked, setPoliciesChecked] = useState<number>(0);
  const [analysisLoading, setAnalysisLoading] = useState<string | null>(null);
  const [analysisProgress, setAnalysisProgress] = useState<{ step: string; detail?: string } | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [autoAssistStatus, setAutoAssistStatus] = useState<'idle' | 'running' | 'completed' | 'needs_docs'>('idle');
  const [autoAssistMessage, setAutoAssistMessage] = useState<string | null>(null);
  const [notes, setNotes] = useState<ERCaseNote[]>([]);
  const [autoReviewRunning, setAutoReviewRunning] = useState(false);
  const autoReviewSignatureRef = useRef<string | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<EvidenceSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [guidanceActionBusyId, setGuidanceActionBusyId] = useState<string | null>(null);
  const [determinationDismissed, setDeterminationDismissed] = useState(false);
  const [determinationAccepting, setDeterminationAccepting] = useState(false);

  // Outcome analysis state (determination panel)
  const [outcomeAnalysis, setOutcomeAnalysis] = useState<OutcomeAnalysisResponse | null>(null);
  const [outcomeLoading, setOutcomeLoading] = useState(false);
  const [outcomeStatusMsg, setOutcomeStatusMsg] = useState<string | null>(null);
  const [outcomeError, setOutcomeError] = useState<string | null>(null);
  const [selectedOutcomeIdx, setSelectedOutcomeIdx] = useState<number | null>(null);
  const [determinationNotes, setDeterminationNotes] = useState('');
  const [closingCase, setClosingCase] = useState(false);
  const outcomeLoadingRef = useRef(false);

  // Standalone add-note state
  const [newNoteContent, setNewNoteContent] = useState('');
  const [addingNote, setAddingNote] = useState(false);

  // Export state
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportPassword, setExportPassword] = useState('');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const handleExport = useCallback(async () => {
    if (!id || exportPassword.length < 4) return;
    setExporting(true);
    setExportError(null);
    try {
      const blob = await erCopilot.exportCase(id, exportPassword);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ER-Case-${erCase?.case_number || id}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setShowExportModal(false);
      setExportPassword('');
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setExporting(false);
    }
  }, [id, exportPassword, erCase?.case_number]);

  const fetchCase = useCallback(async () => {
    if (!id) return;
    try {
      const data = await erCopilot.getCase(id);
      setCase(data);
    } catch (err) {
      console.error('Failed to fetch case:', err);
    }
  }, [id]);

  const fetchDocuments = useCallback(async () => {
    if (!id) return;
    try {
      const docs = await erCopilot.listDocuments(id);
      setDocuments(docs);
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    }
  }, [id]);

  const fetchNotes = useCallback(async () => {
    if (!id) return;
    try {
      const entries = await erCopilot.listCaseNotes(id);
      setNotes(entries);
    } catch (err) {
      console.error('Failed to fetch case notes:', err);
    }
  }, [id]);

  const fetchAnalysis = useCallback(async (type: AnalysisTab) => {
    if (!id) return;
    try {
      if (type === 'timeline') {
        const data = await erCopilot.getTimeline(id);
        if (!data.generated_at) {
          setTimeline([]);
          setTimelineSummary('');
          setTimelineGaps([]);
          return;
        }
        setTimeline(normalizeTimelineEvents(data.analysis.events));
        setTimelineSummary(data.analysis.timeline_summary || '');
        setTimelineGaps(normalizeTimelineGaps(data.analysis.gaps_identified));
      } else if (type === 'discrepancies') {
        const data = await erCopilot.getDiscrepancies(id);
        if (!data.generated_at) {
          setDiscrepancies([]);
          setDiscrepancySummary('');
          return;
        }
        setDiscrepancies(normalizeDiscrepancies(data.analysis.discrepancies));
        setDiscrepancySummary(data.analysis.summary || '');
      } else if (type === 'policy') {
        const data = await erCopilot.getPolicyCheck(id);
        if (!data.generated_at) {
          setViolations([]);
          setPoliciesChecked(0);
          return;
        }
        setViolations(normalizePolicyViolations(data.analysis.violations));
        setPoliciesChecked(data.analysis.policies_potentially_applicable?.length || 0);
      }
    } catch {
      // Analysis not yet generated - that's okay
    }
  }, [id]);

  const fetchOutcomeAnalysis = useCallback(async () => {
    if (!id || outcomeLoadingRef.current) return;
    outcomeLoadingRef.current = true;
    setOutcomeLoading(true);
    setOutcomeStatusMsg(null);
    setOutcomeError(null);
    try {
      const result = await erCopilot.generateOutcomeAnalysisStream(id, (msg) => {
        setOutcomeStatusMsg(msg);
      });
      setOutcomeAnalysis(result);
      setOutcomeStatusMsg(null);
    } catch (err) {
      console.error('Failed to generate outcome analysis:', err);
      setOutcomeError(getErrorMessage(err, 'Failed to generate outcome analysis. Click below to retry.'));
      setOutcomeStatusMsg(null);
    } finally {
      outcomeLoadingRef.current = false;
      setOutcomeLoading(false);
    }
  }, [id]);

  const handleCloseCase = useCallback(async () => {
    if (!id || selectedOutcomeIdx === null || !outcomeAnalysis || !determinationNotes.trim()) return;
    const selected = outcomeAnalysis.outcomes[selectedOutcomeIdx];
    if (!selected) return;

    setClosingCase(true);
    try {
      // 1. Create case note with determination notes + selected outcome reasoning
      await erCopilot.createCaseNote(id, {
        note_type: 'system',
        content: `Determination: ${selected.determination}\nOutcome: ${selected.action_label}\n\nInvestigator Notes:\n${determinationNotes.trim()}\n\nAI Reasoning:\n${selected.reasoning}`,
        metadata: {
          note_purpose: 'determination',
          determination: selected.determination,
          outcome: selected.recommended_action,
          action_label: selected.action_label,
        },
      });

      // 2. Generate determination letter
      await erCopilot.generateDetermination(id, selected.determination);

      // 3. Close case with outcome
      const updated = await erCopilot.updateCase(id, {
        status: 'closed',
        outcome: selected.recommended_action,
      });
      setCase(updated);

      // 4. Refresh notes
      await fetchNotes();

      // Reset state
      setSelectedOutcomeIdx(null);
      setDeterminationNotes('');
      setOutcomeAnalysis(null);
    } catch (err) {
      console.error('Failed to close case:', err);
    } finally {
      setClosingCase(false);
    }
  }, [id, selectedOutcomeIdx, outcomeAnalysis, determinationNotes, fetchNotes]);

  const handleAddNote = useCallback(async () => {
    if (!id || !newNoteContent.trim()) return;
    setAddingNote(true);
    try {
      await erCopilot.createCaseNote(id, {
        note_type: 'general',
        content: newNoteContent.trim(),
      });
      setNewNoteContent('');
      await fetchNotes();
    } catch (err) {
      console.error('Failed to add note:', err);
    } finally {
      setAddingNote(false);
    }
  }, [id, newNoteContent, fetchNotes]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([fetchCase(), fetchDocuments(), fetchNotes()]);
      setLoading(false);
    };
    load();
  }, [fetchCase, fetchDocuments, fetchNotes]);

  useEffect(() => {
    fetchAnalysis(activeTab);
  }, [activeTab, fetchAnalysis]);

  // Auto-load outcome analysis when visiting a pending_determination case
  useEffect(() => {
    if (!loading && erCase?.status === 'pending_determination' && !outcomeAnalysis && !outcomeLoadingRef.current) {
      fetchOutcomeAnalysis();
    }
  }, [loading, erCase?.status, outcomeAnalysis, fetchOutcomeAnalysis]);

  useEffect(() => {
    autoReviewSignatureRef.current = null;
    setAutoAssistStatus('idle');
    setAutoAssistMessage(null);
    setNotes([]);
  }, [id]);

  // WebSocket subscription for real-time analysis updates
  useEffect(() => {
    if (!id) return;

    const apiBase = import.meta.env.VITE_API_URL || '/api';
    const wsUrl = buildNotificationsWsUrl(apiBase);
    console.log('[ERCaseDetail] Connecting to WebSocket:', wsUrl);
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
    } catch (err) {
      console.error('[ERCaseDetail] Failed to initialize WebSocket:', err);
      return;
    }

    ws.onopen = () => {
      console.log('[ERCaseDetail] WebSocket connected, subscribing to channel:', `er_case:${id}`);
      ws.send(JSON.stringify({ action: 'subscribe', channel: `er_case:${id}` }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[ERCaseDetail] WebSocket message received:', data);

        if (data.type === 'task_progress') {
          setAnalysisProgress({
            step: data.message || 'Processing...',
            detail: data.total > 0 ? `Step ${data.progress}/${data.total}` : undefined,
          });
        } else if (data.type === 'task_complete') {
          // Map task_type to tab and fetch new data
          const taskTypeToTab: Record<string, AnalysisTab> = {
            timeline_analysis: 'timeline',
            discrepancy_analysis: 'discrepancies',
            policy_check: 'policy',
          };
          const tab = taskTypeToTab[data.task_type];
          if (tab) {
            fetchAnalysis(tab);
          }
          setAnalysisLoading(null);
          setAnalysisProgress(null);
        } else if (data.type === 'task_error') {
          console.error('[ERCaseDetail] Analysis failed:', data.error);
          setAnalysisError(data.error || 'Analysis failed. Please try again.');
          setAnalysisLoading(null);
          setAnalysisProgress(null);
        }
      } catch (err) {
        console.error('[ERCaseDetail] Failed to parse WebSocket message:', err);
      }
    };

    ws.onerror = (err) => {
      console.error('[ERCaseDetail] WebSocket error:', err);
    };

    ws.onclose = (event) => {
      console.log('[ERCaseDetail] WebSocket closed:', event.code, event.reason);
    };

    return () => {
      console.log('[ERCaseDetail] Cleaning up WebSocket');
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'unsubscribe', channel: `er_case:${id}` }));
      }
      ws.close();
    };
  }, [id, fetchAnalysis]);

  const handleUpload = async (files: File[]) => {
    if (!id || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of files) {
        await erCopilot.uploadDocument(id, file, uploadDocType);
      }
      setShowUploadModal(false);
      fetchDocuments();
    } catch (err) {
      console.error('Failed to upload:', err);
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteDoc = async (docId: string) => {
    if (!id) return;
    if (!confirm('Delete this document?')) return;
    try {
      await erCopilot.deleteDocument(id, docId);
      fetchDocuments();
    } catch (err) {
      console.error('Failed to delete document:', err);
    }
  };

  const handleReprocessDoc = async (docId: string) => {
    if (!id) return;
    try {
      await erCopilot.reprocessDocument(id, docId);
      // Refresh documents to show updated status
      fetchDocuments();
      // Poll for completion
      const pollInterval = setInterval(async () => {
        const docs = await erCopilot.listDocuments(id);
        const doc = docs.find(d => d.id === docId);
        if (doc && (doc.processing_status === 'completed' || doc.processing_status === 'failed')) {
          clearInterval(pollInterval);
          setDocuments(docs);
        }
      }, 2000);
      // Clear interval after 60 seconds max
      setTimeout(() => clearInterval(pollInterval), 60000);
    } catch (err) {
      console.error('Failed to reprocess document:', err);
    }
  };

  const [reprocessingAll, setReprocessingAll] = useState(false);

  const handleReprocessAllDocs = async () => {
    if (!id) return;
    setReprocessingAll(true);
    try {
      const result = await erCopilot.reprocessAllDocuments(id);
      console.log('Reprocess all result:', result);
      // Refresh documents to show updated status
      fetchDocuments();
    } catch (err) {
      console.error('Failed to reprocess all documents:', err);
    } finally {
      setReprocessingAll(false);
    }
  };

  const hasUnprocessedDocs = documents.some(d => d.processing_status === 'pending' || d.processing_status === 'failed');

  useEffect(() => {
    if (!id) return;
    const hasProcessingDocs = documents.some(
      (d) => d.processing_status === 'pending' || d.processing_status === 'processing'
    );
    if (!hasProcessingDocs) return;

    const interval = setInterval(() => {
      void fetchDocuments();
    }, 4000);

    return () => clearInterval(interval);
  }, [id, documents, fetchDocuments]);

  const pollForAnalysis = useCallback(async (type: AnalysisTab, maxAttempts = 60) => {
    // Poll every 2 seconds for up to 2 minutes.
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      try {
        if (type === 'timeline') {
          const data = await erCopilot.getTimeline(id!);
          if (!data.generated_at) {
            continue;
          }
          setTimeline(normalizeTimelineEvents(data.analysis.events));
          setTimelineSummary(data.analysis.timeline_summary || '');
          setTimelineGaps(normalizeTimelineGaps(data.analysis.gaps_identified));
          return true;
        } else if (type === 'discrepancies') {
          const data = await erCopilot.getDiscrepancies(id!);
          if (!data.generated_at) {
            continue;
          }
          setDiscrepancies(normalizeDiscrepancies(data.analysis.discrepancies));
          setDiscrepancySummary(data.analysis.summary || '');
          return true;
        } else if (type === 'policy') {
          const data = await erCopilot.getPolicyCheck(id!);
          if (!data.generated_at) {
            continue;
          }
          setViolations(normalizePolicyViolations(data.analysis.violations));
          setPoliciesChecked(data.analysis.policies_potentially_applicable?.length || 0);
          return true;
        }
      } catch {
        // Not ready yet, continue polling
      }
    }
    return false;
  }, [id]);

  const handleGenerateTimeline = useCallback(async (): Promise<boolean> => {
    if (!id) return false;
    setAnalysisLoading('timeline');
    setAnalysisProgress({ step: 'Starting analysis...' });
    setAnalysisError(null);
    try {
      await erCopilot.generateTimeline(id);
      // WebSocket will notify us when complete; fallback to polling if WS fails
      const success = await pollForAnalysis('timeline');
      if (!success) {
        console.error('Timeline analysis timed out');
        setAnalysisError('Timeline analysis timed out. Please try again.');
        setAnalysisLoading(null);
        setAnalysisProgress(null);
        return false;
      }
      return true;
    } catch (err: unknown) {
      console.error('Failed to generate timeline:', err);
      setAnalysisError(getErrorMessage(err, 'Failed to generate timeline. Please try again.'));
      setAnalysisLoading(null);
      setAnalysisProgress(null);
      return false;
    }
  }, [id, pollForAnalysis]);

  const handleGenerateDiscrepancies = useCallback(async (): Promise<boolean> => {
    if (!id) return false;
    setAnalysisLoading('discrepancies');
    setAnalysisProgress({ step: 'Starting analysis...' });
    setAnalysisError(null);
    try {
      await erCopilot.generateDiscrepancies(id);
      // WebSocket will notify us when complete; fallback to polling if WS fails
      const success = await pollForAnalysis('discrepancies');
      if (!success) {
        console.error('Discrepancy analysis timed out');
        setAnalysisError('Discrepancy analysis timed out. Please try again.');
        setAnalysisLoading(null);
        setAnalysisProgress(null);
        return false;
      }
      return true;
    } catch (err: unknown) {
      console.error('Failed to generate discrepancies:', err);
      setAnalysisError(getErrorMessage(err, 'Failed to analyze discrepancies. Please try again.'));
      setAnalysisLoading(null);
      setAnalysisProgress(null);
      return false;
    }
  }, [id, pollForAnalysis]);

  const handleRunPolicyCheck = useCallback(async (): Promise<boolean> => {
    if (!id) return false;
    setAnalysisLoading('policy');
    setAnalysisProgress({ step: 'Starting analysis...' });
    setAnalysisError(null);
    try {
      await erCopilot.runPolicyCheck(id);
      // WebSocket will notify us when complete; fallback to polling if WS fails
      const success = await pollForAnalysis('policy');
      if (!success) {
        console.error('Policy check timed out');
        setAnalysisError('Policy check timed out. Please try again.');
        setAnalysisLoading(null);
        setAnalysisProgress(null);
        return false;
      }
      return true;
    } catch (err: unknown) {
      console.error('Failed to run policy check:', err);
      setAnalysisError(getErrorMessage(err, 'Failed to run policy check. Please try again.'));
      setAnalysisLoading(null);
      setAnalysisProgress(null);
      return false;
    }
  }, [id, pollForAnalysis]);

  const runEvidenceSearch = useCallback(async (query: string): Promise<boolean> => {
    if (!id || !query.trim()) return false;
    setSearching(true);
    setAnalysisError(null);
    try {
      const data = await erCopilot.searchEvidence(id, query.trim());
      setSearchResults(data.results);
      return true;
    } catch (err: unknown) {
      console.error('Search failed:', err);
      setAnalysisError(getErrorMessage(err, 'Search failed. Please try again.'));
      setSearchResults([]);
      return false;
    } finally {
      setSearching(false);
    }
  }, [id]);

  const handleSearch = useCallback(async () => {
    await runEvidenceSearch(searchQuery);
  }, [runEvidenceSearch, searchQuery]);

  const handleStatusChange = async (newStatus: ERCaseStatus) => {
    if (!id || !erCase) return;

    setStatusUpdating(true);
    try {
      await erCopilot.updateCase(id, { status: newStatus });
      await fetchCase();
    } catch (err) {
      console.error('Failed to update status:', err);
      await fetchCase();
    } finally {
      setStatusUpdating(false);
    }
  };

  const updateGuidanceCardState = useCallback(async (cardId: string, status: GuidanceCardState) => {
    if (!id || !erCase) return;

    const intakeContext = normalizeIntakeContext(erCase.intake_context) || {};
    const existingAssistance = intakeContext.assistance || {};
    const guidanceState = existingAssistance.guidance_state || {};
    const now = new Date().toISOString();

    const nextIntakeContext: ERCaseIntakeContext = {
      ...intakeContext,
      assistance: {
        ...existingAssistance,
        guidance_state: {
          ...guidanceState,
          [cardId]: { status, updated_at: now },
        },
      },
    };

    try {
      const updatedCase = await erCopilot.updateCase(id, { intake_context: nextIntakeContext });
      setCase(updatedCase);
    } catch (err) {
      console.error('Failed to update guidance state:', err);
    }
  }, [id, erCase]);

  const handleGuidanceAction = useCallback(async (card: ERGuidanceCard) => {
    if (!id) return;
    const action = card.action;
    setGuidanceActionBusyId(card.id);
    setAnalysisError(null);

    try {
      if (action.type === 'upload_document') {
        setShowUploadModal(true);
        return;
      }

      if (action.type === 'search_evidence') {
        const query = action.search_query || card.title;
        setActiveTab('search');
        setSearchQuery(query);
        await runEvidenceSearch(query);
        return;
      }

      if (action.type === 'run_analysis') {
        const analysisType = action.analysis_type
          || (action.tab === 'timeline' || action.tab === 'discrepancies' || action.tab === 'policy'
            ? action.tab
            : 'timeline');
        setActiveTab(analysisType);
        if (analysisType === 'timeline') {
          await handleGenerateTimeline();
        } else if (analysisType === 'discrepancies') {
          await handleGenerateDiscrepancies();
        } else {
          await handleRunPolicyCheck();
        }
        return;
      }

      if (action.type === 'open_tab' && action.tab) {
        setActiveTab(action.tab);
        return;
      }

      setActiveTab('timeline');
    } finally {
      setGuidanceActionBusyId(null);
    }
  }, [id, runEvidenceSearch, handleGenerateTimeline, handleGenerateDiscrepancies, handleRunPolicyCheck]);

  const runAssistanceReview = useCallback(async (
    intakeContext: ERCaseIntakeContext | null,
    completedNonPolicyDocs: ERDocument[]
  ) => {
    if (!id) return;

    setAutoReviewRunning(true);
    setAutoAssistStatus('running');
    setAutoAssistMessage('Reviewing uploaded evidence and updating guidance...');
    setActiveTab('timeline');

    const reviewedDocIds = completedNonPolicyDocs.map((doc) => doc.id).sort();
    const reviewedSignature = reviewedDocIds.join(',');
    const shouldRunDiscrepancies = completedNonPolicyDocs.length >= 2;

    try {
      setAutoAssistMessage('Reconstructing event timeline...');
      const timelineOk = await handleGenerateTimeline();

      if (shouldRunDiscrepancies) {
        setAutoAssistMessage('Analyzing witness statement discrepancies...');
      }
      const discrepanciesOk = shouldRunDiscrepancies ? await handleGenerateDiscrepancies() : false;

      setAutoAssistMessage('Checking evidence against company policies...');
      const policyOk = await handleRunPolicyCheck();

      setAutoAssistMessage('Collecting analysis results...');
      const timelineResult = timelineOk ? await erCopilot.getTimeline(id).catch(() => null) : null;
      const discrepancyResult = shouldRunDiscrepancies && discrepanciesOk
        ? await erCopilot.getDiscrepancies(id).catch(() => null)
        : null;
      const policyResult = policyOk ? await erCopilot.getPolicyCheck(id).catch(() => null) : null;

      const discrepancyCount = discrepancyResult?.analysis?.discrepancies?.length ?? 0;
      const normalizedViolations = normalizePolicyViolations(policyResult?.analysis?.violations);
      const violationCount = normalizedViolations.length;
      const reviewSucceeded = timelineOk && policyOk && (!shouldRunDiscrepancies || discrepanciesOk);

      const reviewSummaryLines = [
        `Auto-review processed ${completedNonPolicyDocs.length} completed evidence document(s).`,
      ];

      if (timelineResult?.analysis?.timeline_summary) {
        reviewSummaryLines.push(`Timeline summary: ${timelineResult.analysis.timeline_summary}`);
      }

      if (shouldRunDiscrepancies) {
        reviewSummaryLines.push(
          discrepancyCount > 0
            ? `Discrepancy analysis found ${discrepancyCount} potential inconsistency${discrepancyCount === 1 ? '' : 'ies'}.`
            : 'Discrepancy analysis did not find major inconsistencies in current evidence.'
        );
      } else {
        reviewSummaryLines.push('Upload at least one more witness/evidence document to enable discrepancy analysis.');
      }

      if (policyResult?.analysis?.summary) {
        reviewSummaryLines.push(`Policy review: ${policyResult.analysis.summary}`);
      }

      let suggestedGuidancePayload: ERSuggestedGuidanceResponse | null = null;
      try {
        suggestedGuidancePayload = await erCopilot.generateSuggestedGuidanceStream(
          id,
          (statusMsg) => setAutoAssistMessage(statusMsg),
        );
      } catch (guidanceErr) {
        console.error('Failed to generate streaming suggested guidance:', guidanceErr);
        // Fall back to non-streaming endpoint
        try {
          suggestedGuidancePayload = await erCopilot.generateSuggestedGuidance(id);
        } catch (fallbackErr) {
          console.error('Non-streaming guidance also failed:', fallbackErr);
        }
      }

      if (!suggestedGuidancePayload) {
        suggestedGuidancePayload = {
          summary: reviewSummaryLines.join(' '),
          cards: [],
          generated_at: new Date().toISOString(),
          model: 'client-fallback',
          fallback_used: true,
          determination_suggested: false,
        };
      }
      const guidanceNoteContent = buildSuggestedGuidanceNoteContent(suggestedGuidancePayload);

      await erCopilot.createCaseNote(id, {
        note_type: 'general',
        content: reviewSummaryLines.join('\n'),
        metadata: {
          source: 'assistance_auto_review',
          note_purpose: 'review_summary',
          reviewed_doc_ids: reviewedDocIds,
          timeline_ok: timelineOk,
          discrepancies_ok: shouldRunDiscrepancies ? discrepanciesOk : null,
          policy_ok: policyOk,
          violation_count: violationCount,
          discrepancy_count: discrepancyCount,
        },
      });

      await erCopilot.createCaseNote(id, {
        note_type: 'guidance',
        content: guidanceNoteContent,
        metadata: {
          source: 'assistance_auto_review',
          note_purpose: 'next_steps',
          guidance_version: 3,
          guidance_payload: suggestedGuidancePayload,
          guidance_model: suggestedGuidancePayload.model,
          guidance_fallback_used: suggestedGuidancePayload.fallback_used,
          reviewed_doc_ids: reviewedDocIds,
          timeline_ok: timelineOk,
          discrepancies_ok: shouldRunDiscrepancies ? discrepanciesOk : null,
          policy_ok: policyOk,
          violation_count: violationCount,
          discrepancy_count: discrepancyCount,
        },
      });

      const existingGuidanceState = intakeContext?.assistance?.guidance_state || {};
      const nextGuidanceState = { ...existingGuidanceState };
      const guidanceTimestamp = new Date().toISOString();
      for (const card of suggestedGuidancePayload.cards) {
        nextGuidanceState[card.id] = { status: 'pending', updated_at: guidanceTimestamp };
      }

      const nextIntakeContext: ERCaseIntakeContext = {
        ...(intakeContext || {}),
        assistance_requested: true,
        assistance: {
          ...(intakeContext?.assistance || {}),
          mode: 'auto',
          last_reviewed_signature: reviewedSignature,
          last_reviewed_doc_ids: reviewedDocIds,
          last_reviewed_at: new Date().toISOString(),
          last_run_status: reviewSucceeded ? 'completed' : 'partial',
          guidance_state: nextGuidanceState,
          determination_dismissed: false,
        },
      };
      setDeterminationDismissed(false);

      const updatedCase = await erCopilot.updateCase(id, { intake_context: nextIntakeContext });
      setCase(updatedCase);
      await fetchNotes();

      setAutoAssistStatus('completed');
      setAutoAssistMessage(
        reviewSucceeded
          ? 'Assistance review completed and guidance notes were updated.'
          : 'Assistance review partially completed. Check notes and retry any failed analysis.'
      );
    } catch (err) {
      console.error('Auto assistance review failed:', err);
      setAutoAssistStatus('needs_docs');
      setAutoAssistMessage('Auto assistance review failed. You can retry from the analysis tabs.');
    } finally {
      setAutoReviewRunning(false);
    }
  }, [id, handleGenerateTimeline, handleGenerateDiscrepancies, handleRunPolicyCheck, fetchNotes]);

  // Sync determination dismissed state from persisted intake context
  useEffect(() => {
    if (!erCase) return;
    const ctx = normalizeIntakeContext(erCase.intake_context);
    if (ctx?.assistance?.determination_dismissed) {
      setDeterminationDismissed(true);
    }
  }, [erCase?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!id || loading || !erCase) return;

    const params = new URLSearchParams(location.search);
    const assistanceParam = params.get('assistance') === 'auto';
    if (assistanceParam) {
      navigate(location.pathname, { replace: true });
    }

    const intakeContext = normalizeIntakeContext(erCase.intake_context);
    const assistanceEnabled = Boolean(intakeContext?.assistance_requested);
    if (!assistanceEnabled) return;

    const completedNonPolicyDocs = documents.filter(
      (doc) => doc.processing_status === 'completed' && doc.document_type !== 'policy'
    );
    const currentSignature = completedNonPolicyDocs
      .map((doc) => doc.id)
      .sort()
      .join(',');
    const lastReviewedSignature = intakeContext?.assistance?.last_reviewed_signature || '';
    const hasNextStepsGuidance = notes.some(
      (note) => note.note_type === 'guidance' && getCaseNotePurpose(note) === 'next_steps'
    );

    if (!currentSignature) {
      setAutoAssistStatus('needs_docs');
      setAutoAssistMessage('Assistance enabled. Upload and process evidence documents to receive updated guidance.');
      return;
    }

    if (currentSignature === lastReviewedSignature && hasNextStepsGuidance) {
      if (assistanceParam) {
        setAutoAssistStatus('completed');
        setAutoAssistMessage('Assistance guidance is already up to date for current uploads.');
      }
      return;
    }

    if (autoReviewRunning) return;
    if (hasNextStepsGuidance && autoReviewSignatureRef.current === currentSignature) return;

    autoReviewSignatureRef.current = currentSignature;
    void runAssistanceReview(intakeContext, completedNonPolicyDocs);
  }, [
    id,
    loading,
    erCase,
    documents,
    notes,
    autoReviewRunning,
    location.search,
    location.pathname,
    navigate,
    runAssistanceReview,
  ]);

  if (loading) {
    return <div className="text-center py-12 text-zinc-500 text-xs uppercase tracking-wider">Loading...</div>;
  }

  if (!erCase) {
    return <div className="text-center py-12 text-zinc-500 text-xs uppercase tracking-wider">Case not found</div>;
  }

  const completedDocs = documents.filter(d => d.processing_status === 'completed');
  const completedNonPolicyDocs = documents.filter(
    d => d.processing_status === 'completed' && d.document_type !== 'policy'
  );
  const intakeContext = normalizeIntakeContext(erCase.intake_context);
  const assistanceAnswers = intakeContext?.answers;
  const showAssistancePanel = Boolean(intakeContext?.assistance_requested) || autoAssistStatus !== 'idle';
  const latestGuidanceNote = [...notes].reverse().find(
    (note) => note.note_type === 'guidance' && getCaseNotePurpose(note) === 'next_steps'
  ) || null;
  const latestGuidancePayload = getSuggestedGuidancePayload(latestGuidanceNote);
  const showDeterminationBanner =
    latestGuidancePayload?.determination_suggested === true
    && erCase.status !== 'pending_determination'
    && erCase.status !== 'closed'
    && !determinationDismissed;
  const guidanceState = intakeContext?.assistance?.guidance_state || {};
  const getCardState = (cardId: string): GuidanceCardState => {
    const status = guidanceState[cardId]?.status;
    if (status === 'done' || status === 'dismissed' || status === 'pending') return status;
    return 'pending';
  };
  const caseNotes = notes.filter(
    (note) => !(note.note_type === 'guidance' && getCaseNotePurpose(note) === 'next_steps')
  );

  return (
    <div className="max-w-5xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => navigate('/app/matcha/er-copilot')}
            className="text-xs text-zinc-500 hover:text-zinc-900 mb-4 flex items-center gap-1 uppercase tracking-wider"
          >
            <ChevronLeft size={12} />
            Back to Cases
          </button>
          <div className="flex items-center gap-3 mb-2">
            <span className="text-[10px] text-zinc-400 font-mono tracking-wide">{erCase.case_number}</span>
            <span className={`text-[10px] uppercase tracking-wide font-medium ${STATUS_COLORS[erCase.status]}`}>
              {erCase.status.replace('_', ' ')}
            </span>
          </div>
          <h1 className="text-2xl font-light text-zinc-900 dark:text-zinc-100 tracking-tight">{erCase.title}</h1>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowExportModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] text-zinc-500 hover:text-zinc-800 uppercase tracking-wider transition-colors border border-zinc-200 hover:border-zinc-400"
          >
            <Download size={12} />
            Export
          </button>
          <div className="w-40">
            <select
              value={erCase.status}
              onChange={(e) => handleStatusChange(e.target.value as ERCaseStatus)}
              disabled={statusUpdating}
              className={`w-full px-2 py-1.5 bg-transparent border-b border-zinc-200 text-xs text-zinc-600 focus:outline-none focus:border-zinc-400 cursor-pointer ${
                statusUpdating ? 'opacity-50' : ''
              }`}
            >
              {STATUS_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {showAssistancePanel && (
        <div className="border border-zinc-200 bg-zinc-50/70 p-4 space-y-2">
          <p className="text-[10px] uppercase tracking-widest text-zinc-500">Investigation Assistance Intake</p>
          {assistanceAnswers && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs text-zinc-600">
              <div>
                <span className="text-zinc-400 uppercase tracking-wide text-[10px]">Complaint Format</span>
                <p className="mt-1">{assistanceAnswers.complaint_format || 'unknown'}</p>
              </div>
              <div>
                <span className="text-zinc-400 uppercase tracking-wide text-[10px]">Immediate Risk</span>
                <p className="mt-1">{assistanceAnswers.immediate_risk || 'unsure'}</p>
              </div>
              <div>
                <span className="text-zinc-400 uppercase tracking-wide text-[10px]">Primary Goal</span>
                <p className="mt-1">{formatIntakeObjective(assistanceAnswers.objective)}</p>
              </div>
              <div>
                <span className="text-zinc-400 uppercase tracking-wide text-[10px]">Witnesses</span>
                <p className="mt-1">{assistanceAnswers.witnesses || 'Not provided'}</p>
              </div>
            </div>
          )}
          {assistanceAnswers?.additional_notes && (
            <p className="text-xs text-zinc-600">Notes: {assistanceAnswers.additional_notes}</p>
          )}
          {autoAssistMessage && (
            <p className={`text-xs ${
              autoAssistStatus === 'completed'
                ? 'text-emerald-700'
                : autoAssistStatus === 'running'
                  ? 'text-amber-700'
                  : 'text-zinc-600'
            }`}>
              {autoAssistMessage}
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
        {/* Left: Documents */}
        <div className="lg:col-span-1 space-y-6">
          <div className="flex justify-between items-center border-b border-zinc-200 pb-2">
            <h2 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Evidence</h2>
            <div className="flex items-center gap-3">
              {hasUnprocessedDocs && (
                <button
                  onClick={handleReprocessAllDocs}
                  disabled={reprocessingAll}
                  className="text-[10px] text-amber-600 hover:text-amber-500 flex items-center gap-1 uppercase tracking-wide font-medium disabled:opacity-50"
                  title="Reprocess all pending/failed documents"
                >
                  <RefreshCw size={10} className={reprocessingAll ? 'animate-spin' : ''} />
                  {reprocessingAll ? 'Processing...' : 'Reprocess All'}
                </button>
              )}
              <button
                onClick={() => setShowUploadModal(true)}
                className="text-[10px] text-zinc-900 dark:text-zinc-100 hover:text-zinc-600 dark:hover:text-zinc-300 flex items-center gap-1 uppercase tracking-wide font-medium"
              >
                <Upload size={10} />
                Upload
              </button>
            </div>
          </div>

          <div className="min-h-[200px]">
            {documents.length === 0 ? (
              <div className="text-zinc-400 text-xs py-4">
                No documents uploaded.
              </div>
            ) : (
              <div className="space-y-1">
                {documents.map(doc => (
                  <div key={doc.id} className="py-2 flex items-start justify-between group">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className={`text-[10px] uppercase tracking-wide font-medium ${DOC_TYPE_COLORS[doc.document_type]}`}>
                          {doc.document_type}
                        </span>
                        {doc.processing_status === 'pending' && (
                          <span className="text-[10px] text-zinc-400">Pending</span>
                        )}
                        {doc.processing_status === 'processing' && (
                          <span className="text-[10px] text-amber-500">Processing...</span>
                        )}
                        {doc.processing_status === 'completed' && (
                          <span className="text-[10px] text-emerald-500">✓</span>
                        )}
                        {doc.processing_status === 'failed' && (
                          <span className="text-[10px] text-red-500">Failed</span>
                        )}
                      </div>
                      <p className="text-xs text-zinc-900 dark:text-zinc-100 truncate hover:text-zinc-700 dark:hover:text-zinc-300 cursor-pointer" title={doc.filename}>{doc.filename}</p>
                      {doc.processing_error && (
                        <p className="text-[10px] text-red-400 truncate" title={doc.processing_error}>{doc.processing_error}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
                      {(doc.processing_status === 'pending' || doc.processing_status === 'failed') && (
                        <button
                          onClick={() => handleReprocessDoc(doc.id)}
                          className="text-zinc-300 hover:text-blue-500 transition-colors p-1"
                          title="Reprocess document"
                        >
                          <RefreshCw size={12} />
                        </button>
                      )}
                      <button
                        onClick={() => handleDeleteDoc(doc.id)}
                        className="text-zinc-300 hover:text-red-500 transition-colors p-1"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {showAssistancePanel && (
            <div className="pt-4 border-t border-zinc-200">
              <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 mb-3">Suggested Guidance</h3>

              {showDeterminationBanner && (
                <div className="border border-amber-200 bg-amber-50 p-3 rounded-sm mb-3 space-y-2">
                  <p className="text-xs font-medium text-amber-900">Ready for a determination?</p>
                  <p className="text-xs text-amber-800 leading-relaxed">
                    The current case file contains evidence that appears to meet the standard of
                    'preponderance of the evidence.' Continuing to investigate may produce diminishing returns.
                  </p>
                  {latestGuidancePayload?.determination_confidence != null && (
                    <div className="mt-1.5 space-y-1">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-amber-200 rounded-full overflow-hidden">
                          <div className="h-full bg-amber-600 rounded-full"
                               style={{ width: `${Math.round(latestGuidancePayload.determination_confidence * 100)}%` }} />
                        </div>
                        <span className="text-[10px] font-mono text-amber-700">
                          {Math.round(latestGuidancePayload.determination_confidence * 100)}%
                        </span>
                      </div>
                      {latestGuidancePayload.determination_signals?.map((s, i) => (
                        <p key={i} className="text-[10px] text-amber-600">&middot; {s}</p>
                      ))}
                    </div>
                  )}
                  <div className="flex items-center gap-3">
                    <button
                      onClick={async () => {
                        if (!id) return;
                        setDeterminationAccepting(true);
                        try {
                          const updated = await erCopilot.updateCase(id, { status: 'pending_determination' });
                          setCase(updated);
                          // Fire outcome analysis + summary in parallel, don't block on either
                          fetchOutcomeAnalysis();
                          erCopilot.generateSummary(id).catch((e) => console.error('Summary generation failed:', e));
                          await fetchNotes();
                        } catch (err) {
                          console.error('Failed to transition to pending determination:', err);
                        } finally {
                          setDeterminationAccepting(false);
                        }
                      }}
                      disabled={determinationAccepting}
                      className="text-xs font-medium text-amber-900 bg-amber-200 hover:bg-amber-300 px-3 py-1 rounded-sm disabled:opacity-50"
                    >
                      {determinationAccepting ? 'Working...' : 'Proceed to case determination'}
                    </button>
                    <button
                      onClick={async () => {
                        setDeterminationDismissed(true);
                        if (!id) return;
                        try {
                          const ctx = normalizeIntakeContext(erCase.intake_context);
                          await erCopilot.updateCase(id, {
                            intake_context: {
                              ...(ctx || {}),
                              assistance: {
                                ...(ctx?.assistance || {}),
                                determination_dismissed: true,
                              },
                            },
                          });
                        } catch (err) {
                          console.error('Failed to persist determination dismissal:', err);
                        }
                      }}
                      className="text-xs text-amber-700 hover:text-amber-900"
                    >
                      Continue investigation
                    </button>
                  </div>
                  {latestGuidancePayload?.cards && latestGuidancePayload.cards.length > 0 && (
                    <p className="text-[10px] text-amber-600 mt-1">
                      Still open: {latestGuidancePayload.cards.slice(0, 2).map(c => c.title).join(', ')}
                    </p>
                  )}
                </div>
              )}

              {latestGuidanceNote ? (
                <div className="space-y-2">
                  <div className="border border-emerald-200 bg-emerald-50 p-2.5 rounded-sm">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] uppercase tracking-wide text-emerald-700">Next Steps</span>
                      <span className="text-[10px] text-zinc-400">
                        {new Date(latestGuidancePayload?.generated_at || latestGuidanceNote.created_at).toLocaleString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          hour: 'numeric',
                          minute: '2-digit',
                        })}
                      </span>
                    </div>
                    <p className="text-xs text-zinc-700 whitespace-pre-wrap leading-relaxed">
                      {latestGuidancePayload?.summary || latestGuidanceNote.content}
                    </p>
                    {latestGuidancePayload && (
                      <p className="mt-1 text-[10px] text-zinc-500">
                        Model: {latestGuidancePayload.model}{latestGuidancePayload.fallback_used ? ' (fallback)' : ''}
                      </p>
                    )}
                  </div>

                  {latestGuidancePayload?.cards.length ? (
                    <div className="space-y-2">
                      {latestGuidancePayload.cards.map((card) => {
                        const state = getCardState(card.id);
                        const stateLabel = state === 'done' ? 'Completed' : state === 'dismissed' ? 'Dismissed' : 'Pending';
                        return (
                          <div key={card.id} className="border border-zinc-200 bg-white p-2.5 rounded-sm space-y-2">
                            <div className="flex items-center justify-between gap-2">
                              <p className="text-xs font-medium text-zinc-800">{card.title}</p>
                              <span className={`px-1.5 py-0.5 text-[10px] uppercase tracking-wide rounded ${guidancePriorityStyle(card.priority)}`}>
                                {card.priority}
                              </span>
                            </div>
                            <p className="text-xs text-zinc-700">{card.recommendation}</p>
                            <p className="text-[11px] text-zinc-500">{card.rationale}</p>
                            {card.blockers.length > 0 && (
                              <p className="text-[11px] text-zinc-500">Blockers: {card.blockers.join('; ')}</p>
                            )}
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-[10px] uppercase tracking-wide text-zinc-500">{stateLabel}</span>
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={() => void updateGuidanceCardState(card.id, 'done')}
                                  className="text-[10px] uppercase tracking-wide text-emerald-700 hover:text-emerald-600 disabled:opacity-40"
                                  disabled={state === 'done'}
                                >
                                  Mark Done
                                </button>
                                <button
                                  onClick={() => void updateGuidanceCardState(card.id, 'dismissed')}
                                  className="text-[10px] uppercase tracking-wide text-zinc-500 hover:text-zinc-700 disabled:opacity-40"
                                  disabled={state === 'dismissed'}
                                >
                                  Dismiss
                                </button>
                                <button
                                  onClick={() => void handleGuidanceAction(card)}
                                  className="text-[10px] uppercase tracking-wide text-blue-700 hover:text-blue-600 disabled:opacity-50"
                                  disabled={guidanceActionBusyId === card.id}
                                >
                                  {guidanceActionBusyId === card.id ? 'Working...' : card.action.label}
                                </button>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="text-xs text-zinc-400">No guidance yet. Complete assistance intake and analysis to generate next steps.</p>
              )}
            </div>
          )}

          {showAssistancePanel && erCase.status !== 'pending_determination' && (
            <div className="pt-4 border-t border-zinc-200">
              <h3 className="text-[10px] uppercase tracking-wider text-zinc-500 mb-3">Case Notes</h3>
              {caseNotes.length === 0 ? (
                <p className="text-xs text-zinc-400">No notes yet.</p>
              ) : (
                <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
                  {caseNotes.slice(-10).reverse().map((note) => (
                    <div key={note.id} className="border border-zinc-200 bg-zinc-50 p-2.5 rounded-sm">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] uppercase tracking-wide text-zinc-500">{formatCaseNoteType(note.note_type)}</span>
                        <span className="text-[10px] text-zinc-400">
                          {new Date(note.created_at).toLocaleString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            hour: 'numeric',
                            minute: '2-digit',
                          })}
                        </span>
                      </div>
                      <p className="text-xs text-zinc-700 whitespace-pre-wrap">{note.content}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Determination Panel — shown when status is pending_determination */}
          {erCase.status === 'pending_determination' && (
            <div className="pt-4 border-t border-zinc-200 space-y-4">
              <h3 className="text-[10px] uppercase tracking-wider text-zinc-500">Case Determination</h3>

              {/* Loading state */}
              {outcomeLoading && (
                <div className="border border-orange-200 bg-orange-50 p-3 rounded-sm">
                  <div className="flex items-center gap-2">
                    <RefreshCw size={12} className="animate-spin text-orange-600" />
                    <span className="text-xs text-orange-800">{outcomeStatusMsg || 'Generating outcome analysis...'}</span>
                  </div>
                </div>
              )}

              {/* Outcome analysis results */}
              {outcomeAnalysis && !outcomeLoading && (
                <div className="space-y-3">
                  {outcomeAnalysis.case_summary && (
                    <div className="border border-zinc-200 bg-zinc-50 p-2.5 rounded-sm">
                      <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Case Summary</p>
                      <p className="text-xs text-zinc-700 leading-relaxed">{outcomeAnalysis.case_summary}</p>
                    </div>
                  )}

                  <p className="text-[10px] uppercase tracking-wide text-zinc-500">Recommended Outcomes</p>

                  {outcomeAnalysis.outcomes.map((outcome, idx) => {
                    const isSelected = selectedOutcomeIdx === idx;
                    const confColor = outcome.confidence === 'high'
                      ? 'text-emerald-700 bg-emerald-100'
                      : outcome.confidence === 'moderate'
                        ? 'text-amber-700 bg-amber-100'
                        : 'text-zinc-600 bg-zinc-100';
                    const detColor = outcome.determination === 'substantiated'
                      ? 'text-red-700'
                      : outcome.determination === 'unsubstantiated'
                        ? 'text-emerald-700'
                        : 'text-amber-700';

                    return (
                      <button
                        key={idx}
                        onClick={() => setSelectedOutcomeIdx(isSelected ? null : idx)}
                        className={`w-full text-left border rounded-sm p-3 space-y-2 transition-colors ${
                          isSelected
                            ? 'border-zinc-900 bg-zinc-50 ring-1 ring-zinc-900'
                            : 'border-zinc-200 bg-white hover:border-zinc-400'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <div className={`w-3 h-3 rounded-full border-2 flex-shrink-0 ${
                              isSelected ? 'border-zinc-900 bg-zinc-900' : 'border-zinc-300'
                            }`} />
                            <span className="text-xs font-medium text-zinc-900 truncate">{outcome.action_label}</span>
                          </div>
                          <div className="flex items-center gap-1.5 flex-shrink-0">
                            <span className={`text-[10px] uppercase tracking-wide font-medium ${detColor}`}>
                              {outcome.determination}
                            </span>
                            <span className={`px-1.5 py-0.5 text-[9px] uppercase tracking-wide rounded ${confColor}`}>
                              {outcome.confidence}
                            </span>
                          </div>
                        </div>
                        <p className="text-xs text-zinc-700 leading-relaxed">{outcome.reasoning}</p>
                        {isSelected && (
                          <div className="pt-2 border-t border-zinc-200 space-y-1.5">
                            <div>
                              <span className="text-[10px] uppercase tracking-wide text-zinc-500">Policy Basis</span>
                              <p className="text-xs text-zinc-600 mt-0.5">{outcome.policy_basis}</p>
                            </div>
                            <div>
                              <span className="text-[10px] uppercase tracking-wide text-zinc-500">HR Considerations</span>
                              <p className="text-xs text-zinc-600 mt-0.5">{outcome.hr_considerations}</p>
                            </div>
                            <div>
                              <span className="text-[10px] uppercase tracking-wide text-zinc-500">Precedent</span>
                              <p className="text-xs text-zinc-600 mt-0.5">{outcome.precedent_note}</p>
                            </div>
                          </div>
                        )}
                      </button>
                    );
                  })}

                  {outcomeAnalysis.outcomes.length === 0 && (
                    <p className="text-xs text-zinc-400">No outcome recommendations generated. Please review the case manually.</p>
                  )}

                  {/* Determination notes */}
                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                      Determination Notes <span className="text-red-500">*</span>
                    </label>
                    <textarea
                      value={determinationNotes}
                      onChange={(e) => setDeterminationNotes(e.target.value)}
                      placeholder="Document your reasoning for this determination..."
                      rows={4}
                      className="w-full px-3 py-2 text-xs text-zinc-900 bg-white border border-zinc-200 rounded-sm focus:outline-none focus:border-zinc-400 resize-none"
                    />
                  </div>

                  {/* Close case button */}
                  <button
                    onClick={handleCloseCase}
                    disabled={closingCase || selectedOutcomeIdx === null || !determinationNotes.trim()}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-white bg-zinc-900 hover:bg-zinc-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed rounded-sm"
                  >
                    <CheckCircle size={14} />
                    {closingCase ? 'Closing Case...' : 'Close Case & Finalize'}
                  </button>

                  <p className="text-[10px] text-zinc-400">
                    Model: {outcomeAnalysis.model}
                  </p>
                </div>
              )}

              {/* Error state */}
              {outcomeError && !outcomeLoading && (
                <div className="border border-red-200 bg-red-50 p-3 rounded-sm space-y-2">
                  <div className="flex items-start gap-2">
                    <AlertTriangle size={12} className="text-red-500 mt-0.5 shrink-0" />
                    <p className="text-xs text-red-700">{outcomeError}</p>
                  </div>
                  <button
                    onClick={fetchOutcomeAnalysis}
                    className="text-[10px] uppercase tracking-wider font-medium text-red-700 hover:text-red-900"
                  >
                    Retry
                  </button>
                </div>
              )}

              {/* No analysis yet and not loading */}
              {!outcomeAnalysis && !outcomeLoading && !outcomeError && (
                <div className="text-center py-4">
                  <p className="text-xs text-zinc-400 mb-2">Outcome analysis not yet generated.</p>
                  <button
                    onClick={fetchOutcomeAnalysis}
                    className="text-xs text-zinc-700 hover:text-zinc-900 uppercase tracking-wider font-medium"
                  >
                    Generate Analysis
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Always-visible Case Notes & Add Note */}
          <div className="pt-4 border-t border-zinc-200 space-y-3">
            <h3 className="text-[10px] uppercase tracking-wider text-zinc-500">Case Notes</h3>
            {caseNotes.length > 0 && (
              <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
                {caseNotes.slice(-10).reverse().map((note) => (
                  <div key={note.id} className="border border-zinc-200 bg-zinc-50 p-2.5 rounded-sm">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] uppercase tracking-wide text-zinc-500">{formatCaseNoteType(note.note_type)}</span>
                      <span className="text-[10px] text-zinc-400">
                        {new Date(note.created_at).toLocaleString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          hour: 'numeric',
                          minute: '2-digit',
                        })}
                      </span>
                    </div>
                    <p className="text-xs text-zinc-700 whitespace-pre-wrap">{note.content}</p>
                  </div>
                ))}
              </div>
            )}
            <div className="space-y-2">
              <textarea
                value={newNoteContent}
                onChange={(e) => setNewNoteContent(e.target.value)}
                placeholder="Add a note..."
                rows={2}
                className="w-full px-3 py-2 text-xs text-zinc-900 bg-white border border-zinc-200 rounded-sm focus:outline-none focus:border-zinc-400 resize-none"
              />
              <button
                onClick={handleAddNote}
                disabled={addingNote || !newNoteContent.trim()}
                className="text-[10px] uppercase tracking-wider font-medium text-zinc-700 hover:text-zinc-900 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {addingNote ? 'Adding...' : 'Add Note'}
              </button>
            </div>
          </div>
        </div>

        {/* Right: Analysis */}
        <div className="lg:col-span-2 space-y-6">
          {/* Tabs */}
          <div className="flex gap-6 border-b border-zinc-200 pb-px">
            {[
              { id: 'timeline', label: 'Timeline', icon: Clock },
              { id: 'discrepancies', label: 'Discrepancies', icon: AlertTriangle },
              { id: 'policy', label: 'Policy Check', icon: CheckCircle },
              { id: 'search', label: 'Search', icon: Search },
            ].map(tab => {
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as AnalysisTab)}
                  className={`pb-2 text-[10px] font-medium uppercase tracking-wider transition-colors flex items-center gap-2 border-b-2 ${
                    activeTab === tab.id
                      ? 'border-zinc-900 text-zinc-900'
                      : 'border-transparent text-zinc-400 hover:text-zinc-600'
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          {analysisError && (
            <div className="mb-4 flex items-start gap-2 rounded border border-red-200 bg-red-50 dark:border-red-900/50 dark:bg-red-950/30 px-3 py-2">
              <AlertTriangle size={14} className="text-red-500 mt-0.5 shrink-0" />
              <p className="text-xs text-red-700 dark:text-red-400 flex-1">{analysisError}</p>
              <button onClick={() => setAnalysisError(null)} className="text-red-400 hover:text-red-600">
                <X size={12} />
              </button>
            </div>
          )}

          <div className="min-h-[400px]">
            {/* Timeline Tab */}
            {activeTab === 'timeline' && (
              <div className="space-y-8">
                <div className="flex justify-end">
                  <button
                    onClick={handleGenerateTimeline}
                    disabled={analysisLoading === 'timeline' || completedNonPolicyDocs.length === 0}
                    className="text-[10px] uppercase tracking-wider font-medium text-zinc-900 dark:text-zinc-100 hover:text-zinc-600 dark:hover:text-zinc-300 disabled:opacity-50"
                  >
                    {analysisLoading === 'timeline' ? 'Generating...' : 'Regenerate Analysis'}
                  </button>
                </div>

                {timelineSummary && (
                  <div className="text-sm text-zinc-600 dark:text-zinc-300 leading-relaxed font-serif">
                    {timelineSummary}
                  </div>
                )}

                {timeline.length === 0 ? (
                  <div className="text-center py-12 text-zinc-400 text-xs">
                    {analysisLoading === 'timeline' ? (
                      <div className="flex flex-col items-center gap-3">
                        <RefreshCw size={20} className="animate-spin text-zinc-500" />
                        <span>{analysisProgress?.step || 'Analyzing documents and reconstructing timeline...'}</span>
                        {analysisProgress?.detail && (
                          <span className="text-[10px] text-zinc-500">{analysisProgress.detail}</span>
                        )}
                      </div>
                    ) : (
                      <div>
                        <p className="mb-2">No timeline generated yet.</p>
                        <p className="text-[10px] text-zinc-500">
                          Click "Regenerate Analysis" to reconstruct a timeline from your uploaded documents.
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="relative pl-2 space-y-8 border-l border-zinc-200 ml-2">
                    {timeline.map((event, i) => (
                      <div key={i} className="relative pl-6">
                        <div className="absolute left-[-3px] top-1.5 w-1.5 h-1.5 rounded-full bg-zinc-300" />
                        <div className="flex items-center gap-3 mb-1">
                          <span className="text-xs font-medium text-zinc-900 dark:text-zinc-100">
                            {event.date} {event.time && <span className="text-zinc-400 font-normal">at {event.time}</span>}
                          </span>
                          <span className={`text-[9px] uppercase tracking-wide font-medium ${
                            event.confidence === 'high' ? 'text-emerald-600' :
                            event.confidence === 'medium' ? 'text-amber-600' :
                            'text-red-600'
                          }`}>
                            {event.confidence}
                          </span>
                        </div>
                        <p className="text-zinc-800 dark:text-zinc-200 text-sm mb-2">{event.description}</p>
                        
                        <div className="flex flex-wrap gap-2 mb-2">
                          {event.participants.map(p => (
                            <span key={p} className="text-[10px] text-zinc-500 uppercase tracking-wide">
                              {p}
                            </span>
                          ))}
                        </div>

                        {event.evidence_quote && (
                          <div className="text-xs text-zinc-500 italic pl-2 border-l border-zinc-200">
                            "{event.evidence_quote}"
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {timelineGaps.length > 0 && (
                  <div className="pt-6 border-t border-zinc-100">
                    <h4 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-3">Identified Gaps</h4>
                    <ul className="space-y-2">
                      {timelineGaps.map((gap, i) => (
                        <li key={i} className="text-xs text-zinc-600 flex items-start gap-2">
                          <span className="text-amber-500 mt-0.5">•</span>
                          {gap}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Discrepancies Tab */}
            {activeTab === 'discrepancies' && (
              <div className="space-y-8">
                <div className="flex justify-end">
                  <button
                    onClick={handleGenerateDiscrepancies}
                    disabled={analysisLoading === 'discrepancies' || completedNonPolicyDocs.length < 2}
                    className="text-[10px] uppercase tracking-wider font-medium text-zinc-900 dark:text-zinc-100 hover:text-zinc-600 dark:hover:text-zinc-300 disabled:opacity-50"
                  >
                    {analysisLoading === 'discrepancies' ? 'Analyzing...' : 'Analyze Documents'}
                  </button>
                </div>

                {discrepancySummary && (
                  <div className="text-sm text-zinc-600 dark:text-zinc-300 leading-relaxed font-serif">
                    {discrepancySummary}
                  </div>
                )}

                {discrepancies.length === 0 ? (
                  <div className="text-center py-12 text-zinc-400 text-xs">
                    {analysisLoading === 'discrepancies' ? (
                      <div className="flex flex-col items-center gap-3">
                        <RefreshCw size={20} className="animate-spin text-zinc-500" />
                        <span>{analysisProgress?.step || 'Comparing statements and detecting discrepancies...'}</span>
                        {analysisProgress?.detail && (
                          <span className="text-[10px] text-zinc-500">{analysisProgress.detail}</span>
                        )}
                      </div>
                    ) : discrepancySummary ? (
                      <div>
                        <p className="mb-2">No conflicting statements detected.</p>
                        <p className="text-[10px] text-zinc-500">
                          Analyzed {completedNonPolicyDocs.length} documents.
                          All witness accounts appear consistent on key facts.
                        </p>
                      </div>
                    ) : completedNonPolicyDocs.length < 2 ? (
                      <div>
                        <p className="mb-2">Upload at least 2 non-policy documents to run analysis.</p>
                        <p className="text-[10px] text-zinc-500">
                          Discrepancy detection compares statements across multiple documents.
                        </p>
                      </div>
                    ) : (
                      <div>
                        <p className="mb-2">No analysis run yet.</p>
                        <p className="text-[10px] text-zinc-500">
                          Click "Analyze Documents" to compare statements and detect discrepancies.
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="space-y-8">
                    {discrepancies.map((disc, i) => (
                      <div key={i} className="border-b border-zinc-100 pb-8 last:border-0 last:pb-0">
                        <div className="flex items-center gap-3 mb-2">
                          <span className={`text-[10px] uppercase tracking-wide font-medium ${
                            disc.severity === 'high' ? 'text-red-600' :
                            disc.severity === 'medium' ? 'text-amber-600' :
                            'text-zinc-500'
                          }`}>
                            {disc.severity} Severity
                          </span>
                          <span className="text-[10px] text-zinc-400 uppercase tracking-wide">•</span>
                          <span className="text-[10px] text-zinc-500 uppercase tracking-wide">{disc.type}</span>
                        </div>
                        
                        <p className="text-zinc-900 dark:text-zinc-100 text-sm font-medium mb-4">{disc.description}</p>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
                          <div>
                            <p className="text-[10px] text-zinc-500 mb-1 uppercase tracking-wide">
                              {disc.statement_1?.speaker || 'Source 1'}
                            </p>
                            <p className="text-xs text-zinc-600 italic border-l border-zinc-200 pl-2">
                              "{disc.statement_1?.quote || 'No quote provided.'}"
                            </p>
                          </div>
                          <div>
                            <p className="text-[10px] text-zinc-500 mb-1 uppercase tracking-wide">
                              {disc.statement_2?.speaker || 'Source 2'}
                            </p>
                            <p className="text-xs text-zinc-600 italic border-l border-zinc-200 pl-2">
                              "{disc.statement_2?.quote || 'No quote provided.'}"
                            </p>
                          </div>
                        </div>
                        
                        <div className="text-xs text-zinc-500 bg-zinc-50 p-3 rounded-sm">
                          {disc.analysis}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Policy Check Tab */}
            {activeTab === 'policy' && (
              <div className="space-y-8">
                <div className="flex justify-end">
                  <button
                    onClick={handleRunPolicyCheck}
                    disabled={analysisLoading === 'policy' || completedNonPolicyDocs.length === 0}
                    className="text-[10px] uppercase tracking-wider font-medium text-zinc-900 dark:text-zinc-100 hover:text-zinc-600 dark:hover:text-zinc-300 disabled:opacity-50"
                  >
                    {analysisLoading === 'policy' ? 'Checking...' : 'Run Policy Check'}
                  </button>
                </div>

                {policiesChecked > 0 && (
                  <div className="flex items-center gap-3 text-[10px] font-mono text-zinc-500 uppercase tracking-wider">
                    <span>{policiesChecked} {policiesChecked === 1 ? 'source' : 'sources'} checked</span>
                    <span className="text-zinc-700">·</span>
                    <span className={violations.length > 0 ? 'text-red-400' : 'text-emerald-400'}>
                      {violations.length} violation{violations.length !== 1 ? 's' : ''} found
                    </span>
                  </div>
                )}

                {violations.length === 0 ? (
                  <div className="text-center py-12 text-zinc-400 text-xs">
                    {analysisLoading === 'policy' ? (
                      <div className="flex flex-col items-center gap-3">
                        <RefreshCw size={20} className="animate-spin text-zinc-500" />
                        <span>{analysisProgress?.step || 'Checking evidence against policy documents...'}</span>
                        {analysisProgress?.detail && (
                          <span className="text-[10px] text-zinc-500">{analysisProgress.detail}</span>
                        )}
                      </div>
                    ) : policiesChecked > 0 ? (
                      <div>
                        <p className="mb-2">No policy violations identified.</p>
                        <p className="text-[10px] text-zinc-500">
                          Evidence was reviewed against all active company policies.
                          No clear violations were found.
                        </p>
                      </div>
                    ) : (
                      <div>
                        <p className="mb-2">No policy check run yet.</p>
                        <p className="text-[10px] text-zinc-500">
                          Click "Run Policy Check" to compare evidence against all active company policies.
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="space-y-8">
                    {violations.map((v, i) => (
                      <div key={i} className="border-b border-zinc-100 dark:border-zinc-800 pb-8 last:border-0 last:pb-0">
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`text-[10px] uppercase tracking-wide font-medium ${
                            v.severity === 'major' ? 'text-red-600' : 'text-amber-600'
                          }`}>
                            {v.severity} Violation
                          </span>
                        </div>

                        <h4 className="text-zinc-900 dark:text-zinc-100 text-sm font-medium mb-2">{v.policy_section}</h4>
                        <div className="mb-4">
                          <p className="text-xs text-zinc-500 dark:text-zinc-400 italic">"{v.policy_text}"</p>
                        </div>

                        <div className="space-y-3 pl-3 border-l-2 border-zinc-100 dark:border-zinc-700">
                          {v.evidence.map((e, j) => (
                            <div key={j}>
                              <p className="text-xs text-zinc-700 dark:text-zinc-300 mb-1">"{e.quote}"</p>
                              <p className="text-[10px] text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">→ {e.how_it_violates}</p>
                              {e.source_document_id && (() => {
                                const doc = documents.find(d => d.id === e.source_document_id);
                                const label = doc?.filename || e.source_document_id.slice(0, 8);
                                return (
                                  <p className="text-[9px] text-zinc-600 dark:text-zinc-600 font-mono mt-1">
                                    Source: {label}{e.location ? ` · ${e.location}` : ''}
                                  </p>
                                );
                              })()}
                            </div>
                          ))}
                        </div>
                        
                        <div className="mt-4 text-xs text-zinc-500">
                          {v.analysis}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Search Tab */}
            {activeTab === 'search' && (
              <div className="space-y-6">
                <div className="flex gap-3">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-2.5 text-zinc-400" size={16} />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                      placeholder="Search evidence using natural language..."
                      className="w-full pl-10 pr-4 py-2 bg-white border border-zinc-200 rounded text-sm text-zinc-900 focus:outline-none focus:border-zinc-400 focus:ring-0"
                    />
                  </div>
                  <Button 
                    onClick={handleSearch} 
                    disabled={searching || !searchQuery.trim()}
                    className="bg-zinc-900 text-white hover:bg-zinc-800"
                  >
                    {searching ? 'Searching...' : 'Search'}
                  </Button>
                </div>

                {searchResults.length > 0 ? (
                  <div className="space-y-4">
                    {searchResults.map((result, i) => (
                      <div key={i} className="bg-white border border-zinc-200 rounded p-4 shadow-sm hover:border-zinc-300 transition-colors">
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`px-1.5 py-0.5 text-[10px] uppercase tracking-wide rounded border ${DOC_TYPE_COLORS[result.document_type]}`}>
                            {result.document_type}
                          </span>
                          <span className="text-xs text-zinc-500 font-medium">{result.source_file}</span>
                          <span className="text-[10px] text-zinc-400 ml-auto font-mono">
                            {(result.similarity * 100).toFixed(0)}% Match
                          </span>
                        </div>
                        
                        {result.speaker && (
                          <p className="text-xs text-zinc-500 mb-1 font-medium uppercase tracking-wide">{result.speaker}</p>
                        )}
                        
                        <div className="text-sm text-zinc-800 leading-relaxed bg-zinc-50 p-3 rounded border border-zinc-100">
                          {result.content}
                        </div>
                        
                        {result.line_range && (
                          <div className="mt-2 flex justify-end">
                            <span className="text-[10px] text-zinc-400">Lines {result.line_range}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12 text-zinc-500 text-sm">
                    {completedDocs.length === 0
                      ? 'Upload documents first.'
                      : 'Enter a query to search through case evidence using semantic similarity.'}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-900/20 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-white shadow-2xl rounded-sm flex flex-col max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-4 border-b border-zinc-100">
              <h3 className="text-sm font-light text-zinc-900 uppercase tracking-wider">Upload Document</h3>
              <button 
                onClick={() => setShowUploadModal(false)}
                className="text-zinc-400 hover:text-zinc-600 transition-colors"
              >
                <X size={20} />
              </button>
            </div>
            
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">Document Type</label>
                <select
                  value={uploadDocType}
                  onChange={(e) => setUploadDocType(e.target.value as ERDocumentType)}
                  className="w-full px-3 py-2 bg-white border border-zinc-200 rounded-lg text-sm text-zinc-900 focus:outline-none focus:border-zinc-400"
                >
                  {DOC_TYPE_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              <FileUpload
                accept=".pdf,.docx,.doc,.txt,.csv,.json"
                onUpload={handleUpload}
                multiple={true}
                label={uploading ? 'Uploading...' : 'Drop files here or click to select'}
                description="Supports PDF, DOCX, TXT, CSV, JSON"
              />
            </div>
          </div>
        </div>
      )}

      {/* Export Modal */}
      {showExportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm bg-white border border-zinc-200 shadow-2xl">
            <div className="flex items-center justify-between p-5 border-b border-zinc-100">
              <h3 className="text-xs font-bold text-zinc-900 uppercase tracking-wider">Export Case File</h3>
              <button
                onClick={() => { setShowExportModal(false); setExportPassword(''); setExportError(null); }}
                className="text-zinc-400 hover:text-zinc-600 transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <p className="text-[11px] text-zinc-500">
                Export a password-protected PDF containing the full case file, documents, analyses, and notes.
              </p>
              {exportError && (
                <div className="text-[11px] text-red-500 bg-red-50 px-3 py-2 border border-red-200">
                  {exportError}
                </div>
              )}
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">PDF Password</label>
                <input
                  type="password"
                  value={exportPassword}
                  onChange={(e) => setExportPassword(e.target.value)}
                  placeholder="Min 4 characters"
                  className="w-full px-3 py-2 bg-white border border-zinc-200 text-sm text-zinc-900 focus:outline-none focus:border-zinc-400"
                  onKeyDown={(e) => { if (e.key === 'Enter' && exportPassword.length >= 4) handleExport(); }}
                />
              </div>
              <button
                onClick={handleExport}
                disabled={exporting || exportPassword.length < 4}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-white bg-zinc-900 hover:bg-zinc-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Download size={14} />
                {exporting ? 'Generating…' : 'Export Case File'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ERCaseDetail;
