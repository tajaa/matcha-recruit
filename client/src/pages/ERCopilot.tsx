import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { erCopilot } from '../api/client';
import type {
  ERCase,
  ERCaseCategory,
  ERCaseCreate,
  ERCaseIntakeContext,
  ERCaseStatus,
  ERDocumentType,
  ERIntakeImmediateRisk,
  ERIntakeObjective,
} from '../types';
import { FileUpload } from '../components';
import { X, ChevronRight, ArrowLeft } from 'lucide-react';
import { FeatureGuideTrigger } from '../features/feature-guides';
import { LifecycleWizard } from '../components/LifecycleWizard';
import { useIsLightMode } from '../hooks/useIsLightMode';

// ─── theme ────────────────────────────────────────────────────────────────────

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  cardBg: 'bg-stone-100',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  border: 'border-stone-200',
  divide: 'divide-stone-200',
  rowHover: 'hover:bg-stone-50',
  label: 'text-[10px] text-stone-500 uppercase tracking-wider',
  input: 'bg-white border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:border-stone-400',
  select: 'bg-white border border-stone-300 rounded-xl text-zinc-900 focus:border-stone-400',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  modalBg: 'bg-stone-100 rounded-2xl',
  modalHeader: 'border-b border-stone-200',
  modalFooter: 'border-t border-stone-200',
  tabBorder: 'border-b border-stone-200',
  tabActive: 'border-zinc-900 text-zinc-900',
  tabInactive: 'border-transparent text-stone-400 hover:text-stone-600',
  statusColors: {
    open: 'text-zinc-900',
    in_review: 'text-stone-600',
    pending_determination: 'text-stone-500',
    closed: 'text-stone-400',
  } as Record<ERCaseStatus, string>,
  statusDots: {
    open: 'bg-zinc-900',
    in_review: 'bg-stone-500',
    pending_determination: 'bg-stone-400',
    closed: 'bg-stone-300',
  } as Record<ERCaseStatus, string>,
};

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardBg: 'bg-zinc-900/50',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  border: 'border-white/10',
  divide: 'divide-white/10',
  rowHover: 'hover:bg-white/5',
  label: 'text-[10px] text-zinc-500 uppercase tracking-wider',
  input: 'bg-zinc-800 border border-white/10 text-zinc-100 rounded-xl placeholder:text-zinc-600 focus:border-white/20',
  select: 'bg-zinc-800 border border-white/10 rounded-xl text-zinc-100 focus:border-white/20',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600',
  btnGhost: 'text-zinc-600 hover:text-zinc-100',
  modalBg: 'bg-zinc-900 border border-white/10 rounded-2xl',
  modalHeader: 'border-b border-white/10',
  modalFooter: 'border-t border-white/10',
  tabBorder: 'border-b border-white/10',
  tabActive: 'border-zinc-100 text-zinc-100',
  tabInactive: 'border-transparent text-zinc-600 hover:text-zinc-400',
  statusColors: {
    open: 'text-zinc-100',
    in_review: 'text-zinc-400',
    pending_determination: 'text-zinc-500',
    closed: 'text-zinc-700',
  } as Record<ERCaseStatus, string>,
  statusDots: {
    open: 'bg-zinc-100',
    in_review: 'bg-zinc-400',
    pending_determination: 'bg-zinc-600',
    closed: 'bg-zinc-700',
  } as Record<ERCaseStatus, string>,
};

const STATUS_TABS: { label: string; value: ERCaseStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Open', value: 'open' },
  { label: 'In Review', value: 'in_review' },
  { label: 'Pending', value: 'pending_determination' },
  { label: 'Closed', value: 'closed' },
];

const DARK_STATUS_DOTS: Record<string, string> = {
  open: 'bg-zinc-100',
  in_review: 'bg-zinc-400',
  pending_determination: 'bg-zinc-600',
  closed: 'bg-zinc-700',
};

const DARK_STATUS_COLORS: Record<string, string> = {
  open: 'text-zinc-100',
  in_review: 'text-zinc-400',
  pending_determination: 'text-zinc-500',
  closed: 'text-zinc-700',
};


