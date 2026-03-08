import { useState, useCallback } from 'react';
import { employees as employeesApi } from '../api/client';
import type { PreTermCheck, PreTermCheckRequest } from '../types';
import {
  X,
  CheckCircle,
  AlertTriangle,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Loader2,
  Shield,
  ArrowLeft,
} from 'lucide-react';

// ─── theme ────────────────────────────────────────────────────────────────────

const LT = {
  overlay: 'bg-black/40',
  modalBg: 'bg-stone-100 border border-stone-200 shadow-2xl rounded-2xl',
  modalHeader: 'border-b border-stone-200',
  modalFooter: 'border-t border-stone-200',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  innerEl: 'bg-stone-200/60 rounded-xl border border-stone-200',
  inputCls: 'bg-white border border-stone-300 text-zinc-900 text-sm rounded-xl focus:outline-none focus:border-stone-400 placeholder:text-stone-400 transition-colors',
  selectCls: 'bg-white border border-stone-300 text-zinc-900 text-sm rounded-xl focus:outline-none focus:border-stone-400 transition-colors',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 text-stone-500 hover:text-zinc-900 hover:border-stone-400',
  btnDanger: 'bg-red-600 text-white hover:bg-red-700',
  btnWarning: 'bg-amber-600 text-white hover:bg-amber-700',
  closeBtnCls: 'text-stone-400 hover:text-zinc-900 transition-colors',
  cardBg: 'bg-white border border-stone-200 rounded-xl',
  cardExpandedBg: 'bg-stone-50 border-t border-stone-200',
  separator: 'bg-stone-300',
  wizardActive: 'border-zinc-900 text-zinc-50 bg-zinc-900',
  wizardInactive: 'border-stone-300 text-stone-400',
  toggleActive: 'border-zinc-900 bg-zinc-900 text-zinc-50',
  toggleInactive: 'border-stone-300 text-stone-600 hover:border-stone-400',
  alertError: 'bg-red-50 border border-red-300',
  alertErrorText: 'text-red-700',
  disclaimerBg: 'bg-amber-50 border border-amber-200',
  disclaimerText: 'text-amber-700',
  checkboxBorder: 'border-stone-400',
  narrativeBg: 'bg-stone-50 border border-stone-200 rounded-xl',
} as const;

const DK = {
  overlay: 'bg-black/60',
  modalBg: 'bg-zinc-900 border border-white/10 shadow-2xl rounded-2xl',
  modalHeader: 'border-b border-white/10',
  modalFooter: 'border-t border-white/10',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  innerEl: 'bg-zinc-900/40 rounded-xl border border-white/10',
  inputCls: 'bg-zinc-800 border border-white/10 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-white/20 placeholder:text-zinc-600 transition-colors',
  selectCls: 'bg-zinc-800 border border-white/10 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-white/20 transition-colors',
  btnPrimary: 'bg-zinc-100 text-zinc-900 hover:bg-white',
  btnSecondary: 'border border-white/10 text-zinc-500 hover:text-zinc-100 hover:border-white/20',
  btnDanger: 'bg-red-600 text-white hover:bg-red-700',
  btnWarning: 'bg-amber-600 text-white hover:bg-amber-700',
  closeBtnCls: 'text-zinc-500 hover:text-zinc-100 transition-colors',
  cardBg: 'bg-zinc-800 border border-white/10 rounded-xl',
  cardExpandedBg: 'bg-zinc-800/50 border-t border-white/10',
  separator: 'bg-zinc-700',
  wizardActive: 'border-zinc-100 text-zinc-900 bg-zinc-100',
  wizardInactive: 'border-zinc-700 text-zinc-600',
  toggleActive: 'border-zinc-100 bg-zinc-100 text-zinc-900',
  toggleInactive: 'border-white/10 text-zinc-400 hover:border-white/20',
  alertError: 'bg-red-950/30 border border-red-500/30',
  alertErrorText: 'text-red-400',
  disclaimerBg: 'bg-amber-950/30 border border-amber-500/30',
  disclaimerText: 'text-amber-400',
  checkboxBorder: 'border-zinc-500',
  narrativeBg: 'bg-zinc-800/60 border border-white/10 rounded-xl',
} as const;

