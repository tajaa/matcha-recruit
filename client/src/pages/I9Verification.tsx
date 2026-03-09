import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Calendar,
  CheckCircle,
  Clock,
  ClipboardList,
  FileCheck,
  Filter,
  Plus,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  Users,
  X,
  XCircle,
} from 'lucide-react';
import { i9 } from '../api/client';
import { useIsLightMode } from '../hooks/useIsLightMode';
import type {
  I9Record,
  I9Status,
  I9ListUsed,
  I9CreateRequest,
  I9UpdateRequest,
  I9ComplianceSummary,
  I9IncompleteResponse,
} from '../types';

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  innerEl: 'bg-stone-200/60 rounded-xl border border-stone-200',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  borderTab: 'border-stone-400/40',
  divide: 'divide-stone-200',
  tabActive: 'border-zinc-900 text-zinc-900',
  tabInactive: 'border-transparent text-stone-500 hover:text-stone-700 hover:border-stone-400',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 text-stone-500 hover:text-zinc-900 hover:border-stone-400',
  modalBg: 'bg-stone-100 border border-stone-200 shadow-2xl rounded-2xl',
  modalHeader: 'border-b border-stone-200',
  modalFooter: 'border-t border-stone-200',
  inputCls: 'bg-white border border-stone-300 text-zinc-900 text-sm rounded-xl focus:outline-none focus:border-stone-400 placeholder:text-stone-400 transition-colors',
  rowHover: 'hover:bg-stone-50',
  alertError: 'bg-red-50 border border-red-300',
  alertErrorText: 'text-red-700',
  alertSuccess: 'bg-emerald-50 border border-emerald-300',
  alertSuccessText: 'text-emerald-700',
  closeBtnCls: 'text-stone-400 hover:text-zinc-900 transition-colors',
  cancelBtn: 'text-stone-500 hover:text-zinc-900',
  tableHeader: 'bg-stone-200 text-stone-500',
  statCard: 'bg-stone-200/60 border border-stone-200 rounded-2xl',
  progressBg: 'bg-stone-300',
  progressFill: 'bg-zinc-900',
  urgentBg: 'bg-red-50 border border-red-200',
  urgentText: 'text-red-700',
  warningBg: 'bg-amber-50 border border-amber-200',
  warningText: 'text-amber-700',
  normalBg: 'bg-stone-50 border border-stone-200',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  innerEl: 'bg-zinc-900/40 rounded-xl border border-white/10',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  borderTab: 'border-white/10',
  divide: 'divide-white/10',
  tabActive: 'border-zinc-100 text-zinc-100',
  tabInactive: 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-600',
  btnPrimary: 'bg-zinc-100 text-zinc-900 hover:bg-white',
  btnSecondary: 'border border-white/10 text-zinc-500 hover:text-zinc-100 hover:border-white/20',
  modalBg: 'bg-zinc-900 border border-white/10 shadow-2xl rounded-2xl',
  modalHeader: 'border-b border-white/10',
  modalFooter: 'border-t border-white/10',
  inputCls: 'bg-zinc-800 border border-white/10 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-white/20 placeholder:text-zinc-600 transition-colors',
  rowHover: 'hover:bg-white/5',
  alertError: 'bg-red-950/30 border border-red-500/30',
  alertErrorText: 'text-red-400',
  alertSuccess: 'bg-emerald-950/30 border border-emerald-500/30',
  alertSuccessText: 'text-emerald-400',
  closeBtnCls: 'text-zinc-500 hover:text-zinc-100 transition-colors',
  cancelBtn: 'text-zinc-500 hover:text-zinc-100',
  tableHeader: 'bg-zinc-800 text-zinc-500',
  statCard: 'bg-zinc-800/60 border border-white/10 rounded-2xl',
  progressBg: 'bg-zinc-700',
  progressFill: 'bg-zinc-100',
  urgentBg: 'bg-red-950/30 border border-red-500/30',
  urgentText: 'text-red-400',
  warningBg: 'bg-amber-950/30 border border-amber-500/30',
  warningText: 'text-amber-400',
  normalBg: 'bg-zinc-800/40 border border-white/10',
} as const;

const STATUS_OPTIONS: I9Status[] = [
  'pending_section1',
  'pending_section2',
  'complete',
  'reverification_needed',
  'reverified',
];

const LIST_USED_OPTIONS: I9ListUsed[] = ['list_a', 'list_b_c'];

