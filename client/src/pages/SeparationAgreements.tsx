import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  Calendar,
  Check,
  CheckCircle2,
  ChevronLeft,
  Clock,
  DollarSign,
  Edit3,
  FileSignature,
  Info,
  Plus,
  RefreshCw,
  Scale,
  Shield,
  X,
  XCircle,
} from 'lucide-react';

import { separation } from '../api/client';
import { useIsLightMode } from '../hooks/useIsLightMode';
import { FeatureGuideTrigger } from '../features/feature-guides';
import type {
  SeparationAgreement,
  SeparationAgreementCreate,
  SeparationAgreementUpdate,
  SeparationStatus,
  SeparationStatusInfo,
} from '../types';

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl border border-stone-200',
  innerEl: 'bg-stone-200/60 rounded-xl border border-stone-200',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  divide: 'divide-stone-200',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 text-stone-500 hover:text-zinc-900 hover:border-stone-400',
  btnDanger: 'border border-red-300 text-red-700 hover:bg-red-50 hover:border-red-400',
  modalBg: 'bg-stone-100 border border-stone-200 shadow-2xl rounded-2xl',
  modalHeader: 'border-b border-stone-200',
  modalFooter: 'border-t border-stone-200',
  inputCls: 'bg-white border border-stone-300 text-zinc-900 text-sm rounded-xl focus:outline-none focus:border-stone-400 placeholder:text-stone-400 transition-colors',
  rowHover: 'hover:bg-stone-50',
  emptyBorder: 'border border-dashed border-stone-300 bg-stone-100 rounded-2xl',
  closeBtnCls: 'text-stone-400 hover:text-zinc-900 transition-colors',
  cancelBtn: 'text-stone-500 hover:text-zinc-900',
  tableHeader: 'bg-stone-200 text-stone-500',
  infoBg: 'bg-blue-50 border border-blue-200 text-blue-800',
  infoIcon: 'text-blue-500',
  stepActive: 'bg-zinc-900 text-white border-zinc-900',
  stepCompleted: 'bg-emerald-600 text-white border-emerald-600',
  stepInactive: 'bg-stone-200 text-stone-400 border-stone-300',
  stepLine: 'bg-stone-300',
  stepLineCompleted: 'bg-emerald-500',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 rounded-2xl border border-white/10',
  innerEl: 'bg-zinc-800/60 rounded-xl border border-white/10',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  divide: 'divide-white/10',
  btnPrimary: 'bg-zinc-100 text-zinc-900 hover:bg-white',
  btnSecondary: 'border border-white/10 text-zinc-500 hover:text-zinc-100 hover:border-white/20',
  btnDanger: 'border border-red-500/30 text-red-300 hover:bg-red-500/10 hover:border-red-500/50',
  modalBg: 'bg-zinc-900 border border-white/10 shadow-2xl rounded-2xl',
  modalHeader: 'border-b border-white/10',
  modalFooter: 'border-t border-white/10',
  inputCls: 'bg-zinc-800 border border-white/10 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-white/20 placeholder:text-zinc-600 transition-colors',
  rowHover: 'hover:bg-white/5',
  emptyBorder: 'border border-dashed border-white/10 bg-zinc-900/30 rounded-2xl',
  closeBtnCls: 'text-zinc-500 hover:text-zinc-100 transition-colors',
  cancelBtn: 'text-zinc-500 hover:text-zinc-100',
  tableHeader: 'bg-zinc-800 text-zinc-500',
  infoBg: 'bg-blue-500/10 border border-blue-500/20 text-blue-300',
  infoIcon: 'text-blue-400',
  stepActive: 'bg-zinc-100 text-zinc-900 border-zinc-100',
  stepCompleted: 'bg-emerald-500 text-white border-emerald-500',
  stepInactive: 'bg-zinc-800 text-zinc-600 border-zinc-700',
  stepLine: 'bg-zinc-700',
  stepLineCompleted: 'bg-emerald-500',
} as const;

const STATUS_OPTIONS: SeparationStatus[] = [
  'draft',
  'presented',
  'consideration_period',
  'signed',
  'revoked',
  'effective',
  'expired',
  'void',
];

const LIFECYCLE_STEPS: { key: SeparationStatus; label: string }[] = [
  { key: 'draft', label: 'Draft' },
  { key: 'presented', label: 'Presented' },
  { key: 'consideration_period', label: 'Consideration' },
  { key: 'signed', label: 'Signed' },
  { key: 'effective', label: 'Effective' },
];