// ─── constants ────────────────────────────────────────────────────────────────

const SEPARATION_REASONS = [
  { value: '', label: 'Select a reason...' },
  { value: 'performance', label: 'Performance' },
  { value: 'conduct', label: 'Conduct' },
  { value: 'layoff_rif', label: 'Layoff / RIF' },
  { value: 'restructuring', label: 'Restructuring' },
  { value: 'resignation', label: 'Resignation' },
  { value: 'mutual_agreement', label: 'Mutual Agreement' },
];

const DIMENSION_LABELS: Record<string, string> = {
  er_cases: 'Active ER Cases',
  ir_involvement: 'Recent IR Involvement',
  leave_status: 'Leave & Accommodation Status',
  protected_activity: 'Protected Activity Signals',
  documentation: 'Documentation Completeness',
  tenure_timing: 'Tenure & Timing',
  consistency: 'Consistency Check',
  manager_profile: 'Manager Risk Profile',
};

const DIMENSION_ORDER = [
  'er_cases',
  'ir_involvement',
  'leave_status',
  'protected_activity',
  'documentation',
  'tenure_timing',
  'consistency',
  'manager_profile',
];

const BAND_COLORS: Record<string, string> = {
  low: 'text-green-500',
  moderate: 'text-amber-500',
  high: 'text-orange-500',
  critical: 'text-red-500',
};

const BAND_BG: Record<string, string> = {
  low: 'bg-green-500/10 border-green-500/30',
  moderate: 'bg-amber-500/10 border-amber-500/30',
  high: 'bg-orange-500/10 border-orange-500/30',
  critical: 'bg-red-500/10 border-red-500/30',
};

const BAND_LABELS: Record<string, string> = {
  low: 'Low Risk',
  moderate: 'Moderate Risk',
  high: 'High Risk',
  critical: 'Critical Risk',
};

// ─── types ────────────────────────────────────────────────────────────────────

interface PreTerminationModalProps {
  isOpen: boolean;
  onClose: () => void;
  employee: { id: string; first_name: string; last_name: string; start_date?: string };
  onProceedToOffboard: (checkId: string) => void;
  isDark: boolean;
}

type Step = 1 | 2 | 3;

// ─── component ────────────────────────────────────────────────────────────────

