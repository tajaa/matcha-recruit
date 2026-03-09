import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Clock,
  GraduationCap,
  Plus,
  RefreshCw,
  Save,
  ShieldAlert,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import { training } from '../api/client';
import { useIsLightMode } from '../hooks/useIsLightMode';
import type {
  TrainingComplianceSummary,
  TrainingOverdueRecord,
  TrainingRecord,
  TrainingRecordCreate,
  TrainingRecordStatus,
  TrainingRecordUpdate,
  TrainingRequirement,
  TrainingRequirementCreate,
  TrainingRequirementUpdate,
  TrainingType,
} from '../types';

const TRAINING_TYPES: TrainingType[] = ['harassment_prevention', 'safety', 'food_handler', 'osha', 'custom'];
const RECORD_STATUSES: TrainingRecordStatus[] = ['assigned', 'in_progress', 'completed', 'expired', 'waived'];

type Tab = 'requirements' | 'records' | 'compliance' | 'overdue';

const LT = {
  pageBg: 'bg-stone-50 min-h-screen',
  card: 'bg-white border border-stone-200 rounded-2xl',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  border: 'border-stone-200',
  input: 'bg-white border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:outline-none focus:border-stone-400',
  select: 'bg-white border border-stone-300 text-zinc-900 rounded-xl focus:outline-none focus:border-stone-400',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 text-stone-600 hover:border-stone-400',
  btnDanger: 'border border-red-300 text-red-600 hover:bg-red-50',
  label: 'text-stone-500',
  tableHead: 'text-stone-500 border-b border-stone-200',
  tableRow: 'border-b border-stone-100 hover:bg-stone-50',
  tabActive: 'border-b-2 border-zinc-900 text-zinc-900',
  tabInactive: 'text-stone-400 hover:text-stone-600',
  alertError: 'border border-red-300 bg-red-50 text-red-700',
  alertSuccess: 'border border-emerald-300 bg-emerald-50 text-emerald-700',
  modalOverlay: 'bg-black/30 backdrop-blur-sm',
  modalCard: 'bg-white border border-stone-200 rounded-2xl',
  modalBorder: 'border-stone-200',
  progressBg: 'bg-stone-200',
  progressFill: 'bg-emerald-500',
  overdueCard: 'bg-red-50 border border-red-200',
  overdueText: 'text-red-700',
} as const;

const DK = {
  pageBg: '',
  card: 'bg-zinc-950 border border-white/10',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  border: 'border-white/10',
  input: 'bg-zinc-900 border border-white/10 text-zinc-100 rounded-xl placeholder:text-zinc-600 focus:outline-none focus:border-white/20',
  select: 'bg-zinc-900 border border-white/10 text-zinc-200 rounded-xl focus:outline-none focus:border-white/20',
  btnPrimary: 'bg-white text-zinc-900 hover:bg-zinc-200',
  btnSecondary: 'border border-zinc-700 text-zinc-300 hover:border-zinc-500',
  btnDanger: 'border border-red-500/30 text-red-300 hover:bg-red-500/10',
  label: 'text-zinc-500',
  tableHead: 'text-zinc-500 border-b border-white/10',
  tableRow: 'border-b border-white/5 hover:bg-white/5',
  tabActive: 'border-b-2 border-white text-white',
  tabInactive: 'text-zinc-500 hover:text-zinc-300',
  alertError: 'border border-red-500/30 bg-red-950/20 text-red-300',
  alertSuccess: 'border border-emerald-500/30 bg-emerald-950/20 text-emerald-300',
  modalOverlay: 'bg-black/70 backdrop-blur-sm',
  modalCard: 'bg-zinc-950 border border-zinc-800',
  modalBorder: 'border-white/10',
  progressBg: 'bg-zinc-800',
  progressFill: 'bg-emerald-500',
  overdueCard: 'bg-red-500/10 border border-red-500/20',
  overdueText: 'text-red-300',
} as const;

