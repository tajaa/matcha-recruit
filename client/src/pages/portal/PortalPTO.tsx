import { useEffect, useState } from 'react';
import { Calendar, Clock, CheckCircle, XCircle, AlertCircle, Plus, X } from 'lucide-react';
import { FeatureGuideTrigger } from '../../features/feature-guides';
import { portalApi } from '../../api/portal';

interface PTOBalance {
  balance_hours: number;
  accrued_hours: number;
  used_hours: number;
  carryover_hours: number;
}

interface PTORequest {
  id: string;
  start_date: string;
  end_date: string;
  hours: number;
  reason: string | null;
  request_type: string;
  status: string;
  approved_at: string | null;
  denial_reason: string | null;
  created_at: string;
}

export function PortalPTO() {
  const [balance, setBalance] = useState<PTOBalance | null>(null);
  const [pendingRequests, setPendingRequests] = useState<PTORequest[]>([]);
  const [approvedRequests, setApprovedRequests] = useState<PTORequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showRequestModal, setShowRequestModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Form state
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [hours, setHours] = useState('8');
  const [reason, setReason] = useState('');
  const [requestType, setRequestType] = useState('vacation');

  const fetchData = async () => {
    try {
      setLoading(true);
      const data = await portalApi.getPTOSummary();
      setBalance(data.balance);
      setPendingRequests(data.pending_requests);
      setApprovedRequests(data.approved_requests);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load PTO data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleSubmitRequest = async () => {
    if (!startDate || !endDate || !hours) return;

    setSubmitting(true);
    try {
      await portalApi.submitPTORequest({
        start_date: startDate,
        end_date: endDate,
        hours: parseFloat(hours),
        reason: reason || undefined,
        request_type: requestType,
      });
      setShowRequestModal(false);
      setStartDate('');
      setEndDate('');
      setHours('8');
      setReason('');
      setRequestType('vacation');
      fetchData();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to submit request');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancelRequest = async (requestId: string) => {
    if (!confirm('Are you sure you want to cancel this PTO request?')) return;

    try {
      await portalApi.cancelPTORequest(requestId);
      fetchData();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to cancel request');
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
            <Clock className="w-3 h-3" /> Pending
          </span>
        );
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
            <CheckCircle className="w-3 h-3" /> Approved
          </span>
        );
      case 'denied':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800">
            <XCircle className="w-3 h-3" /> Denied
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-zinc-100 text-zinc-800">
            {status}
          </span>
        );
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

  const availablePTO = balance ? balance.balance_hours - balance.used_hours : 0;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-mono font-medium text-zinc-900">Time Off</h1>
            <FeatureGuideTrigger guideId="portal-pto" variant="light" />
          </div>
          <p className="text-sm text-zinc-500 mt-1">Manage your PTO requests</p>
        </div>
        <button
          data-tour="portal-pto-request-btn"
          onClick={() => setShowRequestModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white text-sm font-medium rounded-lg hover:bg-zinc-800 transition-colors"
        >
          <Plus className="w-4 h-4" /> Request Time Off
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500" />
          <span className="text-red-700">{error}</span>
        </div>
      )}

      {/* Balance Cards */}
      {balance && (
        <div data-tour="portal-pto-balance" className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white border border-zinc-200 rounded-lg p-5">
            <span className="text-xs font-mono uppercase tracking-wider text-zinc-500">Available</span>
            <div className="text-3xl font-mono font-medium text-zinc-900 mt-1">
              {availablePTO.toFixed(1)}
              <span className="text-lg text-zinc-400 ml-1">hrs</span>
            </div>
          </div>
          <div className="bg-white border border-zinc-200 rounded-lg p-5">
            <span className="text-xs font-mono uppercase tracking-wider text-zinc-500">Total Balance</span>
            <div className="text-3xl font-mono font-medium text-zinc-900 mt-1">
              {balance.balance_hours.toFixed(1)}
              <span className="text-lg text-zinc-400 ml-1">hrs</span>
            </div>
          </div>
          <div className="bg-white border border-zinc-200 rounded-lg p-5">
            <span className="text-xs font-mono uppercase tracking-wider text-zinc-500">Used</span>
            <div className="text-3xl font-mono font-medium text-zinc-900 mt-1">
              {balance.used_hours.toFixed(1)}
              <span className="text-lg text-zinc-400 ml-1">hrs</span>
            </div>
          </div>
          <div className="bg-white border border-zinc-200 rounded-lg p-5">
            <span className="text-xs font-mono uppercase tracking-wider text-zinc-500">Accrued YTD</span>
            <div className="text-3xl font-mono font-medium text-zinc-900 mt-1">
              {balance.accrued_hours.toFixed(1)}
              <span className="text-lg text-zinc-400 ml-1">hrs</span>
            </div>
          </div>
        </div>
      )}

      {/* Pending Requests */}
      {pendingRequests.length > 0 && (
        <div data-tour="portal-pto-pending" className="bg-white border border-zinc-200 rounded-lg">
          <div className="px-5 py-4 border-b border-zinc-100">
            <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-500">Pending Requests</h2>
          </div>
          <div className="divide-y divide-zinc-100">
            {pendingRequests.map((req) => (
              <div key={req.id} className="p-5 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                    <Calendar className="w-5 h-5 text-amber-600" />
                  </div>
                  <div>
                    <div className="font-medium text-zinc-900">
                      {new Date(req.start_date).toLocaleDateString()} - {new Date(req.end_date).toLocaleDateString()}
                    </div>
                    <div className="text-sm text-zinc-500">
                      {req.hours} hours - {req.request_type}
                      {req.reason && ` - ${req.reason}`}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {getStatusBadge(req.status)}
                  <button
                    data-tour="portal-pto-cancel-btn"
                    onClick={() => handleCancelRequest(req.id)}
                    className="p-2 text-zinc-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                    title="Cancel request"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Approved Requests */}
      <div data-tour="portal-pto-approved" className="bg-white border border-zinc-200 rounded-lg">
        <div className="px-5 py-4 border-b border-zinc-100">
          <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-500">Approved Time Off</h2>
        </div>
        {approvedRequests.length === 0 ? (
          <div className="p-8 text-center text-zinc-500">
            <Calendar className="w-12 h-12 mx-auto text-zinc-300 mb-3" />
            <p>No approved time off this year</p>
          </div>
        ) : (
          <div className="divide-y divide-zinc-100">
            {approvedRequests.map((req) => (
              <div key={req.id} className="p-5 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                    <Calendar className="w-5 h-5 text-green-600" />
                  </div>
                  <div>
                    <div className="font-medium text-zinc-900">
                      {new Date(req.start_date).toLocaleDateString()} - {new Date(req.end_date).toLocaleDateString()}
                    </div>
                    <div className="text-sm text-zinc-500">
                      {req.hours} hours - {req.request_type}
                    </div>
                  </div>
                </div>
                {getStatusBadge(req.status)}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Request Modal */}
      {showRequestModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-full max-w-md mx-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium text-zinc-900">Request Time Off</h2>
              <button
                onClick={() => setShowRequestModal(false)}
                className="p-1 hover:bg-zinc-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-zinc-500" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 mb-2">Request Type</label>
                <select
                  value={requestType}
                  onChange={(e) => setRequestType(e.target.value)}
                  className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900"
                >
                  <option value="vacation">Vacation</option>
                  <option value="sick">Sick Leave</option>
                  <option value="personal">Personal</option>
                  <option value="other">Other</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-zinc-700 mb-2">Start Date</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    min={new Date().toISOString().split('T')[0]}
                    className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-zinc-700 mb-2">End Date</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    min={startDate || new Date().toISOString().split('T')[0]}
                    className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 mb-2">Hours</label>
                <input
                  type="number"
                  value={hours}
                  onChange={(e) => setHours(e.target.value)}
                  min="1"
                  step="0.5"
                  className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 mb-2">Reason (optional)</label>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  placeholder="Brief description of your time off"
                  className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900 resize-none"
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowRequestModal(false)}
                className="flex-1 px-4 py-2 border border-zinc-200 text-zinc-700 rounded-lg hover:bg-zinc-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmitRequest}
                disabled={!startDate || !endDate || !hours || submitting}
                className="flex-1 px-4 py-2 bg-zinc-900 text-white rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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

export default PortalPTO;
