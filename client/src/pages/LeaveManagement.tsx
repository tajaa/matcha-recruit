import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Calendar,
  CheckCircle,
  Clock,
  FileText,
  RefreshCw,
  ShieldCheck,
  UserCheck,
  XCircle,
} from 'lucide-react';

import {
  LEAVE_TYPES,
  NOTICE_TYPES,
  leaveApi,
  type LeaveActionRequest,
  type LeaveDeadline,
  type LeaveRequestAdmin,
} from '../api/leave';
import { useAuth } from '../context/AuthContext';
import { FeatureGuideTrigger } from '../features/feature-guides';

const STATUS_OPTIONS = ['requested', 'approved', 'active', 'denied', 'completed', 'cancelled'] as const;

function statusBadge(status: string) {
  switch (status) {
    case 'requested':
      return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    case 'approved':
      return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    case 'active':
      return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    case 'denied':
      return 'bg-red-500/10 text-red-400 border-red-500/20';
    case 'completed':
      return 'bg-zinc-500/10 text-zinc-300 border-zinc-500/20';
    case 'cancelled':
      return 'bg-zinc-800/40 text-zinc-500 border-zinc-700';
    default:
      return 'bg-zinc-800/40 text-zinc-400 border-zinc-700';
  }
}

function formatLeaveType(leaveType: string): string {
  return leaveType
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function formatDate(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
}

export default function LeaveManagement() {
  const { hasFeature } = useAuth();
  const [requests, setRequests] = useState<LeaveRequestAdmin[]>([]);
  const [selectedLeaveId, setSelectedLeaveId] = useState<string | null>(null);
  const [selectedLeave, setSelectedLeave] = useState<LeaveRequestAdmin | null>(null);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);

  const [statusFilter, setStatusFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const [eligibility, setEligibility] = useState<Record<string, unknown> | null>(null);
  const [deadlines, setDeadlines] = useState<LeaveDeadline[]>([]);
  const [loadingCompliance, setLoadingCompliance] = useState(false);

  const [noticeType, setNoticeType] = useState<typeof NOTICE_TYPES[number]>('fmla_eligibility_notice');
  const [noticeMessage, setNoticeMessage] = useState<string | null>(null);

  const compliancePlusEnabled = hasFeature('compliance_plus');

  const selectedLeaveSummary = useMemo(() => {
    if (!selectedLeave) return null;
    return [
      { label: 'Employee', value: selectedLeave.employee_name || selectedLeave.employee_id },
      { label: 'Type', value: formatLeaveType(selectedLeave.leave_type) },
      { label: 'Status', value: selectedLeave.status },
      { label: 'Start Date', value: formatDate(selectedLeave.start_date) },
      { label: 'End Date', value: formatDate(selectedLeave.end_date) },
      { label: 'Expected Return', value: formatDate(selectedLeave.expected_return_date) },
      { label: 'Actual Return', value: formatDate(selectedLeave.actual_return_date) },
      { label: 'Intermittent', value: selectedLeave.intermittent ? 'Yes' : 'No' },
    ];
  }, [selectedLeave]);

  const loadRequests = async (silent = false): Promise<string | null> => {
    if (!silent) setLoading(true);
    else setRefreshing(true);

    try {
      const rows = await leaveApi.listAdminRequests({
        status: statusFilter || undefined,
        leave_type: typeFilter || undefined,
      });
      setRequests(rows);

      const nextSelectedId = selectedLeaveId && rows.some((r) => r.id === selectedLeaveId)
        ? selectedLeaveId
        : rows[0]?.id || null;
      setSelectedLeaveId(nextSelectedId);

      if (!nextSelectedId) {
        setSelectedLeave(null);
        setEligibility(null);
        setDeadlines([]);
      }
      setError(null);
      return nextSelectedId;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load leave requests');
      return null;
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const loadSelectedLeave = async (leaveId: string) => {
    try {
      const row = await leaveApi.getAdminRequest(leaveId);
      setSelectedLeave(row);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load leave details');
    }
  };

  const loadComplianceData = async (leaveId: string) => {
    if (!compliancePlusEnabled) return;

    setLoadingCompliance(true);
    try {
      const [eligibilityResult, deadlinesResult] = await Promise.all([
        leaveApi.getEligibility(leaveId).catch(() => null),
        leaveApi.listDeadlines(leaveId).catch(() => [] as LeaveDeadline[]),
      ]);

      setEligibility(eligibilityResult);
      setDeadlines(deadlinesResult);
    } finally {
      setLoadingCompliance(false);
    }
  };

  useEffect(() => {
    loadRequests();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, typeFilter]);

  useEffect(() => {
    if (!selectedLeaveId) return;
    loadSelectedLeave(selectedLeaveId);
    loadComplianceData(selectedLeaveId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLeaveId, compliancePlusEnabled]);

  const runAction = async (payload: LeaveActionRequest) => {
    if (!selectedLeave) return;
    setSaving(true);
    try {
      await leaveApi.updateAdminRequest(selectedLeave.id, payload);
      const nextSelectedId = await loadRequests(true);
      if (nextSelectedId) {
        await loadSelectedLeave(nextSelectedId);
        if (compliancePlusEnabled) {
          await loadComplianceData(nextSelectedId);
        }
      }
      setNoticeMessage(null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update leave request');
    } finally {
      setSaving(false);
    }
  };

  const handleApprove = async () => {
    const expectedReturn = window.prompt('Expected return date (YYYY-MM-DD). Leave blank to skip:')?.trim();
    const payload: LeaveActionRequest = { action: 'approve' };
    if (expectedReturn) payload.expected_return_date = expectedReturn;
    await runAction(payload);
  };

  const handleDeny = async () => {
    const denialReason = window.prompt('Denial reason (required):')?.trim();
    if (!denialReason) return;
    await runAction({ action: 'deny', denial_reason: denialReason });
  };

  const handleActivate = async () => runAction({ action: 'activate' });

  const handleComplete = async () => {
    const actualReturn = window.prompt('Actual return date (YYYY-MM-DD). Leave blank for today:')?.trim();
    const payload: LeaveActionRequest = { action: 'complete' };
    if (actualReturn) payload.actual_return_date = actualReturn;
    await runAction(payload);
  };

  const handleDeadlineAction = async (deadlineId: string, action: 'complete' | 'waive') => {
    if (!selectedLeave) return;
    setSaving(true);
    try {
      await leaveApi.updateDeadline(selectedLeave.id, deadlineId, { action });
      const rows = await leaveApi.listDeadlines(selectedLeave.id);
      setDeadlines(rows);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update deadline');
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateNotice = async () => {
    if (!selectedLeave) return;
    setSaving(true);
    try {
      const result = await leaveApi.createNotice(selectedLeave.id, noticeType);
      setNoticeMessage(`Notice generated: ${result.title}`);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate notice');
    } finally {
      setSaving(false);
    }
  };

  const handleAssignRTW = async () => {
    if (!selectedLeave) return;
    setSaving(true);
    try {
      const assigned = await leaveApi.assignReturnToWorkTasks(selectedLeave.employee_id, selectedLeave.id);
      setNoticeMessage(`Assigned ${assigned.length} return-to-work task(s).`);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to assign return-to-work tasks');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading leave requests...</div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 border-b border-white/10 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Leave Management</h1>
            <FeatureGuideTrigger guideId="leave-management" />
          </div>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Approvals, deadlines, notices, and return-to-work orchestration
          </p>
        </div>
        <div data-tour="leave-admin-filters" className="flex flex-wrap items-center gap-2">
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="px-3 py-2 bg-zinc-900 border border-zinc-800 text-sm text-zinc-200"
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>

          <select
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            className="px-3 py-2 bg-zinc-900 border border-zinc-800 text-sm text-zinc-200"
          >
            <option value="">All leave types</option>
            {LEAVE_TYPES.map((leaveType) => (
              <option key={leaveType} value={leaveType}>{formatLeaveType(leaveType)}</option>
            ))}
          </select>

          <button
            onClick={() => loadRequests(true)}
            className="inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider border border-zinc-700 text-zinc-300 hover:border-zinc-500"
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded p-4 flex items-center gap-3">
          <AlertTriangle className="text-red-400" size={16} />
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {noticeMessage && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded p-4 flex items-center gap-3">
          <CheckCircle className="text-emerald-400" size={16} />
          <p className="text-sm text-emerald-300">{noticeMessage}</p>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[360px_1fr] gap-6">
        <div data-tour="leave-admin-list" className="border border-white/10 bg-zinc-950">
          <div className="px-4 py-3 border-b border-white/10 text-[10px] uppercase tracking-widest text-zinc-500">
            Leave Requests ({requests.length})
          </div>
          {requests.length === 0 ? (
            <div className="px-4 py-10 text-center text-zinc-500 text-sm">No leave requests found.</div>
          ) : (
            <div className="divide-y divide-white/5 max-h-[70vh] overflow-y-auto">
              {requests.map((request) => (
                <button
                  key={request.id}
                  onClick={() => setSelectedLeaveId(request.id)}
                  className={`w-full text-left px-4 py-3 hover:bg-white/5 transition-colors ${
                    selectedLeaveId === request.id ? 'bg-white/5' : ''
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm text-white font-medium truncate">{request.employee_name || 'Unknown employee'}</div>
                    <span className={`text-[9px] px-2 py-0.5 uppercase tracking-widest border ${statusBadge(request.status)}`}>
                      {request.status}
                    </span>
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-1">
                    {formatLeaveType(request.leave_type)} • {formatDate(request.start_date)}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-6">
          {!selectedLeave ? (
            <div className="border border-white/10 bg-zinc-950 p-10 text-center text-zinc-500">Select a leave request to view details.</div>
          ) : (
            <>
              <div data-tour="leave-admin-detail" className="border border-white/10 bg-zinc-950 p-5 space-y-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-semibold text-white">{selectedLeave.employee_name || selectedLeave.employee_id}</h2>
                    <p className="text-xs text-zinc-500 mt-1 uppercase tracking-wider">Leave ID: {selectedLeave.id}</p>
                  </div>
                  <span className={`text-[10px] px-2 py-1 uppercase tracking-widest border ${statusBadge(selectedLeave.status)}`}>
                    {selectedLeave.status}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {selectedLeaveSummary?.map((item) => (
                    <div key={item.label} className="border border-white/5 bg-zinc-900/30 px-3 py-2">
                      <div className="text-[10px] uppercase tracking-widest text-zinc-500">{item.label}</div>
                      <div className="text-sm text-zinc-200 mt-1">{item.value}</div>
                    </div>
                  ))}
                </div>

                {selectedLeave.reason && (
                  <div className="border border-white/5 bg-zinc-900/30 px-3 py-3">
                    <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">Reason</div>
                    <p className="text-sm text-zinc-200 whitespace-pre-wrap">{selectedLeave.reason}</p>
                  </div>
                )}

                <div data-tour="leave-admin-actions" className="flex flex-wrap gap-2">
                  {selectedLeave.status === 'requested' && (
                    <>
                      <button
                        onClick={handleApprove}
                        disabled={saving}
                        className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold uppercase tracking-wider bg-emerald-600/90 hover:bg-emerald-500 text-white disabled:opacity-50"
                      >
                        <CheckCircle size={14} /> Approve
                      </button>
                      <button
                        onClick={handleDeny}
                        disabled={saving}
                        className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold uppercase tracking-wider bg-red-600/90 hover:bg-red-500 text-white disabled:opacity-50"
                      >
                        <XCircle size={14} /> Deny
                      </button>
                    </>
                  )}

                  {selectedLeave.status === 'approved' && (
                    <button
                      onClick={handleActivate}
                      disabled={saving}
                      className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold uppercase tracking-wider bg-blue-600/90 hover:bg-blue-500 text-white disabled:opacity-50"
                    >
                      <Clock size={14} /> Mark Active
                    </button>
                  )}

                  {(selectedLeave.status === 'approved' || selectedLeave.status === 'active') && (
                    <button
                      onClick={handleComplete}
                      disabled={saving}
                      className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold uppercase tracking-wider bg-zinc-200 hover:bg-white text-zinc-900 disabled:opacity-50"
                    >
                      <UserCheck size={14} /> Complete Leave
                    </button>
                  )}

                  {(selectedLeave.status === 'approved' || selectedLeave.status === 'active') && (
                    <button
                      data-tour="leave-admin-rtw-btn"
                      onClick={handleAssignRTW}
                      disabled={saving}
                      className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold uppercase tracking-wider border border-zinc-600 text-zinc-200 hover:border-zinc-400 disabled:opacity-50"
                    >
                      <Calendar size={14} /> Assign RTW Tasks
                    </button>
                  )}
                </div>
              </div>

              {compliancePlusEnabled && (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                  <div className="border border-white/10 bg-zinc-950 p-5 space-y-4">
                    <div className="flex items-center gap-2">
                      <ShieldCheck size={16} className="text-emerald-400" />
                      <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Eligibility</h3>
                    </div>
                    {loadingCompliance ? (
                      <div className="text-xs text-zinc-500 uppercase tracking-widest animate-pulse">Loading eligibility...</div>
                    ) : eligibility ? (
                      <pre className="text-xs text-zinc-300 bg-zinc-900/50 border border-white/5 p-3 overflow-x-auto max-h-72">
                        {JSON.stringify(eligibility, null, 2)}
                      </pre>
                    ) : (
                      <p className="text-sm text-zinc-500">No eligibility data found yet.</p>
                    )}
                  </div>

                  <div data-tour="leave-admin-deadlines" className="border border-white/10 bg-zinc-950 p-5 space-y-4">
                    <div className="flex items-center gap-2">
                      <Clock size={16} className="text-amber-400" />
                      <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Deadlines</h3>
                    </div>

                    {deadlines.length === 0 ? (
                      <p className="text-sm text-zinc-500">No deadlines found for this leave request.</p>
                    ) : (
                      <div className="space-y-2">
                        {deadlines.map((deadline) => (
                          <div key={deadline.id} className="border border-white/5 bg-zinc-900/30 p-3">
                            <div className="flex items-center justify-between gap-3">
                              <div>
                                <div className="text-xs text-zinc-200 font-medium">{deadline.deadline_type}</div>
                                <div className="text-[11px] text-zinc-500">Due: {formatDate(deadline.due_date)}</div>
                              </div>
                              <span className={`text-[9px] px-2 py-0.5 uppercase tracking-wider border ${statusBadge(deadline.status)}`}>
                                {deadline.status}
                              </span>
                            </div>
                            {(deadline.status === 'pending' || deadline.status === 'overdue') && (
                              <div className="mt-3 flex gap-2">
                                <button
                                  onClick={() => handleDeadlineAction(deadline.id, 'complete')}
                                  disabled={saving}
                                  className="px-2.5 py-1 text-[10px] uppercase tracking-wider bg-emerald-600/80 hover:bg-emerald-500 text-white disabled:opacity-50"
                                >
                                  Complete
                                </button>
                                <button
                                  onClick={() => handleDeadlineAction(deadline.id, 'waive')}
                                  disabled={saving}
                                  className="px-2.5 py-1 text-[10px] uppercase tracking-wider border border-zinc-600 text-zinc-300 hover:border-zinc-400 disabled:opacity-50"
                                >
                                  Waive
                                </button>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {compliancePlusEnabled && (
                <div data-tour="leave-admin-notices" className="border border-white/10 bg-zinc-950 p-5 space-y-4">
                  <div className="flex items-center gap-2">
                    <FileText size={16} className="text-blue-400" />
                    <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Notice Generation</h3>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      value={noticeType}
                      onChange={(event) => setNoticeType(event.target.value as typeof NOTICE_TYPES[number])}
                      className="px-3 py-2 bg-zinc-900 border border-zinc-800 text-sm text-zinc-200"
                    >
                      {NOTICE_TYPES.map((type) => (
                        <option key={type} value={type}>{formatLeaveType(type)}</option>
                      ))}
                    </select>
                    <button
                      onClick={handleGenerateNotice}
                      disabled={saving}
                      className="px-3 py-2 text-xs uppercase tracking-wider bg-blue-600/90 hover:bg-blue-500 text-white disabled:opacity-50"
                    >
                      Generate Notice
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