const STATUS_LABELS: Record<ERCaseStatus, string> = {
  open: 'Open',
  in_review: 'In Review',
  pending_determination: 'Pending',
  closed: 'Closed',
};

const DOC_TYPE_OPTIONS: { value: ERDocumentType; label: string }[] = [
  { value: 'transcript', label: 'Interview Transcript' },
  { value: 'policy', label: 'Policy Document' },
  { value: 'email', label: 'Email/Communication' },
  { value: 'other', label: 'Other Evidence' },
];

const CATEGORY_OPTIONS: { value: ERCaseCategory; label: string }[] = [
  { value: 'harassment', label: 'Harassment' },
  { value: 'discrimination', label: 'Discrimination' },
  { value: 'safety', label: 'Safety' },
  { value: 'retaliation', label: 'Retaliation' },
  { value: 'policy_violation', label: 'Policy Violation' },
  { value: 'misconduct', label: 'Misconduct' },
  { value: 'wage_hour', label: 'Wage & Hour' },
  { value: 'other', label: 'Other' },
];

type CreateStep = 'details' | 'documents_prompt' | 'documents_upload' | 'assistance_prompt' | 'assistance_questions';

const DEFAULT_FORM: ERCaseCreate = {
  title: '',
  description: '',
};

const DEFAULT_ASSISTANCE = {
  immediateRisk: 'unsure' as ERIntakeImmediateRisk,
  objective: 'general' as ERIntakeObjective,
  complaintFormat: 'unknown' as 'verbal' | 'written' | 'both' | 'unknown',
  witnesses: '',
  notes: '',
};

const STEP_TITLES: Record<CreateStep, string> = {
  details: 'New Investigation Case',
  documents_prompt: 'Next Step',
  documents_upload: 'Upload Documents',
  assistance_prompt: 'Investigation Assistance',
  assistance_questions: 'Assistance Intake',
};

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

function getPrimaryAssistanceQuestion(description: string): string {
  const text = description.toLowerCase();
  if (text.includes('harass') || text.includes('discrimin') || text.includes('retaliat')) {
    return 'Was the complaint made verbally or in writing?';
  }
  return 'How was the concern initially reported (verbally, in writing, or both)?';
}

function formatComplaintFormat(value: 'verbal' | 'written' | 'both' | 'unknown'): string {
  if (value === 'written') return 'In writing';
  if (value === 'verbal') return 'Verbally';
  if (value === 'both') return 'Both verbal and written';
  return 'Unknown';
}

function buildInitialGuidance(description: string): string {
  return [
    `Intake summary: ${description.trim()}`,
    'Initial recommendation: Preserve evidence and collect the original complaint document if available.',
    'Next step: Upload the complaint and any related communications so ER Copilot can provide targeted follow-up guidance.',
  ].join('\n');
}

const ER_CYCLE_STEPS = [
  {
    id: 1,
    icon: 'intake' as const,
    title: 'Intake Case',
    description: 'Open a new case with a clear title and a description of the allegation or concern.',
    action: 'Click "New Case" to begin the intake process.',
  },
  {
    id: 2,
    icon: 'evidence' as const,
    title: 'Collect Evidence',
    description: 'Upload transcripts, emails, and policies. The more data you provide, the better the AI guidance.',
    action: 'Use the "Upload" tool within a case record.',
  },
  {
    id: 3,
    icon: 'guidance' as const,
    title: 'AI Guidance',
    description: 'The Copilot auto-reviews your intake and evidence to provide immediate preservation and next-step tips.',
    action: 'Check the "Assistance" tab in the case detail view.',
  },
  {
    id: 4,
    icon: 'analysis' as const,
    title: 'Deep Analysis',
    description: 'Use AI to build timelines, find inconsistencies in testimony, and flag potential policy violations.',
    action: 'Review "Case Notes" and AI-generated timelines.',
  },
  {
    id: 5,
    icon: 'decision' as const,
    title: 'Final Decision',
    description: 'Synthesize all evidence and AI insights to reach a determination and officially close the case record.',
    action: 'Update the case status to "Closed" once resolved.',
  },
];