function formatLabel(value: string): string {
  return value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function statusStyle(status: SeparationStatus, isLight: boolean): string {
  if (isLight) {
    switch (status) {
      case 'draft':
        return 'bg-stone-200 text-stone-600 border-stone-300';
      case 'presented':
      case 'consideration_period':
        return 'bg-amber-100 text-amber-700 border-amber-200';
      case 'signed':
        return 'bg-blue-100 text-blue-700 border-blue-200';
      case 'effective':
        return 'bg-emerald-100 text-emerald-700 border-emerald-200';
      case 'revoked':
        return 'bg-red-100 text-red-700 border-red-200';
      case 'expired':
      case 'void':
        return 'bg-stone-200 text-stone-500 border-stone-300';
      default:
        return 'bg-stone-200 text-stone-600 border-stone-300';
    }
  }
  switch (status) {
    case 'draft':
      return 'bg-zinc-700/30 text-zinc-400 border-zinc-600/30';
    case 'presented':
    case 'consideration_period':
      return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    case 'signed':
      return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    case 'effective':
      return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    case 'revoked':
      return 'bg-red-500/10 text-red-400 border-red-500/20';
    case 'expired':
    case 'void':
      return 'bg-zinc-600/20 text-zinc-500 border-zinc-600/30';
    default:
      return 'bg-zinc-700/30 text-zinc-400 border-zinc-600/30';
  }
}

function boolBadge(value: boolean, isLight: boolean): string {
  if (value) {
    return isLight
      ? 'bg-emerald-100 text-emerald-700 border-emerald-200'
      : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
  }
  return isLight
    ? 'bg-stone-200 text-stone-500 border-stone-300'
    : 'bg-zinc-700/30 text-zinc-500 border-zinc-600/30';
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '--';
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function formatCurrency(amount: number | null): string {
  if (amount == null) return '--';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
}

export default function SeparationAgreements() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  const [agreements, setAgreements] = useState<SeparationAgreement[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<SeparationAgreement | null>(null);
  const [statusInfo, setStatusInfo] = useState<SeparationStatusInfo | null>(null);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<string>('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [createPayload, setCreatePayload] = useState<SeparationAgreementCreate>({
    employee_id: '',
    severance_amount: undefined,
    severance_weeks: undefined,
    severance_description: '',
    employee_age_at_separation: undefined,
    is_group_layoff: false,
    decisional_unit: '',
    notes: '',
  });

  const [editPayload, setEditPayload] = useState<SeparationAgreementUpdate>({
    severance_amount: undefined,
    severance_weeks: undefined,
    severance_description: '',
    notes: '',
  });

  const loadAgreements = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);

    try {
      const result = await separation.list({
        status: statusFilter || undefined,
      });
      setAgreements(result);

      const nextId = selectedId && result.some((a) => a.id === selectedId)
        ? selectedId
        : null;
      if (!nextId) {
        setSelected(null);
        setStatusInfo(null);
      }
      setSelectedId(nextId);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load separation agreements');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [statusFilter, selectedId]);

  const loadDetail = useCallback(async (id: string) => {
    try {
      const [agreement, status] = await Promise.all([
        separation.get(id),
        separation.getStatus(id),
      ]);
      setSelected(agreement);
      setStatusInfo(status);
      setEditPayload({
        severance_amount: agreement.severance_amount ?? undefined,
        severance_weeks: agreement.severance_weeks ?? undefined,
        severance_description: agreement.severance_description ?? '',
        notes: agreement.notes ?? '',
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agreement details');
    }
  }, []);

  useEffect(() => {
    loadAgreements();
  }, [statusFilter, loadAgreements]);

  useEffect(() => {
    if (!selectedId) return;
    loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [successMessage]);

  const handleCreate = async () => {
    if (!createPayload.employee_id.trim()) return;

    setSaving(true);
    setCreateError(null);
    try {
      const payload: SeparationAgreementCreate = {
        employee_id: createPayload.employee_id.trim(),
        offboarding_case_id: createPayload.offboarding_case_id?.trim() || undefined,
        pre_term_check_id: createPayload.pre_term_check_id?.trim() || undefined,
        severance_amount: createPayload.severance_amount ?? undefined,
        severance_weeks: createPayload.severance_weeks ?? undefined,
        severance_description: createPayload.severance_description?.trim() || undefined,
        employee_age_at_separation: createPayload.employee_age_at_separation ?? undefined,
        is_group_layoff: createPayload.is_group_layoff ?? false,
        decisional_unit: createPayload.decisional_unit?.trim() || undefined,
        notes: createPayload.notes?.trim() || undefined,
      };

      const created = await separation.create(payload);
      setShowCreateModal(false);
      setCreatePayload({
        employee_id: '',
        severance_amount: undefined,
        severance_weeks: undefined,
        severance_description: '',
        employee_age_at_separation: undefined,
        is_group_layoff: false,
        decisional_unit: '',
        notes: '',
      });

      await loadAgreements(true);
      setSelectedId(created.id);
      setSuccessMessage('Separation agreement created successfully.');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create agreement';
      setCreateError(message);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async () => {
    if (!selected) return;

    setSaving(true);
    try {
      const payload: SeparationAgreementUpdate = {
        severance_amount: editPayload.severance_amount ?? undefined,
        severance_weeks: editPayload.severance_weeks ?? undefined,
        severance_description: editPayload.severance_description?.trim() || undefined,
        notes: editPayload.notes?.trim() || undefined,
      };

      await separation.update(selected.id, payload);
      setShowEditModal(false);
      await loadAgreements(true);
      await loadDetail(selected.id);
      setSuccessMessage('Agreement updated successfully.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update agreement');
    } finally {
      setSaving(false);
    }
  };

  const handlePresent = async () => {
    if (!selected) return;
    if (!window.confirm('Present this agreement to the employee? This will start the consideration period.')) return;

    setSaving(true);
    try {
      await separation.present(selected.id);
      await loadAgreements(true);
      await loadDetail(selected.id);
      setSuccessMessage('Agreement presented. Consideration period has begun.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to present agreement');
    } finally {
      setSaving(false);
    }
  };

  const handleSign = async () => {
    if (!selected) return;
    if (!window.confirm('Record the employee signature for this agreement?')) return;

    setSaving(true);
    try {
      await separation.sign(selected.id);
      await loadAgreements(true);
      await loadDetail(selected.id);
      setSuccessMessage('Signature recorded. Revocation period has begun.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to record signature');
    } finally {
      setSaving(false);
    }
  };

  const handleRevoke = async () => {
    if (!selected) return;
    if (!window.confirm('Record revocation of this agreement? This action cannot be undone.')) return;

    setSaving(true);
    try {
      await separation.revoke(selected.id);
      await loadAgreements(true);
      await loadDetail(selected.id);
      setSuccessMessage('Agreement revoked.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke agreement');
    } finally {
      setSaving(false);
    }
  };

  const getLifecycleIndex = (status: SeparationStatus): number => {
    const idx = LIFECYCLE_STEPS.findIndex((s) => s.key === status);
    return idx >= 0 ? idx : -1;
  };

  if (loading) {
    return (
      <div className={`min-h-screen ${t.pageBg} flex items-center justify-center`}>
        <div className={`text-xs ${t.textMuted} uppercase tracking-wider animate-pulse`}>
          Loading separation agreements...
        </div>
      </div>
    );
  }

  const renderList = () => (
    <div className="space-y-6">
      {/* Header */}
      <div data-tour="separations-context" className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className={`text-3xl font-bold tracking-tight ${t.textMain}`}>Separation Agreements</h1>
            <FeatureGuideTrigger guideId="separations" />
          </div>
          <p className={`text-xs ${t.textMuted} mt-1 font-mono tracking-wide uppercase`}>
            ADEA / OWBPA compliance tracking
          </p>
        </div>
        <div data-tour="separations-tabs" className="flex flex-wrap items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className={`px-3 py-2 text-sm rounded-xl ${t.inputCls}`}
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{formatLabel(s)}</option>
            ))}
          </select>
          <button
            onClick={() => loadAgreements(true)}
            disabled={refreshing}
            className={`inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.btnSecondary} disabled:opacity-50`}
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> Refresh
          </button>
          <button
            data-tour="separations-new-btn"
            onClick={() => {
              setCreateError(null);
              setShowCreateModal(true);
            }}
            className={`inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.btnPrimary}`}
          >
            <Plus size={14} /> New Agreement
          </button>
        </div>
      </div>

      {/* Error / Success */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex items-center gap-3">
          <AlertTriangle className="text-red-400 shrink-0" size={16} />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}
      {successMessage && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 flex items-center gap-3">
          <CheckCircle2 className="text-emerald-400 shrink-0" size={16} />
          <p className="text-sm text-emerald-400">{successMessage}</p>
        </div>
      )}

      {/* Table */}
      {agreements.length === 0 ? (
        <div className={`${t.emptyBorder} p-16 text-center`}>
          <FileSignature size={32} className={`mx-auto mb-3 ${t.textFaint}`} />
          <p className={`text-sm ${t.textMuted}`}>No separation agreements found.</p>
        </div>
      ) : (
        <div data-tour="separations-list" className={`${t.card} overflow-hidden`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={`${t.tableHeader} text-[10px] uppercase tracking-widest`}>
                  <th className="text-left px-4 py-3 font-medium">Employee</th>
                  <th className="text-left px-4 py-3 font-medium">Status</th>
                  <th className="text-left px-4 py-3 font-medium">Severance</th>
                  <th className="text-left px-4 py-3 font-medium">ADEA</th>
                  <th className="text-left px-4 py-3 font-medium">Group Layoff</th>
                  <th className="text-left px-4 py-3 font-medium">Presented</th>
                  <th className="text-left px-4 py-3 font-medium">Created</th>
                </tr>
              </thead>
              <tbody className={t.divide}>
                {agreements.map((ag) => (
                  <tr
                    key={ag.id}
                    onClick={() => setSelectedId(ag.id)}
                    className={`cursor-pointer transition-colors ${t.rowHover} ${t.divide}`}
                  >
                    <td className={`px-4 py-3 ${t.textMain} font-medium`}>
                      {ag.employee_name || ag.employee_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[10px] px-2 py-0.5 uppercase tracking-widest border rounded-full ${statusStyle(ag.status, isLight)}`}>
                        {formatLabel(ag.status)}
                      </span>
                    </td>
                    <td className={`px-4 py-3 ${t.textDim}`}>
                      {formatCurrency(ag.severance_amount)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[10px] px-2 py-0.5 uppercase tracking-widest border rounded-full ${boolBadge(ag.is_adea_applicable, isLight)}`}>
                        {ag.is_adea_applicable ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[10px] px-2 py-0.5 uppercase tracking-widest border rounded-full ${boolBadge(ag.is_group_layoff, isLight)}`}>
                        {ag.is_group_layoff ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td className={`px-4 py-3 ${t.textMuted}`}>
                      {formatDate(ag.presented_date)}
                    </td>
                    <td className={`px-4 py-3 ${t.textMuted}`}>
                      {formatDate(ag.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );

  const renderLifecycleProgress = () => {
    if (!selected) return null;

    const currentIdx = getLifecycleIndex(selected.status);
    const isTerminal = ['revoked', 'expired', 'void'].includes(selected.status);

    return (
      <div data-tour="separations-timeline" className={`${t.innerEl} p-4`}>
        <h3 className={`text-[10px] uppercase tracking-widest ${t.textMuted} mb-4`}>Lifecycle Progress</h3>
        {isTerminal ? (
          <div className="flex items-center gap-2">
            <XCircle size={16} className="text-red-400" />
            <span className={`text-sm font-medium ${t.textMain}`}>
              Agreement {formatLabel(selected.status)}
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-0">
            {LIFECYCLE_STEPS.map((step, idx) => {
              let stepCls: string = t.stepInactive;
              let lineCls: string = t.stepLine;

              if (idx < currentIdx) {
                stepCls = t.stepCompleted;
                lineCls = t.stepLineCompleted;
              } else if (idx === currentIdx) {
                stepCls = t.stepActive;
              }

              return (
                <div key={step.key} className="flex items-center">
                  <div className="flex flex-col items-center">
                    <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center text-xs font-semibold ${stepCls}`}>
                      {idx < currentIdx ? <Check size={14} /> : idx + 1}
                    </div>
                    <span className={`text-[9px] mt-1.5 uppercase tracking-widest ${idx <= currentIdx ? t.textMain : t.textFaint}`}>
                      {step.label}
                    </span>
                  </div>
                  {idx < LIFECYCLE_STEPS.length - 1 && (
                    <div className={`w-8 lg:w-14 h-0.5 mx-1 mt-[-14px] ${idx < currentIdx ? lineCls : t.stepLine}`} />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  const renderTimeline = () => {
    if (!selected) return null;

    const rows: { label: string; date: string | null; extra?: string; icon: React.ReactNode }[] = [
      { label: 'Presented', date: selected.presented_date, icon: <FileSignature size={14} /> },
      {
        label: 'Consideration Deadline',
        date: selected.consideration_deadline,
        extra: statusInfo?.days_remaining_consideration != null
          ? `${statusInfo.days_remaining_consideration} day${statusInfo.days_remaining_consideration !== 1 ? 's' : ''} remaining`
          : undefined,
        icon: <Clock size={14} />,
      },
      { label: 'Signed', date: selected.signed_date, icon: <Check size={14} /> },
      {
        label: 'Revocation Deadline',
        date: selected.revocation_deadline,
        extra: statusInfo?.days_remaining_revocation != null
          ? `${statusInfo.days_remaining_revocation} day${statusInfo.days_remaining_revocation !== 1 ? 's' : ''} remaining`
          : undefined,
        icon: <Clock size={14} />,
      },
      { label: 'Effective', date: selected.effective_date, icon: <CheckCircle2 size={14} /> },
    ];

    if (selected.revoked_date) {
      rows.push({ label: 'Revoked', date: selected.revoked_date, icon: <XCircle size={14} /> });
    }

    return (
      <div className={`${t.innerEl} p-4`}>
        <div className="flex items-center gap-2 mb-3">
          <Calendar size={14} className={t.textMuted} />
          <h3 className={`text-[10px] uppercase tracking-widest ${t.textMuted}`}>Timeline & Deadlines</h3>
        </div>
        <div className="space-y-2">
          {rows.map((row) => (
            <div key={row.label} className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className={t.textMuted}>{row.icon}</span>
                <span className={`text-xs ${t.textDim}`}>{row.label}</span>
              </div>
              <div className="text-right">
                <span className={`text-xs font-medium ${row.date ? t.textMain : t.textFaint}`}>
                  {formatDate(row.date)}
                </span>
                {row.extra && (
                  <span className="ml-2 text-[10px] text-amber-500 font-medium">{row.extra}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderAdeaPanel = () => {
    if (!selected || !selected.is_adea_applicable) return null;

    const considerationDays = selected.is_group_layoff ? 45 : 21;

    return (
      <div data-tour="separations-adea" className={`${t.infoBg} rounded-xl p-4`}>
        <div className="flex items-start gap-3">
          <Scale size={18} className={`${t.infoIcon} shrink-0 mt-0.5`} />
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">ADEA / OWBPA Compliance</h3>
            <p className="text-xs leading-relaxed">
              This employee is age 40 or older (age at separation: {selected.employee_age_at_separation}).
              The Age Discrimination in Employment Act (ADEA) and Older Workers Benefit Protection Act (OWBPA) require:
            </p>
            <ul className="text-xs space-y-1 list-disc list-inside">
              <li>
                <strong>{considerationDays}-day consideration period</strong>
                {selected.is_group_layoff
                  ? ' (45 days applies because this is a group layoff / exit incentive program)'
                  : ' (21 days for individual separation)'}
              </li>
              <li><strong>7-day revocation period</strong> after signing</li>
              <li>Written agreement must advise the employee to consult an attorney</li>
              {selected.is_group_layoff && (
                <li>
                  <strong>Group disclosure required:</strong> Decisional unit, eligibility criteria, job titles and ages of all employees in the decisional unit
                </li>
              )}
            </ul>
            {selected.is_group_layoff && selected.decisional_unit && (
              <div className="mt-2 pt-2 border-t border-current/20">
                <span className="text-[10px] uppercase tracking-widest font-medium">Decisional Unit: </span>
                <span className="text-xs">{selected.decisional_unit}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderActions = () => {
    if (!selected) return null;

    return (
      <div className="flex flex-wrap gap-2">
        {selected.status === 'draft' && (
          <>
            <button
              onClick={() => setShowEditModal(true)}
              disabled={saving}
              className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.btnSecondary} disabled:opacity-50`}
            >
              <Edit3 size={14} /> Edit Terms
            </button>
            <button
              onClick={handlePresent}
              disabled={saving}
              className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.btnPrimary} disabled:opacity-50`}
            >
              <ArrowRight size={14} /> Present Agreement
            </button>
          </>
        )}
        {(selected.status === 'consideration_period' || selected.status === 'presented') && (
          <button
            onClick={handleSign}
            disabled={saving}
            className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.btnPrimary} disabled:opacity-50`}
          >
            <FileSignature size={14} /> Record Signature
          </button>
        )}
        {selected.status === 'signed' && (
          <button
            onClick={handleRevoke}
            disabled={saving}
            className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.btnDanger} disabled:opacity-50`}
          >
            <XCircle size={14} /> Record Revocation
          </button>
        )}
      </div>
    );
  };

  const renderDetail = () => {
    if (!selected) return null;

    return (
      <div className="space-y-6">
        {/* Back + Header */}
        <div className="flex flex-col gap-4">
          <button
            onClick={() => {
              setSelectedId(null);
              setSelected(null);
              setStatusInfo(null);
            }}
            className={`inline-flex items-center gap-1.5 text-xs uppercase tracking-wider ${t.textMuted} hover:${t.textMain} transition-colors self-start`}
          >
            <ChevronLeft size={14} /> Back to list
          </button>

          <div className={`${t.card} p-5`}>
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
              <div>
                <h2 className={`text-xl font-semibold ${t.textMain}`}>
                  {selected.employee_name || `Employee ${selected.employee_id.slice(0, 8)}`}
                </h2>
                <p className={`text-[11px] ${t.textMuted} font-mono mt-1`}>{selected.id}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-[10px] px-2.5 py-1 uppercase tracking-widest border rounded-full ${statusStyle(selected.status, isLight)}`}>
                  {formatLabel(selected.status)}
                </span>
                {selected.is_adea_applicable && (
                  <span className={`text-[10px] px-2.5 py-1 uppercase tracking-widest border rounded-full ${boolBadge(true, isLight)}`}>
                    <span className="inline-flex items-center gap-1"><Shield size={10} /> ADEA</span>
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Error / Success in detail view */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex items-center gap-3">
            <AlertTriangle className="text-red-400 shrink-0" size={16} />
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}
        {successMessage && (
          <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 flex items-center gap-3">
            <CheckCircle2 className="text-emerald-400 shrink-0" size={16} />
            <p className="text-sm text-emerald-400">{successMessage}</p>
          </div>
        )}

        {/* Lifecycle Progress */}
        {renderLifecycleProgress()}

        {/* Severance Info */}
        <div className={`${t.card} p-5 space-y-3`}>
          <div className="flex items-center gap-2">
            <DollarSign size={14} className={t.textMuted} />
            <h3 className={`text-[10px] uppercase tracking-widest ${t.textMuted}`}>Severance Information</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <span className={`block text-[10px] uppercase tracking-widest ${t.textFaint} mb-1`}>Amount</span>
              <span className={`text-lg font-semibold ${t.textMain}`}>{formatCurrency(selected.severance_amount)}</span>
            </div>
            <div>
              <span className={`block text-[10px] uppercase tracking-widest ${t.textFaint} mb-1`}>Weeks</span>
              <span className={`text-lg font-semibold ${t.textMain}`}>{selected.severance_weeks ?? '--'}</span>
            </div>
            <div>
              <span className={`block text-[10px] uppercase tracking-widest ${t.textFaint} mb-1`}>Consideration Period</span>
              <span className={`text-lg font-semibold ${t.textMain}`}>
                {selected.consideration_period_days != null ? `${selected.consideration_period_days} days` : '--'}
              </span>
            </div>
          </div>
          {selected.severance_description && (
            <div>
              <span className={`block text-[10px] uppercase tracking-widest ${t.textFaint} mb-1`}>Description</span>
              <p className={`text-sm ${t.textDim}`}>{selected.severance_description}</p>
            </div>
          )}
          {selected.notes && (
            <div>
              <span className={`block text-[10px] uppercase tracking-widest ${t.textFaint} mb-1`}>Notes</span>
              <p className={`text-sm ${t.textDim}`}>{selected.notes}</p>
            </div>
          )}
        </div>

        {/* Timeline */}
        {renderTimeline()}

        {/* ADEA Info */}
        {renderAdeaPanel()}

        {/* Agreement Details */}
        <div className={`${t.card} p-5 space-y-3`}>
          <div className="flex items-center gap-2">
            <Info size={14} className={t.textMuted} />
            <h3 className={`text-[10px] uppercase tracking-widest ${t.textMuted}`}>Agreement Details</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <span className={`block text-[10px] uppercase tracking-widest ${t.textFaint} mb-1`}>Employee Age</span>
              <span className={`text-sm ${t.textMain}`}>{selected.employee_age_at_separation ?? '--'}</span>
            </div>
            <div>
              <span className={`block text-[10px] uppercase tracking-widest ${t.textFaint} mb-1`}>ADEA Applicable</span>
              <span className={`text-[10px] px-2 py-0.5 uppercase tracking-widest border rounded-full ${boolBadge(selected.is_adea_applicable, isLight)}`}>
                {selected.is_adea_applicable ? 'Yes' : 'No'}
              </span>
            </div>
            <div>
              <span className={`block text-[10px] uppercase tracking-widest ${t.textFaint} mb-1`}>Group Layoff</span>
              <span className={`text-[10px] px-2 py-0.5 uppercase tracking-widest border rounded-full ${boolBadge(selected.is_group_layoff, isLight)}`}>
                {selected.is_group_layoff ? 'Yes' : 'No'}
              </span>
            </div>
            <div>
              <span className={`block text-[10px] uppercase tracking-widest ${t.textFaint} mb-1`}>Revocation Period</span>
              <span className={`text-sm ${t.textMain}`}>
                {selected.revocation_period_days != null ? `${selected.revocation_period_days} days` : '--'}
              </span>
            </div>
            {selected.offboarding_case_id && (
              <div>
                <span className={`block text-[10px] uppercase tracking-widest ${t.textFaint} mb-1`}>Offboarding Case</span>
                <span className={`text-xs font-mono ${t.textDim}`}>{selected.offboarding_case_id.slice(0, 12)}...</span>
              </div>
            )}
            {selected.pre_term_check_id && (
              <div>
                <span className={`block text-[10px] uppercase tracking-widest ${t.textFaint} mb-1`}>Pre-Term Check</span>
                <span className={`text-xs font-mono ${t.textDim}`}>{selected.pre_term_check_id.slice(0, 12)}...</span>
              </div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className={`${t.card} p-5`}>
          <h3 className={`text-[10px] uppercase tracking-widest ${t.textMuted} mb-3`}>Actions</h3>
          {renderActions()}
          {!['draft', 'consideration_period', 'presented', 'signed'].includes(selected.status) && (
            <p className={`text-xs ${t.textFaint}`}>No actions available for this status.</p>
          )}
        </div>
      </div>
    );
  };

  const renderCreateModal = () => {
    if (!showCreateModal) return null;

    return (
      <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm p-4 flex items-center justify-center">
        <div className={`w-full max-w-lg ${t.modalBg}`}>
          <div className={`flex items-center justify-between p-5 ${t.modalHeader}`}>
            <h3 className={`text-lg ${t.textMain} font-semibold uppercase tracking-wider`}>
              Create Separation Agreement
            </h3>
            <button onClick={() => setShowCreateModal(false)} className={t.closeBtnCls}>
              <X size={18} />
            </button>
          </div>

          <div className="p-5 space-y-4 max-h-[65vh] overflow-y-auto">
            <div>
              <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Employee ID *</label>
              <input
                value={createPayload.employee_id}
                onChange={(e) => setCreatePayload((p) => ({ ...p, employee_id: e.target.value }))}
                placeholder="Enter employee ID"
                className={`w-full px-3 py-2 ${t.inputCls}`}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Severance Amount</label>
                <input
                  type="number"
                  value={createPayload.severance_amount ?? ''}
                  onChange={(e) => setCreatePayload((p) => ({ ...p, severance_amount: e.target.value ? Number(e.target.value) : undefined }))}
                  placeholder="0.00"
                  className={`w-full px-3 py-2 ${t.inputCls}`}
                />
              </div>
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Severance Weeks</label>
                <input
                  type="number"
                  value={createPayload.severance_weeks ?? ''}
                  onChange={(e) => setCreatePayload((p) => ({ ...p, severance_weeks: e.target.value ? Number(e.target.value) : undefined }))}
                  placeholder="0"
                  className={`w-full px-3 py-2 ${t.inputCls}`}
                />
              </div>
            </div>

            <div>
              <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Severance Description</label>
              <textarea
                rows={2}
                value={createPayload.severance_description ?? ''}
                onChange={(e) => setCreatePayload((p) => ({ ...p, severance_description: e.target.value }))}
                placeholder="Describe severance package details"
                className={`w-full px-3 py-2 resize-none ${t.inputCls}`}
              />
            </div>

            <div>
              <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Employee Age at Separation</label>
              <input
                type="number"
                value={createPayload.employee_age_at_separation ?? ''}
                onChange={(e) => setCreatePayload((p) => ({ ...p, employee_age_at_separation: e.target.value ? Number(e.target.value) : undefined }))}
                placeholder="Age determines ADEA applicability"
                className={`w-full px-3 py-2 ${t.inputCls}`}
              />
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="is_group_layoff"
                checked={createPayload.is_group_layoff ?? false}
                onChange={(e) => setCreatePayload((p) => ({ ...p, is_group_layoff: e.target.checked }))}
                className="w-4 h-4 rounded"
              />
              <label htmlFor="is_group_layoff" className={`text-sm ${t.textDim}`}>
                Group layoff / exit incentive program
              </label>
            </div>

            {createPayload.is_group_layoff && (
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Decisional Unit</label>
                <input
                  value={createPayload.decisional_unit ?? ''}
                  onChange={(e) => setCreatePayload((p) => ({ ...p, decisional_unit: e.target.value }))}
                  placeholder="Department, division, or group"
                  className={`w-full px-3 py-2 ${t.inputCls}`}
                />
              </div>
            )}

            <div>
              <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Notes</label>
              <textarea
                rows={2}
                value={createPayload.notes ?? ''}
                onChange={(e) => setCreatePayload((p) => ({ ...p, notes: e.target.value }))}
                placeholder="Internal notes"
                className={`w-full px-3 py-2 resize-none ${t.inputCls}`}
              />
            </div>

            {(createPayload.employee_age_at_separation != null && createPayload.employee_age_at_separation >= 40) && (
              <div className={`${t.infoBg} rounded-xl p-3 flex items-start gap-2`}>
                <Info size={14} className={`${t.infoIcon} shrink-0 mt-0.5`} />
                <p className="text-xs leading-relaxed">
                  Employee is 40+. ADEA/OWBPA protections will apply automatically.
                  {createPayload.is_group_layoff
                    ? ' A 45-day consideration period and group disclosure will be required.'
                    : ' A 21-day consideration period will be required.'}
                </p>
              </div>
            )}
          </div>

          <div className={`p-5 ${t.modalFooter} flex justify-end gap-2`}>
            <button
              onClick={() => {
                setCreateError(null);
                setShowCreateModal(false);
              }}
              className={`px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.cancelBtn}`}
            >
              Cancel
            </button>
            <button
              onClick={handleCreate}
              disabled={saving || !createPayload.employee_id.trim()}
              className={`px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.btnPrimary} disabled:opacity-50`}
            >
              {saving ? 'Creating...' : 'Create Agreement'}
            </button>
          </div>

          {createError && (
            <div className="px-5 pb-5">
              <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-xs px-3 py-2 rounded-xl">
                {createError}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderEditModal = () => {
    if (!showEditModal || !selected) return null;

    return (
      <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm p-4 flex items-center justify-center">
        <div className={`w-full max-w-lg ${t.modalBg}`}>
          <div className={`flex items-center justify-between p-5 ${t.modalHeader}`}>
            <h3 className={`text-lg ${t.textMain} font-semibold uppercase tracking-wider`}>
              Edit Severance Terms
            </h3>
            <button onClick={() => setShowEditModal(false)} className={t.closeBtnCls}>
              <X size={18} />
            </button>
          </div>

          <div className="p-5 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Severance Amount</label>
                <input
                  type="number"
                  value={editPayload.severance_amount ?? ''}
                  onChange={(e) => setEditPayload((p) => ({ ...p, severance_amount: e.target.value ? Number(e.target.value) : undefined }))}
                  className={`w-full px-3 py-2 ${t.inputCls}`}
                />
              </div>
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Severance Weeks</label>
                <input
                  type="number"
                  value={editPayload.severance_weeks ?? ''}
                  onChange={(e) => setEditPayload((p) => ({ ...p, severance_weeks: e.target.value ? Number(e.target.value) : undefined }))}
                  className={`w-full px-3 py-2 ${t.inputCls}`}
                />
              </div>
            </div>

            <div>
              <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Severance Description</label>
              <textarea
                rows={3}
                value={editPayload.severance_description ?? ''}
                onChange={(e) => setEditPayload((p) => ({ ...p, severance_description: e.target.value }))}
                className={`w-full px-3 py-2 resize-none ${t.inputCls}`}
              />
            </div>

            <div>
              <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Notes</label>
              <textarea
                rows={2}
                value={editPayload.notes ?? ''}
                onChange={(e) => setEditPayload((p) => ({ ...p, notes: e.target.value }))}
                className={`w-full px-3 py-2 resize-none ${t.inputCls}`}
              />
            </div>
          </div>

          <div className={`p-5 ${t.modalFooter} flex justify-end gap-2`}>
            <button
              onClick={() => setShowEditModal(false)}
              className={`px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.cancelBtn}`}
            >
              Cancel
            </button>
            <button
              onClick={handleUpdate}
              disabled={saving}
              className={`px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.btnPrimary} disabled:opacity-50`}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
          {error && (
            <div className="px-5 pb-5">
              <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-xs px-3 py-2 rounded-xl">
                {error}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className={`min-h-screen ${t.pageBg} p-6 lg:p-10`}>
      <div className="max-w-7xl mx-auto">
        {selectedId && selected ? renderDetail() : renderList()}
      </div>

      {renderCreateModal()}
      {renderEditModal()}
    </div>
  );
}