function formatLabel(value: string): string {
  return value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function statusStyle(status: string, isLight: boolean): string {
  if (isLight) {
    switch (status) {
      case 'completed': return 'bg-emerald-100 text-emerald-700 border-emerald-200';
      case 'expired': return 'bg-red-100 text-red-700 border-red-200';
      case 'in_progress': return 'bg-amber-100 text-amber-700 border-amber-200';
      case 'waived': return 'bg-zinc-100 text-zinc-600 border-zinc-200';
      default: return 'bg-blue-100 text-blue-700 border-blue-200';
    }
  }
  switch (status) {
    case 'completed': return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    case 'expired': return 'bg-red-500/10 text-red-400 border-red-500/20';
    case 'in_progress': return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    case 'waived': return 'bg-zinc-600/20 text-zinc-300 border-zinc-600/30';
    default: return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
  }
}

const EMPTY_REQ_FORM: TrainingRequirementCreate = {
  title: '',
  description: '',
  training_type: 'custom',
  jurisdiction: '',
  frequency_months: 12,
  applies_to: 'all',
};

const EMPTY_RECORD_FORM: TrainingRecordCreate = {
  employee_id: '',
  requirement_id: '',
  title: '',
  training_type: 'custom',
  due_date: '',
  provider: '',
  notes: '',
};

export default function Training() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  const [activeTab, setActiveTab] = useState<Tab>('requirements');

  // Requirements state
  const [requirements, setRequirements] = useState<TrainingRequirement[]>([]);
  const [showActiveOnly, setShowActiveOnly] = useState(true);

  // Records state
  const [records, setRecords] = useState<TrainingRecord[]>([]);
  const [recordStatusFilter, setRecordStatusFilter] = useState<string>('');
  const [recordOverdueFilter, setRecordOverdueFilter] = useState(false);

  // Compliance & overdue state
  const [compliance, setCompliance] = useState<TrainingComplianceSummary[]>([]);
  const [overdueRecords, setOverdueRecords] = useState<TrainingOverdueRecord[]>([]);

  // UI state
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Requirement modals
  const [showReqCreateModal, setShowReqCreateModal] = useState(false);
  const [showReqEditModal, setShowReqEditModal] = useState(false);
  const [reqForm, setReqForm] = useState<TrainingRequirementCreate>(EMPTY_REQ_FORM);
  const [editingReq, setEditingReq] = useState<TrainingRequirement | null>(null);
  const [reqEditForm, setReqEditForm] = useState<TrainingRequirementUpdate>({});

  // Record modals
  const [showRecordCreateModal, setShowRecordCreateModal] = useState(false);
  const [showRecordEditModal, setShowRecordEditModal] = useState(false);
  const [recordForm, setRecordForm] = useState<TrainingRecordCreate>(EMPTY_RECORD_FORM);
  const [editingRecord, setEditingRecord] = useState<TrainingRecord | null>(null);
  const [recordEditForm, setRecordEditForm] = useState<TrainingRecordUpdate>({});

  // Bulk assign
  const [showBulkAssign, setShowBulkAssign] = useState(false);

  const [modalError, setModalError] = useState<string | null>(null);

  // Clear success message after 4 seconds
  useEffect(() => {
    if (!successMessage) return;
    const timer = setTimeout(() => setSuccessMessage(null), 4000);
    return () => clearTimeout(timer);
  }, [successMessage]);

  const loadRequirements = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      const data = await training.listRequirements(showActiveOnly);
      setRequirements(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load requirements');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [showActiveOnly]);

  const loadRecords = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      const params: { status?: string; overdue?: boolean } = {};
      if (recordStatusFilter) params.status = recordStatusFilter;
      if (recordOverdueFilter) params.overdue = true;
      const data = await training.listRecords(params);
      setRecords(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load records');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [recordStatusFilter, recordOverdueFilter]);

  const loadCompliance = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      const data = await training.getCompliance();
      setCompliance(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load compliance data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const loadOverdue = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      const data = await training.getOverdue();
      setOverdueRecords(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load overdue records');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'requirements') loadRequirements();
    else if (activeTab === 'records') loadRecords();
    else if (activeTab === 'compliance') loadCompliance();
    else if (activeTab === 'overdue') loadOverdue();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, showActiveOnly, recordStatusFilter, recordOverdueFilter]);

  const handleRefresh = () => {
    if (activeTab === 'requirements') loadRequirements(true);
    else if (activeTab === 'records') loadRecords(true);
    else if (activeTab === 'compliance') loadCompliance(true);
    else if (activeTab === 'overdue') loadOverdue(true);
  };

  // ---- Requirement CRUD ----

  const handleCreateRequirement = async () => {
    if (!reqForm.title.trim()) return;
    setSaving(true);
    setModalError(null);
    try {
      await training.createRequirement({
        title: reqForm.title.trim(),
        description: reqForm.description?.trim() || undefined,
        training_type: reqForm.training_type,
        jurisdiction: reqForm.jurisdiction?.trim() || undefined,
        frequency_months: reqForm.frequency_months || undefined,
        applies_to: reqForm.applies_to?.trim() || undefined,
      });
      setShowReqCreateModal(false);
      setReqForm(EMPTY_REQ_FORM);
      setSuccessMessage('Requirement created.');
      await loadRequirements(true);
    } catch (err) {
      setModalError(err instanceof Error ? err.message : 'Failed to create requirement');
    } finally {
      setSaving(false);
    }
  };

  const openEditReq = (req: TrainingRequirement) => {
    setEditingReq(req);
    setReqEditForm({
      title: req.title,
      description: req.description || '',
      training_type: req.training_type,
      jurisdiction: req.jurisdiction || '',
      frequency_months: req.frequency_months ?? undefined,
      applies_to: req.applies_to,
      is_active: req.is_active,
    });
    setModalError(null);
    setShowReqEditModal(true);
  };

  const handleUpdateRequirement = async () => {
    if (!editingReq) return;
    setSaving(true);
    setModalError(null);
    try {
      await training.updateRequirement(editingReq.id, {
        title: reqEditForm.title?.trim() || undefined,
        description: reqEditForm.description?.trim() || undefined,
        training_type: reqEditForm.training_type || undefined,
        jurisdiction: reqEditForm.jurisdiction?.trim() || undefined,
        frequency_months: reqEditForm.frequency_months,
        applies_to: reqEditForm.applies_to?.trim() || undefined,
        is_active: reqEditForm.is_active,
      });
      setShowReqEditModal(false);
      setEditingReq(null);
      setSuccessMessage('Requirement updated.');
      await loadRequirements(true);
    } catch (err) {
      setModalError(err instanceof Error ? err.message : 'Failed to update requirement');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteRequirement = async (id: string) => {
    if (!window.confirm('Delete this training requirement?')) return;
    setSaving(true);
    try {
      await training.deleteRequirement(id);
      setSuccessMessage('Requirement deleted.');
      await loadRequirements(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete requirement');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (req: TrainingRequirement) => {
    setSaving(true);
    try {
      await training.updateRequirement(req.id, { is_active: !req.is_active });
      setSuccessMessage(`Requirement ${req.is_active ? 'deactivated' : 'activated'}.`);
      await loadRequirements(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle requirement');
    } finally {
      setSaving(false);
    }
  };

  // ---- Record CRUD ----

  const handleCreateRecord = async () => {
    if (!recordForm.employee_id.trim() || !recordForm.title.trim()) return;
    setSaving(true);
    setModalError(null);
    try {
      await training.createRecord({
        employee_id: recordForm.employee_id.trim(),
        requirement_id: recordForm.requirement_id?.trim() || undefined,
        title: recordForm.title.trim(),
        training_type: recordForm.training_type,
        due_date: recordForm.due_date?.trim() || undefined,
        provider: recordForm.provider?.trim() || undefined,
        notes: recordForm.notes?.trim() || undefined,
      });
      setShowRecordCreateModal(false);
      setRecordForm(EMPTY_RECORD_FORM);
      setSuccessMessage('Record created.');
      await loadRecords(true);
    } catch (err) {
      setModalError(err instanceof Error ? err.message : 'Failed to create record');
    } finally {
      setSaving(false);
    }
  };

  const openEditRecord = (record: TrainingRecord) => {
    setEditingRecord(record);
    setRecordEditForm({
      status: record.status,
      completed_date: record.completed_date || '',
      expiration_date: record.expiration_date || '',
      provider: record.provider || '',
      certificate_number: record.certificate_number || '',
      score: record.score ?? undefined,
      notes: record.notes || '',
    });
    setModalError(null);
    setShowRecordEditModal(true);
  };

  const handleUpdateRecord = async () => {
    if (!editingRecord) return;
    setSaving(true);
    setModalError(null);
    try {
      await training.updateRecord(editingRecord.id, {
        status: recordEditForm.status,
        completed_date: recordEditForm.completed_date?.trim() || undefined,
        expiration_date: recordEditForm.expiration_date?.trim() || undefined,
        provider: recordEditForm.provider?.trim() || undefined,
        certificate_number: recordEditForm.certificate_number?.trim() || undefined,
        score: recordEditForm.score,
        notes: recordEditForm.notes?.trim() || undefined,
      });
      setShowRecordEditModal(false);
      setEditingRecord(null);
      setSuccessMessage('Record updated.');
      await loadRecords(true);
    } catch (err) {
      setModalError(err instanceof Error ? err.message : 'Failed to update record');
    } finally {
      setSaving(false);
    }
  };

  const handleBulkAssign = async (requirementId: string) => {
    setSaving(true);
    try {
      const result = await training.bulkAssign(requirementId);
      setSuccessMessage(`Assigned training to ${result.assigned_count} employee(s).`);
      setShowBulkAssign(false);
      await loadRecords(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to bulk assign');
    } finally {
      setSaving(false);
    }
  };

  // ---- Render helpers ----

  const daysOverdue = (dueDate: string): number => {
    const due = new Date(dueDate);
    const now = new Date();
    return Math.max(0, Math.floor((now.getTime() - due.getTime()) / (1000 * 60 * 60 * 24)));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className={`text-xs uppercase tracking-wider animate-pulse ${t.textMuted}`}>
          Loading training data...
        </div>
      </div>
    );
  }

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: 'requirements', label: 'Requirements', icon: <BookOpen size={14} /> },
    { key: 'records', label: 'Records', icon: <GraduationCap size={14} /> },
    { key: 'compliance', label: 'Compliance', icon: <CheckCircle2 size={14} /> },
    { key: 'overdue', label: 'Overdue', icon: <Clock size={14} /> },
  ];

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className={`flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 border-b ${t.border} pb-6`}>
        <div>
          <h1 className={`text-4xl font-bold tracking-tighter uppercase ${t.textMain}`}>Training</h1>
          <p className={`text-xs mt-2 font-mono tracking-wide uppercase ${t.textMuted}`}>
            Training compliance and certification management
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleRefresh}
            className={`inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider ${t.btnSecondary}`}
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className={`rounded p-4 flex items-center gap-3 ${t.alertError}`}>
          <AlertTriangle size={16} />
          <p className="text-sm">{error}</p>
        </div>
      )}
      {successMessage && (
        <div className={`rounded p-4 flex items-center gap-3 ${t.alertSuccess}`}>
          <ShieldAlert size={16} />
          <p className="text-sm">{successMessage}</p>
        </div>
      )}

      {/* Tabs */}
      <div className={`flex gap-6 border-b ${t.border}`}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`inline-flex items-center gap-1.5 pb-3 text-xs uppercase tracking-wider transition-colors ${
              activeTab === tab.key ? t.tabActive : t.tabInactive
            }`}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* ===================== REQUIREMENTS TAB ===================== */}
      {activeTab === 'requirements' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <label className={`inline-flex items-center gap-2 text-xs uppercase tracking-wider ${t.textMuted}`}>
              <input
                type="checkbox"
                checked={showActiveOnly}
                onChange={(e) => setShowActiveOnly(e.target.checked)}
                className="rounded"
              />
              Active only
            </label>
            <button
              onClick={() => {
                setReqForm(EMPTY_REQ_FORM);
                setModalError(null);
                setShowReqCreateModal(true);
              }}
              className={`inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary}`}
            >
              <Plus size={14} /> New Requirement
            </button>
          </div>

          <div className={`${t.card} overflow-hidden`}>
            <table className="w-full text-sm">
              <thead>
                <tr className={`text-left text-[10px] uppercase tracking-widest ${t.tableHead}`}>
                  <th className="px-4 py-3">Title</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Jurisdiction</th>
                  <th className="px-4 py-3">Frequency</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {requirements.length === 0 ? (
                  <tr>
                    <td colSpan={6} className={`px-4 py-10 text-center text-sm ${t.textMuted}`}>
                      No requirements found.
                    </td>
                  </tr>
                ) : (
                  requirements.map((req) => (
                    <tr
                      key={req.id}
                      className={`${t.tableRow} cursor-pointer`}
                      onClick={() => openEditReq(req)}
                    >
                      <td className={`px-4 py-3 font-medium ${t.textMain}`}>{req.title}</td>
                      <td className={`px-4 py-3 ${t.textMuted}`}>{formatLabel(req.training_type)}</td>
                      <td className={`px-4 py-3 ${t.textMuted}`}>{req.jurisdiction || '--'}</td>
                      <td className={`px-4 py-3 ${t.textMuted}`}>
                        {req.frequency_months ? `${req.frequency_months} mo` : '--'}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`text-[9px] px-2 py-0.5 uppercase tracking-widest border ${
                            req.is_active
                              ? (isLight ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20')
                              : (isLight ? 'bg-zinc-100 text-zinc-500 border-zinc-200' : 'bg-zinc-600/20 text-zinc-400 border-zinc-600/30')
                          }`}
                        >
                          {req.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={() => handleToggleActive(req)}
                            disabled={saving}
                            className={`text-[10px] px-2 py-1 uppercase tracking-wider ${t.btnSecondary} disabled:opacity-50`}
                          >
                            {req.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                          <button
                            onClick={() => handleDeleteRequirement(req.id)}
                            disabled={saving}
                            className={`p-1 ${t.btnDanger} disabled:opacity-50`}
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ===================== RECORDS TAB ===================== */}
      {activeTab === 'records' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={recordStatusFilter}
              onChange={(e) => setRecordStatusFilter(e.target.value)}
              className={`px-3 py-2 text-sm ${t.select}`}
            >
              <option value="">All statuses</option>
              {RECORD_STATUSES.map((s) => (
                <option key={s} value={s}>{formatLabel(s)}</option>
              ))}
            </select>
            <label className={`inline-flex items-center gap-2 text-xs uppercase tracking-wider ${t.textMuted}`}>
              <input
                type="checkbox"
                checked={recordOverdueFilter}
                onChange={(e) => setRecordOverdueFilter(e.target.checked)}
                className="rounded"
              />
              Overdue only
            </label>
            <button
              onClick={() => {
                setRecordForm(EMPTY_RECORD_FORM);
                setModalError(null);
                setShowRecordCreateModal(true);
              }}
              className={`inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary}`}
            >
              <Plus size={14} /> New Record
            </button>
            <div className="relative">
              <button
                onClick={() => setShowBulkAssign(!showBulkAssign)}
                className={`inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider ${t.btnSecondary}`}
              >
                <Users size={14} /> Bulk Assign
              </button>
              {showBulkAssign && (
                <div className={`absolute top-full left-0 mt-1 z-20 w-64 ${t.card} shadow-lg`}>
                  <div className={`px-3 py-2 text-[10px] uppercase tracking-widest ${t.textMuted} border-b ${t.border}`}>
                    Select requirement to assign
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    {requirements.filter((r) => r.is_active).length === 0 ? (
                      <div className={`px-3 py-4 text-xs text-center ${t.textMuted}`}>No active requirements.</div>
                    ) : (
                      requirements
                        .filter((r) => r.is_active)
                        .map((req) => (
                          <button
                            key={req.id}
                            onClick={() => handleBulkAssign(req.id)}
                            disabled={saving}
                            className={`w-full text-left px-3 py-2 text-xs ${t.tableRow} ${t.textMain} disabled:opacity-50`}
                          >
                            {req.title}
                          </button>
                        ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className={`${t.card} overflow-hidden`}>
            <table className="w-full text-sm">
              <thead>
                <tr className={`text-left text-[10px] uppercase tracking-widest ${t.tableHead}`}>
                  <th className="px-4 py-3">Title</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Assigned</th>
                  <th className="px-4 py-3">Due</th>
                  <th className="px-4 py-3">Completed</th>
                  <th className="px-4 py-3">Provider</th>
                </tr>
              </thead>
              <tbody>
                {records.length === 0 ? (
                  <tr>
                    <td colSpan={7} className={`px-4 py-10 text-center text-sm ${t.textMuted}`}>
                      No records found.
                    </td>
                  </tr>
                ) : (
                  records.map((record) => (
                    <tr
                      key={record.id}
                      className={`${t.tableRow} cursor-pointer`}
                      onClick={() => openEditRecord(record)}
                    >
                      <td className={`px-4 py-3 font-medium ${t.textMain}`}>{record.title}</td>
                      <td className={`px-4 py-3 ${t.textMuted}`}>{formatLabel(record.training_type)}</td>
                      <td className="px-4 py-3">
                        <span className={`text-[9px] px-2 py-0.5 uppercase tracking-widest border ${statusStyle(record.status, isLight)}`}>
                          {formatLabel(record.status)}
                        </span>
                      </td>
                      <td className={`px-4 py-3 ${t.textMuted}`}>
                        {new Date(record.assigned_date).toLocaleDateString()}
                      </td>
                      <td className={`px-4 py-3 ${t.textMuted}`}>
                        {record.due_date ? new Date(record.due_date).toLocaleDateString() : '--'}
                      </td>
                      <td className={`px-4 py-3 ${t.textMuted}`}>
                        {record.completed_date ? new Date(record.completed_date).toLocaleDateString() : '--'}
                      </td>
                      <td className={`px-4 py-3 ${t.textMuted}`}>{record.provider || '--'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ===================== COMPLIANCE TAB ===================== */}
      {activeTab === 'compliance' && (
        <div className="space-y-4">
          {compliance.length === 0 ? (
            <div className={`${t.card} p-10 text-center ${t.textMuted}`}>
              No compliance data available.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {compliance.map((item) => {
                const pct = item.total_assigned > 0
                  ? Math.round((item.completed / item.total_assigned) * 100)
                  : 0;
                return (
                  <div key={item.requirement_id} className={`${t.card} p-5 space-y-3`}>
                    <div>
                      <h3 className={`text-sm font-semibold ${t.textMain}`}>{item.title}</h3>
                      <p className={`text-[10px] uppercase tracking-widest mt-1 ${t.textMuted}`}>
                        {formatLabel(item.training_type)}
                        {item.jurisdiction ? ` | ${item.jurisdiction}` : ''}
                        {item.frequency_months ? ` | Every ${item.frequency_months} mo` : ''}
                      </p>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div>
                        <div className={`text-lg font-bold ${t.textMain}`}>{item.total_assigned}</div>
                        <div className={`text-[9px] uppercase tracking-widest ${t.textMuted}`}>Assigned</div>
                      </div>
                      <div>
                        <div className="text-lg font-bold text-emerald-500">{item.completed}</div>
                        <div className={`text-[9px] uppercase tracking-widest ${t.textMuted}`}>Completed</div>
                      </div>
                      <div>
                        <div className={`text-lg font-bold ${item.overdue > 0 ? 'text-red-500' : t.textMuted}`}>
                          {item.overdue}
                        </div>
                        <div className={`text-[9px] uppercase tracking-widest ${t.textMuted}`}>Overdue</div>
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className={`text-[10px] uppercase tracking-wider ${t.textMuted}`}>Progress</span>
                        <span className={`text-[10px] font-medium ${t.textMain}`}>{pct}%</span>
                      </div>
                      <div className={`h-2 rounded-full ${t.progressBg}`}>
                        <div
                          className={`h-2 rounded-full transition-all ${t.progressFill}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ===================== OVERDUE TAB ===================== */}
      {activeTab === 'overdue' && (
        <div className="space-y-4">
          {overdueRecords.length === 0 ? (
            <div className={`${t.card} p-10 text-center ${t.textMuted}`}>
              No overdue training records. All employees are up to date.
            </div>
          ) : (
            <div className="space-y-3">
              {overdueRecords.map((item) => {
                const days = daysOverdue(item.due_date);
                return (
                  <div key={item.record_id} className={`${t.overdueCard} p-4 flex flex-col sm:flex-row sm:items-center gap-3`}>
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <AlertTriangle size={18} className={isLight ? 'text-red-500' : 'text-red-400'} />
                      <div className="min-w-0">
                        <p className={`text-sm font-medium ${t.textMain}`}>
                          {item.first_name} {item.last_name}
                        </p>
                        <p className={`text-xs ${t.textMuted} truncate`}>{item.email}</p>
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm ${t.textMain}`}>{item.training_title}</p>
                      <p className={`text-[10px] uppercase tracking-widest ${t.textMuted}`}>
                        {formatLabel(item.training_type)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className={`text-sm font-semibold ${t.overdueText}`}>
                        {days} day{days !== 1 ? 's' : ''} overdue
                      </p>
                      <p className={`text-[10px] uppercase tracking-widest ${t.textMuted}`}>
                        Due {new Date(item.due_date).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ===================== CREATE REQUIREMENT MODAL ===================== */}
      {showReqCreateModal && (
        <div className={`fixed inset-0 z-50 ${t.modalOverlay} p-4 flex items-center justify-center`}>
          <div className={`w-full max-w-lg ${t.modalCard} rounded-sm`}>
            <div className={`flex items-center justify-between p-5 border-b ${t.modalBorder}`}>
              <h3 className={`text-lg font-semibold uppercase tracking-wider ${t.textMain}`}>
                Create Requirement
              </h3>
              <button onClick={() => setShowReqCreateModal(false)} className={`${t.textMuted} hover:${t.textMain}`}>
                <X size={18} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Title</label>
                <input
                  value={reqForm.title}
                  onChange={(e) => setReqForm((p) => ({ ...p, title: e.target.value }))}
                  className={`w-full px-3 py-2 ${t.input}`}
                />
              </div>
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Description</label>
                <textarea
                  rows={3}
                  value={reqForm.description || ''}
                  onChange={(e) => setReqForm((p) => ({ ...p, description: e.target.value }))}
                  className={`w-full px-3 py-2 resize-none ${t.input}`}
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Training Type</label>
                  <select
                    value={reqForm.training_type}
                    onChange={(e) => setReqForm((p) => ({ ...p, training_type: e.target.value as TrainingType }))}
                    className={`w-full px-3 py-2 ${t.select}`}
                  >
                    {TRAINING_TYPES.map((tt) => (
                      <option key={tt} value={tt}>{formatLabel(tt)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Jurisdiction</label>
                  <input
                    value={reqForm.jurisdiction || ''}
                    onChange={(e) => setReqForm((p) => ({ ...p, jurisdiction: e.target.value }))}
                    placeholder="e.g. CA, Federal"
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Frequency (months)</label>
                  <input
                    type="number"
                    min={1}
                    value={reqForm.frequency_months || ''}
                    onChange={(e) => setReqForm((p) => ({ ...p, frequency_months: parseInt(e.target.value) || undefined }))}
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Applies To</label>
                  <input
                    value={reqForm.applies_to || ''}
                    onChange={(e) => setReqForm((p) => ({ ...p, applies_to: e.target.value }))}
                    placeholder="e.g. all, managers"
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
              </div>
            </div>
            <div className={`p-5 border-t ${t.modalBorder} flex justify-end gap-2`}>
              <button
                onClick={() => setShowReqCreateModal(false)}
                className={`px-3 py-2 text-xs uppercase tracking-wider ${t.textMuted}`}
              >
                Cancel
              </button>
              <button
                onClick={handleCreateRequirement}
                disabled={saving || !reqForm.title.trim()}
                className={`px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary} disabled:opacity-50`}
              >
                {saving ? 'Creating...' : 'Create'}
              </button>
            </div>
            {modalError && (
              <div className="px-5 pb-5">
                <div className={`text-xs px-3 py-2 ${t.alertError}`}>{modalError}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===================== EDIT REQUIREMENT MODAL ===================== */}
      {showReqEditModal && editingReq && (
        <div className={`fixed inset-0 z-50 ${t.modalOverlay} p-4 flex items-center justify-center`}>
          <div className={`w-full max-w-lg ${t.modalCard} rounded-sm`}>
            <div className={`flex items-center justify-between p-5 border-b ${t.modalBorder}`}>
              <h3 className={`text-lg font-semibold uppercase tracking-wider ${t.textMain}`}>
                Edit Requirement
              </h3>
              <button onClick={() => setShowReqEditModal(false)} className={`${t.textMuted} hover:${t.textMain}`}>
                <X size={18} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Title</label>
                <input
                  value={reqEditForm.title || ''}
                  onChange={(e) => setReqEditForm((p) => ({ ...p, title: e.target.value }))}
                  className={`w-full px-3 py-2 ${t.input}`}
                />
              </div>
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Description</label>
                <textarea
                  rows={3}
                  value={reqEditForm.description || ''}
                  onChange={(e) => setReqEditForm((p) => ({ ...p, description: e.target.value }))}
                  className={`w-full px-3 py-2 resize-none ${t.input}`}
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Training Type</label>
                  <select
                    value={reqEditForm.training_type || editingReq.training_type}
                    onChange={(e) => setReqEditForm((p) => ({ ...p, training_type: e.target.value }))}
                    className={`w-full px-3 py-2 ${t.select}`}
                  >
                    {TRAINING_TYPES.map((tt) => (
                      <option key={tt} value={tt}>{formatLabel(tt)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Jurisdiction</label>
                  <input
                    value={reqEditForm.jurisdiction || ''}
                    onChange={(e) => setReqEditForm((p) => ({ ...p, jurisdiction: e.target.value }))}
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Frequency (months)</label>
                  <input
                    type="number"
                    min={1}
                    value={reqEditForm.frequency_months ?? ''}
                    onChange={(e) => setReqEditForm((p) => ({ ...p, frequency_months: parseInt(e.target.value) || undefined }))}
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Applies To</label>
                  <input
                    value={reqEditForm.applies_to || ''}
                    onChange={(e) => setReqEditForm((p) => ({ ...p, applies_to: e.target.value }))}
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
              </div>
              <div>
                <label className={`inline-flex items-center gap-2 text-xs uppercase tracking-wider ${t.textMuted}`}>
                  <input
                    type="checkbox"
                    checked={reqEditForm.is_active ?? editingReq.is_active}
                    onChange={(e) => setReqEditForm((p) => ({ ...p, is_active: e.target.checked }))}
                    className="rounded"
                  />
                  Active
                </label>
              </div>
            </div>
            <div className={`p-5 border-t ${t.modalBorder} flex justify-end gap-2`}>
              <button
                onClick={() => setShowReqEditModal(false)}
                className={`px-3 py-2 text-xs uppercase tracking-wider ${t.textMuted}`}
              >
                Cancel
              </button>
              <button
                onClick={handleUpdateRequirement}
                disabled={saving}
                className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary} disabled:opacity-50`}
              >
                <Save size={14} /> {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
            {modalError && (
              <div className="px-5 pb-5">
                <div className={`text-xs px-3 py-2 ${t.alertError}`}>{modalError}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===================== CREATE RECORD MODAL ===================== */}
      {showRecordCreateModal && (
        <div className={`fixed inset-0 z-50 ${t.modalOverlay} p-4 flex items-center justify-center`}>
          <div className={`w-full max-w-lg ${t.modalCard} rounded-sm`}>
            <div className={`flex items-center justify-between p-5 border-b ${t.modalBorder}`}>
              <h3 className={`text-lg font-semibold uppercase tracking-wider ${t.textMain}`}>
                Create Training Record
              </h3>
              <button onClick={() => setShowRecordCreateModal(false)} className={`${t.textMuted} hover:${t.textMain}`}>
                <X size={18} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Employee ID</label>
                <input
                  value={recordForm.employee_id}
                  onChange={(e) => setRecordForm((p) => ({ ...p, employee_id: e.target.value }))}
                  placeholder="Employee UUID"
                  className={`w-full px-3 py-2 ${t.input}`}
                />
              </div>
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Title</label>
                <input
                  value={recordForm.title}
                  onChange={(e) => setRecordForm((p) => ({ ...p, title: e.target.value }))}
                  className={`w-full px-3 py-2 ${t.input}`}
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Training Type</label>
                  <select
                    value={recordForm.training_type}
                    onChange={(e) => setRecordForm((p) => ({ ...p, training_type: e.target.value as TrainingType }))}
                    className={`w-full px-3 py-2 ${t.select}`}
                  >
                    {TRAINING_TYPES.map((tt) => (
                      <option key={tt} value={tt}>{formatLabel(tt)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>
                    Requirement (optional)
                  </label>
                  <select
                    value={recordForm.requirement_id || ''}
                    onChange={(e) => setRecordForm((p) => ({ ...p, requirement_id: e.target.value || undefined }))}
                    className={`w-full px-3 py-2 ${t.select}`}
                  >
                    <option value="">None</option>
                    {requirements.filter((r) => r.is_active).map((req) => (
                      <option key={req.id} value={req.id}>{req.title}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Due Date</label>
                  <input
                    type="date"
                    value={recordForm.due_date || ''}
                    onChange={(e) => setRecordForm((p) => ({ ...p, due_date: e.target.value }))}
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Provider</label>
                  <input
                    value={recordForm.provider || ''}
                    onChange={(e) => setRecordForm((p) => ({ ...p, provider: e.target.value }))}
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
              </div>
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Notes</label>
                <textarea
                  rows={2}
                  value={recordForm.notes || ''}
                  onChange={(e) => setRecordForm((p) => ({ ...p, notes: e.target.value }))}
                  className={`w-full px-3 py-2 resize-none ${t.input}`}
                />
              </div>
            </div>
            <div className={`p-5 border-t ${t.modalBorder} flex justify-end gap-2`}>
              <button
                onClick={() => setShowRecordCreateModal(false)}
                className={`px-3 py-2 text-xs uppercase tracking-wider ${t.textMuted}`}
              >
                Cancel
              </button>
              <button
                onClick={handleCreateRecord}
                disabled={saving || !recordForm.employee_id.trim() || !recordForm.title.trim()}
                className={`px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary} disabled:opacity-50`}
              >
                {saving ? 'Creating...' : 'Create'}
              </button>
            </div>
            {modalError && (
              <div className="px-5 pb-5">
                <div className={`text-xs px-3 py-2 ${t.alertError}`}>{modalError}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===================== EDIT RECORD MODAL ===================== */}
      {showRecordEditModal && editingRecord && (
        <div className={`fixed inset-0 z-50 ${t.modalOverlay} p-4 flex items-center justify-center`}>
          <div className={`w-full max-w-lg ${t.modalCard} rounded-sm`}>
            <div className={`flex items-center justify-between p-5 border-b ${t.modalBorder}`}>
              <h3 className={`text-lg font-semibold uppercase tracking-wider ${t.textMain}`}>
                Edit Training Record
              </h3>
              <button onClick={() => setShowRecordEditModal(false)} className={`${t.textMuted} hover:${t.textMain}`}>
                <X size={18} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div className={`text-xs ${t.textMuted}`}>
                <span className="font-medium">{editingRecord.title}</span> — {formatLabel(editingRecord.training_type)}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Status</label>
                  <select
                    value={recordEditForm.status || editingRecord.status}
                    onChange={(e) => setRecordEditForm((p) => ({ ...p, status: e.target.value as TrainingRecordStatus }))}
                    className={`w-full px-3 py-2 ${t.select}`}
                  >
                    {RECORD_STATUSES.map((s) => (
                      <option key={s} value={s}>{formatLabel(s)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Score</label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={recordEditForm.score ?? ''}
                    onChange={(e) => setRecordEditForm((p) => ({ ...p, score: e.target.value ? parseInt(e.target.value) : undefined }))}
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Completed Date</label>
                  <input
                    type="date"
                    value={recordEditForm.completed_date || ''}
                    onChange={(e) => setRecordEditForm((p) => ({ ...p, completed_date: e.target.value }))}
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Expiration Date</label>
                  <input
                    type="date"
                    value={recordEditForm.expiration_date || ''}
                    onChange={(e) => setRecordEditForm((p) => ({ ...p, expiration_date: e.target.value }))}
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Provider</label>
                  <input
                    value={recordEditForm.provider || ''}
                    onChange={(e) => setRecordEditForm((p) => ({ ...p, provider: e.target.value }))}
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Certificate Number</label>
                  <input
                    value={recordEditForm.certificate_number || ''}
                    onChange={(e) => setRecordEditForm((p) => ({ ...p, certificate_number: e.target.value }))}
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
              </div>
              <div>
                <label className={`block text-[10px] uppercase tracking-wider ${t.label} mb-1`}>Notes</label>
                <textarea
                  rows={2}
                  value={recordEditForm.notes || ''}
                  onChange={(e) => setRecordEditForm((p) => ({ ...p, notes: e.target.value }))}
                  className={`w-full px-3 py-2 resize-none ${t.input}`}
                />
              </div>
            </div>
            <div className={`p-5 border-t ${t.modalBorder} flex justify-end gap-2`}>
              <button
                onClick={() => setShowRecordEditModal(false)}
                className={`px-3 py-2 text-xs uppercase tracking-wider ${t.textMuted}`}
              >
                Cancel
              </button>
              <button
                onClick={handleUpdateRecord}
                disabled={saving}
                className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary} disabled:opacity-50`}
              >
                <Save size={14} /> {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
            {modalError && (
              <div className="px-5 pb-5">
                <div className={`text-xs px-3 py-2 ${t.alertError}`}>{modalError}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
