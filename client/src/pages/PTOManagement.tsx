import { useState, useEffect } from 'react';
import { getAccessToken } from '../api/client';
import {
  Calendar, Clock, CheckCircle, XCircle, AlertTriangle
} from 'lucide-react';

const API_BASE = 'http://localhost:8001/api';

interface PTORequest {
  id: string;
  employee_id: string;
  employee_name: string;
  employee_email: string;
  start_date: string;
  end_date: string;
  hours: number;
  reason: string | null;
  request_type: string;
  status: string;
  approved_by: string | null;
  approved_at: string | null;
  denial_reason: string | null;
  created_at: string;
}

interface PTOSummary {
  pending_count: number;
  upcoming_time_off: number;
}

export default function PTOManagement() {
  const [requests, setRequests] = useState<PTORequest[]>([]);
  const [summary, setSummary] = useState<PTOSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('pending');
  const [showDenyModal, setShowDenyModal] = useState(false);
  const [selectedRequest, setSelectedRequest] = useState<PTORequest | null>(null);
  const [denialReason, setDenialReason] = useState('');
  const [processing, setProcessing] = useState<string | null>(null);

  const fetchRequests = async () => {
    try {
      const token = getAccessToken();
      const url = filter ? `${API_BASE}/employees/pto/requests?status=${filter}` : `${API_BASE}/employees/pto/requests`;
      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Failed to fetch PTO requests');
      const data = await response.json();
      setRequests(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const fetchSummary = async () => {
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/pto/summary`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Failed to fetch PTO summary');
      const data = await response.json();
      setSummary(data);
    } catch (err) {
      console.error('Failed to fetch summary:', err);
    }
  };

  useEffect(() => {
    fetchRequests();
    fetchSummary();
  }, [filter]);

  const handleApprove = async (requestId: string) => {
    setProcessing(requestId);
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/pto/requests/${requestId}`, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ action: 'approve' }),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to approve request');
      }
      fetchRequests();
      fetchSummary();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setProcessing(null);
    }
  };

  const handleDeny = async () => {
    if (!selectedRequest || !denialReason) return;
    setProcessing(selectedRequest.id);
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/pto/requests/${selectedRequest.id}`, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ action: 'deny', denial_reason: denialReason }),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to deny request');
      }
      setShowDenyModal(false);
      setSelectedRequest(null);
      setDenialReason('');
      fetchRequests();
      fetchSummary();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setProcessing(null);
    }
  };

  const openDenyModal = (request: PTORequest) => {
    setSelectedRequest(request);
    setDenialReason('');
    setShowDenyModal(true);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return (
          <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold bg-amber-900/30 text-amber-400 border border-amber-500/20">
            <Clock size={10} /> Pending
          </span>
        );
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold bg-emerald-900/30 text-emerald-400 border border-emerald-500/20">
            <CheckCircle size={10} /> Approved
          </span>
        );
      case 'denied':
        return (
          <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold bg-red-900/30 text-red-400 border border-red-500/20">
            <XCircle size={10} /> Denied
          </span>
        );
      case 'cancelled':
        return (
          <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold bg-zinc-800 text-zinc-400 border border-zinc-700">
            Cancelled
          </span>
        );
      default:
        return <span className="text-xs text-zinc-400">{status}</span>;
    }
  };

  const formatRequestType = (type: string) => {
    return type.charAt(0).toUpperCase() + type.slice(1);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading requests...</div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Time Off Requests</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Manage employee PTO requests
          </p>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-zinc-900/50 border border-white/10 p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-zinc-500">Pending Approval</p>
                <p className="text-4xl font-bold text-white mt-1">{summary.pending_count}</p>
              </div>
              <div className="w-12 h-12 rounded-full bg-amber-500/20 flex items-center justify-center">
                <Clock className="text-amber-400" size={24} />
              </div>
            </div>
          </div>
          <div className="bg-zinc-900/50 border border-white/10 p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-zinc-500">Upcoming Time Off (30 days)</p>
                <p className="text-4xl font-bold text-white mt-1">{summary.upcoming_time_off}</p>
              </div>
              <div className="w-12 h-12 rounded-full bg-emerald-500/20 flex items-center justify-center">
                <Calendar className="text-emerald-400" size={24} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle className="text-red-400" size={16} />
            <p className="text-sm text-red-400 font-mono">{error}</p>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-xs text-red-400 hover:text-red-300 uppercase tracking-wider font-bold"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Filter tabs */}
      <div className="border-b border-white/10">
        <nav className="-mb-px flex space-x-8">
          {[
            { value: 'pending', label: 'Pending' },
            { value: 'approved', label: 'Approved' },
            { value: 'denied', label: 'Denied' },
            { value: '', label: 'All' },
          ].map((tab) => (
            <button
              key={tab.value}
              onClick={() => setFilter(tab.value)}
              className={`pb-4 px-1 border-b-2 text-xs font-bold uppercase tracking-wider transition-colors ${
                filter === tab.value
                  ? 'border-white text-white'
                  : 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-800'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Requests list */}
      {requests.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-white/10 bg-white/5">
          <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
            <Calendar size={24} className="text-zinc-600" />
          </div>
          <h3 className="text-white text-sm font-bold mb-1 uppercase tracking-wide">No requests found</h3>
          <p className="text-zinc-500 text-xs font-mono">
            {filter === 'pending' ? 'No pending requests to review.' : 'No PTO requests match your filter.'}
          </p>
        </div>
      ) : (
        <div className="space-y-px bg-white/10 border border-white/10">
          {/* Table Header */}
          <div className="hidden md:flex items-center gap-4 py-3 px-6 bg-zinc-950 text-[10px] text-zinc-500 uppercase tracking-widest border-b border-white/10">
            <div className="flex-1">Employee</div>
            <div className="w-24 text-center">Type</div>
            <div className="w-40 text-center">Dates</div>
            <div className="w-20 text-center">Hours</div>
            <div className="w-24 text-center">Status</div>
            <div className="w-40"></div>
          </div>

          {requests.map((request) => (
            <div
              key={request.id}
              className="group bg-zinc-950 hover:bg-zinc-900 transition-colors p-4 md:px-6 flex flex-col md:flex-row md:items-center gap-4"
            >
              <div className="flex items-center min-w-0 flex-1">
                <div className="flex-shrink-0">
                  <div className="h-10 w-10 rounded bg-zinc-800 border border-zinc-700 flex items-center justify-center text-white font-bold text-xs">
                    {request.employee_name.split(' ').map((n) => n[0]).join('')}
                  </div>
                </div>
                <div className="ml-4 min-w-0">
                  <p className="text-sm font-bold text-white truncate group-hover:text-zinc-200">
                    {request.employee_name}
                  </p>
                  <p className="text-xs text-zinc-500 font-mono truncate">{request.employee_email}</p>
                </div>
              </div>

              <div className="flex items-center justify-between md:justify-end gap-4 md:gap-8 w-full md:w-auto">
                <div className="w-24 text-center">
                  <p className="text-xs text-zinc-400">{formatRequestType(request.request_type)}</p>
                </div>
                <div className="w-40 text-center">
                  <p className="text-xs text-white font-mono">
                    {new Date(request.start_date).toLocaleDateString()} -{' '}
                    {new Date(request.end_date).toLocaleDateString()}
                  </p>
                </div>
                <div className="w-20 text-center">
                  <p className="text-sm text-white font-mono">{request.hours}h</p>
                </div>
                <div className="w-24 text-center">{getStatusBadge(request.status)}</div>
                <div className="w-40 flex justify-end gap-2">
                  {request.status === 'pending' && (
                    <>
                      <button
                        onClick={() => handleApprove(request.id)}
                        disabled={processing === request.id}
                        className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] font-bold uppercase tracking-wider rounded transition-colors disabled:opacity-50"
                      >
                        {processing === request.id ? '...' : 'Approve'}
                      </button>
                      <button
                        onClick={() => openDenyModal(request)}
                        disabled={processing === request.id}
                        className="px-3 py-1.5 border border-white/10 text-zinc-400 hover:text-white hover:border-white/30 text-[10px] font-bold uppercase tracking-wider rounded transition-colors disabled:opacity-50"
                      >
                        Deny
                      </button>
                    </>
                  )}
                  {request.status === 'denied' && request.denial_reason && (
                    <span className="text-xs text-red-400 italic truncate max-w-[140px]" title={request.denial_reason}>
                      {request.denial_reason}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Deny Modal */}
      {showDenyModal && selectedRequest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-zinc-950 border border-zinc-800 shadow-2xl rounded-sm">
            <div className="p-6 border-b border-white/10">
              <h3 className="text-xl font-bold text-white uppercase tracking-tight">Deny Request</h3>
              <p className="text-sm text-zinc-500 mt-1">
                Deny PTO request from {selectedRequest.employee_name}
              </p>
            </div>
            <div className="p-6 space-y-4">
              <div className="bg-zinc-900 border border-zinc-800 p-4 rounded text-sm">
                <p className="text-zinc-400">
                  <span className="text-white font-medium">{formatRequestType(selectedRequest.request_type)}</span>
                  {' - '}
                  {new Date(selectedRequest.start_date).toLocaleDateString()} to{' '}
                  {new Date(selectedRequest.end_date).toLocaleDateString()}
                </p>
                <p className="text-zinc-500 mt-1">{selectedRequest.hours} hours requested</p>
                {selectedRequest.reason && (
                  <p className="text-zinc-500 mt-2 italic">"{selectedRequest.reason}"</p>
                )}
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                  Reason for denial <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={denialReason}
                  onChange={(e) => setDenialReason(e.target.value)}
                  rows={3}
                  placeholder="Please provide a reason for denying this request..."
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors resize-none"
                />
              </div>
            </div>
            <div className="p-6 border-t border-white/10 flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowDenyModal(false);
                  setSelectedRequest(null);
                  setDenialReason('');
                }}
                className="px-4 py-2 text-zinc-500 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDeny}
                disabled={!denialReason || processing === selectedRequest.id}
                className="px-6 py-2 bg-red-600 hover:bg-red-500 text-white text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50"
              >
                {processing === selectedRequest.id ? 'Processing...' : 'Deny Request'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
