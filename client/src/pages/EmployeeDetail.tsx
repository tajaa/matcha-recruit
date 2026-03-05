import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getAccessToken, provisioning } from '../api/client';
import type { EmployeeGoogleWorkspaceProvisioningStatus, EmployeeSlackProvisioningStatus, ProvisioningRunStatus } from '../types';
import {
  ArrowLeft, Mail, Phone, MapPin, Calendar, Users, CheckCircle, Clock, FileText,
  Laptop, GraduationCap, Settings, Plus, X, AlertTriangle, SkipForward, RotateCcw,
  Pencil, DollarSign, Briefcase, Save, ChevronRight
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

interface Employee {
  id: string;
  email: string;
  work_email?: string | null;
  personal_email?: string | null;
  first_name: string;
  last_name: string;
  work_state: string | null;
  work_city: string | null;
  employment_type: string | null;
  start_date: string | null;
  termination_date: string | null;
  manager_id: string | null;
  manager_name: string | null;
  user_id: string | null;
  invitation_status: string | null;
  phone: string | null;
  address: string | null;
  pay_classification: string | null;
  pay_rate: number | null;
  job_title: string | null;
  department: string | null;
  emergency_contact: object | null;
  created_at: string;
}

interface EmployeeListItem {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
}

interface EditFields {
  first_name: string;
  last_name: string;
  work_email: string;
  personal_email: string;
  phone: string;
  address: string;
  work_state: string;
  work_city: string;
  employment_type: string;
  start_date: string;
  pay_classification: string;
  pay_rate: string;
  job_title: string;
  department: string;
  manager_id: string;
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

interface OnboardingTemplate {
  id: string;
  title: string;
  description: string | null;
  category: string;
  is_employee_task: boolean;
  due_days: number;
  is_active: boolean;
}

const CATEGORIES = [
  { value: 'documents', label: 'Documents', icon: FileText, color: 'text-blue-400', bgColor: 'bg-blue-500/10' },
  { value: 'equipment', label: 'Equipment', icon: Laptop, color: 'text-purple-400', bgColor: 'bg-purple-500/10' },
  { value: 'training', label: 'Training', icon: GraduationCap, color: 'text-amber-400', bgColor: 'bg-amber-500/10' },
  { value: 'admin', label: 'Admin', icon: Settings, color: 'text-zinc-400', bgColor: 'bg-zinc-500/10' },
  { value: 'return_to_work', label: 'Return to Work', icon: RotateCcw, color: 'text-emerald-400', bgColor: 'bg-emerald-500/10' },
];

function provisioningStatusBadge(status?: string | null): string {
  if (status === 'connected' || status === 'completed' || status === 'active') {
    return 'bg-emerald-900/30 text-emerald-300 border border-emerald-600/30';
  }
  if (status === 'failed' || status === 'error') {
    return 'bg-red-900/30 text-red-300 border border-red-600/30';
  }
  if (status === 'needs_action' || status === 'running' || status === 'pending' || status === 'disconnected') {
    return 'bg-amber-900/30 text-amber-300 border border-amber-600/30';
  }
  return 'bg-zinc-800 text-zinc-300 border border-zinc-700';
}

export default function EmployeeDetail() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const navigate = useNavigate();
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [tasks, setTasks] = useState<OnboardingTask[]>([]);
  const [templates, setTemplates] = useState<OnboardingTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [selectedTemplates, setSelectedTemplates] = useState<string[]>([]);
  const [assigningAll, setAssigningAll] = useState(false);
  const [provisioningStatus, setProvisioningStatus] = useState<EmployeeGoogleWorkspaceProvisioningStatus | null>(null);
  const [slackProvisioningStatus, setSlackProvisioningStatus] = useState<EmployeeSlackProvisioningStatus | null>(null);
  const [provisioningLoading, setProvisioningLoading] = useState(false);
  const [provisioningActionLoading, setProvisioningActionLoading] = useState(false);
  const [slackActionLoading, setSlackActionLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editFields, setEditFields] = useState<EditFields | null>(null);
  const [saving, setSaving] = useState(false);
  const [allEmployees, setAllEmployees] = useState<EmployeeListItem[]>([]);
  const [directReports, setDirectReports] = useState<EmployeeListItem[]>([]);
  const [departments, setDepartments] = useState<string[]>([]);

  const startEditing = () => {
    if (!employee) return;
    setEditFields({
      first_name: employee.first_name || '',
      last_name: employee.last_name || '',
      work_email: employee.work_email || employee.email || '',
      personal_email: employee.personal_email || '',
      phone: employee.phone || '',
      address: employee.address || '',
      work_state: employee.work_state || '',
      work_city: employee.work_city || '',
      employment_type: employee.employment_type || '',
      start_date: employee.start_date || '',
      pay_classification: employee.pay_classification || '',
      pay_rate: employee.pay_rate != null ? String(employee.pay_rate) : '',
      job_title: employee.job_title || '',
      department: employee.department || '',
      manager_id: employee.manager_id || '',
    });
    setEditing(true);
  };

  const cancelEditing = () => {
    setEditing(false);
    setEditFields(null);
  };

  const handleSave = async () => {
    if (!employeeId || !editFields) return;
    setSaving(true);
    setError(null);
    try {
      const token = getAccessToken();
      const body: Record<string, unknown> = {};
      if (editFields.first_name !== (employee?.first_name || '')) body.first_name = editFields.first_name;
      if (editFields.last_name !== (employee?.last_name || '')) body.last_name = editFields.last_name;
      if (editFields.work_email !== (employee?.work_email || employee?.email || '')) body.work_email = editFields.work_email;
      if (editFields.personal_email !== (employee?.personal_email || '')) body.personal_email = editFields.personal_email || null;
      if (editFields.phone !== (employee?.phone || '')) body.phone = editFields.phone || null;
      if (editFields.address !== (employee?.address || '')) body.address = editFields.address || null;
      if (editFields.work_state !== (employee?.work_state || '')) body.work_state = editFields.work_state || null;
      if (editFields.work_city !== (employee?.work_city || '')) body.work_city = editFields.work_city || null;
      if (editFields.employment_type !== (employee?.employment_type || '')) body.employment_type = editFields.employment_type || null;
      if (editFields.start_date !== (employee?.start_date || '')) body.start_date = editFields.start_date || null;
      if (editFields.pay_classification !== (employee?.pay_classification || '')) body.pay_classification = editFields.pay_classification || null;
      const newRate = editFields.pay_rate ? parseFloat(editFields.pay_rate) : null;
      const oldRate = employee?.pay_rate ?? null;
      if (newRate !== oldRate) body.pay_rate = newRate;
      if (editFields.job_title !== (employee?.job_title || '')) body.job_title = editFields.job_title || null;
      if (editFields.department !== (employee?.department || '')) body.department = editFields.department || null;
      if (editFields.manager_id !== (employee?.manager_id || '')) body.manager_id = editFields.manager_id || null;

      if (Object.keys(body).length === 0) {
        setEditing(false);
        setEditFields(null);
        return;
      }

      const response = await fetch(`${API_BASE}/employees/${employeeId}`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({ detail: 'Failed to save' }));
        throw new Error(data.detail || 'Failed to save');
      }
      const updated = await response.json();
      setEmployee(updated);
      setEditing(false);
      setEditFields(null);
      setStatusMessage('Employee updated successfully.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const fetchEmployee = async () => {
    if (!employeeId) return;
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/${employeeId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Failed to fetch employee');
      const data = await response.json();
      setEmployee(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  const fetchTasks = async () => {
    if (!employeeId) return;
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/${employeeId}/onboarding`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Failed to fetch tasks');
      const data = await response.json();
      setTasks(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  const fetchTemplates = async () => {
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/onboarding/templates?is_active=true`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Failed to fetch templates');
      const data = await response.json();
      setTemplates(data);
    } catch (err) {
      console.error('Failed to fetch templates:', err);
    }
  };

  const fetchProvisioningStatus = async () => {
    if (!employeeId) return;
    setProvisioningLoading(true);
    try {
      const [gwData, slackData] = await Promise.allSettled([
        provisioning.getEmployeeGoogleWorkspaceStatus(employeeId),
        provisioning.getEmployeeSlackStatus(employeeId),
      ]);
      if (gwData.status === 'fulfilled') setProvisioningStatus(gwData.value);
      if (slackData.status === 'fulfilled') setSlackProvisioningStatus(slackData.value);
    } catch (err) {
      console.error('Failed to fetch provisioning status:', err);
    } finally {
      setProvisioningLoading(false);
    }
  };

  const fetchAllEmployees = async () => {
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) return;
      const data = await response.json();
      setAllEmployees(data.map((e: Employee) => ({ id: e.id, first_name: e.first_name, last_name: e.last_name, email: e.email })));
    } catch {
      // non-critical
    }
  };

  const fetchDirectReports = async () => {
    if (!employeeId) return;
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees?manager_id=${employeeId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) return;
      const data = await response.json();
      setDirectReports(data.map((e: Employee) => ({ id: e.id, first_name: e.first_name, last_name: e.last_name, email: e.email })));
    } catch {
      // non-critical
    }
  };

  const fetchDepartments = async () => {
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/departments`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) return;
      setDepartments(await response.json());
    } catch {
      // non-critical
    }
  };

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchEmployee(), fetchTasks(), fetchTemplates(), fetchProvisioningStatus()]);
      setLoading(false);
    };
    loadData();
    fetchAllEmployees();
    fetchDirectReports();
    fetchDepartments();
  }, [employeeId]);

  const handleAssignAll = async () => {
    if (!employeeId) return;
    setAssigningAll(true);
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/${employeeId}/onboarding/assign-all`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to assign tasks');
      }
      fetchTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setAssigningAll(false);
    }
  };

  const handleAssignSelected = async () => {
    if (!employeeId || selectedTemplates.length === 0) return;
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/${employeeId}/onboarding`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ task_ids: selectedTemplates }),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to assign tasks');
      }
      setShowAssignModal(false);
      setSelectedTemplates([]);
      fetchTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  const handleUpdateTask = async (taskId: string, status: string, notes?: string) => {
    if (!employeeId) return;
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/${employeeId}/onboarding/${taskId}`, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ status, notes }),
      });
      if (!response.ok) throw new Error('Failed to update task');
      fetchTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    if (!employeeId || !confirm('Remove this onboarding task?')) return;
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/${employeeId}/onboarding/${taskId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Failed to delete task');
      fetchTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  const handleProvisionGoogleWorkspace = async () => {
    if (!employeeId) return;
    setProvisioningActionLoading(true);
    setError(null);
    setStatusMessage(null);
    try {
      const run = await provisioning.provisionEmployeeGoogleWorkspace(employeeId);
      await fetchProvisioningStatus();
      setStatusMessage(`Google Workspace provisioning run started (${run.status}).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to provision Google Workspace account');
    } finally {
      setProvisioningActionLoading(false);
    }
  };

  const handleRetryProvisioningRun = async (runId: string) => {
    setProvisioningActionLoading(true);
    setError(null);
    setStatusMessage(null);
    try {
      const run = await provisioning.retryRun(runId);
      await fetchProvisioningStatus();
      setStatusMessage(`Provisioning retry queued (${run.status}).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry provisioning run');
    } finally {
      setProvisioningActionLoading(false);
    }
  };

  const handleProvisionSlack = async () => {
    if (!employeeId) return;
    setSlackActionLoading(true);
    setError(null);
    setStatusMessage(null);
    try {
      const run = await provisioning.provisionEmployeeSlack(employeeId);
      await fetchProvisioningStatus();
      setStatusMessage(`Slack provisioning run started (${run.status}).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to provision Slack account');
    } finally {
      setSlackActionLoading(false);
    }
  };

  const groupedTasks = tasks.reduce((acc, task) => {
    const cat = task.category;
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(task);
    return acc;
  }, {} as Record<string, OnboardingTask[]>);

  const completedCount = tasks.filter((t) => t.status === 'completed').length;
  const pendingCount = tasks.filter((t) => t.status === 'pending').length;
  const progress = tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0;
  const googleConnection = provisioningStatus?.connection;
  const recentProvisioningRuns = provisioningStatus?.runs?.slice(0, 3) || [];
  const latestRetryableRun: ProvisioningRunStatus | null =
    provisioningStatus?.runs.find((run) => run.status === 'failed' || run.status === 'needs_action') || null;

  const slackConnection = slackProvisioningStatus?.connection;
  const recentSlackRuns = slackProvisioningStatus?.runs?.slice(0, 3) || [];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading...</div>
      </div>
    );
  }

  if (!employee) {
    return (
      <div className="text-center py-24">
        <p className="text-zinc-500">Employee not found</p>
        <button onClick={() => navigate('/app/matcha/employees')} className="text-white underline mt-4">
          Back to Directory
        </button>
      </div>
    );
  }

  const displayWorkEmail = employee.work_email || employee.email;

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-center gap-4 border-b border-white/10 pb-8">
        <button
          onClick={() => navigate('/app/matcha/employees')}
          className="p-2 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded transition-colors"
        >
          <ArrowLeft size={20} />
        </button>
        <div className="flex-1">
          <h1 className="text-4xl font-bold tracking-tighter text-white">
            {employee.first_name} {employee.last_name}
          </h1>
          <div className="flex items-center gap-3 mt-1">
            {employee.job_title && <span className="text-sm text-zinc-400">{employee.job_title}</span>}
            {employee.job_title && employee.department && <span className="text-zinc-600">·</span>}
            {employee.department && <span className="text-sm text-zinc-400">{employee.department}</span>}
            {!employee.job_title && !employee.department && <span className="text-xs text-zinc-500 font-mono">{displayWorkEmail}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {employee.termination_date ? (
            <span className="px-3 py-1 bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wider rounded">
              Terminated
            </span>
          ) : employee.user_id ? (
            <span className="px-3 py-1 bg-emerald-900/30 text-emerald-400 text-xs uppercase tracking-wider rounded border border-emerald-500/20">
              Active
            </span>
          ) : (
            <span className="px-3 py-1 bg-amber-900/30 text-amber-400 text-xs uppercase tracking-wider rounded border border-amber-500/20">
              {employee.invitation_status === 'pending' ? 'Invited' : 'Not Invited'}
            </span>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle className="text-red-400" size={16} />
            <p className="text-sm text-red-400 font-mono">{error}</p>
          </div>
          <button onClick={() => setError(null)} className="text-xs text-red-400 hover:text-red-300 uppercase tracking-wider font-bold">
            Dismiss
          </button>
        </div>
      )}
      {statusMessage && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded p-4 flex items-center justify-between">
          <p className="text-sm text-emerald-300 font-mono">{statusMessage}</p>
          <button
            onClick={() => setStatusMessage(null)}
            className="text-xs text-emerald-300 hover:text-emerald-200 uppercase tracking-wider font-bold"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Employee Info */}
        <div className="lg:col-span-1 space-y-6">
          <div className="bg-zinc-900/50 border border-white/10 p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-bold uppercase tracking-wider text-zinc-500">Contact Info</h2>
              {!editing && (
                <button onClick={startEditing} className="p-1.5 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded transition-colors" title="Edit">
                  <Pencil size={14} />
                </button>
              )}
            </div>
            {editing && editFields ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[10px] text-zinc-500 uppercase tracking-wider">First Name</label>
                    <input value={editFields.first_name} onChange={(e) => setEditFields({ ...editFields, first_name: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30" />
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Last Name</label>
                    <input value={editFields.last_name} onChange={(e) => setEditFields({ ...editFields, last_name: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30" />
                  </div>
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Work Email</label>
                  <input type="email" value={editFields.work_email} onChange={(e) => setEditFields({ ...editFields, work_email: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30" />
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Personal Email</label>
                  <input type="email" value={editFields.personal_email} onChange={(e) => setEditFields({ ...editFields, personal_email: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30" placeholder="Optional" />
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Phone</label>
                  <input value={editFields.phone} onChange={(e) => setEditFields({ ...editFields, phone: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30" placeholder="Optional" />
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Address</label>
                  <input value={editFields.address} onChange={(e) => setEditFields({ ...editFields, address: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30" placeholder="Optional" />
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <Mail size={16} className="text-zinc-500" />
                  <span className="text-sm text-white">{displayWorkEmail}</span>
                </div>
                {employee.personal_email && (
                  <div className="flex items-center gap-3">
                    <Mail size={16} className="text-zinc-600" />
                    <span className="text-sm text-zinc-300">Personal: {employee.personal_email}</span>
                  </div>
                )}
                {employee.phone && (
                  <div className="flex items-center gap-3">
                    <Phone size={16} className="text-zinc-500" />
                    <span className="text-sm text-white">{employee.phone}</span>
                  </div>
                )}
                {employee.address && (
                  <div className="flex items-center gap-3">
                    <MapPin size={16} className="text-zinc-500" />
                    <span className="text-sm text-white">{employee.address}</span>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="bg-zinc-900/50 border border-white/10 p-6 space-y-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-zinc-500">Employment</h2>
            {editing && editFields ? (
              <div className="space-y-3">
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Job Title</label>
                  <input value={editFields.job_title} onChange={(e) => setEditFields({ ...editFields, job_title: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30" placeholder="e.g. Software Engineer" />
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Department</label>
                  <input value={editFields.department} onChange={(e) => setEditFields({ ...editFields, department: e.target.value })} list="dept-options" className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30" placeholder="e.g. Engineering" />
                  <datalist id="dept-options">
                    {departments.map((d) => <option key={d} value={d} />)}
                  </datalist>
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Employment Type</label>
                  <select value={editFields.employment_type} onChange={(e) => setEditFields({ ...editFields, employment_type: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30">
                    <option value="">Select...</option>
                    <option value="full_time">Full Time</option>
                    <option value="part_time">Part Time</option>
                    <option value="contract">Contract</option>
                    <option value="intern">Intern</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Start Date</label>
                  <input type="date" value={editFields.start_date} onChange={(e) => setEditFields({ ...editFields, start_date: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Work State</label>
                    <input value={editFields.work_state} onChange={(e) => setEditFields({ ...editFields, work_state: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30" placeholder="e.g. CA" />
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Work City</label>
                    <input value={editFields.work_city} onChange={(e) => setEditFields({ ...editFields, work_city: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30" placeholder="e.g. San Francisco" />
                  </div>
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Manager</label>
                  <select
                    value={editFields.manager_id}
                    onChange={(e) => setEditFields({ ...editFields, manager_id: e.target.value })}
                    className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30"
                  >
                    <option value="">No Manager</option>
                    {allEmployees
                      .filter((e) => e.id !== employeeId)
                      .map((e) => (
                        <option key={e.id} value={e.id}>{e.first_name} {e.last_name}</option>
                      ))}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-wider">Pay Classification</label>
                  <select value={editFields.pay_classification} onChange={(e) => setEditFields({ ...editFields, pay_classification: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30">
                    <option value="">Select...</option>
                    <option value="exempt">Exempt (Salary)</option>
                    <option value="hourly">Hourly</option>
                  </select>
                </div>
                {editFields.pay_classification && (
                  <div>
                    <label className="text-[10px] text-zinc-500 uppercase tracking-wider">
                      {editFields.pay_classification === 'hourly' ? 'Hourly Rate ($)' : 'Annual Salary ($)'}
                    </label>
                    <input type="number" step="0.01" min="0" value={editFields.pay_rate} onChange={(e) => setEditFields({ ...editFields, pay_rate: e.target.value })} className="w-full mt-1 px-3 py-1.5 bg-zinc-950 border border-white/10 text-sm text-white rounded focus:outline-none focus:border-white/30" placeholder={editFields.pay_classification === 'hourly' ? '18.50' : '65000'} />
                  </div>
                )}
                <div className="flex items-center gap-2 pt-2">
                  <button onClick={handleSave} disabled={saving} className="flex items-center gap-1.5 px-4 py-1.5 bg-white text-black hover:bg-zinc-200 text-[10px] font-bold uppercase tracking-wider disabled:opacity-50 transition-colors">
                    <Save size={12} />
                    {saving ? 'Saving...' : 'Save Changes'}
                  </button>
                  <button onClick={cancelEditing} disabled={saving} className="px-4 py-1.5 text-zinc-400 hover:text-white text-[10px] font-bold uppercase tracking-wider transition-colors">
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {employee.job_title && (
                  <div className="flex items-center gap-3">
                    <Briefcase size={16} className="text-zinc-500" />
                    <span className="text-sm text-zinc-400">
                      Title: <span className="text-white">{employee.job_title}</span>
                    </span>
                  </div>
                )}
                {employee.department && (
                  <div className="flex items-center gap-3">
                    <Users size={16} className="text-zinc-500" />
                    <span className="text-sm text-zinc-400">
                      Department: <span className="text-white">{employee.department}</span>
                    </span>
                  </div>
                )}
                {employee.start_date && (
                  <div className="flex items-center gap-3">
                    <Calendar size={16} className="text-zinc-500" />
                    <span className="text-sm text-zinc-400">
                      Started: <span className="text-white">{employee.start_date}</span>
                    </span>
                  </div>
                )}
                {employee.employment_type && (
                  <div className="flex items-center gap-3">
                    <Briefcase size={16} className="text-zinc-500" />
                    <span className="text-sm text-zinc-400">
                      Type: <span className="text-white">{employee.employment_type.replace('_', ' ')}</span>
                    </span>
                  </div>
                )}
                <div className="flex items-center gap-3">
                  <MapPin size={16} className="text-zinc-500" />
                  <span className="text-sm text-zinc-400">
                    Location: <span className="text-white">{employee.work_city && employee.work_state ? `${employee.work_city}, ${employee.work_state}` : employee.work_state || employee.work_city || '—'}</span>
                  </span>
                </div>
                {employee.pay_classification && (
                  <div className="flex items-center gap-3">
                    <DollarSign size={16} className="text-zinc-500" />
                    <span className="text-sm text-zinc-400">
                      Pay: <span className="text-white">
                        {employee.pay_classification === 'hourly' ? `$${employee.pay_rate?.toFixed(2) || '—'}/hr` : `$${employee.pay_rate?.toLocaleString() || '—'}/yr`}
                        {' '}({employee.pay_classification})
                      </span>
                    </span>
                  </div>
                )}
                {employee.manager_name && (
                  <div className="flex items-center gap-3">
                    <Users size={16} className="text-zinc-500" />
                    <span className="text-sm text-zinc-400">
                      Manager: <span className="text-white cursor-pointer hover:underline" onClick={() => employee.manager_id && navigate(`/app/matcha/employees/${employee.manager_id}`)}>{employee.manager_name}</span>
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Direct Reports */}
          <div className="bg-zinc-900/50 border border-white/10 p-6 space-y-4">
            <h2 className="text-xs font-bold uppercase tracking-wider text-zinc-500">Direct Reports</h2>
            {directReports.length === 0 ? (
              <p className="text-xs text-zinc-600 font-mono uppercase">No direct reports</p>
            ) : (
              <div className="space-y-2">
                {directReports.map((dr) => (
                  <div
                    key={dr.id}
                    onClick={() => navigate(`/app/matcha/employees/${dr.id}`)}
                    className="flex items-center gap-3 p-2 rounded hover:bg-white/5 cursor-pointer transition-colors"
                  >
                    <div className="h-7 w-7 rounded-lg bg-zinc-800 border border-white/5 flex items-center justify-center text-[10px] font-bold text-zinc-400">
                      {dr.first_name[0]}{dr.last_name[0]}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-white truncate">{dr.first_name} {dr.last_name}</p>
                    </div>
                    <ChevronRight size={14} className="text-zinc-600" />
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-zinc-900/50 border border-white/10 p-6 space-y-4">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-xs font-bold uppercase tracking-wider text-zinc-500">Google Workspace</h2>
              <button
                onClick={() => navigate('/app/matcha/google-workspace')}
                className="text-[10px] uppercase tracking-wider text-zinc-400 hover:text-white"
              >
                Settings
              </button>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-zinc-500 uppercase tracking-wider">Connection</span>
                <span className={`px-2 py-1 text-[10px] uppercase tracking-wider rounded ${provisioningStatusBadge(googleConnection?.status)}`}>
                  {googleConnection?.status || 'disconnected'}
                </span>
              </div>

              {provisioningLoading && (
                <p className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading provisioning status...</p>
              )}

              {googleConnection?.last_error && (
                <p className="text-xs text-red-300">Last error: {googleConnection.last_error}</p>
              )}

              {provisioningStatus?.external_identity ? (
                <div className="space-y-1 border border-white/10 bg-zinc-950/50 p-3">
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider">External Identity</p>
                  <p className="text-xs text-white">{provisioningStatus.external_identity.external_email || 'No external email returned'}</p>
                  <p className="text-[10px] text-zinc-500">
                    Status: <span className="text-zinc-300 uppercase">{provisioningStatus.external_identity.status}</span>
                  </p>
                </div>
              ) : (
                <p className="text-xs text-zinc-500">No Google account provisioned yet.</p>
              )}

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => {
                    if (!googleConnection?.connected) {
                      navigate('/app/matcha/google-workspace');
                      return;
                    }
                    handleProvisionGoogleWorkspace();
                  }}
                  disabled={provisioningActionLoading}
                  className="px-3 py-1.5 bg-white text-black hover:bg-zinc-200 text-[10px] font-bold uppercase tracking-wider disabled:opacity-50"
                >
                  {provisioningActionLoading ? 'Working...' : googleConnection?.connected ? 'Provision Now' : 'Connect Google'}
                </button>

                {latestRetryableRun && (
                  <button
                    onClick={() => handleRetryProvisioningRun(latestRetryableRun.run_id)}
                    disabled={provisioningActionLoading}
                    className="px-3 py-1.5 border border-white/10 text-zinc-300 hover:text-white hover:border-white/30 text-[10px] font-bold uppercase tracking-wider disabled:opacity-50"
                  >
                    Retry Last Run
                  </button>
                )}
              </div>

              {recentProvisioningRuns.length > 0 && (
                <div className="space-y-2">
                  <p className="text-[10px] text-zinc-500 uppercase tracking-wider">Recent Runs</p>
                  {recentProvisioningRuns.map((run) => (
                    <div key={run.run_id} className="border border-white/10 bg-zinc-950/50 p-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[10px] text-zinc-400">
                          {new Date(run.created_at).toLocaleString()}
                        </span>
                        <span className={`px-2 py-0.5 text-[10px] uppercase tracking-wider rounded ${provisioningStatusBadge(run.status)}`}>
                          {run.status}
                        </span>
                      </div>
                      {run.last_error && (
                        <p className="text-[10px] text-red-300 mt-1">{run.last_error}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Slack Provisioning Card */}
        <div className="bg-zinc-900/50 border border-white/10 p-6 space-y-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-zinc-500">Slack</h2>
            <button
              onClick={() => navigate('/app/matcha/slack-provisioning')}
              className="text-[10px] uppercase tracking-wider text-zinc-400 hover:text-white"
            >
              Settings
            </button>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-zinc-500 uppercase tracking-wider">Connection</span>
              <span className={`px-2 py-1 text-[10px] uppercase tracking-wider rounded ${provisioningStatusBadge(slackConnection?.status)}`}>
                {slackConnection?.status || 'disconnected'}
              </span>
            </div>

            {slackConnection?.slack_team_name && (
              <p className="text-xs text-zinc-400">
                Workspace: <span className="text-white">{slackConnection.slack_team_name}</span>
              </p>
            )}

            {slackProvisioningStatus?.external_identity ? (
              <div className="space-y-1 border border-white/10 bg-zinc-950/50 p-3">
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider">External Identity</p>
                <p className="text-xs text-white">{slackProvisioningStatus.external_identity.external_email || 'No email returned'}</p>
                <p className="text-[10px] text-zinc-500">
                  Slack ID: <span className="text-zinc-300">{slackProvisioningStatus.external_identity.external_user_id || '—'}</span>
                </p>
                <p className="text-[10px] text-zinc-500">
                  Status: <span className="text-zinc-300 uppercase">{slackProvisioningStatus.external_identity.status}</span>
                </p>
              </div>
            ) : (
              <p className="text-xs text-zinc-500">No Slack account provisioned yet.</p>
            )}

            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => {
                  if (!slackConnection?.connected) {
                    navigate('/app/matcha/slack-provisioning');
                    return;
                  }
                  handleProvisionSlack();
                }}
                disabled={slackActionLoading}
                className="px-3 py-1.5 bg-white text-black hover:bg-zinc-200 text-[10px] font-bold uppercase tracking-wider disabled:opacity-50"
              >
                {slackActionLoading ? 'Working...' : slackConnection?.connected ? 'Provision Now' : 'Connect Slack'}
              </button>
            </div>

            {recentSlackRuns.length > 0 && (
              <div className="space-y-2">
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider">Recent Runs</p>
                {recentSlackRuns.map((run) => {
                  const warningsRaw = run.steps?.[0]?.last_response?.warnings;
                  const warnings = Array.isArray(warningsRaw)
                    ? warningsRaw.filter((item): item is string => typeof item === 'string')
                    : [];

                  return (
                    <div key={run.run_id} className="border border-white/10 bg-zinc-950/50 p-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[10px] text-zinc-400">
                          {new Date(run.created_at).toLocaleString()}
                        </span>
                        <span className={`px-2 py-0.5 text-[10px] uppercase tracking-wider rounded ${provisioningStatusBadge(run.status)}`}>
                          {run.status}
                        </span>
                      </div>
                      {run.last_error && (
                        <p className="text-[10px] text-red-300 mt-1">{run.last_error}</p>
                      )}
                      {warnings.length > 0 && (
                        <p className="text-[10px] text-amber-400 mt-1">{warnings[0]}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Onboarding Section */}
        <div className="lg:col-span-2 space-y-6">
          {/* Progress */}
          <div className="bg-zinc-900/50 border border-white/10 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xs font-bold uppercase tracking-wider text-zinc-500">Onboarding Progress</h2>
              <div className="flex items-center gap-4">
                <span className="text-sm text-zinc-400">
                  <span className="text-white font-bold">{completedCount}</span> / {tasks.length} completed
                </span>
                {tasks.length === 0 && (
                  <button
                    onClick={handleAssignAll}
                    disabled={assigningAll}
                    className="flex items-center gap-2 px-4 py-1.5 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50"
                  >
                    {assigningAll ? 'Assigning...' : 'Assign All Tasks'}
                  </button>
                )}
                {tasks.length > 0 && (
                  <button
                    onClick={() => setShowAssignModal(true)}
                    className="flex items-center gap-1 px-3 py-1.5 border border-white/10 text-zinc-400 hover:text-white hover:border-white/30 text-xs font-bold uppercase tracking-wider transition-colors"
                  >
                    <Plus size={12} /> Add Task
                  </button>
                )}
              </div>
            </div>
            <div className="w-full h-2 bg-zinc-800 rounded overflow-hidden">
              <div
                className="h-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="flex items-center gap-6 mt-3 text-xs text-zinc-500">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500" /> {completedCount} Completed
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-amber-500" /> {pendingCount} Pending
              </span>
            </div>
          </div>

          {/* Tasks by Category */}
          {tasks.length === 0 ? (
            <div className="text-center py-12 border border-dashed border-white/10 bg-white/5">
              <CheckCircle size={32} className="mx-auto text-zinc-600 mb-4" />
              <p className="text-zinc-500 text-sm">No onboarding tasks assigned yet</p>
              <button
                onClick={handleAssignAll}
                disabled={assigningAll}
                className="mt-4 text-white text-xs uppercase tracking-wider underline underline-offset-4"
              >
                {assigningAll ? 'Assigning...' : 'Assign standard onboarding tasks'}
              </button>
            </div>
          ) : (
            CATEGORIES.map((cat) => {
              const categoryTasks = groupedTasks[cat.value] || [];
              if (categoryTasks.length === 0) return null;

              return (
                <div key={cat.value} className="bg-zinc-900/50 border border-white/10">
                  <div className="flex items-center gap-2 px-6 py-4 border-b border-white/10">
                    <cat.icon size={16} className={cat.color} />
                    <h3 className="text-sm font-bold uppercase tracking-wider text-white">{cat.label}</h3>
                    <span className="text-xs text-zinc-500 font-mono">
                      ({categoryTasks.filter((t) => t.status === 'completed').length}/{categoryTasks.length})
                    </span>
                  </div>
                  <div className="divide-y divide-white/5">
                    {categoryTasks.map((task) => (
                      <div key={task.id} className="px-6 py-4 flex items-center gap-4">
                        <div
                          className={`w-8 h-8 rounded flex items-center justify-center ${
                            task.status === 'completed'
                              ? 'bg-emerald-500/20 text-emerald-400'
                              : task.status === 'skipped'
                              ? 'bg-zinc-500/20 text-zinc-400'
                              : cat.bgColor + ' ' + cat.color
                          }`}
                        >
                          {task.status === 'completed' ? (
                            <CheckCircle size={16} />
                          ) : task.status === 'skipped' ? (
                            <SkipForward size={16} />
                          ) : (
                            <Clock size={16} />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p
                            className={`text-sm font-medium ${
                              task.status === 'completed' ? 'text-zinc-400 line-through' : 'text-white'
                            }`}
                          >
                            {task.title}
                          </p>
                          {task.description && (
                            <p className="text-xs text-zinc-500 truncate">{task.description}</p>
                          )}
                          <div className="flex items-center gap-4 mt-1">
                            <span className="text-[10px] text-zinc-500 uppercase tracking-wider">
                              {task.is_employee_task ? 'Employee Task' : 'HR Task'}
                            </span>
                            {task.due_date && (
                              <span className="text-[10px] text-zinc-500">Due: {task.due_date}</span>
                            )}
                            {task.completed_at && (
                              <span className="text-[10px] text-emerald-400">
                                Completed: {new Date(task.completed_at).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {task.status === 'pending' && (
                            <>
                              <button
                                onClick={() => handleUpdateTask(task.id, 'completed')}
                                className="p-2 text-zinc-400 hover:text-emerald-400 hover:bg-emerald-500/10 rounded transition-colors"
                                title="Mark Complete"
                              >
                                <CheckCircle size={16} />
                              </button>
                              <button
                                onClick={() => handleUpdateTask(task.id, 'skipped')}
                                className="p-2 text-zinc-400 hover:text-zinc-300 hover:bg-zinc-700 rounded transition-colors"
                                title="Skip"
                              >
                                <SkipForward size={16} />
                              </button>
                            </>
                          )}
                          {task.status !== 'pending' && (
                            <button
                              onClick={() => handleUpdateTask(task.id, 'pending')}
                              className="p-2 text-zinc-400 hover:text-amber-400 hover:bg-amber-500/10 rounded transition-colors"
                              title="Reopen"
                            >
                              <Clock size={16} />
                            </button>
                          )}
                          <button
                            onClick={() => handleDeleteTask(task.id)}
                            className="p-2 text-zinc-400 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                            title="Remove"
                          >
                            <X size={16} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Assign Tasks Modal */}
      {showAssignModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-zinc-950 border border-zinc-800 shadow-2xl rounded-sm max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <h3 className="text-xl font-bold text-white uppercase tracking-tight">Add Tasks</h3>
              <button onClick={() => setShowAssignModal(false)} className="text-zinc-500 hover:text-white transition-colors">
                <X size={20} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              <p className="text-xs text-zinc-500 mb-4">Select templates to assign:</p>
              <div className="space-y-2">
                {templates.map((template) => (
                  <label
                    key={template.id}
                    className={`flex items-center gap-3 p-3 border cursor-pointer transition-colors ${
                      selectedTemplates.includes(template.id)
                        ? 'border-white/30 bg-white/5'
                        : 'border-white/10 hover:border-white/20'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedTemplates.includes(template.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedTemplates([...selectedTemplates, template.id]);
                        } else {
                          setSelectedTemplates(selectedTemplates.filter((id) => id !== template.id));
                        }
                      }}
                      className="w-4 h-4"
                    />
                    <div className="flex-1">
                      <p className="text-sm text-white">{template.title}</p>
                      <p className="text-xs text-zinc-500">
                        {template.category} - Due in {template.due_days} days
                      </p>
                    </div>
                  </label>
                ))}
              </div>
            </div>
            <div className="p-6 border-t border-white/10 flex justify-end gap-3">
              <button
                onClick={() => setShowAssignModal(false)}
                className="px-4 py-2 text-zinc-500 hover:text-white text-xs font-bold uppercase tracking-wider"
              >
                Cancel
              </button>
              <button
                onClick={handleAssignSelected}
                disabled={selectedTemplates.length === 0}
                className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider disabled:opacity-50"
              >
                Assign ({selectedTemplates.length})
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
