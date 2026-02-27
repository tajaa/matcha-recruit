import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileText, Clock, Calendar, User, ChevronRight, AlertCircle, Sparkles, CheckSquare, Square, ExternalLink, BookOpen, Globe } from 'lucide-react';
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

interface PriorityTask {
  id: string;
  title: string;
  description: string | null;
  due_date: string | null;
  status: string;
  completed_at: string | null;
  link_type: string | null;
  link_id: string | null;
  link_label: string | null;
  link_url: string | null;
}

function TaskLink({ task }: { task: PriorityTask }) {
  if (!task.link_type) return null;
  const label = task.link_label || 'View';
  if (task.link_type === 'url' && task.link_url) {
    return (
      <a
        href={task.link_url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider text-emerald-400 hover:text-emerald-300 transition-colors"
      >
        <Globe className="w-3 h-3" />
        {label}
        <ExternalLink className="w-2.5 h-2.5" />
      </a>
    );
  }
  if (task.link_type === 'policy' || task.link_type === 'handbook') {
    const Icon = task.link_type === 'handbook' ? BookOpen : FileText;
    const color = task.link_type === 'handbook'
      ? 'text-purple-400 hover:text-purple-300'
      : 'text-blue-400 hover:text-blue-300';
    return (
      <Link
        to="/portal/policies"
        className={`flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider ${color} transition-colors`}
      >
        <Icon className="w-3 h-3" />
        {label}
        <ChevronRight className="w-2.5 h-2.5" />
      </Link>
    );
  }
  return null;
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
  const [priorities, setPriorities] = useState<PriorityTask[]>([]);
  const [completingId, setCompletingId] = useState<string | null>(null);

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        const [data, priorityData] = await Promise.all([
          portalApi.getDashboard(),
          portalApi.getPriorities().catch(() => ({ tasks: [] })),
        ]);
        setDashboard(data);
        setPriorities(priorityData.tasks || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    };

    fetchDashboard();
  }, []);

  const handleCompleteTask = async (taskId: string) => {
    setCompletingId(taskId);
    try {
      await portalApi.completePriority(taskId);
      setPriorities(prev =>
        prev.map(t => t.id === taskId ? { ...t, status: 'completed', completed_at: new Date().toISOString() } : t)
      );
    } catch {
      // ignore — task stays unchecked
    } finally {
      setCompletingId(null);
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

      {/* Priorities */}
      {priorities.length > 0 && (
        <div className="bg-zinc-900/30 border border-white/10">
          <div className="px-6 py-4 border-b border-white/10 bg-white/5 flex items-center justify-between">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Priorities</h2>
            <span className="text-[10px] font-mono text-zinc-600">
              {priorities.filter(t => t.status === 'completed').length}/{priorities.length} done
            </span>
          </div>
          <div className="divide-y divide-white/5">
            {priorities.map(task => {
              const done = task.status === 'completed';
              const isCompleting = completingId === task.id;
              return (
                <div
                  key={task.id}
                  className={`flex items-start gap-4 px-6 py-4 transition-colors ${
                    done ? 'opacity-50' : 'hover:bg-white/5'
                  }`}
                >
                  <button
                    onClick={() => !done && handleCompleteTask(task.id)}
                    disabled={done || isCompleting}
                    className={`mt-0.5 flex-shrink-0 transition-colors ${
                      done ? 'text-emerald-400 cursor-default' : 'text-zinc-600 hover:text-white'
                    } disabled:opacity-50`}
                  >
                    {done ? (
                      <CheckSquare className="w-4 h-4" />
                    ) : (
                      <Square className="w-4 h-4" />
                    )}
                  </button>
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium ${done ? 'line-through text-zinc-500' : 'text-white'}`}>
                      {task.title}
                    </p>
                    {task.description && (
                      <p className="text-xs text-zinc-500 mt-0.5">{task.description}</p>
                    )}
                    <div className="flex items-center gap-3 mt-1 flex-wrap">
                      {task.due_date && !done && (
                        <p className="text-[10px] font-mono uppercase tracking-wider text-zinc-600">
                          Due {new Date(task.due_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                        </p>
                      )}
                      <TaskLink task={task} />
                    </div>
                  </div>
                  {isCompleting && (
                    <div className="w-1.5 h-1.5 rounded-full bg-zinc-400 animate-pulse mt-2 flex-shrink-0" />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

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
