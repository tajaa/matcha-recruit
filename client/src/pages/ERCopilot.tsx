import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { erCopilot } from '../api/client';
import type {
  ERCase,
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

const STATUS_TABS: { label: string; value: ERCaseStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Open', value: 'open' },
  { label: 'In Review', value: 'in_review' },
  { label: 'Pending', value: 'pending_determination' },
  { label: 'Closed', value: 'closed' },
];

const STATUS_COLORS: Record<ERCaseStatus, string> = {
  open: 'text-white',
  in_review: 'text-amber-400',
  pending_determination: 'text-orange-400',
  closed: 'text-zinc-500',
};

const STATUS_DOTS: Record<ERCaseStatus, string> = {
  open: 'bg-white',
  in_review: 'bg-amber-500',
  pending_determination: 'bg-orange-500',
  closed: 'bg-zinc-700',
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

// ─── ER Lifecycle Wizard ──────────────────────────────────────────────────────

type ERStepIcon = 'intake' | 'evidence' | 'guidance' | 'analysis' | 'decision';

type ERWizardStep = {
  id: number;
  icon: ERStepIcon;
  title: string;
  description: string;
  action?: string;
};

const ER_CYCLE_STEPS: ERWizardStep[] = [
  {
    id: 1,
    icon: 'intake',
    title: 'Intake Case',
    description: 'Open a new case with a clear title and a description of the allegation or concern.',
    action: 'Click "New Case" to begin the intake process.',
  },
  {
    id: 2,
    icon: 'evidence',
    title: 'Collect Evidence',
    description: 'Upload transcripts, emails, and policies. The more data you provide, the better the AI guidance.',
    action: 'Use the "Upload" tool within a case record.',
  },
  {
    id: 3,
    icon: 'guidance',
    title: 'AI Guidance',
    description: 'The Copilot auto-reviews your intake and evidence to provide immediate preservation and next-step tips.',
    action: 'Check the "Assistance" tab in the case detail view.',
  },
  {
    id: 4,
    icon: 'analysis',
    title: 'Deep Analysis',
    description: 'Use AI to build timelines, find inconsistencies in testimony, and flag potential policy violations.',
    action: 'Review "Case Notes" and AI-generated timelines.',
  },
  {
    id: 5,
    icon: 'decision',
    title: 'Final Decision',
    description: 'Synthesize all evidence and AI insights to reach a determination and officially close the case record.',
    action: 'Update the case status to "Closed" once resolved.',
  },
];

function ERCycleIcon({ icon, className = '' }: { icon: ERStepIcon; className?: string }) {
  const common = { className, width: 16, height: 16, viewBox: '0 0 20 20', fill: 'none', 'aria-hidden': true as const };
  
  if (icon === 'intake') {
    return (
      <svg {...common}>
        <path d="M10 5V15M5 10H15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  if (icon === 'evidence') {
    return (
      <svg {...common}>
        <path d="M4 10L10 4L16 10M10 4V16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (icon === 'guidance') {
    return (
      <svg {...common}>
        <rect x="5" y="5" width="10" height="10" rx="1" stroke="currentColor" strokeWidth="1.6" />
        <path d="M10 8V12M8 10H12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (icon === 'analysis') {
    return (
      <svg {...common}>
        <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.6" />
        <path d="M10 10L13 13M10 10V6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (icon === 'decision') {
    return (
      <svg {...common}>
        <path d="M6 10.3L8.5 12.8L14 7.3" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  return null;
}

function ERCycleWizard({ casesCount, openCasesCount }: { casesCount: number, openCasesCount: number }) {
  const storageKey = 'er-wizard-collapsed-v1';
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(storageKey) === 'true'; } catch { return false; }
  });

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem(storageKey, String(next)); } catch {}
  };

  const activeStep = (casesCount - openCasesCount) > 0 ? 5 
                  : openCasesCount > 0 ? 3
                  : casesCount > 0 ? 2
                  : 1;

  return (
    <div className="border border-white/10 bg-zinc-950/60 mb-10">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500">ER Cycle</span>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-zinc-800 border border-zinc-700 text-zinc-400">
              Step {activeStep} of 5
            </span>
            <span className="text-[10px] text-zinc-600 hidden sm:inline">
              {ER_CYCLE_STEPS[activeStep - 1].title}
            </span>
          </div>
        </div>
        <ChevronDownIcon className={`text-zinc-600 transition-transform duration-200 shrink-0 ${collapsed ? '' : 'rotate-180'}`} />
      </button>

      {!collapsed && (
        <div className="border-t border-white/10">
          <div className="relative px-5 pt-5 pb-2 overflow-x-auto no-scrollbar">
            <div className="flex items-start gap-0 min-w-max">
              {ER_CYCLE_STEPS.map((step, idx) => {
                const isComplete = step.id < activeStep;
                const isActive = step.id === activeStep;

                return (
                  <div key={step.id} className="flex items-start">
                    <div className="flex flex-col items-center w-28">
                      <div className={`relative w-9 h-9 rounded-full border-2 flex items-center justify-center text-sm transition-all ${
                        isComplete
                          ? 'bg-matcha-500/20 border-matcha-500/50 text-matcha-400'
                          : isActive
                          ? 'bg-white/10 border-white text-white shadow-[0_0_12px_rgba(255,255,255,0.15)]'
                          : 'bg-zinc-900 border-zinc-700 text-zinc-600'
                      }`}>
                        {isComplete ? '✓' : <ERCycleIcon icon={step.icon} className="w-4 h-4" />}
                      </div>
                      <div className={`mt-2 text-center text-[10px] font-bold uppercase tracking-wider leading-tight px-1 ${
                        isActive ? 'text-white' : isComplete ? 'text-matcha-400/70' : 'text-zinc-600'
                      }`}>
                        {step.title}
                      </div>
                    </div>
                    {idx < ER_CYCLE_STEPS.length - 1 && (
                      <div className={`w-10 h-0.5 mt-[18px] flex-shrink-0 transition-colors ${
                        step.id < activeStep ? 'bg-matcha-500/40' : 'bg-zinc-800'
                      }`} />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mx-5 mb-5 p-4 bg-white/[0.03] border border-white/10">
            <div className="flex items-start gap-3">
              <span className="text-xl flex-shrink-0 text-zinc-200">
                <ERCycleIcon icon={ER_CYCLE_STEPS[activeStep - 1].icon} className="w-5 h-5" />
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold text-white uppercase tracking-wider">
                    {ER_CYCLE_STEPS[activeStep - 1].title}
                  </span>
                  <span className="text-[9px] px-1.5 py-0.5 font-bold uppercase tracking-widest bg-white/10 text-zinc-400 border border-white/10">
                    Current Step
                  </span>
                </div>
                <p className="text-[11px] text-zinc-400 leading-relaxed mb-2">
                  {ER_CYCLE_STEPS[activeStep - 1].description}
                </p>
                {ER_CYCLE_STEPS[activeStep - 1].action && (
                  <p className="text-[11px] text-matcha-400/80 font-medium">
                    → {ER_CYCLE_STEPS[activeStep - 1].action}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ChevronDownIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={className}
      width="14"
      height="14"
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
    >
      <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ERCopilot() {
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
    <div className="max-w-5xl mx-auto">
      <div className="flex justify-between items-start mb-12 border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">ER Copilot</h1>
            <FeatureGuideTrigger guideId="er-copilot" />
          </div>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Investigation Assistant</p>
        </div>
        <button
          data-tour="er-new-case"
          onClick={openCreateModal}
          className="px-6 py-2 bg-white text-black text-xs font-bold hover:bg-zinc-200 uppercase tracking-wider transition-colors"
        >
          New Case
        </button>
      </div>

      <ERCycleWizard casesCount={cases.length} openCasesCount={cases.filter(c => c.status !== 'closed').length} />

      <div data-tour="er-tabs" className="flex gap-8 mb-px border-b border-white/10">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`pb-3 text-[10px] font-bold uppercase tracking-widest transition-colors border-b-2 ${
              activeTab === tab.value
                ? 'border-white text-white'
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center min-h-[20vh]">
          <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading...</div>
        </div>
      ) : cases.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-white/10 bg-white/5 mt-8">
          <div className="text-xs text-zinc-500 mb-4 font-mono uppercase tracking-wider">No cases found</div>
          <button
            onClick={openCreateModal}
            className="text-xs text-white hover:text-zinc-300 font-bold uppercase tracking-wider underline underline-offset-4"
          >
            Create first case
          </button>
        </div>
      ) : (
        <div data-tour="er-case-list" className="space-y-px bg-white/10 border border-white/10 mt-8">
          <div className="flex items-center gap-4 py-3 px-4 text-[10px] text-zinc-500 uppercase tracking-widest bg-zinc-950 border-b border-white/10">
            <div className="w-8"></div>
            <div className="w-24">ID</div>
            <div className="flex-1">Title</div>
            <div className="w-32">Status</div>
            <div className="w-24 text-right">Created</div>
            <div className="w-8"></div>
          </div>

          {cases.map((erCase) => (
            <div
              data-tour="er-case-row"
              key={erCase.id}
              className="group flex items-center gap-4 py-4 px-4 cursor-pointer bg-zinc-950 hover:bg-zinc-900 transition-colors"
              onClick={() => navigate(`/app/matcha/er-copilot/${erCase.id}`)}
            >
              <div className="w-8 flex justify-center">
                <div className={`w-1.5 h-1.5 rounded-full ${STATUS_DOTS[erCase.status] || 'bg-zinc-700'}`} />
              </div>

              <div className="w-24 text-[10px] text-zinc-500 font-mono group-hover:text-zinc-400">
                {erCase.case_number}
              </div>

              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-bold text-white truncate group-hover:text-zinc-300">
                  {erCase.title}
                </h3>
                {erCase.description && (
                  <p className="text-[10px] text-zinc-500 mt-1 truncate max-w-lg font-mono">{erCase.description}</p>
                )}
              </div>

              <div data-tour="er-status-col" className={`w-32 text-[10px] font-bold uppercase tracking-wider ${STATUS_COLORS[erCase.status]}`}>
                {STATUS_LABELS[erCase.status]}
              </div>

              <div className="w-24 text-right text-[10px] text-zinc-500 font-mono">
                {formatDate(erCase.created_at)}
              </div>

              <div className="w-8 flex justify-center text-zinc-600 group-hover:text-white">
                <ChevronRight className="w-4 h-4" />
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-zinc-950 border border-zinc-800 shadow-2xl flex flex-col">
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">{STEP_TITLES[createStep]}</h3>
              <button
                onClick={resetCreateFlow}
                className="text-zinc-500 hover:text-white transition-colors disabled:opacity-40"
                disabled={isBusy}
              >
                <X size={20} />
              </button>
            </div>

            {createError && (
              <div className="px-6 pt-4 text-xs text-red-400 uppercase tracking-wide">
                {createError}
              </div>
            )}

            <div className="p-8 space-y-6">
              {createStep === 'details' && (
                <>
                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Case Title</label>
                    <input
                      type="text"
                      value={formData.title}
                      onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                      placeholder="e.g., Harassment Allegation - Sales Team"
                      className="w-full px-0 py-2 bg-transparent border-b border-zinc-800 text-white placeholder-zinc-600 text-sm focus:outline-none focus:border-white transition-colors"
                      autoFocus
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Description</label>
                    <textarea
                      value={formData.description || ''}
                      onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                      placeholder="Brief summary of the allegation or incident..."
                      rows={4}
                      className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white placeholder-zinc-600 text-sm focus:outline-none focus:border-white/20 resize-none transition-colors"
                    />
                  </div>
                </>
              )}

              {createStep === 'documents_prompt' && (
                <div className="space-y-4">
                  <p className="text-sm text-zinc-200">Do you have any documents to upload?</p>
                  <p className="text-xs text-zinc-500 uppercase tracking-wide">
                    You can upload interviews, emails, policies, or other evidence now.
                  </p>
                </div>
              )}

              {createStep === 'documents_upload' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">Document Type</label>
                    <select
                      value={uploadDocType}
                      onChange={(e) => setUploadDocType(e.target.value as ERDocumentType)}
                      className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-zinc-500"
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

                  <p className="text-[10px] text-zinc-500 uppercase tracking-wide">
                    Upload now, then choose whether to start investigation assistance.
                  </p>
                  {uploadedCount > 0 && (
                    <p className="text-[10px] text-emerald-400 uppercase tracking-wide">
                      Uploaded {uploadedCount} file{uploadedCount === 1 ? '' : 's'}.
                    </p>
                  )}
                </div>
              )}

              {createStep === 'assistance_prompt' && (
                <div className="space-y-4">
                  <p className="text-sm text-zinc-200">Would you like investigation assistance?</p>
                  <p className="text-xs text-zinc-500 uppercase tracking-wide">
                    {uploadedCount > 0
                      ? 'We can auto-review uploaded evidence and keep updating guidance as new documents are added.'
                      : 'We can start from your description and keep updating guidance as documents are uploaded later.'}
                  </p>
                </div>
              )}

              {createStep === 'assistance_questions' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                      {getPrimaryAssistanceQuestion(formData.description || '')}
                    </label>
                    <select
                      value={assistanceData.complaintFormat}
                      onChange={(e) => setAssistanceData({
                        ...assistanceData,
                        complaintFormat: e.target.value as 'verbal' | 'written' | 'both' | 'unknown',
                      })}
                      className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-zinc-500"
                    >
                      <option value="unknown">Unknown</option>
                      <option value="written">In writing</option>
                      <option value="verbal">Verbally</option>
                      <option value="both">Both</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                      Immediate Safety Risk?
                    </label>
                    <select
                      value={assistanceData.immediateRisk}
                      onChange={(e) => setAssistanceData({
                        ...assistanceData,
                        immediateRisk: e.target.value as ERIntakeImmediateRisk,
                      })}
                      className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-zinc-500"
                    >
                      <option value="unsure">Unsure</option>
                      <option value="yes">Yes</option>
                      <option value="no">No</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                      Primary Goal
                    </label>
                    <select
                      value={assistanceData.objective}
                      onChange={(e) => setAssistanceData({
                        ...assistanceData,
                        objective: e.target.value as ERIntakeObjective,
                      })}
                      className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-sm text-zinc-100 focus:outline-none focus:border-zinc-500"
                    >
                      <option value="general">General guidance</option>
                      <option value="timeline">Build timeline first</option>
                      <option value="discrepancies">Find inconsistencies</option>
                      <option value="policy">Check policy risks</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                      Known Witnesses (Optional)
                    </label>
                    <input
                      type="text"
                      value={assistanceData.witnesses}
                      onChange={(e) => setAssistanceData({ ...assistanceData, witnesses: e.target.value })}
                      placeholder="Names or roles"
                      className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white placeholder-zinc-600 text-sm focus:outline-none focus:border-zinc-500"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                      Notes (Optional)
                    </label>
                    <textarea
                      value={assistanceData.notes}
                      onChange={(e) => setAssistanceData({ ...assistanceData, notes: e.target.value })}
                      rows={3}
                      placeholder="Anything the copilot should prioritize"
                      className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white placeholder-zinc-600 text-sm focus:outline-none focus:border-zinc-500 resize-none"
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-between items-center p-6 border-t border-white/10 bg-zinc-900/50">
              <div>
                {createStep !== 'details' ? (
                  <button
                    onClick={handleBackStep}
                    disabled={isBusy}
                    className="px-4 py-2 text-zinc-500 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-40 flex items-center gap-1"
                  >
                    <ArrowLeft size={12} />
                    Back
                  </button>
                ) : (
                  <button
                    onClick={resetCreateFlow}
                    disabled={isBusy}
                    className="px-4 py-2 text-zinc-500 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-40"
                  >
                    Cancel
                  </button>
                )}
              </div>

              {createStep === 'details' && (
                <button
                  onClick={handleCreateDetails}
                  disabled={creating || !formData.title?.trim() || !formData.description?.trim()}
                  className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {creating ? 'Creating...' : 'Continue'}
                </button>
              )}

              {createStep === 'documents_prompt' && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setCreateStep('assistance_prompt')}
                    className="px-4 py-2 text-zinc-300 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors"
                  >
                    No
                  </button>
                  <button
                    onClick={() => setCreateStep('documents_upload')}
                    className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
                  >
                    Yes, Upload
                  </button>
                </div>
              )}

              {createStep === 'documents_upload' && (
                <button
                  onClick={() => setCreateStep('assistance_prompt')}
                  disabled={uploading}
                  className="px-4 py-2 text-zinc-300 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-40"
                >
                  Skip Upload
                </button>
              )}

              {createStep === 'assistance_prompt' && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleGoToCase(false)}
                    className="px-4 py-2 text-zinc-300 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors"
                  >
                    No
                  </button>
                  <button
                    onClick={() => setCreateStep('assistance_questions')}
                    className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
                  >
                    Yes
                  </button>
                </div>
              )}

              {createStep === 'assistance_questions' && (
                <button
                  onClick={handleSaveAssistanceIntake}
                  disabled={savingAssistance}
                  className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {savingAssistance ? 'Starting...' : 'Start Assistance'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ERCopilot;
