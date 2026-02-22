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

function toFiniteNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
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
      if (data.balance) {
        setBalance({
          ...data.balance,
          balance_hours: toFiniteNumber(data.balance.balance_hours),
          accrued_hours: toFiniteNumber(data.balance.accrued_hours),
          used_hours: toFiniteNumber(data.balance.used_hours),
          carryover_hours: toFiniteNumber(data.balance.carryover_hours),
        });
      } else {
        setBalance(null);
      }
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
          <span className="inline-flex items-center px-2.5 py-1 bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[9px] uppercase tracking-widest font-bold">
            <Clock className="w-3 h-3 mr-1.5" /> Pending
          </span>
        );
      case 'approved':
        return (
          <span className="inline-flex items-center px-2.5 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[9px] uppercase tracking-widest font-bold">
            <CheckCircle className="w-3 h-3 mr-1.5" /> Approved
          </span>
        );
      case 'denied':
        return (
          <span className="inline-flex items-center px-2.5 py-1 bg-red-500/10 text-red-400 border border-red-500/20 text-[9px] uppercase tracking-widest font-bold">
            <XCircle className="w-3 h-3 mr-1.5" /> Denied
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-1 bg-zinc-500/10 text-zinc-400 border border-zinc-500/20 text-[9px] uppercase tracking-widest font-bold">
            {status}
          </span>
        );
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-zinc-600 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  const availablePTO = balance ? balance.balance_hours - balance.used_hours : 0;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white uppercase">Time Off</h1>
            <FeatureGuideTrigger guideId="portal-pto" variant="light" />
          </div>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Manage your PTO requests</p>
        </div>
        <button
          data-tour="portal-pto-request-btn"
          onClick={() => setShowRequestModal(true)}
          className="inline-flex items-center gap-2 px-6 py-2 bg-white text-black text-[10px] uppercase tracking-widest font-bold border border-white hover:bg-zinc-200 transition-colors"
        >
          <Plus className="w-4 h-4" /> Request Time Off
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <span className="text-red-400 font-mono text-sm uppercase">{error}</span>
        </div>
      )}

      {/* Balance Cards */}
      {balance && (
        <div data-tour="portal-pto-balance" className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div className="bg-zinc-900/50 border border-dashed border-white/10 p-6">
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Available</span>
            <div className="text-3xl font-bold text-white tracking-tight mt-2">
              {availablePTO.toFixed(1)}
              <span className="text-sm font-normal text-zinc-500 ml-2">hrs</span>
            </div>
          </div>
          <div className="bg-zinc-900/50 border border-dashed border-white/10 p-6">
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Total Balance</span>
            <div className="text-3xl font-bold text-white tracking-tight mt-2">
              {balance.balance_hours.toFixed(1)}
              <span className="text-sm font-normal text-zinc-500 ml-2">hrs</span>
            </div>
          </div>
          <div className="bg-zinc-900/50 border border-dashed border-white/10 p-6">
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Used</span>
            <div className="text-3xl font-bold text-white tracking-tight mt-2">
              {balance.used_hours.toFixed(1)}
              <span className="text-sm font-normal text-zinc-500 ml-2">hrs</span>
            </div>
          </div>
          <div className="bg-zinc-900/50 border border-dashed border-white/10 p-6">
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Accrued YTD</span>
            <div className="text-3xl font-bold text-white tracking-tight mt-2">
              {balance.accrued_hours.toFixed(1)}
              <span className="text-sm font-normal text-zinc-500 ml-2">hrs</span>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Pending Requests */}
        <div data-tour="portal-pto-pending" className="bg-zinc-900/30 border border-white/10">
          <div className="px-6 py-4 border-b border-white/10 bg-white/5">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Pending Requests</h2>
          </div>
          {pendingRequests.length === 0 ? (
            <div className="p-16 text-center">
                <Clock className="w-10 h-10 mx-auto text-zinc-700 mb-4 opacity-50" />
                <p className="text-xs text-zinc-500 font-mono uppercase tracking-widest">No pending requests</p>
            </div>
          ) : (
            <div className="divide-y divide-white/5">
                {pendingRequests.map((req) => (
                <div key={req.id} className="p-6 flex items-center justify-between hover:bg-white/5 transition-colors group">
                    <div className="flex items-center gap-5">
                    <div className="w-10 h-10 border border-white/10 bg-amber-900/20 flex items-center justify-center">
                        <Calendar className="w-4 h-4 text-amber-400" />
                    </div>
                    <div>
                        <div className="text-sm font-bold text-white tracking-tight">
                        {new Date(req.start_date).toLocaleDateString()} - {new Date(req.end_date).toLocaleDateString()}
                        </div>
                        <div className="text-[11px] text-zinc-500 mt-0.5">
                        {req.hours} hours &bull; {req.request_type}
                        {req.reason && ` &bull; ${req.reason}`}
                        </div>
                    </div>
                    </div>
                    <div className="flex items-center gap-4">
                    {getStatusBadge(req.status)}
                    <button
                        data-tour="portal-pto-cancel-btn"
                        onClick={() => handleCancelRequest(req.id)}
                        className="p-2 text-zinc-600 hover:text-red-400 transition-colors"
                        title="Cancel request"
                    >
                        <X className="w-4 h-4" />
                    </button>
                    </div>
                </div>
                ))}
            </div>
          )}
        </div>

        {/* Approved Requests */}
        <div data-tour="portal-pto-approved" className="bg-zinc-900/30 border border-white/10">
            <div className="px-6 py-4 border-b border-white/10 bg-white/5">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Approved Time Off</h2>
            </div>
            {approvedRequests.length === 0 ? (
            <div className="p-16 text-center">
                <Calendar className="w-10 h-10 mx-auto text-zinc-700 mb-4 opacity-50" />
                <p className="text-xs text-zinc-500 font-mono uppercase tracking-widest">No approved time off this year</p>
            </div>
            ) : (
            <div className="divide-y divide-white/5">
                {approvedRequests.map((req) => (
                <div key={req.id} className="p-6 flex items-center justify-between hover:bg-white/5 transition-colors group">
                    <div className="flex items-center gap-5">
                    <div className="w-10 h-10 border border-white/10 bg-emerald-900/20 flex items-center justify-center">
                        <Calendar className="w-4 h-4 text-emerald-400" />
                    </div>
                    <div>
                        <div className="text-sm font-bold text-white tracking-tight">
                        {new Date(req.start_date).toLocaleDateString()} - {new Date(req.end_date).toLocaleDateString()}
                        </div>
                        <div className="text-[11px] text-zinc-500 mt-0.5">
                        {req.hours} hours &bull; {req.request_type}
                        </div>
                    </div>
                    </div>
                    {getStatusBadge(req.status)}
                </div>
                ))}
            </div>
            )}
        </div>
      </div>

      {/* Request Modal */}
      {showRequestModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-950 border border-white/10 p-8 w-full max-w-md animate-in fade-in zoom-in duration-200 shadow-2xl">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-lg font-bold text-white uppercase tracking-tight">Request Time Off</h2>
              <button
                onClick={() => setShowRequestModal(false)}
                className="p-1 hover:bg-white/5 transition-colors"
              >
                <X className="w-5 h-5 text-zinc-500" />
              </button>
            </div>

            <div className="space-y-6">
              <div>
                <label className="block text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-2 ml-1">Request Type</label>
                <select
                  value={requestType}
                  onChange={(e) => setRequestType(e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none appearance-none font-mono"
                >
                  <option value="vacation">Vacation</option>
                  <option value="sick">Sick Leave</option>
                  <option value="personal">Personal</option>
                  <option value="other">Other</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="block text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-2 ml-1">Start Date</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    min={new Date().toISOString().split('T')[0]}
                    className="w-full bg-zinc-900 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none font-mono"
                  />
                </div>
                <div>
                  <label className="block text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-2 ml-1">End Date</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    min={startDate || new Date().toISOString().split('T')[0]}
                    className="w-full bg-zinc-900 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-2 ml-1">Hours</label>
                <input
                  type="number"
                  value={hours}
                  onChange={(e) => setHours(e.target.value)}
                  min="1"
                  step="0.5"
                  className="w-full bg-zinc-900 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none font-mono"
                />
              </div>

              <div>
                <label className="block text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-2 ml-1">Reason (optional)</label>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  placeholder="Brief description of your time off"
                  className="w-full bg-zinc-900 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none resize-none font-mono leading-relaxed"
                />
              </div>
            </div>

            <div className="flex gap-4 mt-8">
              <button
                onClick={() => setShowRequestModal(false)}
                className="flex-1 px-4 py-3 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-zinc-500 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmitRequest}
                disabled={!startDate || !endDate || !hours || submitting}
                className="flex-1 px-4 py-3 bg-white text-black text-[10px] font-bold uppercase tracking-widest border border-white hover:bg-zinc-200 transition-colors disabled:opacity-50"
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
