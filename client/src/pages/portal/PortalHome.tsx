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
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <span className="text-red-400">{error || 'Failed to load dashboard'}</span>
        </div>
      </div>
    );
  }

  const availablePTO = dashboard.pto_balance
    ? toFiniteNumber(dashboard.pto_balance.balance_hours) - toFiniteNumber(dashboard.pto_balance.used_hours)
    : 0;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="border-b border-white/10 pb-6">
        <h1 className="text-2xl font-bold tracking-tight text-white uppercase">
          Welcome, {dashboard.employee.first_name}
        </h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
          Employee Self-Service Portal
        </p>
      </div>

      {/* Pending Tasks Alert */}
      {dashboard.pending_tasks_count > 0 && (
        <div className="bg-amber-500/10 border border-dashed border-amber-500/20 p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-amber-500" />
            <span className="text-amber-200 text-sm">
              You have {dashboard.pending_tasks_count} pending task{dashboard.pending_tasks_count > 1 ? 's' : ''}
            </span>
          </div>
          <Link
            to="/portal/documents"
            className="text-xs text-amber-400 hover:text-amber-300 font-bold uppercase tracking-wider flex items-center gap-1"
          >
            View <ChevronRight className="w-3 h-3" />
          </Link>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* PTO Balance */}
        <div className="bg-zinc-900/50 border border-dashed border-white/10 p-6 hover:border-white/20 transition-colors group">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-zinc-800 border border-zinc-700 flex items-center justify-center group-hover:bg-zinc-700 transition-colors">
              <Clock className="w-5 h-5 text-zinc-400 group-hover:text-white" />
            </div>
            <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 font-bold">PTO Available</span>
          </div>
          <div className="text-3xl font-bold text-white tracking-tight">
            {availablePTO.toFixed(1)}
            <span className="text-sm font-normal text-zinc-500 ml-2">hrs</span>
          </div>
          <Link
            to="/portal/pto"
            className="text-[10px] uppercase tracking-widest text-zinc-500 hover:text-white mt-4 inline-flex items-center gap-1 transition-colors"
          >
            Manage PTO <ChevronRight className="w-3 h-3" />
          </Link>
        </div>

        {/* Pending Documents */}
        <div className="bg-zinc-900/50 border border-dashed border-white/10 p-6 hover:border-white/20 transition-colors group">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-zinc-800 border border-zinc-700 flex items-center justify-center group-hover:bg-zinc-700 transition-colors">
              <FileText className="w-5 h-5 text-zinc-400 group-hover:text-white" />
            </div>
            <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 font-bold">Documents</span>
          </div>
          <div className="text-3xl font-bold text-white tracking-tight">
            {dashboard.pending_documents_count}
            <span className="text-sm font-normal text-zinc-500 ml-2">pending</span>
          </div>
          <Link
            to="/portal/documents"
            className="text-[10px] uppercase tracking-widest text-zinc-500 hover:text-white mt-4 inline-flex items-center gap-1 transition-colors"
          >
            View documents <ChevronRight className="w-3 h-3" />
          </Link>
        </div>

        {/* PTO Requests */}
        <div className="bg-zinc-900/50 border border-dashed border-white/10 p-6 hover:border-white/20 transition-colors group">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-zinc-800 border border-zinc-700 flex items-center justify-center group-hover:bg-zinc-700 transition-colors">
              <Calendar className="w-5 h-5 text-zinc-400 group-hover:text-white" />
            </div>
            <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 font-bold">PTO Requests</span>
          </div>
          <div className="text-3xl font-bold text-white tracking-tight">
            {dashboard.pending_pto_requests_count}
            <span className="text-sm font-normal text-zinc-500 ml-2">pending</span>
          </div>
          <Link
            to="/portal/pto"
            className="text-[10px] uppercase tracking-widest text-zinc-500 hover:text-white mt-4 inline-flex items-center gap-1 transition-colors"
          >
            Request time off <ChevronRight className="w-3 h-3" />
          </Link>
        </div>
      </div>

      {/* Quick Links */}
      <div className="bg-zinc-900/30 border border-white/10">
        <div className="px-6 py-4 border-b border-white/10 bg-white/5">
          <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Quick Links</h2>
        </div>
        <div className="divide-y divide-white/5">
          <Link
            to="/portal/documents"
            className="flex items-center justify-between px-6 py-4 hover:bg-white/5 transition-colors group"
          >
            <div className="flex items-center gap-4">
              <FileText className="w-4 h-4 text-zinc-500 group-hover:text-zinc-300 transition-colors" />
              <span className="text-sm text-zinc-300 group-hover:text-white transition-colors">My Documents</span>
            </div>
            <ChevronRight className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
          </Link>
          <Link
            to="/portal/pto"
            className="flex items-center justify-between px-6 py-4 hover:bg-white/5 transition-colors group"
          >
            <div className="flex items-center gap-4">
              <Calendar className="w-4 h-4 text-zinc-500 group-hover:text-zinc-300 transition-colors" />
              <span className="text-sm text-zinc-300 group-hover:text-white transition-colors">Time Off</span>
            </div>
            <ChevronRight className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
          </Link>
          <Link
            to="/portal/policies"
            className="flex items-center justify-between px-6 py-4 hover:bg-white/5 transition-colors group"
          >
            <div className="flex items-center gap-4">
              <FileText className="w-4 h-4 text-zinc-500 group-hover:text-zinc-300 transition-colors" />
              <span className="text-sm text-zinc-300 group-hover:text-white transition-colors">Company Policies</span>
            </div>
            <ChevronRight className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
          </Link>
          <Link
            to="/portal/profile"
            className="flex items-center justify-between px-6 py-4 hover:bg-white/5 transition-colors group"
          >
            <div className="flex items-center gap-4">
              <User className="w-4 h-4 text-zinc-500 group-hover:text-zinc-300 transition-colors" />
              <span className="text-sm text-zinc-300 group-hover:text-white transition-colors">My Profile</span>
            </div>
            <ChevronRight className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
          </Link>
          <Link
            to="/app/portal/mobility"
            className="flex items-center justify-between px-6 py-4 hover:bg-white/5 transition-colors group"
          >
            <div className="flex items-center gap-4">
              <Sparkles className="w-4 h-4 text-zinc-500 group-hover:text-zinc-300 transition-colors" />
              <span className="text-sm text-zinc-300 group-hover:text-white transition-colors">Internal Mobility</span>
            </div>
            <ChevronRight className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
          </Link>
        </div>
      </div>
    </div>
  );
}

export default PortalHome;
