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
  TimelineEvent,
  Discrepancy,
  PolicyViolation,
  EvidenceSearchResult,
} from '../types';
import {
  ChevronLeft, Upload, Trash2, Search,
  AlertTriangle, CheckCircle, Clock, X, RefreshCw
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

function normalizeGuidanceFragment(value: string, maxLength: number): string {
  const cleaned = value.replace(/\s+/g, ' ').trim();
  if (!cleaned) return '';
  if (cleaned.length <= maxLength) return cleaned.replace(/[.]+$/, '');
  return `${cleaned.slice(0, maxLength).replace(/[.]+$/, '')}...`;
}

function formatGapQuestion(value: string): string {
  const cleaned = normalizeGuidanceFragment(value, 160);
  if (!cleaned) return '';
  if (cleaned.includes('?')) return cleaned;
  return `${cleaned}?`;
}

type SuggestedGuidanceInput = {
  reviewedDocCount: number;
  reviewedDocNames: string[];
  shouldRunDiscrepancies: boolean;
  timelineSummary: string;
  timelineGaps: string[];
  discrepancies: Discrepancy[];
  discrepancySummary: string;
  violations: PolicyViolation[];
  policySummary: string;
  reviewSucceeded: boolean;
  objective?: ERCaseIntakeContext['answers'] extends infer Answers
    ? Answers extends { objective?: infer Objective }
      ? Objective
      : never
    : never;
  immediateRisk?: ERCaseIntakeContext['answers'] extends infer Answers
    ? Answers extends { immediate_risk?: infer ImmediateRisk }
      ? ImmediateRisk
      : never
    : never;
};

function buildSuggestedGuidance(input: SuggestedGuidanceInput): string {
  const discrepancyRank = { high: 3, medium: 2, low: 1 } as const;
  const sortedDiscrepancies = [...input.discrepancies].sort(
    (a, b) => discrepancyRank[b.severity] - discrepancyRank[a.severity]
  );
  const topDiscrepancy = sortedDiscrepancies[0];
  const topViolation = input.violations.find((v) => v.severity === 'major') || input.violations[0];
  const timelineGaps = input.timelineGaps.filter(Boolean);
  const docPreview = input.reviewedDocNames.slice(0, 2).join(', ');

  const lines: string[] = ['Suggested Guidance'];

  if (topViolation) {
    const section = normalizeGuidanceFragment(topViolation.policy_section || 'high-risk policy sections', 90);
    lines.push(
      `1. Prioritize follow-ups for policy risk in ${section} and collect source evidence before interviews conclude.`
    );
  } else if (topDiscrepancy) {
    lines.push(
      `1. Run discrepancy-focused follow-up interviews on: ${normalizeGuidanceFragment(topDiscrepancy.description, 150)}.`
    );
  } else {
    lines.push(
      '1. Continue neutral fact-finding interviews and confirm each witness account in writing.'
    );
  }

  const followUpQuestions: string[] = [];
  if (topDiscrepancy) {
    const speaker1 = topDiscrepancy.statement_1?.speaker || 'Witness 1';
    const speaker2 = topDiscrepancy.statement_2?.speaker || 'Witness 2';
    followUpQuestions.push(
      `What specific evidence supports the conflicting accounts from ${speaker1} and ${speaker2}?`
    );
  }
  timelineGaps.slice(0, 2).forEach((gap) => {
    const question = formatGapQuestion(gap);
    if (question) followUpQuestions.push(question);
  });
  if (input.immediateRisk === 'yes') {
    followUpQuestions.push('Has any retaliation or immediate safety risk occurred since the last interview?');
  }
  if (followUpQuestions.length === 0) {
    followUpQuestions.push('What unresolved fact still prevents a final determination?');
  }
  lines.push(`2. Ask these follow-up questions next: ${followUpQuestions.slice(0, 3).join(' ')}`);

  if (timelineGaps.length > 0) {
    const gapSummary = timelineGaps
      .slice(0, 2)
      .map((gap) => normalizeGuidanceFragment(gap, 90))
      .join('; ');
    lines.push(`3. Close timeline gaps before concluding: ${gapSummary}.`);
  } else {
    lines.push('3. Timeline coverage is currently complete; validate critical event times against documentary evidence.');
  }

  if (topViolation) {
    lines.push(
      '4. Document policy-by-policy findings with linked quotes so legal and HR can verify conclusion quality.'
    );
  } else if (topDiscrepancy) {
    lines.push(
      '4. Reconcile conflicting testimony against objective artifacts (emails, logs, messages) and capture credibility impacts.'
    );
  } else {
    lines.push(
      '4. Preserve a neutral interview record and document corroboration for each material fact.'
    );
  }

  const readyForDetermination = input.reviewSucceeded
    && input.shouldRunDiscrepancies
    && timelineGaps.length === 0
    && input.discrepancies.length === 0
    && input.violations.length === 0;

  if (readyForDetermination) {
    lines.push(
      '5. Determination readiness: evidence is currently consistent. If final interviews add no new facts, draft a preliminary determination recommendation.'
    );
  } else {
    const blockers: string[] = [];
    if (timelineGaps.length > 0) blockers.push(`${timelineGaps.length} timeline gap${timelineGaps.length === 1 ? '' : 's'}`);
    if (input.discrepancies.length > 0) blockers.push(`${input.discrepancies.length} discrepancy flag${input.discrepancies.length === 1 ? '' : 's'}`);
    if (input.violations.length > 0) blockers.push(`${input.violations.length} policy risk finding${input.violations.length === 1 ? '' : 's'}`);
    if (!input.shouldRunDiscrepancies) blockers.push('one more completed witness/evidence document for discrepancy analysis');
    lines.push(`5. Determination gate: hold final determination until ${blockers.join(', ')} ${blockers.length === 1 ? 'is' : 'are'} resolved.`);
  }

  const contextFragments: string[] = [];
  contextFragments.push(`Review basis: ${input.reviewedDocCount} completed evidence document(s)`);
  if (docPreview) {
    contextFragments.push(`latest docs include ${docPreview}${input.reviewedDocNames.length > 2 ? ', ...' : ''}`);
  }
  if (input.objective && input.objective !== 'general') {
    contextFragments.push(`intake objective is ${formatIntakeObjective(input.objective)}`);
  }
  if (input.timelineSummary) {
    contextFragments.push(`timeline: ${normalizeGuidanceFragment(input.timelineSummary, 120)}`);
  }
  if (input.discrepancySummary && input.discrepancies.length > 0) {
    contextFragments.push(`discrepancies: ${normalizeGuidanceFragment(input.discrepancySummary, 120)}`);
  }
  if (input.policySummary && input.violations.length > 0) {
    contextFragments.push(`policy: ${normalizeGuidanceFragment(input.policySummary, 120)}`);
  }
  lines.push(`6. ${contextFragments.join('; ')}.`);

  return lines.join('\n');
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
  const [violationSummary, setViolationSummary] = useState<string>('');
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
        setTimeline(data.analysis.events || []);
        setTimelineSummary(data.analysis.timeline_summary || '');
        setTimelineGaps(data.analysis.gaps_identified || []);
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
          setViolationSummary('');
          setPoliciesChecked(0);
          return;
        }
        setViolations(data.analysis.violations || []);
        setViolationSummary(data.analysis.summary || '');
        setPoliciesChecked(data.analysis.policies_potentially_applicable?.length || 0);
      }
    } catch {
      // Analysis not yet generated - that's okay
    }
  }, [id]);

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

  useEffect(() => {
    autoReviewSignatureRef.current = null;
    setAutoAssistStatus('idle');
    setAutoAssistMessage(null);
    setNotes([]);
  }, [id]);

  // WebSocket subscription for real-time analysis updates
  useEffect(() => {
    if (!id) return;

    const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';
    const wsHost = apiBase.replace(/^https?:\/\//, '').replace(/\/api$/, '');
    const wsProtocol = apiBase.startsWith('https') ? 'wss' : 'ws';
    const wsUrl = `${wsProtocol}://${wsHost}/ws/notifications`;
    console.log('[ERCaseDetail] Connecting to WebSocket:', wsUrl);
    const ws = new WebSocket(wsUrl);

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
          setTimeline(data.analysis.events || []);
          setTimelineSummary(data.analysis.timeline_summary || '');
          setTimelineGaps(data.analysis.gaps_identified || []);
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
          setViolations(data.analysis.violations || []);
          setViolationSummary(data.analysis.summary || '');
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

  const handleSearch = async () => {
    if (!id || !searchQuery.trim()) return;
    setSearching(true);
    setAnalysisError(null);
    try {
      const data = await erCopilot.searchEvidence(id, searchQuery);
      setSearchResults(data.results);
    } catch (err: unknown) {
      console.error('Search failed:', err);
      setAnalysisError(getErrorMessage(err, 'Search failed. Please try again.'));
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

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
      const timelineOk = await handleGenerateTimeline();
      const discrepanciesOk = shouldRunDiscrepancies ? await handleGenerateDiscrepancies() : false;
      const policyOk = await handleRunPolicyCheck();

      const timelineResult = timelineOk ? await erCopilot.getTimeline(id).catch(() => null) : null;
      const discrepancyResult = shouldRunDiscrepancies && discrepanciesOk
        ? await erCopilot.getDiscrepancies(id).catch(() => null)
        : null;
      const policyResult = policyOk ? await erCopilot.getPolicyCheck(id).catch(() => null) : null;

      const discrepancyCount = discrepancyResult?.analysis?.discrepancies?.length ?? 0;
      const violationCount = policyResult?.analysis?.violations?.length ?? 0;
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

      const normalizedDiscrepancies = normalizeDiscrepancies(discrepancyResult?.analysis?.discrepancies);
      const timelineGaps = Array.isArray(timelineResult?.analysis?.gaps_identified)
        ? timelineResult?.analysis?.gaps_identified
        : [];
      const suggestedGuidance = buildSuggestedGuidance({
        reviewedDocCount: completedNonPolicyDocs.length,
        reviewedDocNames: completedNonPolicyDocs.map((doc) => doc.filename).filter(Boolean),
        shouldRunDiscrepancies,
        timelineSummary: timelineResult?.analysis?.timeline_summary || '',
        timelineGaps,
        discrepancies: normalizedDiscrepancies,
        discrepancySummary: discrepancyResult?.analysis?.summary || '',
        violations: policyResult?.analysis?.violations || [],
        policySummary: policyResult?.analysis?.summary || '',
        reviewSucceeded,
        objective: intakeContext?.answers?.objective,
        immediateRisk: intakeContext?.answers?.immediate_risk,
      });

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
        content: suggestedGuidance,
        metadata: {
          source: 'assistance_auto_review',
          note_purpose: 'next_steps',
          guidance_version: 2,
          reviewed_doc_ids: reviewedDocIds,
          timeline_ok: timelineOk,
          discrepancies_ok: shouldRunDiscrepancies ? discrepanciesOk : null,
          policy_ok: policyOk,
          violation_count: violationCount,
          discrepancy_count: discrepancyCount,
        },
      });

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
        },
      };

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
              {latestGuidanceNote ? (
                <div className="border border-emerald-200 bg-emerald-50 p-2.5 rounded-sm">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] uppercase tracking-wide text-emerald-700">Next Steps</span>
                    <span className="text-[10px] text-zinc-400">
                      {new Date(latestGuidanceNote.created_at).toLocaleString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        hour: 'numeric',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-700 whitespace-pre-wrap leading-relaxed">{latestGuidanceNote.content}</p>
                </div>
              ) : (
                <p className="text-xs text-zinc-400">No guidance yet. Complete assistance intake and analysis to generate next steps.</p>
              )}
            </div>
          )}

          {showAssistancePanel && (
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
          <div className="w-full max-w-md bg-white shadow-2xl rounded-sm flex flex-col">
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
    </div>
  );
}

export default ERCaseDetail;
