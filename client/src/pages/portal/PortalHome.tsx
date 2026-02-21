import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileText, Clock, Calendar, User, ChevronRight, AlertCircle, Sparkles } from 'lucide-react';
import { portalApi } from '../../api/portal';

interface PortalDashboard {
  employee: {
    id: string;
    first_name: string;
    last_name: string;
    email: string;
    work_state: string | null;
    employment_type: string | null;
    start_date: string | null;
  };
  pto_balance: {
    balance_hours: number;
    accrued_hours: number;
    used_hours: number;
  } | null;
  pending_tasks_count: number;
  pending_documents_count: number;
  pending_pto_requests_count: number;
}

function toFiniteNumber(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
}

export function PortalHome() {
  const [dashboard, setDashboard] = useState<PortalDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        const data = await portalApi.getDashboard();
        setDashboard(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    };

    fetchDashboard();
  }, []);

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

  if (error || !dashboard) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500" />
          <span className="text-red-700">{error || 'Failed to load dashboard'}</span>
        </div>
      </div>
    );
  }

  const availablePTO = dashboard.pto_balance
    ? toFiniteNumber(dashboard.pto_balance.balance_hours) - toFiniteNumber(dashboard.pto_balance.used_hours)
    : 0;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-mono font-medium text-zinc-900">
          Welcome, {dashboard.employee.first_name}
        </h1>
        <p className="text-sm text-zinc-500 mt-1">
          Employee Self-Service Portal
        </p>
      </div>

      {/* Pending Tasks Alert */}
      {dashboard.pending_tasks_count > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600" />
            <span className="text-amber-800">
              You have {dashboard.pending_tasks_count} pending task{dashboard.pending_tasks_count > 1 ? 's' : ''}
            </span>
          </div>
          <Link
            to="/portal/documents"
            className="text-sm text-amber-700 hover:text-amber-900 font-medium flex items-center gap-1"
          >
            View <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* PTO Balance */}
        <div className="bg-white border border-zinc-200 rounded-lg p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-zinc-100 flex items-center justify-center">
              <Clock className="w-5 h-5 text-zinc-600" />
            </div>
            <span className="text-xs font-mono uppercase tracking-wider text-zinc-500">PTO Available</span>
          </div>
          <div className="text-3xl font-mono font-medium text-zinc-900">
            {availablePTO.toFixed(1)}
            <span className="text-lg text-zinc-400 ml-1">hrs</span>
          </div>
          <Link
            to="/portal/pto"
            className="text-sm text-zinc-500 hover:text-zinc-700 mt-2 inline-flex items-center gap-1"
          >
            Manage PTO <ChevronRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Pending Documents */}
        <div className="bg-white border border-zinc-200 rounded-lg p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-zinc-100 flex items-center justify-center">
              <FileText className="w-5 h-5 text-zinc-600" />
            </div>
            <span className="text-xs font-mono uppercase tracking-wider text-zinc-500">Documents</span>
          </div>
          <div className="text-3xl font-mono font-medium text-zinc-900">
            {dashboard.pending_documents_count}
            <span className="text-lg text-zinc-400 ml-1">pending</span>
          </div>
          <Link
            to="/portal/documents"
            className="text-sm text-zinc-500 hover:text-zinc-700 mt-2 inline-flex items-center gap-1"
          >
            View documents <ChevronRight className="w-4 h-4" />
          </Link>
        </div>

        {/* PTO Requests */}
        <div className="bg-white border border-zinc-200 rounded-lg p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-zinc-100 flex items-center justify-center">
              <Calendar className="w-5 h-5 text-zinc-600" />
            </div>
            <span className="text-xs font-mono uppercase tracking-wider text-zinc-500">PTO Requests</span>
          </div>
          <div className="text-3xl font-mono font-medium text-zinc-900">
            {dashboard.pending_pto_requests_count}
            <span className="text-lg text-zinc-400 ml-1">pending</span>
          </div>
          <Link
            to="/portal/pto"
            className="text-sm text-zinc-500 hover:text-zinc-700 mt-2 inline-flex items-center gap-1"
          >
            Request time off <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      </div>

      {/* Quick Links */}
      <div className="bg-white border border-zinc-200 rounded-lg">
        <div className="px-5 py-4 border-b border-zinc-100">
          <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-500">Quick Links</h2>
        </div>
        <div className="divide-y divide-zinc-100">
          <Link
            to="/portal/documents"
            className="flex items-center justify-between px-5 py-4 hover:bg-zinc-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <FileText className="w-5 h-5 text-zinc-400" />
              <span className="text-zinc-900">My Documents</span>
            </div>
            <ChevronRight className="w-5 h-5 text-zinc-400" />
          </Link>
          <Link
            to="/portal/pto"
            className="flex items-center justify-between px-5 py-4 hover:bg-zinc-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <Calendar className="w-5 h-5 text-zinc-400" />
              <span className="text-zinc-900">Time Off</span>
            </div>
            <ChevronRight className="w-5 h-5 text-zinc-400" />
          </Link>
          <Link
            to="/portal/policies"
            className="flex items-center justify-between px-5 py-4 hover:bg-zinc-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <FileText className="w-5 h-5 text-zinc-400" />
              <span className="text-zinc-900">Company Policies</span>
            </div>
            <ChevronRight className="w-5 h-5 text-zinc-400" />
          </Link>
          <Link
            to="/portal/profile"
            className="flex items-center justify-between px-5 py-4 hover:bg-zinc-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <User className="w-5 h-5 text-zinc-400" />
              <span className="text-zinc-900">My Profile</span>
            </div>
            <ChevronRight className="w-5 h-5 text-zinc-400" />
          </Link>
          <Link
            to="/app/portal/mobility"
            className="flex items-center justify-between px-5 py-4 hover:bg-zinc-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <Sparkles className="w-5 h-5 text-zinc-400" />
              <span className="text-zinc-900">Internal Mobility</span>
            </div>
            <ChevronRight className="w-5 h-5 text-zinc-400" />
          </Link>
        </div>
      </div>
    </div>
  );
}

export default PortalHome;
