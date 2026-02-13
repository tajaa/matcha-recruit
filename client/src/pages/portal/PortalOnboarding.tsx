import { useState, useEffect } from 'react';
import { CheckCircle, Clock, FileText, Laptop, GraduationCap, Settings, AlertCircle } from 'lucide-react';
import { FeatureGuideTrigger } from '../../features/feature-guides';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

interface OnboardingTask {
  id: string;
  title: string;
  description: string | null;
  category: string;
  is_employee_task: boolean;
  due_date: string | null;
  status: 'pending' | 'completed' | 'skipped';
  completed_at: string | null;
  notes: string | null;
  created_at: string;
}

interface OnboardingProgress {
  total: number;
  completed: number;
  pending: number;
  tasks: OnboardingTask[];
}

const CATEGORIES = [
  { value: 'documents', label: 'Documents', icon: FileText, color: 'text-blue-500', bgColor: 'bg-blue-100' },
  { value: 'equipment', label: 'Equipment', icon: Laptop, color: 'text-purple-500', bgColor: 'bg-purple-100' },
  { value: 'training', label: 'Training', icon: GraduationCap, color: 'text-amber-500', bgColor: 'bg-amber-100' },
  { value: 'admin', label: 'Admin', icon: Settings, color: 'text-zinc-500', bgColor: 'bg-zinc-100' },
];

async function fetchWithAuth(url: string, options: RequestInit = {}) {
  const token = localStorage.getItem('access_token');
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }
  return response.json();
}

export function PortalOnboarding() {
  const [progress, setProgress] = useState<OnboardingProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [completingTask, setCompletingTask] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const data = await fetchWithAuth(`${API_BASE}/v1/portal/onboarding`);
      setProgress(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load onboarding tasks');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCompleteTask = async (taskId: string) => {
    setCompletingTask(taskId);
    try {
      await fetchWithAuth(`${API_BASE}/v1/portal/onboarding/${taskId}`, {
        method: 'PATCH',
        body: JSON.stringify({}),
      });
      fetchData();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to complete task');
    } finally {
      setCompletingTask(null);
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

  const progressPercent = progress ? Math.round((progress.completed / Math.max(progress.total, 1)) * 100) : 0;
  const myTasks = progress?.tasks.filter((t) => t.is_employee_task) || [];
  const hrTasks = progress?.tasks.filter((t) => !t.is_employee_task) || [];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-mono font-medium text-zinc-900">Onboarding Checklist</h1>
          <FeatureGuideTrigger guideId="portal-onboarding" variant="light" />
        </div>
        <p className="text-sm text-zinc-500 mt-1">Complete your onboarding tasks to get started</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500" />
          <span className="text-red-700">{error}</span>
        </div>
      )}

      {/* Progress Card */}
      {progress && progress.total > 0 && (
        <div data-tour="portal-onboard-progress" className="bg-white border border-zinc-200 rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-medium text-zinc-900">Your Progress</span>
            <span className="text-sm text-zinc-500">
              {progress.completed} of {progress.total} tasks complete
            </span>
          </div>
          <div className="w-full h-3 bg-zinc-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-green-500 rounded-full transition-all duration-500"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="flex items-center gap-4 mt-3 text-xs text-zinc-500">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-500" /> {progress.completed} Completed
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-amber-500" /> {progress.pending} Pending
            </span>
          </div>
        </div>
      )}

      {/* No Tasks */}
      {progress && progress.total === 0 && (
        <div className="bg-white border border-zinc-200 rounded-lg p-12 text-center">
          <CheckCircle className="w-12 h-12 mx-auto text-green-500 mb-4" />
          <h3 className="text-lg font-medium text-zinc-900 mb-2">All caught up!</h3>
          <p className="text-zinc-500">No onboarding tasks have been assigned yet.</p>
        </div>
      )}

      {/* My Tasks Section */}
      {myTasks.length > 0 && (
        <div data-tour="portal-onboard-my-tasks" className="bg-white border border-zinc-200 rounded-lg">
          <div className="px-5 py-4 border-b border-zinc-100">
            <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-500">Your Tasks</h2>
          </div>
          <div className="divide-y divide-zinc-100">
            {CATEGORIES.map((cat) => {
              const categoryTasks = myTasks.filter((t) => t.category === cat.value);
              if (categoryTasks.length === 0) return null;

              return categoryTasks.map((task) => (
                <div key={task.id} className="p-5 flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div
                      className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        task.status === 'completed' ? 'bg-green-100' : cat.bgColor
                      }`}
                    >
                      {task.status === 'completed' ? (
                        <CheckCircle className="w-5 h-5 text-green-600" />
                      ) : (
                        <cat.icon className={`w-5 h-5 ${cat.color}`} />
                      )}
                    </div>
                    <div>
                      <div
                        className={`font-medium ${
                          task.status === 'completed' ? 'text-zinc-400 line-through' : 'text-zinc-900'
                        }`}
                      >
                        {task.title}
                      </div>
                      <div className="text-sm text-zinc-500">
                        {task.description}
                        {task.due_date && (
                          <span className="ml-2">
                            Due: {new Date(task.due_date).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {task.status === 'completed' ? (
                      <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                        <CheckCircle className="w-3 h-3" /> Done
                      </span>
                    ) : (
                      <button
                        data-tour="portal-onboard-complete-btn"
                        onClick={() => handleCompleteTask(task.id)}
                        disabled={completingTask === task.id}
                        className="px-4 py-2 bg-zinc-900 text-white text-sm font-medium rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50"
                      >
                        {completingTask === task.id ? 'Saving...' : 'Mark Complete'}
                      </button>
                    )}
                  </div>
                </div>
              ));
            })}
          </div>
        </div>
      )}

      {/* HR Tasks Section */}
      {hrTasks.length > 0 && (
        <div data-tour="portal-onboard-hr-tasks" className="bg-white border border-zinc-200 rounded-lg">
          <div className="px-5 py-4 border-b border-zinc-100">
            <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-500">HR/Manager Tasks</h2>
            <p className="text-xs text-zinc-400 mt-1">These tasks will be completed by your HR team or manager</p>
          </div>
          <div className="divide-y divide-zinc-100">
            {CATEGORIES.map((cat) => {
              const categoryTasks = hrTasks.filter((t) => t.category === cat.value);
              if (categoryTasks.length === 0) return null;

              return categoryTasks.map((task) => (
                <div key={task.id} className="p-5 flex items-center justify-between opacity-75">
                  <div className="flex items-center gap-4">
                    <div
                      className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        task.status === 'completed' ? 'bg-green-100' : cat.bgColor
                      }`}
                    >
                      {task.status === 'completed' ? (
                        <CheckCircle className="w-5 h-5 text-green-600" />
                      ) : (
                        <Clock className={`w-5 h-5 ${cat.color}`} />
                      )}
                    </div>
                    <div>
                      <div
                        className={`font-medium ${
                          task.status === 'completed' ? 'text-zinc-400 line-through' : 'text-zinc-700'
                        }`}
                      >
                        {task.title}
                      </div>
                      {task.description && <div className="text-sm text-zinc-500">{task.description}</div>}
                    </div>
                  </div>
                  {task.status === 'completed' ? (
                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      <CheckCircle className="w-3 h-3" /> Done
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
                      <Clock className="w-3 h-3" /> Pending
                    </span>
                  )}
                </div>
              ));
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default PortalOnboarding;