export function ERCopilot() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const navigate = useNavigate();
  const [cases, setCases] = useState<ERCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<ERCaseStatus | 'all'>('all');

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createStep, setCreateStep] = useState<CreateStep>('details');
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [savingAssistance, setSavingAssistance] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createdCaseId, setCreatedCaseId] = useState<string | null>(null);
  const [uploadedCount, setUploadedCount] = useState(0);

  const [formData, setFormData] = useState<ERCaseCreate>(DEFAULT_FORM);
  const [uploadDocType, setUploadDocType] = useState<ERDocumentType>('transcript');
  const [assistanceData, setAssistanceData] = useState(DEFAULT_ASSISTANCE);

  const fetchCases = useCallback(async () => {
    try {
      setLoading(true);
      const status = activeTab !== 'all' ? activeTab : undefined;
      const response = await erCopilot.listCases(status);
      setCases(response.cases);
    } catch (err) {
      console.error('Failed to fetch cases:', err);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    fetchCases();
  }, [fetchCases]);

  const resetCreateFlow = () => {
    setShowCreateModal(false);
    setCreateStep('details');
    setCreateError(null);
    setCreatedCaseId(null);
    setUploadedCount(0);
    setFormData(DEFAULT_FORM);
    setUploadDocType('transcript');
    setAssistanceData(DEFAULT_ASSISTANCE);
    setCreating(false);
    setUploading(false);
    setSavingAssistance(false);
  };

  const openCreateModal = () => {
    setCreateStep('details');
    setCreateError(null);
    setCreatedCaseId(null);
    setUploadedCount(0);
    setFormData(DEFAULT_FORM);
    setUploadDocType('transcript');
    setAssistanceData(DEFAULT_ASSISTANCE);
    setShowCreateModal(true);
  };

  const handleCreateDetails = async () => {
    if (!formData.title?.trim() || !formData.description?.trim()) {
      return;
    }

    setCreating(true);
    setCreateError(null);
    try {
      const created = await erCopilot.createCase({
        title: formData.title.trim(),
        description: formData.description.trim(),
        category: formData.category || undefined,
      });
      setCreatedCaseId(created.id);
      setCreateStep('documents_prompt');
      await fetchCases();
    } catch (err: unknown) {
      console.error('Failed to create case:', err);
      setCreateError(getErrorMessage(err, 'Failed to create case. Please try again.'));
    } finally {
      setCreating(false);
    }
  };

  const handleGoToCase = async (withAssistance: boolean) => {
    if (!createdCaseId) return;
    await fetchCases();
    const caseId = createdCaseId;
    resetCreateFlow();
    navigate(withAssistance
      ? `/app/matcha/er-copilot/${caseId}?assistance=auto`
      : `/app/matcha/er-copilot/${caseId}`);
  };

  const handleUploadDocuments = async (files: File[]) => {
    if (!createdCaseId || files.length === 0) return;

    setUploading(true);
    setCreateError(null);
    try {
      for (const file of files) {
        await erCopilot.uploadDocument(createdCaseId, file, uploadDocType);
      }
      setUploadedCount((prev) => prev + files.length);
      setCreateStep('assistance_prompt');
    } catch (err: unknown) {
      console.error('Failed to upload documents:', err);
      setCreateError(getErrorMessage(err, 'Upload failed. Please try again.'));
    } finally {
      setUploading(false);
    }
  };

  const handleSaveAssistanceIntake = async () => {
    if (!createdCaseId) return;
    const primaryQuestion = getPrimaryAssistanceQuestion(formData.description || '');

    const intakeContext: ERCaseIntakeContext = {
      assistance_requested: true,
      no_documents_at_intake: uploadedCount === 0,
      captured_at: new Date().toISOString(),
      assistance: {
        mode: 'auto',
        last_reviewed_signature: '',
        last_reviewed_doc_ids: [],
      },
      answers: {
        immediate_risk: assistanceData.immediateRisk,
        objective: assistanceData.objective,
        complaint_format: assistanceData.complaintFormat,
        witnesses: assistanceData.witnesses.trim() || undefined,
        additional_notes: assistanceData.notes.trim() || undefined,
      },
    };

    setSavingAssistance(true);
    setCreateError(null);
    try {
      await erCopilot.updateCase(createdCaseId, { intake_context: intakeContext });
      const intakeNotes = [
        {
          note_type: 'question' as const,
          content: primaryQuestion,
          metadata: { source: 'assistance_intake', question_key: 'complaint_format' },
        },
        {
          note_type: 'answer' as const,
          content: formatComplaintFormat(assistanceData.complaintFormat),
          metadata: { source: 'assistance_intake', question_key: 'complaint_format' },
        },
        {
          note_type: 'question' as const,
          content: 'Is there any immediate safety risk or retaliation concern?',
          metadata: { source: 'assistance_intake', question_key: 'immediate_risk' },
        },
        {
          note_type: 'answer' as const,
          content: assistanceData.immediateRisk,
          metadata: { source: 'assistance_intake', question_key: 'immediate_risk' },
        },
        {
          note_type: 'question' as const,
          content: 'What is your primary objective for assistance?',
          metadata: { source: 'assistance_intake', question_key: 'objective' },
        },
        {
          note_type: 'answer' as const,
          content: assistanceData.objective,
          metadata: { source: 'assistance_intake', question_key: 'objective' },
        },
      ];

      if (assistanceData.witnesses.trim()) {
        intakeNotes.push(
          {
            note_type: 'question',
            content: 'Who are known witnesses at intake?',
            metadata: { source: 'assistance_intake', question_key: 'witnesses' },
          },
          {
            note_type: 'answer',
            content: assistanceData.witnesses.trim(),
            metadata: { source: 'assistance_intake', question_key: 'witnesses' },
          }
        );
      }

      if (assistanceData.notes.trim()) {
        intakeNotes.push(
          {
            note_type: 'question',
            content: 'Additional intake notes',
            metadata: { source: 'assistance_intake', question_key: 'additional_notes' },
          },
          {
            note_type: 'answer',
            content: assistanceData.notes.trim(),
            metadata: { source: 'assistance_intake', question_key: 'additional_notes' },
          }
        );
      }

      for (const note of intakeNotes) {
        await erCopilot.createCaseNote(createdCaseId, note);
      }

      if (uploadedCount === 0 && formData.description?.trim()) {
        await erCopilot.createCaseNote(createdCaseId, {
          note_type: 'guidance',
          content: buildInitialGuidance(formData.description),
          metadata: { source: 'assistance_initial', auto_generated: true },
        });
      }

      await handleGoToCase(true);
    } catch (err: unknown) {
      console.error('Failed to save assistance intake:', err);
      setCreateError(getErrorMessage(err, 'Could not start investigation assistance. Please try again.'));
    } finally {
      setSavingAssistance(false);
    }
  };

  const handleBackStep = () => {
    if (createStep === 'documents_prompt') {
      setCreateStep('details');
      return;
    }
    if (createStep === 'documents_upload') {
      setCreateStep('documents_prompt');
      return;
    }
    if (createStep === 'assistance_prompt') {
      setCreateStep('documents_prompt');
      return;
    }
    if (createStep === 'assistance_questions') {
      setCreateStep('assistance_prompt');
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const isBusy = creating || uploading || savingAssistance;

  return (
    <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
    <div className="max-w-5xl mx-auto">
      <div className="flex justify-between items-start mb-12 pb-8">
        <div>
          <div className="flex items-center gap-3">
            <h1 className={`text-4xl font-bold tracking-tighter ${t.textMain} uppercase`}>ER Copilot</h1>
            <FeatureGuideTrigger guideId="er-copilot" />
          </div>
          <p className={`text-xs ${t.textMuted} mt-2 font-mono tracking-wide uppercase`}>Investigation Assistant</p>
        </div>
        <button
          data-tour="er-new-case"
          onClick={openCreateModal}
          className={`px-5 py-2 text-xs uppercase tracking-wider font-bold ${t.btnPrimary} rounded-xl transition-all`}
        >
          New Case
        </button>
      </div>

      <LifecycleWizard
        steps={ER_CYCLE_STEPS}
        activeStep={(cases.length - cases.filter(c => c.status !== 'closed').length) > 0 ? 5
                  : cases.filter(c => c.status !== 'closed').length > 0 ? 3
                  : cases.length > 0 ? 2
                  : 1}
        title="ER Cycle"
        storageKey="er-wizard-collapsed-v1"
      />

      <div data-tour="er-tabs" className={`flex gap-8 mb-px ${t.tabBorder}`}>
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`pb-3 text-[10px] font-bold uppercase tracking-widest transition-colors border-b-2 ${
              activeTab === tab.value ? t.tabActive : t.tabInactive
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center min-h-[20vh]">
          <div className={`text-xs ${t.textFaint} uppercase tracking-wider animate-pulse`}>Loading...</div>
        </div>
      ) : cases.length === 0 ? (
        <div className={`text-center py-24 border border-dashed ${t.border} ${t.cardBg} rounded-2xl mt-8`}>
          <div className={`text-xs ${t.textMuted} mb-4 font-mono uppercase tracking-wider`}>No cases found</div>
          <button
            onClick={openCreateModal}
            className={`text-xs ${t.textMain} font-bold uppercase tracking-wider underline underline-offset-4`}
          >
            Create first case
          </button>
        </div>
      ) : (
        <div data-tour="er-case-list" className="bg-zinc-900 rounded-2xl overflow-hidden mt-8">
          <div className="flex items-center gap-4 py-3 px-4 text-[10px] text-zinc-600 uppercase tracking-widest font-bold border-b border-zinc-800">
            <div className="w-8"></div>
            <div className="w-24">ID</div>
            <div className="flex-1">Title</div>
            <div className="w-32">Status</div>
            <div className="w-24 text-right">Created</div>
            <div className="w-8"></div>
          </div>

          <div className="divide-y divide-zinc-800">
          {cases.map((erCase) => (
            <div
              data-tour="er-case-row"
              key={erCase.id}
              className="group flex items-center gap-4 py-4 px-4 cursor-pointer hover:bg-white/5 transition-colors"
              onClick={() => navigate(`/app/matcha/er-copilot/${erCase.id}`)}
            >
              <div className="w-8 flex justify-center">
                <div className={`w-1.5 h-1.5 rounded-full ${DARK_STATUS_DOTS[erCase.status] || 'bg-zinc-600'}`} />
              </div>

              <div className="w-24 text-[10px] text-zinc-500 font-mono">
                {erCase.case_number}
              </div>

              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-bold text-zinc-100 truncate">
                  {erCase.title}
                </h3>
                {erCase.description && (
                  <p className="text-[10px] text-zinc-600 mt-1 truncate max-w-lg font-mono">{erCase.description}</p>
                )}
              </div>

              <div data-tour="er-status-col" className={`w-32 text-[10px] font-bold uppercase tracking-wider ${DARK_STATUS_COLORS[erCase.status]}`}>
                {STATUS_LABELS[erCase.status]}
              </div>

              <div className="w-24 text-right text-[10px] text-zinc-500 font-mono">
                {formatDate(erCase.created_at)}
              </div>

              <div className="w-8 flex justify-center text-zinc-600 group-hover:text-zinc-400">
                <ChevronRight className="w-4 h-4" />
              </div>
            </div>
          ))}
          </div>
        </div>
      )}

      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className={`w-full max-w-lg ${t.modalBg} shadow-2xl flex flex-col`}>
            <div className={`flex items-center justify-between px-6 py-5 ${t.modalHeader}`}>
              <h3 className={`text-sm font-bold ${t.textMain} uppercase tracking-wider`}>{STEP_TITLES[createStep]}</h3>
              <button
                onClick={resetCreateFlow}
                className={`${t.btnGhost} transition-colors disabled:opacity-40`}
                disabled={isBusy}
              >
                <X size={20} />
              </button>
            </div>

            {createError && (
              <div className="px-6 pt-4 text-xs text-red-600 uppercase tracking-wide">
                {createError}
              </div>
            )}

            <div className="px-6 py-6 space-y-5">
              {createStep === 'details' && (
                <>
                  <div>
                    <label className={`block ${t.label} mb-2`}>Case Title</label>
                    <input
                      type="text"
                      value={formData.title}
                      onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                      placeholder="e.g., Harassment Allegation - Sales Team"
                      className={`w-full ${t.input} text-sm px-3.5 py-2.5 focus:outline-none transition-colors`}
                      autoFocus
                    />
                  </div>

                  <div>
                    <label className={`block ${t.label} mb-2`}>Description</label>
                    <textarea
                      value={formData.description || ''}
                      onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                      placeholder="Brief summary of the allegation or incident..."
                      rows={4}
                      className={`w-full ${t.input} text-sm px-3.5 py-2.5 focus:outline-none resize-none transition-colors`}
                    />
                  </div>

                  <div>
                    <label className={`block ${t.label} mb-2`}>Category</label>
                    <select
                      value={formData.category || ''}
                      onChange={(e) => setFormData({ ...formData, category: (e.target.value || undefined) as ERCaseCategory | undefined })}
                      className={`w-full ${t.select} text-sm px-3 py-2.5 focus:outline-none`}
                    >
                      <option value="">Select category...</option>
                      {CATEGORY_OPTIONS.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                </>
              )}

              {createStep === 'documents_prompt' && (
                <div className="space-y-4">
                  <p className={`text-sm ${t.textMain}`}>Do you have any documents to upload?</p>
                  <p className={`text-xs ${t.textMuted} uppercase tracking-wide`}>
                    You can upload interviews, emails, policies, or other evidence now.
                  </p>
                </div>
              )}

              {createStep === 'documents_upload' && (
                <div className="space-y-4">
                  <div>
                    <label className={`block ${t.label} mb-1.5`}>Document Type</label>
                    <select
                      value={uploadDocType}
                      onChange={(e) => setUploadDocType(e.target.value as ERDocumentType)}
                      className={`w-full ${t.select} text-sm px-3 py-2 focus:outline-none`}
                      disabled={uploading}
                    >
                      {DOC_TYPE_OPTIONS.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>

                  <FileUpload
                    accept=".pdf,.docx,.doc,.txt,.csv,.json"
                    onUpload={handleUploadDocuments}
                    multiple={true}
                    disabled={uploading}
                    label={uploading ? 'Uploading...' : 'Drop files here or click to select'}
                    description="Supports PDF, DOCX, TXT, CSV, JSON"
                  />

                  <p className={`text-[10px] ${t.textMuted} uppercase tracking-wide`}>
                    Upload now, then choose whether to start investigation assistance.
                  </p>
                  {uploadedCount > 0 && (
                    <p className={`text-[10px] ${t.textMain} uppercase tracking-wide`}>
                      Uploaded {uploadedCount} file{uploadedCount === 1 ? '' : 's'}.
                    </p>
                  )}
                </div>
              )}

              {createStep === 'assistance_prompt' && (
                <div className="space-y-4">
                  <p className={`text-sm ${t.textMain}`}>Would you like investigation assistance?</p>
                  <p className={`text-xs ${t.textMuted} uppercase tracking-wide`}>
                    {uploadedCount > 0
                      ? 'We can auto-review uploaded evidence and keep updating guidance as new documents are added.'
                      : 'We can start from your description and keep updating guidance as documents are uploaded later.'}
                  </p>
                </div>
              )}

              {createStep === 'assistance_questions' && (
                <div className="space-y-4">
                  <div>
                    <label className={`block ${t.label} mb-1.5`}>
                      {getPrimaryAssistanceQuestion(formData.description || '')}
                    </label>
                    <select
                      value={assistanceData.complaintFormat}
                      onChange={(e) => setAssistanceData({
                        ...assistanceData,
                        complaintFormat: e.target.value as 'verbal' | 'written' | 'both' | 'unknown',
                      })}
                      className={`w-full ${t.select} text-sm px-3 py-2 focus:outline-none`}
                    >
                      <option value="unknown">Unknown</option>
                      <option value="written">In writing</option>
                      <option value="verbal">Verbally</option>
                      <option value="both">Both</option>
                    </select>
                  </div>

                  <div>
                    <label className={`block ${t.label} mb-1.5`}>
                      Immediate Safety Risk?
                    </label>
                    <select
                      value={assistanceData.immediateRisk}
                      onChange={(e) => setAssistanceData({
                        ...assistanceData,
                        immediateRisk: e.target.value as ERIntakeImmediateRisk,
                      })}
                      className={`w-full ${t.select} text-sm px-3 py-2 focus:outline-none`}
                    >
                      <option value="unsure">Unsure</option>
                      <option value="yes">Yes</option>
                      <option value="no">No</option>
                    </select>
                  </div>

                  <div>
                    <label className={`block ${t.label} mb-1.5`}>
                      Primary Goal
                    </label>
                    <select
                      value={assistanceData.objective}
                      onChange={(e) => setAssistanceData({
                        ...assistanceData,
                        objective: e.target.value as ERIntakeObjective,
                      })}
                      className={`w-full ${t.select} text-sm px-3 py-2 focus:outline-none`}
                    >
                      <option value="general">General guidance</option>
                      <option value="timeline">Build timeline first</option>
                      <option value="discrepancies">Find inconsistencies</option>
                      <option value="policy">Check policy risks</option>
                    </select>
                  </div>

                  <div>
                    <label className={`block ${t.label} mb-1.5`}>
                      Known Witnesses (Optional)
                    </label>
                    <input
                      type="text"
                      value={assistanceData.witnesses}
                      onChange={(e) => setAssistanceData({ ...assistanceData, witnesses: e.target.value })}
                      placeholder="Names or roles"
                      className={`w-full ${t.input} text-sm px-3.5 py-2.5 focus:outline-none transition-colors`}
                    />
                  </div>

                  <div>
                    <label className={`block ${t.label} mb-1.5`}>
                      Notes (Optional)
                    </label>
                    <textarea
                      value={assistanceData.notes}
                      onChange={(e) => setAssistanceData({ ...assistanceData, notes: e.target.value })}
                      rows={3}
                      placeholder="Anything the copilot should prioritize"
                      className={`w-full ${t.input} text-sm px-3.5 py-2.5 focus:outline-none resize-none transition-colors`}
                    />
                  </div>
                </div>
              )}
            </div>

            <div className={`flex justify-between items-center px-6 py-4 ${t.modalFooter}`}>
              <div>
                {createStep !== 'details' ? (
                  <button
                    onClick={handleBackStep}
                    disabled={isBusy}
                    className={`px-4 py-2 ${t.btnGhost} text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-40 flex items-center gap-1`}
                  >
                    <ArrowLeft size={12} />
                    Back
                  </button>
                ) : (
                  <button
                    onClick={resetCreateFlow}
                    disabled={isBusy}
                    className={`px-4 py-2 ${t.btnGhost} text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-40`}
                  >
                    Cancel
                  </button>
                )}
              </div>

              {createStep === 'details' && (
                <button
                  onClick={handleCreateDetails}
                  disabled={creating || !formData.title?.trim() || !formData.description?.trim()}
                  className={`px-5 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {creating ? 'Creating...' : 'Continue'}
                </button>
              )}

              {createStep === 'documents_prompt' && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setCreateStep('assistance_prompt')}
                    className={`px-4 py-2 ${t.btnGhost} text-xs font-bold uppercase tracking-wider transition-colors`}
                  >
                    No
                  </button>
                  <button
                    onClick={() => setCreateStep('documents_upload')}
                    className={`px-5 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-all`}
                  >
                    Yes, Upload
                  </button>
                </div>
              )}

              {createStep === 'documents_upload' && (
                <button
                  onClick={() => setCreateStep('assistance_prompt')}
                  disabled={uploading}
                  className={`px-4 py-2 ${t.btnGhost} text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-40`}
                >
                  Skip Upload
                </button>
              )}

              {createStep === 'assistance_prompt' && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleGoToCase(false)}
                    className={`px-4 py-2 ${t.btnGhost} text-xs font-bold uppercase tracking-wider transition-colors`}
                  >
                    No
                  </button>
                  <button
                    onClick={() => setCreateStep('assistance_questions')}
                    className={`px-5 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-all`}
                  >
                    Yes
                  </button>
                </div>
              )}

              {createStep === 'assistance_questions' && (
                <button
                  onClick={handleSaveAssistanceIntake}
                  disabled={savingAssistance}
                  className={`px-5 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {savingAssistance ? 'Starting...' : 'Start Assistance'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
    </div>
  );
}

export default ERCopilot;
