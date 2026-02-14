import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Bot,
  FileText,
  Plus,
  RefreshCw,
  Save,
  ShieldAlert,
  Trash2,
  Upload,
  User,
  X,
} from 'lucide-react';

import {
  accommodationsApi,
  type AccommodationAnalysis,
  type AccommodationCase,
  type AccommodationCaseCreate,
  type AccommodationDocument,
  type AccommodationDocumentType,
  type AccommodationStatus,
  type AuditLogEntry,
  type DisabilityCategory,
  type EmployeeOption,
} from '../api/accommodations';

const STATUS_OPTIONS: AccommodationStatus[] = [
  'requested',
  'interactive_process',
  'medical_review',
  'approved',
  'denied',
  'implemented',
  'review',
  'closed',
];

const DISABILITY_OPTIONS: DisabilityCategory[] = [
  'physical',
  'cognitive',
  'sensory',
  'mental_health',
  'chronic_illness',
  'pregnancy',
  'other',
];

const DOC_TYPES: AccommodationDocumentType[] = [
  'medical_certification',
  'accommodation_request_form',
  'interactive_process_notes',
  'job_description',
  'hardship_analysis',
  'approval_letter',
  'other',
];

function formatLabel(value: string): string {
  return value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function statusStyle(status: string): string {
  switch (status) {
    case 'approved':
    case 'implemented':
      return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    case 'denied':
      return 'bg-red-500/10 text-red-400 border-red-500/20';
    case 'interactive_process':
    case 'medical_review':
    case 'review':
      return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    case 'closed':
      return 'bg-zinc-600/20 text-zinc-300 border-zinc-600/30';
    default:
      return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
  }
}

interface CaseFormState {
  title: string;
  description: string;
  status: AccommodationStatus;
  disability_category: DisabilityCategory | '';
  requested_accommodation: string;
  approved_accommodation: string;
  denial_reason: string;
}

const EMPTY_CASE_FORM: CaseFormState = {
  title: '',
  description: '',
  status: 'requested',
  disability_category: '',
  requested_accommodation: '',
  approved_accommodation: '',
  denial_reason: '',
};

export default function Accommodations() {
  const [cases, setCases] = useState<AccommodationCase[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [selectedCase, setSelectedCase] = useState<AccommodationCase | null>(null);

  const [documents, setDocuments] = useState<AccommodationDocument[]>([]);
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);
  const [suggestions, setSuggestions] = useState<AccommodationAnalysis | null>(null);
  const [hardship, setHardship] = useState<AccommodationAnalysis | null>(null);
  const [jobFunctions, setJobFunctions] = useState<AccommodationAnalysis | null>(null);

  const [employees, setEmployees] = useState<EmployeeOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<string>('');

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createPayload, setCreatePayload] = useState<AccommodationCaseCreate>({
    employee_id: '',
    title: '',
    description: '',
    disability_category: undefined,
    requested_accommodation: '',
    linked_leave_id: '',
  });

  const [editForm, setEditForm] = useState<CaseFormState>(EMPTY_CASE_FORM);

  const [selectedDocType, setSelectedDocType] = useState<AccommodationDocumentType>('other');
  const [analysisLoading, setAnalysisLoading] = useState<string | null>(null);

  const loadEmployees = async () => {
    try {
      const rows = await accommodationsApi.listEmployees();
      setEmployees(rows);
      if (!createPayload.employee_id && rows.length > 0) {
        setCreatePayload((prev) => ({ ...prev, employee_id: rows[0].id }));
      }
    } catch {
      setEmployees([]);
    }
  };

  const loadCases = async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);

    try {
      const response = await accommodationsApi.listCases({
        status: statusFilter ? (statusFilter as AccommodationStatus) : undefined,
      });
      setCases(response.cases);
      const nextId = selectedCaseId && response.cases.some((item) => item.id === selectedCaseId)
        ? selectedCaseId
        : response.cases[0]?.id || null;
      setSelectedCaseId(nextId);
      if (!nextId) {
        setSelectedCase(null);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load accommodation cases');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const loadSelectedCaseData = async (caseId: string) => {
    try {
      const [caseDetail, docs, audit, suggestionsResult, hardshipResult, jobFunctionsResult] = await Promise.all([
        accommodationsApi.getCase(caseId),
        accommodationsApi.listDocuments(caseId),
        accommodationsApi.getAuditLog(caseId).then((response) => response.entries),
        accommodationsApi.getSuggestions(caseId).catch(() => null),
        accommodationsApi.getHardship(caseId).catch(() => null),
        accommodationsApi.getJobFunctions(caseId).catch(() => null),
      ]);

      setSelectedCase(caseDetail);
      setDocuments(docs);
      setAuditLog(audit);
      setSuggestions(suggestionsResult);
      setHardship(hardshipResult);
      setJobFunctions(jobFunctionsResult);

      setEditForm({
        title: caseDetail.title,
        description: caseDetail.description || '',
        status: caseDetail.status,
        disability_category: caseDetail.disability_category || '',
        requested_accommodation: caseDetail.requested_accommodation || '',
        approved_accommodation: caseDetail.approved_accommodation || '',
        denial_reason: caseDetail.denial_reason || '',
      });

      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load case details');
    }
  };

  useEffect(() => {
    loadCases();
    loadEmployees();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  useEffect(() => {
    if (!selectedCaseId) return;
    loadSelectedCaseData(selectedCaseId);
  }, [selectedCaseId]);

  const handleCreateCase = async () => {
    if (!createPayload.employee_id || !createPayload.title.trim()) return;

    setSaving(true);
    try {
      const payload: AccommodationCaseCreate = {
        employee_id: createPayload.employee_id,
        title: createPayload.title.trim(),
        description: createPayload.description?.trim() || undefined,
        disability_category: createPayload.disability_category || undefined,
        requested_accommodation: createPayload.requested_accommodation?.trim() || undefined,
        linked_leave_id: createPayload.linked_leave_id?.trim() || undefined,
      };

      const created = await accommodationsApi.createCase(payload);
      setShowCreateModal(false);
      setCreatePayload({
        employee_id: employees[0]?.id || '',
        title: '',
        description: '',
        disability_category: undefined,
        requested_accommodation: '',
        linked_leave_id: '',
      });

      await loadCases(true);
      setSelectedCaseId(created.id);
      setSuccessMessage(`Created case ${created.case_number}.`);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create case');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveCase = async () => {
    if (!selectedCase) return;

    setSaving(true);
    try {
      await accommodationsApi.updateCase(selectedCase.id, {
        title: editForm.title.trim(),
        description: editForm.description.trim() || undefined,
        status: editForm.status,
        disability_category: editForm.disability_category || undefined,
        requested_accommodation: editForm.requested_accommodation.trim() || undefined,
        approved_accommodation: editForm.approved_accommodation.trim() || undefined,
        denial_reason: editForm.denial_reason.trim() || undefined,
      });

      await loadCases(true);
      await loadSelectedCaseData(selectedCase.id);
      setSuccessMessage('Case updated.');
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update case');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteCase = async () => {
    if (!selectedCase) return;
    if (!window.confirm('Delete this accommodation case and all related documents/analysis?')) return;

    setSaving(true);
    try {
      await accommodationsApi.deleteCase(selectedCase.id);
      await loadCases(true);
      setSuccessMessage('Case deleted.');
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete case');
    } finally {
      setSaving(false);
    }
  };

  const handleUploadDocument = async (file: File | null) => {
    if (!file || !selectedCase) return;

    setSaving(true);
    try {
      await accommodationsApi.uploadDocument(selectedCase.id, file, selectedDocType);
      const docs = await accommodationsApi.listDocuments(selectedCase.id);
      setDocuments(docs);
      setSuccessMessage('Document uploaded.');
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload document');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteDocument = async (docId: string) => {
    if (!selectedCase) return;

    setSaving(true);
    try {
      await accommodationsApi.deleteDocument(selectedCase.id, docId);
      const docs = await accommodationsApi.listDocuments(selectedCase.id);
      setDocuments(docs);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete document');
    } finally {
      setSaving(false);
    }
  };

  const runAnalysis = async (type: 'suggestions' | 'hardship' | 'job-functions') => {
    if (!selectedCase) return;

    setAnalysisLoading(type);
    try {
      if (type === 'suggestions') {
        const result = await accommodationsApi.generateSuggestions(selectedCase.id);
        setSuggestions(result);
      } else if (type === 'hardship') {
        const result = await accommodationsApi.generateHardship(selectedCase.id);
        setHardship(result);
      } else {
        const result = await accommodationsApi.generateJobFunctions(selectedCase.id);
        setJobFunctions(result);
      }
      const audit = await accommodationsApi.getAuditLog(selectedCase.id);
      setAuditLog(audit.entries);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate analysis');
    } finally {
      setAnalysisLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading accommodation cases...</div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 border-b border-white/10 pb-6">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Accommodations</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            ADA interactive process case management
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="px-3 py-2 bg-zinc-900 border border-zinc-800 text-sm text-zinc-200"
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>{formatLabel(status)}</option>
            ))}
          </select>
          <button
            onClick={() => loadCases(true)}
            className="inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider border border-zinc-700 text-zinc-300 hover:border-zinc-500"
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> Refresh
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider bg-white text-zinc-900 hover:bg-zinc-200"
          >
            <Plus size={14} /> New Case
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded p-4 flex items-center gap-3">
          <AlertTriangle className="text-red-400" size={16} />
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {successMessage && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded p-4 flex items-center gap-3">
          <ShieldAlert className="text-emerald-400" size={16} />
          <p className="text-sm text-emerald-300">{successMessage}</p>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[340px_1fr] gap-6">
        <div className="border border-white/10 bg-zinc-950">
          <div className="px-4 py-3 border-b border-white/10 text-[10px] uppercase tracking-widest text-zinc-500">
            Cases ({cases.length})
          </div>
          {cases.length === 0 ? (
            <div className="px-4 py-10 text-center text-zinc-500 text-sm">No cases found.</div>
          ) : (
            <div className="divide-y divide-white/5 max-h-[70vh] overflow-y-auto">
              {cases.map((caseItem) => (
                <button
                  key={caseItem.id}
                  onClick={() => setSelectedCaseId(caseItem.id)}
                  className={`w-full text-left px-4 py-3 hover:bg-white/5 transition-colors ${
                    selectedCaseId === caseItem.id ? 'bg-white/5' : ''
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm text-white font-medium truncate">{caseItem.case_number}</p>
                    <span className={`text-[9px] px-2 py-0.5 uppercase tracking-widest border ${statusStyle(caseItem.status)}`}>
                      {caseItem.status}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-400 mt-1 truncate">{caseItem.title}</p>
                </button>
              ))}
            </div>
          )}
        </div>

        {!selectedCase ? (
          <div className="border border-white/10 bg-zinc-950 p-10 text-center text-zinc-500">Select a case to view details.</div>
        ) : (
          <div className="space-y-6">
            <div className="border border-white/10 bg-zinc-950 p-5 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-xl text-white font-semibold">{selectedCase.case_number}</h2>
                  <p className="text-xs text-zinc-500 uppercase tracking-wider mt-1">{selectedCase.id}</p>
                </div>
                <span className={`text-[10px] px-2 py-1 uppercase tracking-widest border ${statusStyle(selectedCase.status)}`}>
                  {selectedCase.status}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Title</label>
                  <input
                    value={editForm.title}
                    onChange={(event) => setEditForm((prev) => ({ ...prev, title: event.target.value }))}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-100"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Status</label>
                  <select
                    value={editForm.status}
                    onChange={(event) => setEditForm((prev) => ({ ...prev, status: event.target.value as AccommodationStatus }))}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-100"
                  >
                    {STATUS_OPTIONS.map((status) => (
                      <option key={status} value={status}>{formatLabel(status)}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Description</label>
                <textarea
                  rows={3}
                  value={editForm.description}
                  onChange={(event) => setEditForm((prev) => ({ ...prev, description: event.target.value }))}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-100 resize-none"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Disability Category</label>
                  <select
                    value={editForm.disability_category}
                    onChange={(event) => setEditForm((prev) => ({ ...prev, disability_category: event.target.value as DisabilityCategory | '' }))}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-100"
                  >
                    <option value="">Not set</option>
                    {DISABILITY_OPTIONS.map((option) => (
                      <option key={option} value={option}>{formatLabel(option)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Employee ID</label>
                  <div className="px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-300 text-sm">{selectedCase.employee_id}</div>
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Linked Leave ID</label>
                  <div className="px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-300 text-sm truncate">{selectedCase.linked_leave_id || '—'}</div>
                </div>
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Requested Accommodation</label>
                <textarea
                  rows={2}
                  value={editForm.requested_accommodation}
                  onChange={(event) => setEditForm((prev) => ({ ...prev, requested_accommodation: event.target.value }))}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-100 resize-none"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Approved Accommodation</label>
                  <textarea
                    rows={2}
                    value={editForm.approved_accommodation}
                    onChange={(event) => setEditForm((prev) => ({ ...prev, approved_accommodation: event.target.value }))}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-100 resize-none"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Denial Reason</label>
                  <textarea
                    rows={2}
                    value={editForm.denial_reason}
                    onChange={(event) => setEditForm((prev) => ({ ...prev, denial_reason: event.target.value }))}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-100 resize-none"
                  />
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={handleSaveCase}
                  disabled={saving}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider bg-white text-zinc-900 hover:bg-zinc-200 disabled:opacity-50"
                >
                  <Save size={14} /> Save Case
                </button>
                <button
                  onClick={handleDeleteCase}
                  disabled={saving}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider border border-red-500/30 text-red-300 hover:bg-red-500/10 disabled:opacity-50"
                >
                  <Trash2 size={14} /> Delete Case
                </button>
              </div>
            </div>

            <div className="border border-white/10 bg-zinc-950 p-5 space-y-4">
              <div className="flex items-center gap-2">
                <FileText size={16} className="text-blue-400" />
                <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Documents</h3>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={selectedDocType}
                  onChange={(event) => setSelectedDocType(event.target.value as AccommodationDocumentType)}
                  className="px-3 py-2 bg-zinc-900 border border-zinc-800 text-sm text-zinc-200"
                >
                  {DOC_TYPES.map((type) => (
                    <option key={type} value={type}>{formatLabel(type)}</option>
                  ))}
                </select>
                <label className="inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider border border-zinc-700 text-zinc-300 hover:border-zinc-500 cursor-pointer">
                  <Upload size={14} /> Upload
                  <input
                    type="file"
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0] || null;
                      void handleUploadDocument(file);
                      event.target.value = '';
                    }}
                  />
                </label>
              </div>

              {documents.length === 0 ? (
                <p className="text-sm text-zinc-500">No documents uploaded.</p>
              ) : (
                <div className="space-y-2">
                  {documents.map((doc) => (
                    <div key={doc.id} className="border border-white/5 bg-zinc-900/30 px-3 py-2 flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm text-zinc-200 truncate">{doc.filename}</p>
                        <p className="text-[11px] text-zinc-500">{formatLabel(doc.document_type)} • {new Date(doc.created_at).toLocaleString()}</p>
                      </div>
                      <button
                        onClick={() => handleDeleteDocument(doc.id)}
                        className="text-xs text-red-300 border border-red-500/30 px-2 py-1 hover:bg-red-500/10"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="border border-white/10 bg-zinc-950 p-5 space-y-4">
              <div className="flex items-center gap-2">
                <Bot size={16} className="text-emerald-400" />
                <h3 className="text-sm font-semibold text-white uppercase tracking-wider">AI Analysis</h3>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => runAnalysis('suggestions')}
                  disabled={analysisLoading !== null}
                  className="px-3 py-2 text-xs uppercase tracking-wider border border-zinc-600 text-zinc-200 hover:border-zinc-400 disabled:opacity-50"
                >
                  {analysisLoading === 'suggestions' ? 'Generating...' : 'Generate Suggestions'}
                </button>
                <button
                  onClick={() => runAnalysis('hardship')}
                  disabled={analysisLoading !== null}
                  className="px-3 py-2 text-xs uppercase tracking-wider border border-zinc-600 text-zinc-200 hover:border-zinc-400 disabled:opacity-50"
                >
                  {analysisLoading === 'hardship' ? 'Generating...' : 'Assess Hardship'}
                </button>
                <button
                  onClick={() => runAnalysis('job-functions')}
                  disabled={analysisLoading !== null}
                  className="px-3 py-2 text-xs uppercase tracking-wider border border-zinc-600 text-zinc-200 hover:border-zinc-400 disabled:opacity-50"
                >
                  {analysisLoading === 'job-functions' ? 'Generating...' : 'Analyze Job Functions'}
                </button>
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
                <div className="border border-white/5 bg-zinc-900/30 p-3">
                  <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Suggestions</h4>
                  {suggestions ? (
                    <pre className="text-xs text-zinc-300 overflow-x-auto max-h-72">{JSON.stringify(suggestions.analysis_data, null, 2)}</pre>
                  ) : (
                    <p className="text-xs text-zinc-500">No analysis generated.</p>
                  )}
                </div>
                <div className="border border-white/5 bg-zinc-900/30 p-3">
                  <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Hardship</h4>
                  {hardship ? (
                    <pre className="text-xs text-zinc-300 overflow-x-auto max-h-72">{JSON.stringify(hardship.analysis_data, null, 2)}</pre>
                  ) : (
                    <p className="text-xs text-zinc-500">No analysis generated.</p>
                  )}
                </div>
                <div className="border border-white/5 bg-zinc-900/30 p-3">
                  <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Job Functions</h4>
                  {jobFunctions ? (
                    <pre className="text-xs text-zinc-300 overflow-x-auto max-h-72">{JSON.stringify(jobFunctions.analysis_data, null, 2)}</pre>
                  ) : (
                    <p className="text-xs text-zinc-500">No analysis generated.</p>
                  )}
                </div>
              </div>
            </div>

            <div className="border border-white/10 bg-zinc-950 p-5 space-y-4">
              <div className="flex items-center gap-2">
                <User size={16} className="text-violet-400" />
                <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Audit Log</h3>
              </div>
              {auditLog.length === 0 ? (
                <p className="text-sm text-zinc-500">No audit entries yet.</p>
              ) : (
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {auditLog.map((entry) => (
                    <div key={entry.id} className="border border-white/5 bg-zinc-900/30 px-3 py-2">
                      <p className="text-xs text-zinc-200">{entry.action}</p>
                      <p className="text-[11px] text-zinc-500">{new Date(entry.created_at).toLocaleString()}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm p-4 flex items-center justify-center">
          <div className="w-full max-w-lg bg-zinc-950 border border-zinc-800 rounded-sm">
            <div className="flex items-center justify-between p-5 border-b border-white/10">
              <h3 className="text-lg text-white font-semibold uppercase tracking-wider">Create Accommodation Case</h3>
              <button onClick={() => setShowCreateModal(false)} className="text-zinc-500 hover:text-white">
                <X size={18} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Employee</label>
                <select
                  value={createPayload.employee_id}
                  onChange={(event) => setCreatePayload((prev) => ({ ...prev, employee_id: event.target.value }))}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-200"
                >
                  {employees.map((employee) => (
                    <option key={employee.id} value={employee.id}>
                      {employee.first_name} {employee.last_name} ({employee.email})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Case Title</label>
                <input
                  value={createPayload.title}
                  onChange={(event) => setCreatePayload((prev) => ({ ...prev, title: event.target.value }))}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-200"
                />
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Description</label>
                <textarea
                  rows={3}
                  value={createPayload.description || ''}
                  onChange={(event) => setCreatePayload((prev) => ({ ...prev, description: event.target.value }))}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-200 resize-none"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Disability Category</label>
                  <select
                    value={createPayload.disability_category || ''}
                    onChange={(event) => setCreatePayload((prev) => ({
                      ...prev,
                      disability_category: (event.target.value || undefined) as DisabilityCategory | undefined,
                    }))}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-200"
                  >
                    <option value="">Not set</option>
                    {DISABILITY_OPTIONS.map((option) => (
                      <option key={option} value={option}>{formatLabel(option)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Linked Leave ID (optional)</label>
                  <input
                    value={createPayload.linked_leave_id || ''}
                    onChange={(event) => setCreatePayload((prev) => ({ ...prev, linked_leave_id: event.target.value }))}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-200"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Requested Accommodation</label>
                <textarea
                  rows={3}
                  value={createPayload.requested_accommodation || ''}
                  onChange={(event) => setCreatePayload((prev) => ({ ...prev, requested_accommodation: event.target.value }))}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-200 resize-none"
                />
              </div>
            </div>

            <div className="p-5 border-t border-white/10 flex justify-end gap-2">
              <button
                onClick={() => setShowCreateModal(false)}
                className="px-3 py-2 text-xs uppercase tracking-wider text-zinc-400 hover:text-zinc-200"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateCase}
                disabled={saving || !createPayload.employee_id || !createPayload.title.trim()}
                className="px-3 py-2 text-xs uppercase tracking-wider bg-white text-zinc-900 hover:bg-zinc-200 disabled:opacity-50"
              >
                {saving ? 'Creating...' : 'Create Case'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
