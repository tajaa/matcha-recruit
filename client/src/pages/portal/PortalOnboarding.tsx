import { useState, useEffect, useRef } from 'react';
import { CheckCircle, Clock, FileText, Laptop, GraduationCap, Settings, AlertCircle, RotateCcw, Upload, Shield } from 'lucide-react';
import { FeatureGuideTrigger } from '../../features/feature-guides';
import { portalApi } from '../../api/portal';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

const CREDENTIAL_DOC_TYPES = [
  { value: 'medical_license', label: 'Medical License' },
  { value: 'dea', label: 'DEA Registration' },
  { value: 'npi', label: 'NPI Card' },
  { value: 'board_cert', label: 'Board Certification' },
  { value: 'malpractice', label: 'Malpractice Insurance' },
  { value: 'health_clearance', label: 'Health Clearance (CPR/BLS/TB/etc)' },
  { value: 'other', label: 'Other' },
] as const;

interface CredentialDoc {
  id: string;
  document_type: string;
  filename: string;
  extraction_status: string;
  review_status: string;
  created_at: string | null;
}

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
  { value: 'documents', label: 'Documents', icon: FileText, color: 'text-emerald-400', bgColor: 'bg-emerald-900/20' },
  { value: 'equipment', label: 'Equipment', icon: Laptop, color: 'text-blue-400', bgColor: 'bg-blue-900/20' },
  { value: 'training', label: 'Training', icon: GraduationCap, color: 'text-amber-400', bgColor: 'bg-amber-900/20' },
  { value: 'admin', label: 'Admin', icon: Settings, color: 'text-zinc-400', bgColor: 'bg-zinc-800/20' },
  { value: 'return_to_work', label: 'Return to Work', icon: RotateCcw, color: 'text-purple-400', bgColor: 'bg-purple-900/20' },
];

