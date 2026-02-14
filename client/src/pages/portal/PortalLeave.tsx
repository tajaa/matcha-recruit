import { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  Calendar,
  CheckCircle,
  Clock,
  Plus,
  RefreshCw,
  ShieldCheck,
  X,
} from 'lucide-react';

import {
  LEAVE_TYPES,
  leaveApi,
  type LeaveRequest,
  type LeaveRequestCreate,
} from '../../api/leave';
import { useAuth } from '../../context/AuthContext';
import { FeatureGuideTrigger } from '../../features/feature-guides';

function formatLeaveType(value: string): string {
  return value
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function formatDate(value?: string | null): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString();
}

function statusClasses(status: string): string {
  switch (status) {
    case 'requested':
      return 'bg-amber-100 text-amber-800';
    case 'approved':
      return 'bg-emerald-100 text-emerald-800';
    case 'active':
      return 'bg-blue-100 text-blue-800';
    case 'completed':
      return 'bg-zinc-100 text-zinc-700';
    case 'denied':
      return 'bg-red-100 text-red-800';
    case 'cancelled':
      return 'bg-zinc-200 text-zinc-600';
    default:
      return 'bg-zinc-100 text-zinc-800';
  }
}

export default function PortalLeave() {
  const { hasFeature } = useAuth();
  const [requests, setRequests] = useState<LeaveRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [showModal, setShowModal] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('');

  const [leaveType, setLeaveType] = useState<(typeof LEAVE_TYPES)[number]>('medical');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [expectedReturnDate, setExpectedReturnDate] = useState('');
  const [reason, setReason] = useState('');
  const [intermittent, setIntermittent] = useState(false);
  const [intermittentSchedule, setIntermittentSchedule] = useState('');

  const [eligibility, setEligibility] = useState<Record<string, unknown> | null>(null);
  const [eligibilityLoading, setEligibilityLoading] = useState(false);

  const compliancePlusEnabled = hasFeature('compliance_plus');

  const visibleRequests = useMemo(() => {
    if (!statusFilter) return requests;
    return requests.filter((request) => request.status === statusFilter);
  }, [requests, statusFilter]);

  const resetForm = () => {
    setLeaveType('medical');
    setStartDate('');
    setEndDate('');
    setExpectedReturnDate('');
    setReason('');
    setIntermittent(false);
    setIntermittentSchedule('');
  };

  const loadRequests = async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);

    try {
      const response = await leaveApi.getMyRequests();
      setRequests(response.requests);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load leave requests');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const loadEligibility = async () => {
    if (!compliancePlusEnabled) return;

    setEligibilityLoading(true);
    try {
      const result = await leaveApi.getMyEligibility();
      setEligibility(result);
    } catch {
      setEligibility(null);
    } finally {
      setEligibilityLoading(false);
    }
  };

  useEffect(() => {
    loadRequests();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadEligibility();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compliancePlusEnabled]);

  const handleSubmit = async () => {
    if (!startDate) return;

    setSubmitting(true);
    try {
      const payload: LeaveRequestCreate = {
        leave_type: leaveType,
        start_date: startDate,
        end_date: endDate || undefined,
        expected_return_date: expectedReturnDate || undefined,
        reason: reason || undefined,
        intermittent,
        intermittent_schedule: intermittent ? intermittentSchedule || undefined : undefined,
      };

      await leaveApi.submitMyRequest(payload);
      setShowModal(false);
      resetForm();
      setSuccessMessage('Leave request submitted successfully.');
      await loadRequests(true);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit leave request');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = async (leaveId: string) => {
    if (!window.confirm('Cancel this leave request?')) return;

    setSubmitting(true);
    try {
      await leaveApi.cancelMyRequest(leaveId);
      setSuccessMessage('Leave request cancelled.');
      await loadRequests(true);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel leave request');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-zinc-400 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-mono font-medium text-zinc-900">Extended Leave</h1>
            <FeatureGuideTrigger guideId="portal-leave" variant="light" />
          </div>
          <p className="text-sm text-zinc-500 mt-1">Submit and track long-duration leave requests</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => loadRequests(true)}
            className="inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider border border-zinc-300 text-zinc-700 hover:border-zinc-500"
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            data-tour="portal-leave-request-btn"
            onClick={() => setShowModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white text-sm font-medium rounded-lg hover:bg-zinc-800 transition-colors"
          >
            <Plus className="w-4 h-4" /> Request Leave
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500" />
          <span className="text-red-700">{error}</span>
        </div>
      )}

      {successMessage && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 flex items-center gap-3">
          <CheckCircle className="w-5 h-5 text-emerald-600" />
          <span className="text-emerald-700">{successMessage}</span>
        </div>
      )}

      {compliancePlusEnabled && (
        <div data-tour="portal-leave-eligibility" className="bg-white border border-zinc-200 rounded-lg p-5">
          <div className="flex items-center gap-2 mb-3">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <h2 className="text-sm font-medium text-zinc-900">Eligibility Snapshot</h2>
          </div>
          {eligibilityLoading ? (
            <p className="text-sm text-zinc-500">Loading eligibility...</p>
          ) : eligibility ? (
            <pre className="text-xs text-zinc-700 bg-zinc-50 border border-zinc-200 rounded-lg p-3 overflow-x-auto max-h-60">
              {JSON.stringify(eligibility, null, 2)}
            </pre>
          ) : (
            <p className="text-sm text-zinc-500">Eligibility data is not available for your account.</p>
          )}
        </div>
      )}

      <div data-tour="portal-leave-list" className="bg-white border border-zinc-200 rounded-lg">
        <div className="px-5 py-4 border-b border-zinc-100 flex items-center justify-between">
          <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-500">My Leave Requests</h2>
          <select
            data-tour="portal-leave-filters"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="px-3 py-1.5 border border-zinc-200 rounded-lg text-sm"
          >
            <option value="">All statuses</option>
            <option value="requested">Requested</option>
            <option value="approved">Approved</option>
            <option value="active">Active</option>
            <option value="denied">Denied</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>

        {visibleRequests.length === 0 ? (
          <div className="p-8 text-center text-zinc-500">
            <Calendar className="w-12 h-12 mx-auto text-zinc-300 mb-3" />
            <p>No leave requests found</p>
          </div>
        ) : (
          <div className="divide-y divide-zinc-100">
            {visibleRequests.map((request) => (
              <div key={request.id} className="p-5 flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                <div className="space-y-2 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium text-zinc-900">{formatLeaveType(request.leave_type)}</h3>
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${statusClasses(request.status)}`}>
                      {request.status === 'requested' ? <Clock className="w-3 h-3" /> : <CheckCircle className="w-3 h-3" />}
                      {request.status}
                    </span>
                  </div>
                  <div className="text-sm text-zinc-600">
                    {formatDate(request.start_date)} - {formatDate(request.end_date)}
                  </div>
                  <div className="text-xs text-zinc-500">
                    Expected return: {formatDate(request.expected_return_date)}
                  </div>
                  {request.reason && (
                    <p className="text-sm text-zinc-600 whitespace-pre-wrap">{request.reason}</p>
                  )}
                  {request.denial_reason && (
                    <p className="text-sm text-red-600">Denied: {request.denial_reason}</p>
                  )}
                </div>

                {request.status === 'requested' && (
                  <button
                    data-tour="portal-leave-cancel-btn"
                    onClick={() => handleCancel(request.id)}
                    disabled={submitting}
                    className="self-start px-3 py-1.5 border border-red-200 text-red-600 text-xs font-medium rounded-lg hover:bg-red-50"
                  >
                    Cancel Request
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl p-6 w-full max-w-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium text-zinc-900">Request Extended Leave</h2>
              <button onClick={() => setShowModal(false)} className="p-1 hover:bg-zinc-100 rounded-lg transition-colors">
                <X className="w-5 h-5 text-zinc-500" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 mb-2">Leave Type</label>
                <select
                  value={leaveType}
                  onChange={(event) => setLeaveType(event.target.value as (typeof LEAVE_TYPES)[number])}
                  className="w-full px-4 py-3 border border-zinc-200 rounded-lg"
                >
                  {LEAVE_TYPES.map((type) => (
                    <option key={type} value={type}>{formatLeaveType(type)}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-zinc-700 mb-2">Start Date *</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(event) => setStartDate(event.target.value)}
                    className="w-full px-4 py-3 border border-zinc-200 rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-zinc-700 mb-2">End Date</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(event) => setEndDate(event.target.value)}
                    className="w-full px-4 py-3 border border-zinc-200 rounded-lg"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 mb-2">Expected Return Date</label>
                <input
                  type="date"
                  value={expectedReturnDate}
                  onChange={(event) => setExpectedReturnDate(event.target.value)}
                  className="w-full px-4 py-3 border border-zinc-200 rounded-lg"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 mb-2">Reason</label>
                <textarea
                  rows={4}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="Provide context for your leave request"
                  className="w-full px-4 py-3 border border-zinc-200 rounded-lg resize-none"
                />
              </div>

              <div className="space-y-3">
                <label className="inline-flex items-center gap-2 text-sm text-zinc-700">
                  <input
                    type="checkbox"
                    checked={intermittent}
                    onChange={(event) => setIntermittent(event.target.checked)}
                    className="w-4 h-4"
                  />
                  This is an intermittent leave request
                </label>

                {intermittent && (
                  <div>
                    <label className="block text-sm font-medium text-zinc-700 mb-2">Intermittent Schedule</label>
                    <input
                      type="text"
                      value={intermittentSchedule}
                      onChange={(event) => setIntermittentSchedule(event.target.value)}
                      placeholder="Example: 3 days/week"
                      className="w-full px-4 py-3 border border-zinc-200 rounded-lg"
                    />
                  </div>
                )}
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowModal(false)}
                className="flex-1 px-4 py-2 border border-zinc-200 text-zinc-700 rounded-lg hover:bg-zinc-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={!startDate || submitting}
                className="flex-1 px-4 py-2 bg-zinc-900 text-white rounded-lg hover:bg-zinc-800 disabled:opacity-50"
              >
                {submitting ? 'Submitting...' : 'Submit Request'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