export default function PreTerminationModal({
  isOpen,
  onClose,
  employee,
  onProceedToOffboard,
  isDark,
}: PreTerminationModalProps) {
  const t = isDark ? DK : LT;

  // Step 1 state
  const [step, setStep] = useState<Step>(1);
  const [isVoluntary, setIsVoluntary] = useState(true);
  const [separationCategory, setSeparationCategory] = useState('');
  const [separationNotes, setSeparationNotes] = useState('');
  const [proposedLastDay, setProposedLastDay] = useState('');

  // Step 2 state
  const [riskCheck, setRiskCheck] = useState<PreTermCheck | null>(null);
  const [expandedDimensions, setExpandedDimensions] = useState<Set<string>>(new Set());
  const [showNarrative, setShowNarrative] = useState(false);

  // Step 3 state
  const [ackNotes, setAckNotes] = useState('');
  const [legalConfirmed, setLegalConfirmed] = useState(false);

  // Shared state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── handlers ──────────────────────────────────────────────────────────

  const resetState = useCallback(() => {
    setStep(1);
    setIsVoluntary(true);
    setSeparationCategory('');
    setSeparationNotes('');
    setProposedLastDay('');
    setRiskCheck(null);
    setExpandedDimensions(new Set());
    setShowNarrative(false);
    setAckNotes('');
    setLegalConfirmed(false);
    setLoading(false);
    setError(null);
  }, []);

  const handleClose = useCallback(() => {
    resetState();
    onClose();
  }, [onClose, resetState]);

  const buildSeparationReason = (): string => {
    const parts: string[] = [];
    if (separationCategory) {
      const label = SEPARATION_REASONS.find((r) => r.value === separationCategory)?.label;
      if (label) parts.push(label);
    }
    if (separationNotes.trim()) parts.push(separationNotes.trim());
    return parts.join(' - ') || 'Not specified';
  };

  const handleRunRiskCheck = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body: PreTermCheckRequest = {
        separation_reason: buildSeparationReason(),
        is_voluntary: isVoluntary,
      };
      const result = await employeesApi.runPreTermCheck(employee.id, body);
      setRiskCheck(result);
      setStep(2);
    } catch (err: any) {
      setError(err?.message || 'Failed to run risk check. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [employee.id, isVoluntary, separationCategory, separationNotes]);

  const handleProceedVoluntary = useCallback(() => {
    // For voluntary separations, skip the risk check
    onProceedToOffboard('');
    handleClose();
  }, [onProceedToOffboard, handleClose]);

  const handleProceedLowModerate = useCallback(() => {
    if (riskCheck) {
      onProceedToOffboard(riskCheck.id);
      handleClose();
    }
  }, [riskCheck, onProceedToOffboard, handleClose]);

  const handleAcknowledgeAndProceed = useCallback(async () => {
    if (!riskCheck) return;
    setLoading(true);
    setError(null);
    try {
      await employeesApi.acknowledgePreTermCheck(riskCheck.id, { notes: ackNotes });
      onProceedToOffboard(riskCheck.id);
      handleClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to submit acknowledgment. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [riskCheck, ackNotes, onProceedToOffboard, handleClose]);

  const toggleDimension = useCallback((key: string) => {
    setExpandedDimensions((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  // ── helpers ───────────────────────────────────────────────────────────

  const StatusIcon = ({ status }: { status: string }) => {
    if (status === 'green')
      return <CheckCircle size={18} className="text-green-500 flex-shrink-0" />;
    if (status === 'yellow')
      return <AlertTriangle size={18} className="text-amber-500 flex-shrink-0" />;
    return <AlertCircle size={18} className="text-red-500 flex-shrink-0" />;
  };

  const stepLabel = (s: number): string => {
    if (s === 1) return 'Separation Context';
    if (s === 2) return 'Risk Report';
    return 'Acknowledgment';
  };

  // ── render nothing if not open ────────────────────────────────────────

  if (!isOpen) return null;

  // ── render ────────────────────────────────────────────────────────────

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center ${t.overlay} p-4`}
      onClick={handleClose}
    >
      <div
        className={`w-full max-w-2xl ${t.modalBg} max-h-[90vh] overflow-hidden flex flex-col`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ──────────────────────────────────────────────── */}
        <div className={`flex items-center justify-between p-6 ${t.modalHeader}`}>
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-amber-500/10">
              <Shield size={18} className="text-amber-500" />
            </div>
            <div>
              <h3 className={`text-lg font-bold ${t.textMain} uppercase tracking-tight`}>
                Initiate Separation
              </h3>
              <p className={`text-xs ${t.textMuted}`}>
                {employee.first_name} {employee.last_name}
              </p>
            </div>
          </div>
          <button onClick={handleClose} className={t.closeBtnCls}>
            <X size={20} />
          </button>
        </div>

        {/* ── Step Indicators ─────────────────────────────────────── */}
        <div className="px-6 pt-4">
          <div className="flex items-center gap-3">
            {[1, 2, 3].map((s) => (
              <div key={s} className="flex items-center gap-3">
                <div className="flex flex-col items-center gap-1">
                  <div
                    className={`h-6 w-6 rounded-full border text-[10px] font-bold flex items-center justify-center ${
                      step >= s ? t.wizardActive : t.wizardInactive
                    }`}
                  >
                    {s}
                  </div>
                  <span className={`text-[9px] uppercase tracking-wider ${step >= s ? t.textDim : t.textFaint}`}>
                    {stepLabel(s)}
                  </span>
                </div>
                {s < 3 && <div className={`h-px w-8 ${t.separator} mb-4`} />}
              </div>
            ))}
          </div>
        </div>

        {/* ── Body ────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Error banner */}
          {error && (
            <div className={`${t.alertError} rounded-xl p-3 flex items-start gap-2`}>
              <AlertCircle size={16} className={`${t.alertErrorText} flex-shrink-0 mt-0.5`} />
              <p className={`text-xs ${t.alertErrorText}`}>{error}</p>
            </div>
          )}

          {/* ── Step 1: Separation Context ────────────────────────── */}
          {step === 1 && (
            <div className="space-y-5">
              <div className={`${t.innerEl} p-3`}>
                <p className={`text-[10px] uppercase tracking-wider ${t.textMuted}`}>
                  Step 1 of 3
                </p>
                <p className={`text-xs ${t.textDim} mt-1`}>
                  Provide separation context. Involuntary separations require a risk scan before proceeding to offboarding.
                </p>
              </div>

              {/* Voluntary / Involuntary toggle */}
              <div className="space-y-2">
                <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted}`}>
                  Separation Type
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setIsVoluntary(true)}
                    className={`border p-3 text-left rounded-xl transition-colors ${
                      isVoluntary ? t.toggleActive : t.toggleInactive
                    }`}
                  >
                    <p className="text-xs font-bold uppercase tracking-wider">Voluntary</p>
                    <p className={`text-[11px] mt-1 ${isVoluntary ? (isDark ? 'text-zinc-500' : 'text-zinc-400') : t.textFaint}`}>
                      Employee-initiated (resignation, retirement)
                    </p>
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsVoluntary(false)}
                    className={`border p-3 text-left rounded-xl transition-colors ${
                      !isVoluntary ? t.toggleActive : t.toggleInactive
                    }`}
                  >
                    <p className="text-xs font-bold uppercase tracking-wider">Involuntary</p>
                    <p className={`text-[11px] mt-1 ${!isVoluntary ? (isDark ? 'text-zinc-500' : 'text-zinc-400') : t.textFaint}`}>
                      Employer-initiated (termination, layoff)
                    </p>
                  </button>
                </div>
              </div>

              {/* Separation reason dropdown */}
              <div className="space-y-2">
                <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted}`}>
                  Separation Reason
                </label>
                <select
                  value={separationCategory}
                  onChange={(e) => setSeparationCategory(e.target.value)}
                  className={`w-full px-3 py-2 ${t.selectCls}`}
                >
                  {SEPARATION_REASONS.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Additional notes */}
              <div className="space-y-2">
                <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted}`}>
                  Additional Context <span className={t.textFaint}>(optional)</span>
                </label>
                <textarea
                  value={separationNotes}
                  onChange={(e) => setSeparationNotes(e.target.value)}
                  placeholder="Provide additional details about the separation..."
                  rows={3}
                  className={`w-full px-3 py-2 ${t.inputCls} resize-none`}
                />
              </div>

              {/* Proposed last day */}
              <div className="space-y-2">
                <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted}`}>
                  Proposed Last Day <span className={t.textFaint}>(optional)</span>
                </label>
                <input
                  type="date"
                  value={proposedLastDay}
                  onChange={(e) => setProposedLastDay(e.target.value)}
                  className={`w-full px-3 py-2 ${t.inputCls}`}
                />
              </div>
            </div>
          )}

          {/* ── Step 2: Risk Report ──────────────────────────────── */}
          {step === 2 && riskCheck && (
            <div className="space-y-5">
              {/* Overall risk band */}
              <div className={`border rounded-xl p-4 ${BAND_BG[riskCheck.overall_band]}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`text-3xl font-black ${BAND_COLORS[riskCheck.overall_band]}`}>
                      {riskCheck.overall_score}
                    </div>
                    <div>
                      <p className={`text-sm font-bold uppercase tracking-wider ${BAND_COLORS[riskCheck.overall_band]}`}>
                        {BAND_LABELS[riskCheck.overall_band] || riskCheck.overall_band}
                      </p>
                      <p className={`text-[11px] ${t.textDim}`}>
                        Overall pre-termination risk score
                      </p>
                    </div>
                  </div>
                  <Shield size={28} className={BAND_COLORS[riskCheck.overall_band]} />
                </div>
              </div>

              {/* Dimension cards — 2 columns */}
              <div>
                <p className={`text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-3`}>
                  Risk Dimensions
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {DIMENSION_ORDER.map((key) => {
                    const dim = riskCheck.dimensions?.[key];
                    if (!dim) return null;
                    const expanded = expandedDimensions.has(key);
                    return (
                      <div key={key} className={`${t.cardBg} overflow-hidden`}>
                        <button
                          type="button"
                          onClick={() => toggleDimension(key)}
                          className="w-full text-left p-3 flex items-start gap-3"
                        >
                          <StatusIcon status={dim.status} />
                          <div className="flex-1 min-w-0">
                            <p className={`text-xs font-bold ${t.textMain}`}>
                              {DIMENSION_LABELS[key] || key}
                            </p>
                            <p className={`text-[11px] ${t.textDim} mt-0.5 line-clamp-2`}>
                              {dim.summary}
                            </p>
                          </div>
                          {expanded ? (
                            <ChevronDown size={14} className={`${t.textFaint} flex-shrink-0 mt-0.5`} />
                          ) : (
                            <ChevronRight size={14} className={`${t.textFaint} flex-shrink-0 mt-0.5`} />
                          )}
                        </button>
                        {expanded && dim.details && (
                          <div className={`${t.cardExpandedBg} px-3 py-2`}>
                            <pre className={`text-[11px] ${t.textDim} whitespace-pre-wrap font-sans`}>
                              {typeof dim.details === 'string'
                                ? dim.details
                                : JSON.stringify(dim.details, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Recommended actions */}
              {riskCheck.recommended_actions && riskCheck.recommended_actions.length > 0 && (
                <div>
                  <p className={`text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-3`}>
                    Recommended Actions
                  </p>
                  <div className={`${t.cardBg} p-4`}>
                    <ul className="space-y-2">
                      {riskCheck.recommended_actions.map((action, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className={`text-[11px] ${t.textFaint} mt-0.5 flex-shrink-0`}>
                            {i + 1}.
                          </span>
                          <span className={`text-xs ${t.textDim}`}>{action}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* AI Narrative */}
              {riskCheck.ai_narrative && (
                <div>
                  <button
                    type="button"
                    onClick={() => setShowNarrative(!showNarrative)}
                    className="flex items-center gap-2 mb-2"
                  >
                    {showNarrative ? (
                      <ChevronDown size={14} className={t.textFaint} />
                    ) : (
                      <ChevronRight size={14} className={t.textFaint} />
                    )}
                    <p className={`text-[10px] font-bold uppercase tracking-widest ${t.textMuted}`}>
                      AI Analysis
                    </p>
                  </button>
                  {showNarrative && (
                    <div className={`${t.narrativeBg} p-4`}>
                      <p className={`text-xs ${t.textDim} whitespace-pre-wrap leading-relaxed`}>
                        {riskCheck.ai_narrative}
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Disclaimer */}
              <div className={`${t.disclaimerBg} rounded-xl p-3`}>
                <p className={`text-[11px] ${t.disclaimerText}`}>
                  This is a risk screening tool, not legal advice. Consult employment counsel for all termination decisions.
                </p>
              </div>
            </div>
          )}

          {/* ── Loading state ────────────────────────────────────── */}
          {loading && step === 1 && (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Loader2 size={28} className={`${t.textMuted} animate-spin`} />
              <p className={`text-sm ${t.textDim}`}>Running pre-termination risk scan...</p>
              <p className={`text-[11px] ${t.textFaint}`}>Analyzing 8 risk dimensions across employee history</p>
            </div>
          )}

          {/* ── Step 3: Acknowledgment Form ──────────────────────── */}
          {step === 3 && riskCheck && (
            <div className="space-y-5">
              <div className={`${t.innerEl} p-3`}>
                <p className={`text-[10px] uppercase tracking-wider ${t.textMuted}`}>
                  Step 3 of 3
                </p>
                <p className={`text-xs ${t.textDim} mt-1`}>
                  This separation has been flagged as{' '}
                  <span className={`font-bold ${BAND_COLORS[riskCheck.overall_band]}`}>
                    {BAND_LABELS[riskCheck.overall_band]?.toLowerCase()}
                  </span>
                  . Please provide justification for proceeding.
                </p>
              </div>

              {/* Overall score reminder */}
              <div className={`border rounded-xl p-3 ${BAND_BG[riskCheck.overall_band]} flex items-center gap-3`}>
                <div className={`text-2xl font-black ${BAND_COLORS[riskCheck.overall_band]}`}>
                  {riskCheck.overall_score}
                </div>
                <div>
                  <p className={`text-xs font-bold uppercase tracking-wider ${BAND_COLORS[riskCheck.overall_band]}`}>
                    {BAND_LABELS[riskCheck.overall_band]}
                  </p>
                  <p className={`text-[11px] ${t.textDim}`}>
                    {employee.first_name} {employee.last_name}
                  </p>
                </div>
              </div>

              {/* Notes */}
              <div className="space-y-2">
                <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted}`}>
                  Justification Notes <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={ackNotes}
                  onChange={(e) => setAckNotes(e.target.value)}
                  placeholder="Explain why this separation should proceed despite elevated risk..."
                  rows={4}
                  className={`w-full px-3 py-2 ${t.inputCls} resize-none`}
                  required
                />
                <p className={`text-[10px] ${t.textFaint}`}>
                  This will be recorded in the audit trail for compliance purposes.
                </p>
              </div>

              {/* Legal counsel checkbox (critical only) */}
              {riskCheck.overall_band === 'critical' && (
                <label className={`flex items-start gap-3 cursor-pointer ${t.cardBg} p-4`}>
                  <input
                    type="checkbox"
                    checked={legalConfirmed}
                    onChange={(e) => setLegalConfirmed(e.target.checked)}
                    className={`mt-0.5 rounded border-2 ${t.checkboxBorder} flex-shrink-0`}
                  />
                  <div>
                    <p className={`text-xs font-bold ${t.textMain}`}>
                      I confirm legal counsel has been consulted
                    </p>
                    <p className={`text-[11px] ${t.textDim} mt-0.5`}>
                      Critical risk separations require documented legal review before proceeding.
                    </p>
                  </div>
                </label>
              )}
            </div>
          )}
        </div>

        {/* ── Footer ──────────────────────────────────────────────── */}
        <div className={`flex items-center justify-between p-6 ${t.modalFooter}`}>
          <div>
            {step === 3 && (
              <button
                type="button"
                onClick={() => setStep(2)}
                className={`flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-xl transition-colors ${t.btnSecondary}`}
              >
                <ArrowLeft size={14} />
                Back
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleClose}
              className={`text-xs font-medium px-4 py-2 rounded-xl transition-colors ${t.btnSecondary}`}
            >
              Cancel
            </button>

            {/* Step 1 actions */}
            {step === 1 && !loading && (
              <>
                {isVoluntary ? (
                  <button
                    type="button"
                    onClick={handleProceedVoluntary}
                    className={`text-xs font-bold uppercase tracking-wider px-5 py-2 rounded-xl transition-colors ${t.btnPrimary}`}
                  >
                    Proceed to Offboarding
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleRunRiskCheck}
                    disabled={loading}
                    className={`text-xs font-bold uppercase tracking-wider px-5 py-2 rounded-xl transition-colors ${t.btnWarning}`}
                  >
                    Run Risk Check
                  </button>
                )}
              </>
            )}

            {/* Step 2 actions */}
            {step === 2 && riskCheck && (
              <>
                {riskCheck.overall_band === 'low' || riskCheck.overall_band === 'moderate' ? (
                  <button
                    type="button"
                    onClick={handleProceedLowModerate}
                    className={`text-xs font-bold uppercase tracking-wider px-5 py-2 rounded-xl transition-colors ${t.btnPrimary}`}
                  >
                    Proceed to Offboarding
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setStep(3);
                      setError(null);
                    }}
                    className={`text-xs font-bold uppercase tracking-wider px-5 py-2 rounded-xl transition-colors ${
                      riskCheck.overall_band === 'critical' ? t.btnDanger : t.btnWarning
                    }`}
                  >
                    Acknowledge &amp; Proceed
                  </button>
                )}
              </>
            )}

            {/* Step 3 actions */}
            {step === 3 && riskCheck && (
              <button
                type="button"
                onClick={handleAcknowledgeAndProceed}
                disabled={
                  loading ||
                  !ackNotes.trim() ||
                  (riskCheck.overall_band === 'critical' && !legalConfirmed)
                }
                className={`text-xs font-bold uppercase tracking-wider px-5 py-2 rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${t.btnDanger}`}
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <Loader2 size={14} className="animate-spin" />
                    Submitting...
                  </span>
                ) : (
                  'Submit & Proceed'
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