type TabKey = 'records' | 'expiring' | 'incomplete' | 'compliance';

function formatLabel(value: string): string {
  return value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function statusStyle(status: string, isLight: boolean): string {
  if (isLight) {
    switch (status) {
      case 'complete':
      case 'reverified':
        return 'bg-emerald-100 text-emerald-800 border-emerald-200';
      case 'reverification_needed':
        return 'bg-amber-100 text-amber-800 border-amber-200';
      case 'pending_section1':
      case 'pending_section2':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      default:
        return 'bg-stone-200 text-stone-700 border-stone-300';
    }
  }
  switch (status) {
    case 'complete':
    case 'reverified':
      return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    case 'reverification_needed':
      return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    case 'pending_section1':
    case 'pending_section2':
      return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    default:
      return 'bg-zinc-600/20 text-zinc-300 border-zinc-600/30';
  }
}

function daysUntil(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const diff = new Date(dateStr).getTime() - Date.now();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '\u2014';
  return new Date(dateStr).toLocaleDateString();
}

export default function I9Verification() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  const [tab, setTab] = useState<TabKey>('records');
  const [records, setRecords] = useState<I9Record[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Detail/edit modal
  const [selectedRecord, setSelectedRecord] = useState<I9Record | null>(null);
  const [editForm, setEditForm] = useState<I9UpdateRequest>({});
  const [saving, setSaving] = useState(false);

  // Create modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createForm, setCreateForm] = useState<I9CreateRequest>({ employee_id: '' });
  const [createError, setCreateError] = useState<string | null>(null);

  // Expiring tab
  const [expiringDays, setExpiringDays] = useState(90);
  const [expiringRecords, setExpiringRecords] = useState<I9Record[]>([]);
  const [expiringLoading, setExpiringLoading] = useState(false);

  // Incomplete tab
  const [incompleteData, setIncompleteData] = useState<I9IncompleteResponse | null>(null);
  const [incompleteLoading, setIncompleteLoading] = useState(false);

  // Compliance tab
  const [complianceData, setComplianceData] = useState<I9ComplianceSummary | null>(null);
  const [complianceLoading, setComplianceLoading] = useState(false);

  const loadRecords = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      const data = await i9.list(statusFilter ? { status: statusFilter } : undefined);
      setRecords(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load I-9 records');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [statusFilter]);

  const loadExpiring = useCallback(async () => {
    setExpiringLoading(true);
    try {
      const data = await i9.getExpiring(expiringDays);
      setExpiringRecords(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load expiring records');
    } finally {
      setExpiringLoading(false);
    }
  }, [expiringDays]);

  const loadIncomplete = useCallback(async () => {
    setIncompleteLoading(true);
    try {
      const data = await i9.getIncomplete();
      setIncompleteData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load incomplete records');
    } finally {
      setIncompleteLoading(false);
    }
  }, []);

  const loadCompliance = useCallback(async () => {
    setComplianceLoading(true);
    try {
      const data = await i9.getComplianceSummary();
      setComplianceData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load compliance summary');
    } finally {
      setComplianceLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === 'records') void loadRecords();
    else if (tab === 'expiring') void loadExpiring();
    else if (tab === 'incomplete') void loadIncomplete();
    else if (tab === 'compliance') void loadCompliance();
  }, [tab, statusFilter, loadRecords, loadExpiring, loadIncomplete, loadCompliance]);

  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [successMessage]);

  const handleCreate = async () => {
    if (!createForm.employee_id.trim()) return;
    setSaving(true);
    setCreateError(null);
    try {
      await i9.create(createForm);
      setShowCreateModal(false);
      setCreateForm({ employee_id: '' });
      setSuccessMessage('I-9 record created.');
      void loadRecords(true);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create record');
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async () => {
    if (!selectedRecord) return;
    setSaving(true);
    try {
      const updated = await i9.update(selectedRecord.id, editForm);
      setSelectedRecord(updated);
      setSuccessMessage('I-9 record updated.');
      void loadRecords(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update record');
    } finally {
      setSaving(false);
    }
  };

  const openDetailModal = (record: I9Record) => {
    setSelectedRecord(record);
    setEditForm({
      status: record.status,
      section1_completed_date: record.section1_completed_date ?? undefined,
      section2_completed_date: record.section2_completed_date ?? undefined,
      document_title: record.document_title ?? undefined,
      list_used: record.list_used ?? undefined,
      document_number: record.document_number ?? undefined,
      issuing_authority: record.issuing_authority ?? undefined,
      expiration_date: record.expiration_date ?? undefined,
      reverification_date: record.reverification_date ?? undefined,
      reverification_document: record.reverification_document ?? undefined,
      reverification_expiration: record.reverification_expiration ?? undefined,
      everify_case_number: record.everify_case_number ?? undefined,
      everify_status: record.everify_status ?? undefined,
      notes: record.notes ?? undefined,
    });
  };

  const tabs: { key: TabKey; label: string; icon: React.ReactNode }[] = [
    { key: 'records', label: 'Records', icon: <ClipboardList size={15} /> },
    { key: 'expiring', label: 'Expiring', icon: <Clock size={15} /> },
    { key: 'incomplete', label: 'Incomplete', icon: <AlertTriangle size={15} /> },
    { key: 'compliance', label: 'Compliance', icon: <Shield size={15} /> },
  ];

  if (loading && tab === 'records') {
    return (
      <div className={`min-h-screen ${t.pageBg} flex items-center justify-center`}>
        <div className={`text-xs ${t.textMuted} uppercase tracking-wider animate-pulse`}>
          Loading I-9 records...
        </div>
      </div>
    );
  }

  return (
    <div className={`min-h-screen ${t.pageBg}`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">
        {/* Header */}
        <div className={`flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 border-b ${t.border} pb-6`}>
          <div>
            <div className="flex items-center gap-3">
              <FileCheck size={28} className={isLight ? 'text-zinc-900' : 'text-zinc-100'} />
              <h1 className={`text-4xl font-bold tracking-tighter ${t.textMain} uppercase`}>
                I-9 Verification
              </h1>
            </div>
            <p className={`text-xs ${t.textMuted} mt-2 font-mono tracking-wide uppercase`}>
              Employment eligibility verification tracking
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => {
                if (tab === 'records') void loadRecords(true);
                else if (tab === 'expiring') void loadExpiring();
                else if (tab === 'incomplete') void loadIncomplete();
                else void loadCompliance();
              }}
              className={`inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.btnSecondary}`}
              disabled={refreshing}
            >
              <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> Refresh
            </button>
            <button
              onClick={() => { setCreateError(null); setShowCreateModal(true); }}
              className={`inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.btnPrimary}`}
            >
              <Plus size={14} /> New I-9
            </button>
          </div>
        </div>

        {/* Alerts */}
        {error && (
          <div className={`${t.alertError} rounded-xl p-4 flex items-center gap-3`}>
            <AlertTriangle className={t.alertErrorText} size={16} />
            <p className={`text-sm ${t.alertErrorText}`}>{error}</p>
            <button onClick={() => setError(null)} className={`ml-auto ${t.closeBtnCls}`}><X size={14} /></button>
          </div>
        )}
        {successMessage && (
          <div className={`${t.alertSuccess} rounded-xl p-4 flex items-center gap-3`}>
            <CheckCircle className={t.alertSuccessText} size={16} />
            <p className={`text-sm ${t.alertSuccessText}`}>{successMessage}</p>
          </div>
        )}

        {/* Tabs */}
        <div className={`flex gap-6 border-b ${t.borderTab}`}>
          {tabs.map((tb) => (
            <button
              key={tb.key}
              onClick={() => setTab(tb.key)}
              className={`inline-flex items-center gap-2 pb-3 text-xs uppercase tracking-wider border-b-2 transition-colors ${
                tab === tb.key ? t.tabActive : t.tabInactive
              }`}
            >
              {tb.icon} {tb.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {tab === 'records' && (
          <RecordsTab
            t={t}
            isLight={isLight}
            records={records}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            onRowClick={openDetailModal}
          />
        )}
        {tab === 'expiring' && (
          <ExpiringTab
            t={t}
            isLight={isLight}
            records={expiringRecords}
            days={expiringDays}
            setDays={setExpiringDays}
            loading={expiringLoading}
            onReload={loadExpiring}
          />
        )}
        {tab === 'incomplete' && (
          <IncompleteTab t={t} isLight={isLight} data={incompleteData} loading={incompleteLoading} />
        )}
        {tab === 'compliance' && (
          <ComplianceTab t={t} isLight={isLight} data={complianceData} loading={complianceLoading} />
        )}

        {/* Detail / Edit Modal */}
        {selectedRecord && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm p-4 flex items-center justify-center overflow-y-auto">
            <div className={`w-full max-w-2xl ${t.modalBg} my-8`}>
              <div className={`flex items-center justify-between p-5 ${t.modalHeader}`}>
                <h3 className={`text-lg font-semibold uppercase tracking-wider ${t.textMain}`}>
                  I-9 Record Detail
                </h3>
                <button onClick={() => setSelectedRecord(null)} className={t.closeBtnCls}>
                  <X size={18} />
                </button>
              </div>
              <div className="p-5 space-y-5 max-h-[70vh] overflow-y-auto">
                {/* Employee info */}
                <div className={`${t.innerEl} p-3`}>
                  <p className={`text-[10px] uppercase tracking-widest ${t.textMuted} mb-1`}>Employee</p>
                  <p className={`text-sm font-medium ${t.textMain}`}>
                    {selectedRecord.first_name} {selectedRecord.last_name}
                  </p>
                  <p className={`text-xs ${t.textFaint}`}>ID: {selectedRecord.employee_id}</p>
                </div>

                {/* Section 1 */}
                <div>
                  <h4 className={`text-[10px] uppercase tracking-widest ${t.textMuted} mb-3 flex items-center gap-2`}>
                    <FileCheck size={12} /> Section 1 - Employee Information
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Status</label>
                      <select
                        value={editForm.status || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, status: e.target.value as I9Status }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                      >
                        {STATUS_OPTIONS.map((s) => (
                          <option key={s} value={s}>{formatLabel(s)}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Section 1 Completed</label>
                      <input
                        type="date"
                        value={editForm.section1_completed_date || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, section1_completed_date: e.target.value || undefined }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                      />
                    </div>
                  </div>
                </div>

                {/* Section 2 / Documents */}
                <div>
                  <h4 className={`text-[10px] uppercase tracking-widest ${t.textMuted} mb-3 flex items-center gap-2`}>
                    <ClipboardList size={12} /> Section 2 - Employer Review & Documents
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Section 2 Completed</label>
                      <input
                        type="date"
                        value={editForm.section2_completed_date || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, section2_completed_date: e.target.value || undefined }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                      />
                    </div>
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>List Used</label>
                      <select
                        value={editForm.list_used || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, list_used: (e.target.value || undefined) as I9ListUsed | undefined }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                      >
                        <option value="">Not set</option>
                        {LIST_USED_OPTIONS.map((l) => (
                          <option key={l} value={l}>{formatLabel(l)}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Document Title</label>
                      <input
                        value={editForm.document_title || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, document_title: e.target.value || undefined }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                        placeholder="e.g., US Passport"
                      />
                    </div>
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Document Number</label>
                      <input
                        value={editForm.document_number || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, document_number: e.target.value || undefined }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                      />
                    </div>
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Issuing Authority</label>
                      <input
                        value={editForm.issuing_authority || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, issuing_authority: e.target.value || undefined }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                      />
                    </div>
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Expiration Date</label>
                      <input
                        type="date"
                        value={editForm.expiration_date || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, expiration_date: e.target.value || undefined }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                      />
                    </div>
                  </div>
                </div>

                {/* E-Verify */}
                <div>
                  <h4 className={`text-[10px] uppercase tracking-widest ${t.textMuted} mb-3 flex items-center gap-2`}>
                    <Shield size={12} /> E-Verify
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Case Number</label>
                      <input
                        value={editForm.everify_case_number || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, everify_case_number: e.target.value || undefined }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                      />
                    </div>
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>E-Verify Status</label>
                      <input
                        value={editForm.everify_status || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, everify_status: e.target.value || undefined }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                        placeholder="e.g., Employment Authorized"
                      />
                    </div>
                  </div>
                </div>

                {/* Reverification */}
                <div>
                  <h4 className={`text-[10px] uppercase tracking-widest ${t.textMuted} mb-3 flex items-center gap-2`}>
                    <RefreshCw size={12} /> Reverification
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Reverification Date</label>
                      <input
                        type="date"
                        value={editForm.reverification_date || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, reverification_date: e.target.value || undefined }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                      />
                    </div>
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Reverification Document</label>
                      <input
                        value={editForm.reverification_document || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, reverification_document: e.target.value || undefined }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                      />
                    </div>
                    <div>
                      <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Reverification Expiration</label>
                      <input
                        type="date"
                        value={editForm.reverification_expiration || ''}
                        onChange={(e) => setEditForm((p) => ({ ...p, reverification_expiration: e.target.value || undefined }))}
                        className={`w-full px-3 py-2 ${t.inputCls}`}
                      />
                    </div>
                  </div>
                </div>

                {/* Notes */}
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Notes</label>
                  <textarea
                    rows={3}
                    value={editForm.notes || ''}
                    onChange={(e) => setEditForm((p) => ({ ...p, notes: e.target.value || undefined }))}
                    className={`w-full px-3 py-2 resize-none ${t.inputCls}`}
                  />
                </div>
              </div>
              <div className={`p-5 ${t.modalFooter} flex justify-end gap-2`}>
                <button
                  onClick={() => setSelectedRecord(null)}
                  className={`px-3 py-2 text-xs uppercase tracking-wider ${t.cancelBtn}`}
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
            </div>
          </div>
        )}

        {/* Create Modal */}
        {showCreateModal && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm p-4 flex items-center justify-center">
            <div className={`w-full max-w-lg ${t.modalBg}`}>
              <div className={`flex items-center justify-between p-5 ${t.modalHeader}`}>
                <h3 className={`text-lg font-semibold uppercase tracking-wider ${t.textMain}`}>
                  Create I-9 Record
                </h3>
                <button onClick={() => setShowCreateModal(false)} className={t.closeBtnCls}>
                  <X size={18} />
                </button>
              </div>
              <div className="p-5 space-y-4">
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Employee ID</label>
                  <input
                    value={createForm.employee_id}
                    onChange={(e) => setCreateForm((p) => ({ ...p, employee_id: e.target.value }))}
                    className={`w-full px-3 py-2 ${t.inputCls}`}
                    placeholder="Enter employee ID"
                  />
                </div>
                <div>
                  <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted} mb-1`}>Notes (optional)</label>
                  <textarea
                    rows={3}
                    value={createForm.notes || ''}
                    onChange={(e) => setCreateForm((p) => ({ ...p, notes: e.target.value || undefined }))}
                    className={`w-full px-3 py-2 resize-none ${t.inputCls}`}
                    placeholder="Any initial notes..."
                  />
                </div>
              </div>
              <div className={`p-5 ${t.modalFooter} flex justify-end gap-2`}>
                <button
                  onClick={() => { setCreateError(null); setShowCreateModal(false); }}
                  className={`px-3 py-2 text-xs uppercase tracking-wider ${t.cancelBtn}`}
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={saving || !createForm.employee_id.trim()}
                  className={`px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.btnPrimary} disabled:opacity-50`}
                >
                  {saving ? 'Creating...' : 'Create Record'}
                </button>
              </div>
              {createError && (
                <div className="px-5 pb-5">
                  <div className={`${t.alertError} rounded-xl ${t.alertErrorText} text-xs px-3 py-2`}>
                    {createError}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ───────────────────── Records Tab ───────────────────── */

function RecordsTab({
  t,
  isLight,
  records,
  statusFilter,
  setStatusFilter,
  onRowClick,
}: {
  t: typeof LT;
  isLight: boolean;
  records: I9Record[];
  statusFilter: string;
  setStatusFilter: (v: string) => void;
  onRowClick: (r: I9Record) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Filter size={14} className={t.textMuted} />
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
        <span className={`text-xs ${t.textMuted}`}>{records.length} record{records.length !== 1 ? 's' : ''}</span>
      </div>

      <div className={`${t.card} overflow-hidden`}>
        {records.length === 0 ? (
          <div className={`px-4 py-10 text-center ${t.textMuted} text-sm`}>No I-9 records found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={t.tableHeader}>
                  <th className="px-4 py-3 text-left text-[10px] uppercase tracking-widest font-medium">Employee</th>
                  <th className="px-4 py-3 text-left text-[10px] uppercase tracking-widest font-medium">Status</th>
                  <th className="px-4 py-3 text-left text-[10px] uppercase tracking-widest font-medium hidden md:table-cell">Section 1</th>
                  <th className="px-4 py-3 text-left text-[10px] uppercase tracking-widest font-medium hidden md:table-cell">Section 2</th>
                  <th className="px-4 py-3 text-left text-[10px] uppercase tracking-widest font-medium hidden lg:table-cell">Document</th>
                  <th className="px-4 py-3 text-left text-[10px] uppercase tracking-widest font-medium hidden lg:table-cell">Expiration</th>
                </tr>
              </thead>
              <tbody className={t.divide}>
                {records.map((rec) => (
                  <tr
                    key={rec.id}
                    onClick={() => onRowClick(rec)}
                    className={`cursor-pointer transition-colors ${t.rowHover}`}
                  >
                    <td className={`px-4 py-3 ${t.textMain} font-medium`}>
                      {rec.first_name || rec.last_name
                        ? `${rec.first_name ?? ''} ${rec.last_name ?? ''}`.trim()
                        : rec.employee_id}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[9px] px-2 py-0.5 uppercase tracking-widest border rounded-full ${statusStyle(rec.status, isLight)}`}>
                        {formatLabel(rec.status)}
                      </span>
                    </td>
                    <td className={`px-4 py-3 ${t.textDim} hidden md:table-cell`}>{formatDate(rec.section1_completed_date)}</td>
                    <td className={`px-4 py-3 ${t.textDim} hidden md:table-cell`}>{formatDate(rec.section2_completed_date)}</td>
                    <td className={`px-4 py-3 ${t.textDim} hidden lg:table-cell truncate max-w-[160px]`}>{rec.document_title || '\u2014'}</td>
                    <td className={`px-4 py-3 ${t.textDim} hidden lg:table-cell`}>{formatDate(rec.expiration_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ───────────────────── Expiring Tab ───────────────────── */

function ExpiringTab({
  t,
  isLight,
  records,
  days,
  setDays,
  loading,
  onReload,
}: {
  t: typeof LT;
  isLight: boolean;
  records: I9Record[];
  days: number;
  setDays: (d: number) => void;
  loading: boolean;
  onReload: () => void;
}) {
  const [inputVal, setInputVal] = useState(String(days));

  const applyDays = () => {
    const n = parseInt(inputVal, 10);
    if (!isNaN(n) && n > 0) {
      setDays(n);
    } else {
      setInputVal(String(days));
    }
  };

  useEffect(() => {
    setInputVal(String(days));
  }, [days]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Calendar size={14} className={t.textMuted} />
        <span className={`text-xs ${t.textMuted} uppercase tracking-wider`}>Expiring within</span>
        <input
          type="number"
          min={1}
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          onBlur={applyDays}
          onKeyDown={(e) => e.key === 'Enter' && applyDays()}
          className={`w-20 px-3 py-2 text-sm ${t.inputCls}`}
        />
        <span className={`text-xs ${t.textMuted} uppercase tracking-wider`}>days</span>
        <button
          onClick={onReload}
          className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider rounded-xl ${t.btnSecondary}`}
        >
          <Search size={12} /> Search
        </button>
      </div>

      {loading ? (
        <div className={`${t.card} p-10 text-center`}>
          <p className={`text-xs ${t.textMuted} uppercase tracking-wider animate-pulse`}>Loading expiring records...</p>
        </div>
      ) : records.length === 0 ? (
        <div className={`${t.card} p-10 text-center`}>
          <p className={`text-sm ${t.textMuted}`}>No documents expiring within {days} days.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {records.map((rec) => {
            const remaining = daysUntil(rec.expiration_date);
            let urgencyClass: string;
            if (remaining !== null && remaining <= 14) {
              urgencyClass = `${t.urgentBg} ${t.urgentText}`;
            } else if (remaining !== null && remaining <= 30) {
              urgencyClass = `${t.warningBg} ${t.warningText}`;
            } else {
              urgencyClass = `${t.normalBg} ${t.textDim}`;
            }

            return (
              <div key={rec.id} className={`${urgencyClass} rounded-xl p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2`}>
                <div>
                  <p className={`text-sm font-medium ${t.textMain}`}>
                    {rec.first_name || rec.last_name
                      ? `${rec.first_name ?? ''} ${rec.last_name ?? ''}`.trim()
                      : rec.employee_id}
                  </p>
                  <p className={`text-xs ${t.textDim}`}>
                    {rec.document_title || 'Document'} &middot; Expires {formatDate(rec.expiration_date)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {remaining !== null && (
                    <span className={`text-xs font-semibold px-2 py-1 rounded-lg ${
                      remaining <= 0
                        ? (isLight ? 'bg-red-200 text-red-900' : 'bg-red-500/20 text-red-300')
                        : remaining <= 14
                          ? (isLight ? 'bg-red-100 text-red-800' : 'bg-red-500/10 text-red-400')
                          : remaining <= 30
                            ? (isLight ? 'bg-amber-100 text-amber-800' : 'bg-amber-500/10 text-amber-400')
                            : (isLight ? 'bg-stone-200 text-stone-700' : 'bg-zinc-700 text-zinc-300')
                    }`}>
                      {remaining <= 0 ? 'OVERDUE' : `${remaining}d remaining`}
                    </span>
                  )}
                  <span className={`text-[9px] px-2 py-0.5 uppercase tracking-widest border rounded-full ${statusStyle(rec.status, isLight)}`}>
                    {formatLabel(rec.status)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ───────────────────── Incomplete Tab ───────────────────── */

function IncompleteTab({
  t,
  isLight,
  data,
  loading,
}: {
  t: typeof LT;
  isLight: boolean;
  data: I9IncompleteResponse | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className={`${t.card} p-10 text-center`}>
        <p className={`text-xs ${t.textMuted} uppercase tracking-wider animate-pulse`}>Loading incomplete records...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className={`${t.card} p-10 text-center`}>
        <p className={`text-sm ${t.textMuted}`}>Unable to load incomplete data.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* No I-9 on File */}
      <div className={`${t.card} overflow-hidden`}>
        <div className={`px-5 py-4 ${t.modalHeader} flex items-center gap-2`}>
          <XCircle size={16} className={isLight ? 'text-red-600' : 'text-red-400'} />
          <h3 className={`text-sm font-semibold uppercase tracking-wider ${t.textMain}`}>
            No I-9 on File ({data.no_record.length})
          </h3>
        </div>
        {data.no_record.length === 0 ? (
          <div className={`px-5 py-8 text-center ${t.textMuted} text-sm`}>All employees have I-9 records on file.</div>
        ) : (
          <div className={`${t.divide}`}>
            {data.no_record.map((emp) => (
              <div key={emp.id} className={`px-5 py-3 flex items-center justify-between ${t.rowHover}`}>
                <div>
                  <p className={`text-sm font-medium ${t.textMain}`}>{emp.first_name} {emp.last_name}</p>
                  <p className={`text-xs ${t.textFaint}`}>{emp.email}</p>
                </div>
                <span className={`text-[9px] px-2 py-0.5 uppercase tracking-widest border rounded-full ${
                  isLight ? 'bg-red-100 text-red-800 border-red-200' : 'bg-red-500/10 text-red-400 border-red-500/20'
                }`}>
                  Missing
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Incomplete I-9s */}
      <div className={`${t.card} overflow-hidden`}>
        <div className={`px-5 py-4 ${t.modalHeader} flex items-center gap-2`}>
          <Clock size={16} className={isLight ? 'text-amber-600' : 'text-amber-400'} />
          <h3 className={`text-sm font-semibold uppercase tracking-wider ${t.textMain}`}>
            Incomplete I-9s ({data.incomplete.length})
          </h3>
        </div>
        {data.incomplete.length === 0 ? (
          <div className={`px-5 py-8 text-center ${t.textMuted} text-sm`}>All existing I-9 records are complete.</div>
        ) : (
          <div className={t.divide}>
            {data.incomplete.map((rec) => (
              <div key={rec.id} className={`px-5 py-3 flex items-center justify-between gap-3 ${t.rowHover}`}>
                <div className="min-w-0">
                  <p className={`text-sm font-medium ${t.textMain}`}>
                    {rec.first_name || rec.last_name
                      ? `${rec.first_name ?? ''} ${rec.last_name ?? ''}`.trim()
                      : rec.employee_id}
                  </p>
                  <p className={`text-xs ${t.textFaint}`}>
                    Created {formatDate(rec.created_at)}
                    {rec.section1_completed_date ? ` \u00b7 Section 1 done` : ''}
                  </p>
                </div>
                <span className={`text-[9px] px-2 py-0.5 uppercase tracking-widest border rounded-full whitespace-nowrap ${statusStyle(rec.status, isLight)}`}>
                  {formatLabel(rec.status)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ───────────────────── Compliance Tab ───────────────────── */

function ComplianceTab({
  t,
  isLight,
  data,
  loading,
}: {
  t: typeof LT;
  isLight: boolean;
  data: I9ComplianceSummary | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className={`${t.card} p-10 text-center`}>
        <p className={`text-xs ${t.textMuted} uppercase tracking-wider animate-pulse`}>Loading compliance summary...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className={`${t.card} p-10 text-center`}>
        <p className={`text-sm ${t.textMuted}`}>Unable to load compliance data.</p>
      </div>
    );
  }

  const pct = Math.round(data.completion_rate * 100);

  const stats: { label: string; value: number | string; icon: React.ReactNode; color: string }[] = [
    {
      label: 'Total Employees',
      value: data.total_employees,
      icon: <Users size={20} />,
      color: isLight ? 'text-zinc-900' : 'text-zinc-100',
    },
    {
      label: 'Complete',
      value: data.complete_count,
      icon: <CheckCircle size={20} />,
      color: isLight ? 'text-emerald-700' : 'text-emerald-400',
    },
    {
      label: 'Incomplete',
      value: data.incomplete_count,
      icon: <AlertTriangle size={20} />,
      color: isLight ? 'text-amber-700' : 'text-amber-400',
    },
    {
      label: 'Expiring Soon',
      value: data.expiring_soon_count,
      icon: <Clock size={20} />,
      color: isLight ? 'text-orange-700' : 'text-orange-400',
    },
    {
      label: 'Overdue',
      value: data.overdue_count,
      icon: <ShieldAlert size={20} />,
      color: isLight ? 'text-red-700' : 'text-red-400',
    },
    {
      label: 'Completion Rate',
      value: `${pct}%`,
      icon: <FileCheck size={20} />,
      color: pct >= 90
        ? (isLight ? 'text-emerald-700' : 'text-emerald-400')
        : pct >= 70
          ? (isLight ? 'text-amber-700' : 'text-amber-400')
          : (isLight ? 'text-red-700' : 'text-red-400'),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {stats.map((stat) => (
          <div key={stat.label} className={`${t.statCard} p-5 space-y-3`}>
            <div className="flex items-center justify-between">
              <span className={`text-[10px] uppercase tracking-widest ${t.textMuted}`}>{stat.label}</span>
              <span className={stat.color}>{stat.icon}</span>
            </div>
            <p className={`text-3xl font-bold tracking-tight ${stat.color}`}>{stat.value}</p>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className={`${t.card} p-5 space-y-3`}>
        <div className="flex items-center justify-between">
          <span className={`text-[10px] uppercase tracking-widest ${t.textMuted}`}>Overall Completion</span>
          <span className={`text-sm font-semibold ${t.textMain}`}>{pct}%</span>
        </div>
        <div className={`w-full h-3 rounded-full ${t.progressBg} overflow-hidden`}>
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              pct >= 90
                ? (isLight ? 'bg-emerald-600' : 'bg-emerald-500')
                : pct >= 70
                  ? (isLight ? 'bg-amber-500' : 'bg-amber-500')
                  : (isLight ? 'bg-red-500' : 'bg-red-500')
            }`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
        <div className={`flex justify-between text-xs ${t.textFaint}`}>
          <span>{data.complete_count} complete</span>
          <span>{data.total_employees} total</span>
        </div>
      </div>

      {/* Summary breakdown */}
      {(data.overdue_count > 0 || data.expiring_soon_count > 0) && (
        <div className={`${t.card} p-5 space-y-3`}>
          <h3 className={`text-sm font-semibold uppercase tracking-wider ${t.textMain}`}>Action Required</h3>
          {data.overdue_count > 0 && (
            <div className={`${t.urgentBg} rounded-xl p-4 flex items-center gap-3`}>
              <ShieldAlert size={16} className={t.urgentText} />
              <p className={`text-sm ${t.urgentText}`}>
                {data.overdue_count} employee{data.overdue_count !== 1 ? 's have' : ' has'} overdue I-9 verification.
              </p>
            </div>
          )}
          {data.expiring_soon_count > 0 && (
            <div className={`${t.warningBg} rounded-xl p-4 flex items-center gap-3`}>
              <Clock size={16} className={t.warningText} />
              <p className={`text-sm ${t.warningText}`}>
                {data.expiring_soon_count} employee{data.expiring_soon_count !== 1 ? 's have' : ' has'} documents expiring soon.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