async function fetchWithAuth(url: string, options: RequestInit = {}) {
  const token = localStorage.getItem('matcha_access_token');
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

  // Credential document upload state
  const [credDocs, setCredDocs] = useState<CredentialDoc[]>([]);
  const [credDocType, setCredDocType] = useState('medical_license');
  const [credUploading, setCredUploading] = useState(false);
  const credFileRef = useRef<HTMLInputElement>(null);

  const fetchCredDocs = async () => {
    try {
      const docs = await portalApi.listCredentialDocuments();
      setCredDocs(docs);
    } catch { /* ignore if not available */ }
  };

  useEffect(() => { fetchCredDocs(); }, []);

  const handleCredUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCredUploading(true);
    try {
      await portalApi.uploadCredentialDocument(file, credDocType);
      fetchCredDocs();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setCredUploading(false);
      if (credFileRef.current) credFileRef.current.value = '';
    }
  };

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
          <div className="w-2 h-2 rounded-full bg-zinc-600 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  const progressPercent = progress ? Math.round((progress.completed / Math.max(progress.total, 1)) * 100) : 0;
  const myTasks = progress?.tasks.filter((t) => t.is_employee_task) || [];
  const hrTasks = progress?.tasks.filter((t) => !t.is_employee_task) || [];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="border-b border-white/10 pb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-white uppercase">Onboarding Checklist</h1>
          <FeatureGuideTrigger guideId="portal-onboarding" />
        </div>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Complete your onboarding tasks to get started</p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <span className="text-red-400 text-sm font-mono uppercase">{error}</span>
        </div>
      )}

      {/* Progress Card */}
      {progress && progress.total > 0 && (
        <div data-tour="portal-onboard-progress" className="bg-zinc-900/50 border border-dashed border-white/10 p-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] font-bold text-white uppercase tracking-widest">Your Progress</span>
            <span className="text-[10px] text-zinc-500 font-mono uppercase">
              {progress.completed} / {progress.total} tasks complete
            </span>
          </div>
          <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 rounded-full transition-all duration-1000"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="flex items-center gap-4 mt-4 text-[10px] font-mono uppercase tracking-wider">
            <span className="flex items-center gap-1.5 text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> {progress.completed} Completed
            </span>
            <span className="flex items-center gap-1.5 text-amber-400">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" /> {progress.pending} Pending
            </span>
          </div>
        </div>
      )}

      {/* No Tasks */}
      {progress && progress.total === 0 && (
        <div className="bg-zinc-900/30 border border-dashed border-white/10 p-16 text-center">
          <CheckCircle className="w-12 h-12 mx-auto text-emerald-500 mb-4 opacity-50" />
          <h3 className="text-lg font-bold text-white uppercase tracking-tight mb-2">All caught up!</h3>
          <p className="text-xs text-zinc-500 font-mono uppercase tracking-wider">No onboarding tasks have been assigned yet.</p>
        </div>
      )}

      {/* My Tasks Section */}
      {myTasks.length > 0 && (
        <div data-tour="portal-onboard-my-tasks" className="bg-zinc-900/30 border border-white/10">
          <div className="px-6 py-4 border-b border-white/10 bg-white/5">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Your Tasks</h2>
          </div>
          <div className="divide-y divide-white/5">
            {CATEGORIES.map((cat) => {
              const categoryTasks = myTasks.filter((t) => t.category === cat.value);
              if (categoryTasks.length === 0) return null;

              return categoryTasks.map((task) => (
                <div key={task.id} className="p-6 flex items-center justify-between hover:bg-white/5 transition-colors group">
                  <div className="flex items-center gap-5">
                    <div
                      className={`w-10 h-10 border border-white/10 flex items-center justify-center transition-colors ${
                        task.status === 'completed' ? 'bg-emerald-900/20' : cat.bgColor
                      }`}
                    >
                      {task.status === 'completed' ? (
                        <CheckCircle className="w-5 h-5 text-emerald-400" />
                      ) : (
                        <cat.icon className={`w-5 h-5 ${cat.color}`} />
                      )}
                    </div>
                    <div>
                      <div
                        className={`text-sm font-bold tracking-tight transition-colors ${
                          task.status === 'completed' ? 'text-zinc-600 line-through' : 'text-white'
                        }`}
                      >
                        {task.title}
                      </div>
                      <div className="text-[11px] text-zinc-500 mt-0.5">
                        {task.description}
                        {task.due_date && (
                          <span className="ml-3 font-mono uppercase text-zinc-600 border-l border-white/10 pl-3">
                            Due: {new Date(task.due_date).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {task.status === 'completed' ? (
                      <span className="inline-flex items-center px-2.5 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[9px] uppercase tracking-widest font-bold">
                        Completed
                      </span>
                    ) : (
                      <button
                        data-tour="portal-onboard-complete-btn"
                        onClick={() => handleCompleteTask(task.id)}
                        disabled={completingTask === task.id}
                        className="px-6 py-2 bg-white text-black text-[10px] uppercase tracking-widest font-bold border border-white hover:bg-zinc-200 transition-colors disabled:opacity-50"
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
        <div data-tour="portal-onboard-hr-tasks" className="bg-zinc-900/30 border border-white/10">
          <div className="px-6 py-4 border-b border-white/10 bg-white/5">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">HR/Manager Tasks</h2>
            <p className="text-[9px] text-zinc-600 uppercase tracking-widest mt-1">These tasks will be completed by your HR team or manager</p>
          </div>
          <div className="divide-y divide-white/5">
            {CATEGORIES.map((cat) => {
              const categoryTasks = hrTasks.filter((t) => t.category === cat.value);
              if (categoryTasks.length === 0) return null;

              return categoryTasks.map((task) => (
                <div key={task.id} className="p-6 flex items-center justify-between opacity-60 grayscale hover:opacity-100 hover:grayscale-0 transition-all group">
                  <div className="flex items-center gap-5">
                    <div
                      className={`w-10 h-10 border border-white/10 flex items-center justify-center ${
                        task.status === 'completed' ? 'bg-emerald-900/20' : cat.bgColor
                      }`}
                    >
                      {task.status === 'completed' ? (
                        <CheckCircle className="w-5 h-5 text-emerald-400" />
                      ) : (
                        <Clock className={`w-5 h-5 ${cat.color}`} />
                      )}
                    </div>
                    <div>
                      <div
                        className={`text-sm font-bold tracking-tight ${
                          task.status === 'completed' ? 'text-zinc-600 line-through' : 'text-zinc-400'
                        }`}
                      >
                        {task.title}
                      </div>
                      {task.description && <div className="text-[11px] text-zinc-600 mt-0.5">{task.description}</div>}
                    </div>
                  </div>
                  {task.status === 'completed' ? (
                    <span className="inline-flex items-center px-2.5 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[9px] uppercase tracking-widest font-bold">
                      Done
                    </span>
                  ) : (
                    <span className="inline-flex items-center px-2.5 py-1 bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[9px] uppercase tracking-widest font-bold">
                      Pending
                    </span>
                  )}
                </div>
              ));
            })}
          </div>
        </div>
      )}

      {/* Credential Documents Upload */}
      <div className="bg-zinc-900/30 border border-white/10">
        <div className="px-6 py-4 border-b border-white/10 bg-white/5">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-blue-400" />
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Upload Credentials (Optional)</h2>
          </div>
          <p className="text-[9px] text-zinc-600 uppercase tracking-widest mt-1">Upload licenses, certifications, or other credential documents for verification</p>
        </div>
        <div className="p-6 space-y-4">
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="text-[9px] text-zinc-500 uppercase tracking-wider font-bold block mb-1.5">Document Type</label>
              <select
                value={credDocType}
                onChange={(e) => setCredDocType(e.target.value)}
                className="w-full bg-zinc-800 border border-white/10 text-zinc-100 text-sm px-3 py-2 focus:outline-none focus:border-white/20"
              >
                {CREDENTIAL_DOC_TYPES.map((dt) => (
                  <option key={dt.value} value={dt.value}>{dt.label}</option>
                ))}
              </select>
            </div>
            <div>
              <input
                ref={credFileRef}
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.gif,.tiff"
                onChange={handleCredUpload}
                className="hidden"
              />
              <button
                onClick={() => credFileRef.current?.click()}
                disabled={credUploading}
                className="px-6 py-2 bg-white text-black text-[10px] uppercase tracking-widest font-bold border border-white hover:bg-zinc-200 transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                <Upload className="w-3.5 h-3.5" />
                {credUploading ? 'Uploading...' : 'Upload'}
              </button>
            </div>
          </div>

          {credDocs.length > 0 && (
            <div className="space-y-2">
              {credDocs.map((doc) => (
                <div key={doc.id} className="flex items-center justify-between px-4 py-3 bg-zinc-800/50 border border-white/5">
                  <div className="flex items-center gap-3">
                    <FileText className="w-4 h-4 text-zinc-500" />
                    <div>
                      <div className="text-xs text-zinc-300">{doc.filename}</div>
                      <div className="text-[9px] text-zinc-600 uppercase tracking-wider">
                        {CREDENTIAL_DOC_TYPES.find((t) => t.value === doc.document_type)?.label || doc.document_type}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center px-2 py-0.5 text-[9px] uppercase tracking-widest font-bold border ${
                      doc.extraction_status === 'extracted' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                      doc.extraction_status === 'failed' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                      'bg-amber-500/10 text-amber-400 border-amber-500/20 animate-pulse'
                    }`}>
                      {doc.extraction_status === 'extracted' ? 'Scanned' : doc.extraction_status === 'failed' ? 'Scan Failed' : 'Scanning...'}
                    </span>
                    <span className={`inline-flex items-center px-2 py-0.5 text-[9px] uppercase tracking-widest font-bold border ${
                      doc.review_status === 'approved' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                      doc.review_status === 'rejected' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                      'bg-zinc-500/10 text-zinc-400 border-zinc-500/20'
                    }`}>
                      {doc.review_status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default PortalOnboarding;
