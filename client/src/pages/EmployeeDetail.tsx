import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getAccessToken, provisioning, employees as employeesApi } from '../api/client';
import type { EmployeeGoogleWorkspaceProvisioningStatus, EmployeeSlackProvisioningStatus, ProvisioningRunStatus, EmployeeIncidentItem } from '../types';
import { useAuth } from '../context/AuthContext';
import { useIsLightMode } from '../hooks/useIsLightMode';
import { leaveApi, LEAVE_TYPES } from '../api/leave';
import type { LeaveRequestAdmin } from '../api/leave';
import {
  ArrowLeft, Mail, Phone, MapPin, Calendar, Users, CheckCircle, Clock, FileText,
  Laptop, GraduationCap, Settings, Plus, X, AlertTriangle, SkipForward, RotateCcw,
  Pencil, DollarSign, Briefcase, Save, ChevronRight, Shield
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

const LT = {
  pageBg: 'bg-stone-300',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  card: 'bg-stone-100 border border-stone-200 rounded-2xl',
  innerEl: 'bg-stone-200/60 rounded-xl border border-stone-200',
  inputCls: 'bg-white border border-stone-300 text-zinc-900 text-sm rounded-xl focus:outline-none focus:border-stone-400 placeholder:text-stone-400 transition-colors',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 text-stone-500 hover:text-zinc-900 hover:border-stone-400',
  modalBg: 'bg-stone-100 border border-stone-200 shadow-2xl rounded-2xl',
  divide: 'divide-stone-200',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  innerEl: 'bg-zinc-900/40 rounded-xl border border-white/10',
  inputCls: 'bg-zinc-800 border border-white/10 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-white/20 placeholder:text-zinc-600 transition-colors',
  btnPrimary: 'bg-zinc-100 text-zinc-900 hover:bg-white',
  btnSecondary: 'border border-white/10 text-zinc-500 hover:text-zinc-100 hover:border-white/20',
  modalBg: 'bg-zinc-900 border border-white/10 shadow-2xl rounded-2xl',
  divide: 'divide-white/10',
} as const;

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
  employment_status: string | null;
  status_reason: string | null;
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

interface LeaveProgram {
  program: string;
  label: string;
  eligible: boolean;
  paid: boolean;
  max_weeks: number | null;
  wage_replacement_pct: number | null;
  job_protection: boolean;
  reasons: string[];
  notes: string | null;
}

interface LeaveProtection {
  fmla_protected_weeks: number;
  state_protected_weeks: number;
  total_protected_weeks: number;
  weeks_used: number;
  weeks_remaining: number;
  qualifying_state_programs: string[];
}

interface LeaveEligibilityData {
  fmla: { eligible: boolean; reasons: string[]; months_employed: number | null; hours_worked_12mo: number; company_employee_count: number };
  state_programs: { state: string | null; programs: LeaveProgram[]; message?: string };
  checked_at: string;
  protection: LeaveProtection;
}

const CATEGORIES = [
  { value: 'documents', label: 'Documents', icon: FileText, color: 'text-blue-400', bgColor: 'bg-blue-500/10' },
  { value: 'equipment', label: 'Equipment', icon: Laptop, color: 'text-purple-400', bgColor: 'bg-purple-500/10' },
  { value: 'training', label: 'Training', icon: GraduationCap, color: 'text-amber-400', bgColor: 'bg-amber-500/10' },
  { value: 'admin', label: 'Admin', icon: Settings, color: 'text-zinc-400', bgColor: 'bg-zinc-500/10' },
  { value: 'return_to_work', label: 'Return to Work', icon: RotateCcw, color: 'text-emerald-400', bgColor: 'bg-emerald-500/10' },
];

function provisioningStatusBadge(status: string | null | undefined, isLight: boolean): string {
  if (status === 'connected' || status === 'completed' || status === 'active') {
    return isLight ? 'bg-emerald-50 text-emerald-700 border border-emerald-300' : 'bg-emerald-900/30 text-emerald-300 border border-emerald-600/30';
  }
  if (status === 'failed' || status === 'error') {
    return isLight ? 'bg-red-50 text-red-700 border border-red-300' : 'bg-red-900/30 text-red-300 border border-red-600/30';
  }
  if (status === 'needs_action' || status === 'running' || status === 'pending' || status === 'disconnected') {
    return isLight ? 'bg-amber-50 text-amber-700 border border-amber-300' : 'bg-amber-900/30 text-amber-300 border border-amber-600/30';
  }
  return isLight ? 'bg-stone-200 text-stone-600 border border-stone-300' : 'bg-zinc-800 text-zinc-300 border border-zinc-700';
}

export default function EmployeeDetail() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const { employeeId } = useParams<{ employeeId: string }>();
  const navigate = useNavigate();
  const { hasFeature } = useAuth();
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
  const [incidents, setIncidents] = useState<EmployeeIncidentItem[]>([]);

  // Leave state
  const [leaveEligibility, setLeaveEligibility] = useState<LeaveEligibilityData | null>(null);
  const [leaveHistory, setLeaveHistory] = useState<LeaveRequestAdmin[]>([]);
  const [leaveLoading, setLeaveLoading] = useState(false);
  const [showPlaceOnLeaveModal, setShowPlaceOnLeaveModal] = useState(false);
  const [showExtendLeaveModal, setShowExtendLeaveModal] = useState(false);
  const [showReturnCheckinModal, setShowReturnCheckinModal] = useState(false);
  const [leaveActionLoading, setLeaveActionLoading] = useState(false);
  const [placeOnLeaveForm, setPlaceOnLeaveForm] = useState({
    leave_type: 'medical' as typeof LEAVE_TYPES[number],
    start_date: '',
    end_date: '',
    expected_return_date: '',
    reason: '',
  });
  const [extendLeaveForm, setExtendLeaveForm] = useState({
    end_date: '',
    expected_return_date: '',
    notes: '',
  });
  const [returnCheckinForm, setReturnCheckinForm] = useState({
    returning: true,
    action: 'extend' as 'extend' | 'new_leave',
    new_end_date: '',
    new_expected_return_date: '',
    new_leave_type: 'medical' as typeof LEAVE_TYPES[number],
    notes: '',
  });

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

  // Fetch incidents related to this employee
  useEffect(() => {
    if (!employeeId || !hasFeature('incidents')) return;
    employeesApi.getIncidents(employeeId).then(setIncidents).catch(() => setIncidents([]));
  }, [employeeId]);

  // Fetch leave data
  const fetchLeaveData = async () => {
    if (!employeeId) return;
    setLeaveLoading(true);
    try {
      const [eligibility, history] = await Promise.all([
        leaveApi.getEmployeeEligibility(employeeId),
        leaveApi.getEmployeeLeaveHistory(employeeId),
      ]);
      setLeaveEligibility(eligibility as unknown as LeaveEligibilityData);
      setLeaveHistory(history);
    } catch {
      // non-critical
    } finally {
      setLeaveLoading(false);
    }
  };

  useEffect(() => {
    fetchLeaveData();
  }, [employeeId]);

  const activeLeaverequest = leaveHistory.find(
    (l) => l.status === 'active' || l.status === 'approved',
  );

  const handlePlaceOnLeave = async () => {
    if (!employeeId || !placeOnLeaveForm.start_date) return;
    setLeaveActionLoading(true);
    try {
      await leaveApi.placeOnLeave(employeeId, {
        leave_type: placeOnLeaveForm.leave_type,
        start_date: placeOnLeaveForm.start_date,
        end_date: placeOnLeaveForm.end_date || undefined,
        expected_return_date: placeOnLeaveForm.expected_return_date || undefined,
        reason: placeOnLeaveForm.reason || undefined,
      });
      setShowPlaceOnLeaveModal(false);
      setPlaceOnLeaveForm({ leave_type: 'medical', start_date: '', end_date: '', expected_return_date: '', reason: '' });
      await Promise.all([fetchEmployee(), fetchLeaveData()]);
      setStatusMessage('Employee placed on leave.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to place on leave');
    } finally {
      setLeaveActionLoading(false);
    }
  };

  const handleExtendLeave = async () => {
    if (!activeLeaverequest || !extendLeaveForm.end_date) return;
    setLeaveActionLoading(true);
    try {
      await leaveApi.extendLeave(activeLeaverequest.id, {
        end_date: extendLeaveForm.end_date,
        expected_return_date: extendLeaveForm.expected_return_date || undefined,
        notes: extendLeaveForm.notes || undefined,
      });
      setShowExtendLeaveModal(false);
      setExtendLeaveForm({ end_date: '', expected_return_date: '', notes: '' });
      await fetchLeaveData();
      setStatusMessage('Leave extended.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to extend leave');
    } finally {
      setLeaveActionLoading(false);
    }
  };

  const handleReturnCheckin = async () => {
    if (!activeLeaverequest) return;
    setLeaveActionLoading(true);
    try {
      await leaveApi.returnCheckin(activeLeaverequest.id, {
        returning: returnCheckinForm.returning,
        action: returnCheckinForm.returning ? undefined : returnCheckinForm.action,
        new_end_date: returnCheckinForm.new_end_date || undefined,
        new_expected_return_date: returnCheckinForm.new_expected_return_date || undefined,
        new_leave_type: returnCheckinForm.returning ? undefined : returnCheckinForm.new_leave_type,
        notes: returnCheckinForm.notes || undefined,
      });
      setShowReturnCheckinModal(false);
      setReturnCheckinForm({ returning: true, action: 'extend', new_end_date: '', new_expected_return_date: '', new_leave_type: 'medical', notes: '' });
      await Promise.all([fetchEmployee(), fetchLeaveData()]);
      setStatusMessage(returnCheckinForm.returning ? 'Employee marked as returned.' : 'Leave updated.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to process check-in');
    } finally {
      setLeaveActionLoading(false);
    }
  };

  const handleMarkLeaveComplete = async () => {
    if (!activeLeaverequest) return;
    setLeaveActionLoading(true);
    try {
      await leaveApi.updateAdminRequest(activeLeaverequest.id, { action: 'complete' });
      await Promise.all([fetchEmployee(), fetchLeaveData()]);
      setStatusMessage('Leave marked as complete.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to complete leave');
    } finally {
      setLeaveActionLoading(false);
    }
  };

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

  const wrapperClass = `-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`;

  return (
    <div className={wrapperClass}>
    <div className={`max-w-5xl mx-auto space-y-8 animate-in fade-in duration-500`}>
      {/* Header */}
      <div className={`flex items-center gap-4 border-b ${t.border} pb-8`}>
        <button
          onClick={() => navigate('/app/matcha/employees')}
          className={`p-2 ${t.textMuted} hover:${t.textMain} hover:${isLight ? 'bg-stone-200' : 'bg-zinc-800'} rounded transition-colors`}
        >
          <ArrowLeft size={20} />
        </button>
        <div className="flex-1">
          <h1 className={`text-4xl font-bold tracking-tighter ${t.textMain} uppercase`}>
            {employee.first_name} {employee.last_name}
          </h1>
          <div className="flex items-center gap-3 mt-1">
            {employee.job_title && <span className={`text-sm ${t.textDim}`}>{employee.job_title}</span>}
            {employee.job_title && employee.department && <span className={t.textFaint}>·</span>}
            {employee.department && <span className={`text-sm ${t.textDim}`}>{employee.department}</span>}
            {!employee.job_title && !employee.department && <span className={`text-xs ${t.textMuted} font-mono`}>{displayWorkEmail}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {employee.termination_date ? (
            <span className={`px-3 py-1 ${isLight ? 'bg-stone-200 text-stone-600 border border-stone-300' : 'bg-zinc-800 text-zinc-400 border border-zinc-700'} text-[10px] font-bold uppercase tracking-wider rounded`}>
              Terminated
            </span>
          ) : employee.employment_status === 'on_leave' ? (
            <span className={`px-3 py-1 ${isLight ? 'bg-blue-50 text-blue-700 border border-blue-300' : 'bg-blue-900/30 text-blue-400 border border-blue-500/20'} text-[10px] font-bold uppercase tracking-wider rounded`}>
              On Leave
            </span>
          ) : employee.user_id ? (
            <span className={`px-3 py-1 ${isLight ? 'bg-emerald-50 text-emerald-700 border border-emerald-300' : 'bg-emerald-900/30 text-emerald-400 border border-emerald-500/20'} text-[10px] font-bold uppercase tracking-wider rounded`}>
              Active
            </span>
          ) : (
            <span className={`px-3 py-1 ${isLight ? 'bg-amber-50 text-amber-700 border border-amber-300' : 'bg-amber-900/30 text-amber-400 border border-amber-500/20'} text-[10px] font-bold uppercase tracking-wider rounded`}>
              {employee.invitation_status === 'pending' ? 'Invited' : 'Not Invited'}
            </span>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className={`${isLight ? 'bg-red-50 border-red-300' : 'bg-red-500/10 border-red-500/20'} border rounded p-4 flex items-center justify-between`}>
          <div className="flex items-center gap-3">
            <AlertTriangle className={isLight ? 'text-red-700' : 'text-red-400'} size={16} />
            <p className={`text-sm ${isLight ? 'text-red-700' : 'text-red-400'} font-mono`}>{error}</p>
          </div>
          <button onClick={() => setError(null)} className={`text-xs ${isLight ? 'text-red-700' : 'text-red-400'} hover:opacity-80 uppercase tracking-wider font-bold`}>
            Dismiss
          </button>
        </div>
      )}
      {statusMessage && (
        <div className={`${isLight ? 'bg-emerald-50 border-emerald-300' : 'bg-emerald-500/10 border-emerald-500/20'} border rounded p-4 flex items-center justify-between`}>
          <p className={`text-sm ${isLight ? 'text-emerald-700' : 'text-emerald-300'} font-mono`}>{statusMessage}</p>
          <button
            onClick={() => setStatusMessage(null)}
            className={`text-xs ${isLight ? 'text-emerald-700' : 'text-emerald-300'} hover:opacity-80 uppercase tracking-wider font-bold`}
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Employee Info */}
        <div className="lg:col-span-1 space-y-6">
          <div className={`${t.card} p-6 space-y-4 shadow-sm`}>
            <div className="flex items-center justify-between">
              <h2 className={`text-[10px] font-bold uppercase tracking-wider ${t.textMuted}`}>Contact Info</h2>
              {!editing && (
                <button onClick={startEditing} className={`p-1.5 ${t.textMuted} hover:${t.textMain} hover:${isLight ? 'bg-stone-200' : 'bg-zinc-800'} rounded transition-colors`} title="Edit">
                  <Pencil size={14} />
                </button>
              )}
            </div>
            {editing && editFields ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>First Name</label>
                    <input value={editFields.first_name} onChange={(e) => setEditFields({ ...editFields, first_name: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`} />
                  </div>
                  <div>
                    <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Last Name</label>
                    <input value={editFields.last_name} onChange={(e) => setEditFields({ ...editFields, last_name: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`} />
                  </div>
                </div>
                <div>
                  <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Work Email</label>
                  <input type="email" value={editFields.work_email} onChange={(e) => setEditFields({ ...editFields, work_email: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`} />
                </div>
                <div>
                  <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Personal Email</label>
                  <input type="email" value={editFields.personal_email} onChange={(e) => setEditFields({ ...editFields, personal_email: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`} placeholder="Optional" />
                </div>
                <div>
                  <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Phone</label>
                  <input value={editFields.phone} onChange={(e) => setEditFields({ ...editFields, phone: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`} placeholder="Optional" />
                </div>
                <div>
                  <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Address</label>
                  <input value={editFields.address} onChange={(e) => setEditFields({ ...editFields, address: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`} placeholder="Optional" />
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <Mail size={16} className={t.textFaint} />
                  <span className={`text-sm ${t.textMain}`}>{displayWorkEmail}</span>
                </div>
                {employee.personal_email && (
                  <div className="flex items-center gap-3">
                    <Mail size={16} className={t.textFaint} />
                    <span className={`text-sm ${t.textDim}`}>Personal: {employee.personal_email}</span>
                  </div>
                )}
                {employee.phone && (
                  <div className="flex items-center gap-3">
                    <Phone size={16} className={t.textFaint} />
                    <span className={`text-sm ${t.textMain}`}>{employee.phone}</span>
                  </div>
                )}
                {employee.address && (
                  <div className="flex items-center gap-3">
                    <MapPin size={16} className={t.textFaint} />
                    <span className={`text-sm ${t.textMain}`}>{employee.address}</span>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className={`${t.card} p-6 space-y-4 shadow-sm`}>
            <h2 className={`text-[10px] font-bold uppercase tracking-wider ${t.textMuted}`}>Employment</h2>
            {editing && editFields ? (
              <div className="space-y-3">
                <div>
                  <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Job Title</label>
                  <input value={editFields.job_title} onChange={(e) => setEditFields({ ...editFields, job_title: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`} placeholder="e.g. Software Engineer" />
                </div>
                <div>
                  <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Department</label>
                  <input value={editFields.department} onChange={(e) => setEditFields({ ...editFields, department: e.target.value })} list="dept-options" className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`} placeholder="e.g. Engineering" />
                  <datalist id="dept-options">
                    {departments.map((d) => <option key={d} value={d} />)}
                  </datalist>
                </div>
                <div>
                  <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Employment Type</label>
                  <select value={editFields.employment_type} onChange={(e) => setEditFields({ ...editFields, employment_type: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`}>
                    <option value="">Select...</option>
                    <option value="full_time">Full Time</option>
                    <option value="part_time">Part Time</option>
                    <option value="contract">Contract</option>
                    <option value="intern">Intern</option>
                  </select>
                </div>
                <div>
                  <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Start Date</label>
                  <input type="date" value={editFields.start_date} onChange={(e) => setEditFields({ ...editFields, start_date: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Work State</label>
                    <input value={editFields.work_state} onChange={(e) => setEditFields({ ...editFields, work_state: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`} placeholder="e.g. CA" />
                  </div>
                  <div>
                    <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Work City</label>
                    <input value={editFields.work_city} onChange={(e) => setEditFields({ ...editFields, work_city: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`} placeholder="e.g. San Francisco" />
                  </div>
                </div>
                <div>
                  <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Manager</label>
                  <select
                    value={editFields.manager_id}
                    onChange={(e) => setEditFields({ ...editFields, manager_id: e.target.value })}
                    className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`}
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
                  <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Pay Classification</label>
                  <select value={editFields.pay_classification} onChange={(e) => setEditFields({ ...editFields, pay_classification: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`}>
                    <option value="">Select...</option>
                    <option value="exempt">Exempt (Salary)</option>
                    <option value="hourly">Hourly</option>
                  </select>
                </div>
                {editFields.pay_classification && (
                  <div>
                    <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>
                      {editFields.pay_classification === 'hourly' ? 'Hourly Rate ($)' : 'Annual Salary ($)'}
                    </label>
                    <input type="number" step="0.01" min="0" value={editFields.pay_rate} onChange={(e) => setEditFields({ ...editFields, pay_rate: e.target.value })} className={`w-full mt-1 px-3 py-1.5 ${t.inputCls}`} placeholder={editFields.pay_classification === 'hourly' ? '18.50' : '65000'} />
                  </div>
                )}
                <div className="flex items-center gap-2 pt-2">
                  <button onClick={handleSave} disabled={saving} className={`flex items-center gap-1.5 px-4 py-1.5 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl disabled:opacity-50 transition-colors`}>
                    <Save size={12} />
                    {saving ? 'Saving...' : 'Save Changes'}
                  </button>
                  <button onClick={cancelEditing} disabled={saving} className={`px-4 py-1.5 ${t.textMuted} hover:${t.textMain} text-[10px] font-bold uppercase tracking-wider transition-colors`}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {employee.job_title && (
                  <div className="flex items-center gap-3">
                    <Briefcase size={16} className={t.textFaint} />
                    <span className={`text-sm ${t.textDim}`}>
                      Title: <span className={t.textMain}>{employee.job_title}</span>
                    </span>
                  </div>
                )}
                {employee.department && (
                  <div className="flex items-center gap-3">
                    <Users size={16} className={t.textFaint} />
                    <span className={`text-sm ${t.textDim}`}>
                      Department: <span className={t.textMain}>{employee.department}</span>
                    </span>
                  </div>
                )}
                {employee.start_date && (
                  <div className="flex items-center gap-3">
                    <Calendar size={16} className={t.textFaint} />
                    <span className={`text-sm ${t.textDim}`}>
                      Started: <span className={t.textMain}>{employee.start_date}</span>
                    </span>
                  </div>
                )}
                {employee.employment_type && (
                  <div className="flex items-center gap-3">
                    <Briefcase size={16} className={t.textFaint} />
                    <span className={`text-sm ${t.textDim}`}>
                      Type: <span className={t.textMain}>{employee.employment_type.replace('_', ' ')}</span>
                    </span>
                  </div>
                )}
                <div className="flex items-center gap-3">
                  <MapPin size={16} className={t.textFaint} />
                  <span className={`text-sm ${t.textDim}`}>
                    Location: <span className={t.textMain}>{employee.work_city && employee.work_state ? `${employee.work_city}, ${employee.work_state}` : employee.work_state || employee.work_city || '—'}</span>
                  </span>
                </div>
                {employee.pay_classification && (
                  <div className="flex items-center gap-3">
                    <DollarSign size={16} className={t.textFaint} />
                    <span className={`text-sm ${t.textDim}`}>
                      Pay: <span className={t.textMain}>
                        {employee.pay_classification === 'hourly' ? `$${employee.pay_rate?.toFixed(2) || '—'}/hr` : `$${employee.pay_rate?.toLocaleString() || '—'}/yr`}
                        {' '}({employee.pay_classification})
                      </span>
                    </span>
                  </div>
                )}
                {employee.manager_name && (
                  <div className="flex items-center gap-3">
                    <Users size={16} className={t.textFaint} />
                    <span className={`text-sm ${t.textDim}`}>
                      Manager: <span className={`${t.textMain} cursor-pointer hover:underline`} onClick={() => employee.manager_id && navigate(`/app/matcha/employees/${employee.manager_id}`)}>{employee.manager_name}</span>
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Direct Reports */}
          <div className={`${t.card} p-6 space-y-4 shadow-sm`}>
            <h2 className={`text-[10px] font-bold uppercase tracking-wider ${t.textMuted}`}>Direct Reports</h2>
            {directReports.length === 0 ? (
              <p className={`text-xs ${t.textFaint} font-mono uppercase`}>No direct reports</p>
            ) : (
              <div className="space-y-2">
                {directReports.map((dr) => (
                  <div
                    key={dr.id}
                    onClick={() => navigate(`/app/matcha/employees/${dr.id}`)}
                    className={`flex items-center gap-3 p-2 rounded ${isLight ? 'hover:bg-stone-200' : 'hover:bg-white/5'} cursor-pointer transition-colors`}
                  >
                    <div className={`h-7 w-7 rounded-lg ${isLight ? 'bg-stone-200 text-stone-600' : 'bg-zinc-800 text-zinc-400'} border ${t.border} flex items-center justify-center text-[10px] font-bold`}>
                      {dr.first_name[0]}{dr.last_name[0]}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className={`text-sm ${t.textMain} truncate`}>{dr.first_name} {dr.last_name}</p>
                    </div>
                    <ChevronRight size={14} className={t.textFaint} />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Incident Reports */}
          {hasFeature('incidents') && (
          <div className={`${t.card} p-6 space-y-4 shadow-sm`}>
            <div className="flex items-center gap-2">
              <AlertTriangle size={14} className={t.textMuted} />
              <h2 className={`text-[10px] font-bold uppercase tracking-wider ${t.textMuted}`}>Incident Reports</h2>
              {incidents.length > 0 && (
                <span className={`ml-auto px-1.5 py-0.5 text-[10px] font-bold tabular-nums ${isLight ? 'bg-stone-200 text-stone-600' : 'bg-zinc-800 text-zinc-300'} border ${t.border} rounded`}>
                  {incidents.length}
                </span>
              )}
            </div>
            {incidents.length === 0 ? (
              <p className={`text-xs ${t.textFaint} font-mono uppercase`}>No incidents on record</p>
            ) : (
              <div className="space-y-2">
                {incidents.map((inc) => {
                  const sevDot: Record<string, string> = { critical: isLight ? 'bg-red-500' : 'bg-zinc-100', high: isLight ? 'bg-red-400' : 'bg-zinc-400', medium: isLight ? 'bg-amber-500' : 'bg-zinc-500', low: isLight ? 'bg-stone-400' : 'bg-zinc-600' };
                  const statusColor: Record<string, string> = { reported: t.textMain, investigating: t.textDim, action_required: t.textMain, resolved: t.textMuted, closed: t.textFaint };
                  const typeLabel: Record<string, string> = { safety: 'Safety', behavioral: 'Behavioral', property: 'Property', near_miss: 'Near Miss', other: 'Other' };
                  const roleLabel: Record<string, string> = { reporter: 'Reporter', involved: 'Involved', witness: 'Witness' };
                  return (
                    <div
                      key={inc.id}
                      onClick={() => navigate(`/app/ir/incidents/${inc.id}`)}
                      className={`p-3 rounded ${isLight ? 'bg-white' : 'bg-zinc-950/50'} border ${t.border} hover:border-zinc-400/50 cursor-pointer transition-colors group`}
                    >
                      <div className="flex items-center gap-2 mb-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${sevDot[inc.severity] || 'bg-zinc-600'}`} />
                        <span className={`text-[10px] ${t.textFaint} font-mono`}>
                          #IR-{String(inc.incident_number).padStart(4, '0')}
                        </span>
                        <span className={`ml-auto text-[10px] uppercase tracking-wider font-bold ${statusColor[inc.status] || t.textMuted}`}>
                          {inc.status.replace('_', ' ')}
                        </span>
                      </div>
                      <p className={`text-xs ${t.textDim} group-hover:${t.textMain} truncate transition-colors font-medium`}>
                        {inc.title}
                      </p>
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        <span className={`px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${isLight ? 'bg-stone-100 text-stone-500' : 'bg-zinc-800 text-zinc-400'} border ${t.border} rounded`}>
                          {typeLabel[inc.incident_type] || inc.incident_type}
                        </span>
                        <span className={`px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${isLight ? 'bg-stone-100 text-stone-500' : 'bg-zinc-800 text-zinc-400'} border ${t.border} rounded`}>
                          {roleLabel[inc.role] || inc.role}
                        </span>
                        <span className={`ml-auto text-[10px] ${t.textFaint} font-mono`}>
                          {new Date(inc.occurred_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
          )}

          {/* Leave of Absence */}
          <div className={`${t.card} p-6 space-y-4 shadow-sm`}>
            <div className="flex items-center gap-2">
              <Shield size={14} className={t.textMuted} />
              <h2 className={`text-[10px] font-bold uppercase tracking-wider ${t.textMuted}`}>Leave of Absence</h2>
            </div>

            {leaveLoading ? (
              <p className={`text-xs ${t.textFaint} font-mono uppercase animate-pulse`}>Loading...</p>
            ) : (
              <>
                {/* Current Leave Status */}
                {employee.employment_status === 'on_leave' && activeLeaverequest ? (
                  <div className={`p-3 rounded-xl ${isLight ? 'bg-blue-50 border border-blue-200' : 'bg-blue-900/20 border border-blue-500/20'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className={`text-[10px] font-bold uppercase tracking-wider ${isLight ? 'text-blue-700' : 'text-blue-400'}`}>
                        Active Leave
                      </span>
                      <span className={`text-[10px] font-mono ${isLight ? 'text-blue-600' : 'text-blue-300'}`}>
                        {activeLeaverequest.leave_type.replace(/_/g, ' ').toUpperCase()}
                      </span>
                    </div>
                    <p className={`text-xs ${isLight ? 'text-blue-800' : 'text-blue-200'} mb-1`}>
                      {activeLeaverequest.start_date} → {activeLeaverequest.end_date || 'Open-ended'}
                    </p>
                    {activeLeaverequest.expected_return_date && (
                      <p className={`text-[10px] ${isLight ? 'text-blue-600' : 'text-blue-400'}`}>
                        Expected return: {activeLeaverequest.expected_return_date}
                      </p>
                    )}
                    {leaveEligibility?.protection && (
                      <p className={`text-[10px] mt-1 ${isLight ? 'text-blue-600' : 'text-blue-400'}`}>
                        <Shield size={10} className="inline mr-1" />
                        {leaveEligibility.protection.weeks_remaining?.toFixed(1)} protected weeks remaining
                      </p>
                    )}
                    <div className="flex flex-wrap gap-2 mt-3">
                      <button
                        onClick={() => setShowExtendLeaveModal(true)}
                        className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded ${isLight ? 'bg-blue-100 text-blue-700 hover:bg-blue-200' : 'bg-blue-900/40 text-blue-300 hover:bg-blue-900/60'} transition-colors`}
                      >
                        Extend
                      </button>
                      <button
                        onClick={() => setShowReturnCheckinModal(true)}
                        className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded ${isLight ? 'bg-blue-100 text-blue-700 hover:bg-blue-200' : 'bg-blue-900/40 text-blue-300 hover:bg-blue-900/60'} transition-colors`}
                      >
                        Return Check-in
                      </button>
                      <button
                        onClick={handleMarkLeaveComplete}
                        disabled={leaveActionLoading}
                        className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded ${isLight ? 'bg-stone-200 text-stone-600 hover:bg-stone-300' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'} disabled:opacity-50 transition-colors`}
                      >
                        Mark Complete
                      </button>
                    </div>
                  </div>
                ) : !employee.termination_date ? (
                  <button
                    onClick={() => setShowPlaceOnLeaveModal(true)}
                    className={`flex items-center gap-2 px-3 py-2 w-full text-left text-[10px] font-bold uppercase tracking-wider rounded-xl border border-dashed ${t.border} ${t.textMuted} hover:${t.textMain} transition-colors`}
                  >
                    <Plus size={12} />
                    Place on Leave
                  </button>
                ) : null}

                {/* Eligibility Snapshot */}
                {leaveEligibility && (
                  <div className="space-y-1.5">
                    <p className={`text-[9px] font-bold uppercase tracking-wider ${t.textFaint}`}>Eligibility</p>
                    {/* FMLA */}
                    {(() => {
                      const fmla = leaveEligibility.fmla;
                      if (!fmla) return null;
                      return (
                        <div className="flex items-center justify-between">
                          <span className={`text-xs ${t.textDim}`}>FMLA</span>
                          <span className={`px-1.5 py-0.5 text-[9px] font-bold uppercase rounded ${fmla.eligible ? (isLight ? 'bg-emerald-100 text-emerald-700' : 'bg-emerald-900/30 text-emerald-400') : (isLight ? 'bg-stone-200 text-stone-500' : 'bg-zinc-800 text-zinc-500')}`}>
                            {fmla.eligible ? 'Eligible' : 'Not Eligible'}
                          </span>
                        </div>
                      );
                    })()}
                    {/* State programs */}
                    {(leaveEligibility.state_programs?.programs || []).map((prog) => (
                      <div key={prog.program} className="flex items-center justify-between">
                        <span className={`text-xs ${t.textDim} truncate mr-2`}>{prog.label}</span>
                        <span className={`flex-shrink-0 px-1.5 py-0.5 text-[9px] font-bold uppercase rounded ${prog.eligible ? (isLight ? 'bg-emerald-100 text-emerald-700' : 'bg-emerald-900/30 text-emerald-400') : (isLight ? 'bg-stone-200 text-stone-500' : 'bg-zinc-800 text-zinc-500')}`}>
                          {prog.eligible ? 'Eligible' : 'Not Yet'}
                        </span>
                      </div>
                    ))}
                    {!leaveEligibility.state_programs?.programs?.length && (
                      <p className={`text-xs ${t.textFaint}`}>No state programs for this work state</p>
                    )}
                  </div>
                )}

                {/* Leave History */}
                {leaveHistory.length > 0 && (
                  <div className="space-y-1.5">
                    <p className={`text-[9px] font-bold uppercase tracking-wider ${t.textFaint}`}>History</p>
                    {leaveHistory.slice(0, 5).map((leave) => {
                      const statusColors: Record<string, string> = {
                        approved: isLight ? 'text-emerald-700' : 'text-emerald-400',
                        active: isLight ? 'text-blue-700' : 'text-blue-400',
                        completed: isLight ? 'text-stone-500' : 'text-zinc-500',
                        denied: isLight ? 'text-red-600' : 'text-red-400',
                        cancelled: isLight ? 'text-stone-400' : 'text-zinc-600',
                        requested: isLight ? 'text-amber-700' : 'text-amber-400',
                      };
                      return (
                        <div key={leave.id} className={`flex items-center justify-between text-xs`}>
                          <div className="flex-1 min-w-0 mr-2">
                            <span className={t.textDim}>{leave.leave_type.replace(/_/g, ' ')}</span>
                            <span className={`ml-1.5 text-[10px] ${t.textFaint} font-mono`}>{leave.start_date}</span>
                          </div>
                          <span className={`text-[9px] font-bold uppercase ${statusColors[leave.status] || t.textFaint}`}>
                            {leave.status}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </div>

          <div className={`${t.card} p-6 space-y-4 shadow-sm`}>
            <div className="flex items-center justify-between gap-2">
              <h2 className={`text-[10px] font-bold uppercase tracking-wider ${t.textMuted}`}>Google Workspace</h2>
              <button
                onClick={() => navigate('/app/matcha/google-workspace')}
                className={`text-[10px] uppercase tracking-wider ${t.textMuted} hover:${t.textMain}`}
              >
                Settings
              </button>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <span className={`text-xs ${t.textMuted} uppercase tracking-wider`}>Connection</span>
                <span className={`px-2 py-1 text-[10px] uppercase tracking-wider rounded ${provisioningStatusBadge(googleConnection?.status, isLight)}`}>
                  {googleConnection?.status || 'disconnected'}
                </span>
              </div>

              {provisioningLoading && (
                <p className={`text-xs ${t.textMuted} font-mono uppercase tracking-wider`}>Loading provisioning status...</p>
              )}

              {googleConnection?.last_error && (
                <p className={`text-xs ${isLight ? 'text-red-700' : 'text-red-300'}`}>Last error: {googleConnection.last_error}</p>
              )}

              {provisioningStatus?.external_identity ? (
                <div className={`space-y-1 border ${t.border} ${isLight ? 'bg-white' : 'bg-zinc-950/50'} p-3 rounded-xl`}>
                  <p className={`text-[10px] ${t.textMuted} uppercase tracking-wider`}>External Identity</p>
                  <p className={`text-xs ${t.textMain}`}>{provisioningStatus.external_identity.external_email || 'No external email returned'}</p>
                  <p className={`text-[10px] ${t.textMuted}`}>
                    Status: <span className={`${t.textDim} uppercase`}>{provisioningStatus.external_identity.status}</span>
                  </p>
                </div>
              ) : (
                <p className={`text-xs ${t.textMuted}`}>No Google account provisioned yet.</p>
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
                  className={`px-4 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl disabled:opacity-50 transition-colors`}
                >
                  {provisioningActionLoading ? 'Working...' : googleConnection?.connected ? 'Provision Now' : 'Connect Google'}
                </button>

                {latestRetryableRun && (
                  <button
                    onClick={() => handleRetryProvisioningRun(latestRetryableRun.run_id)}
                    disabled={provisioningActionLoading}
                    className={`px-4 py-2 ${t.btnSecondary} text-[10px] font-bold uppercase tracking-wider rounded-xl disabled:opacity-50 transition-colors`}
                  >
                    Retry Last Run
                  </button>
                )}
              </div>

              {recentProvisioningRuns.length > 0 && (
                <div className="space-y-2">
                  <p className={`text-[10px] ${t.textMuted} uppercase tracking-wider`}>Recent Runs</p>
                  {recentProvisioningRuns.map((run) => (
                    <div key={run.run_id} className={`border ${t.border} ${isLight ? 'bg-white' : 'bg-zinc-950/50'} p-3 rounded-xl`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className={`text-[10px] ${t.textFaint}`}>
                          {new Date(run.created_at).toLocaleString()}
                        </span>
                        <span className={`px-2 py-0.5 text-[10px] uppercase tracking-wider rounded ${provisioningStatusBadge(run.status, isLight)}`}>
                          {run.status}
                        </span>
                      </div>
                      {run.last_error && (
                        <p className={`text-[10px] ${isLight ? 'text-red-700' : 'text-red-300'} mt-1`}>{run.last_error}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Slack Provisioning Card */}
        <div className={`${t.card} p-6 space-y-4 shadow-sm`}>
          <div className="flex items-center justify-between gap-2">
            <h2 className={`text-[10px] font-bold uppercase tracking-wider ${t.textMuted}`}>Slack</h2>
            <button
              onClick={() => navigate('/app/matcha/slack-provisioning')}
              className={`text-[10px] uppercase tracking-wider ${t.textMuted} hover:${t.textMain}`}
            >
              Settings
            </button>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className={`text-xs ${t.textMuted} uppercase tracking-wider`}>Connection</span>
              <span className={`px-2 py-1 text-[10px] uppercase tracking-wider rounded ${provisioningStatusBadge(slackConnection?.status, isLight)}`}>
                {slackConnection?.status || 'disconnected'}
              </span>
            </div>

            {slackConnection?.slack_team_name && (
              <p className={`text-xs ${t.textDim}`}>
                Workspace: <span className={t.textMain}>{slackConnection.slack_team_name}</span>
              </p>
            )}

            {slackProvisioningStatus?.external_identity ? (
              <div className={`space-y-1 border ${t.border} ${isLight ? 'bg-white' : 'bg-zinc-950/50'} p-3 rounded-xl`}>
                <p className={`text-[10px] ${t.textMuted} uppercase tracking-wider`}>External Identity</p>
                <p className={`text-xs ${t.textMain}`}>{slackProvisioningStatus.external_identity.external_email || 'No email returned'}</p>
                <p className={`text-[10px] ${t.textMuted}`}>
                  Slack ID: <span className={t.textDim}>{slackProvisioningStatus.external_identity.external_user_id || '—'}</span>
                </p>
                <p className={`text-[10px] ${t.textMuted}`}>
                  Status: <span className={`${t.textDim} uppercase`}>{slackProvisioningStatus.external_identity.status}</span>
                </p>
              </div>
            ) : (
              <p className={`text-xs ${t.textMuted}`}>No Slack account provisioned yet.</p>
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
                className={`px-4 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl disabled:opacity-50 transition-colors`}
              >
                {slackActionLoading ? 'Working...' : slackConnection?.connected ? 'Provision Now' : 'Connect Slack'}
              </button>
            </div>

            {recentSlackRuns.length > 0 && (
              <div className="space-y-2">
                <p className={`text-[10px] ${t.textMuted} uppercase tracking-wider`}>Recent Runs</p>
                {recentSlackRuns.map((run) => {
                  const warningsRaw = run.steps?.[0]?.last_response?.warnings;
                  const warnings = Array.isArray(warningsRaw)
                    ? warningsRaw.filter((item): item is string => typeof item === 'string')
                    : [];

                  return (
                    <div key={run.run_id} className={`border ${t.border} ${isLight ? 'bg-white' : 'bg-zinc-950/50'} p-3 rounded-xl`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className={`text-[10px] ${t.textFaint}`}>
                          {new Date(run.created_at).toLocaleString()}
                        </span>
                        <span className={`px-2 py-0.5 text-[10px] uppercase tracking-wider rounded ${provisioningStatusBadge(run.status, isLight)}`}>
                          {run.status}
                        </span>
                      </div>
                      {run.last_error && (
                        <p className={`text-[10px] ${isLight ? 'text-red-700' : 'text-red-300'} mt-1`}>{run.last_error}</p>
                      )}
                      {warnings.length > 0 && (
                        <p className={`text-[10px] ${isLight ? 'text-amber-700' : 'text-amber-400'} mt-1`}>{warnings[0]}</p>
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
          <div className={`${t.card} p-6 shadow-sm`}>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-4">
              <h2 className={`text-[10px] font-bold uppercase tracking-wider ${t.textMuted}`}>Onboarding Progress</h2>
              <div className="flex flex-wrap items-center gap-4">
                <span className={`text-xs ${t.textDim}`}>
                  <span className={`${t.textMain} font-bold`}>{completedCount}</span> / {tasks.length} completed
                </span>
                {tasks.length === 0 && (
                  <button
                    onClick={handleAssignAll}
                    disabled={assigningAll}
                    className={`flex items-center gap-2 px-4 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-50`}
                  >
                    {assigningAll ? 'Assigning...' : 'Assign All Tasks'}
                  </button>
                )}
                {tasks.length > 0 && (
                  <button
                    onClick={() => setShowAssignModal(true)}
                    className={`flex items-center gap-1 px-3 py-1.5 ${t.btnSecondary} text-[10px] font-bold uppercase tracking-wider rounded-xl transition-colors`}
                  >
                    <Plus size={12} /> Add Task
                  </button>
                )}
              </div>
            </div>
            <div className={`w-full h-2 ${isLight ? 'bg-stone-200' : 'bg-zinc-800'} rounded overflow-hidden`}>
              <div
                className="h-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="flex items-center gap-6 mt-3 text-[10px] font-bold uppercase tracking-wider">
              <span className={`flex items-center gap-1.5 ${isLight ? 'text-emerald-700' : 'text-emerald-400'}`}>
                <span className="w-2 h-2 rounded-full bg-emerald-500" /> {completedCount} Completed
              </span>
              <span className={`flex items-center gap-1.5 ${isLight ? 'text-amber-700' : 'text-amber-400'}`}>
                <span className="w-2 h-2 rounded-full bg-amber-500" /> {pendingCount} Pending
              </span>
            </div>
          </div>

          {/* Tasks by Category */}
          {tasks.length === 0 ? (
            <div className={`text-center py-12 border-2 border-dashed ${t.border} ${isLight ? 'bg-white' : 'bg-white/5'} rounded-2xl`}>
              <CheckCircle size={32} className={`mx-auto ${t.textFaint} mb-4`} />
              <p className={`${t.textMuted} text-xs font-mono uppercase`}>No onboarding tasks assigned yet</p>
              <button
                onClick={handleAssignAll}
                disabled={assigningAll}
                className={`${t.textMain} text-[10px] font-bold uppercase tracking-wider mt-4 underline underline-offset-4 hover:opacity-80 transition-opacity`}
              >
                {assigningAll ? 'Assigning...' : 'Assign standard onboarding tasks'}
              </button>
            </div>
          ) : (
            CATEGORIES.map((cat) => {
              const categoryTasks = groupedTasks[cat.value] || [];
              if (categoryTasks.length === 0) return null;

              return (
                <div key={cat.value} className={`${t.card} overflow-hidden shadow-sm`}>
                  <div className={`flex items-center gap-2 px-6 py-4 border-b ${t.border} ${isLight ? 'bg-stone-200/40' : 'bg-white/5'}`}>
                    <cat.icon size={16} className={cat.color} />
                    <h3 className={`text-xs font-bold uppercase tracking-wider ${t.textMain}`}>{cat.label}</h3>
                    <span className={`text-[10px] ${t.textMuted} font-mono`}>
                      ({categoryTasks.filter((t) => t.status === 'completed').length}/{categoryTasks.length})
                    </span>
                  </div>
                  <div className={`divide-y ${t.divide}`}>
                    {categoryTasks.map((task) => (
                      <div key={task.id} className="px-6 py-4 flex items-center gap-4">
                        <div
                          className={`w-8 h-8 rounded flex items-center justify-center ${
                            task.status === 'completed'
                              ? isLight ? 'bg-emerald-100 text-emerald-700' : 'bg-emerald-500/20 text-emerald-400'
                              : task.status === 'skipped'
                              ? isLight ? 'bg-stone-200 text-stone-600' : 'bg-zinc-500/20 text-zinc-400'
                              : isLight ? 'bg-stone-100 ' + cat.color : cat.bgColor + ' ' + cat.color
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
                              task.status === 'completed' ? t.textFaint + ' line-through' : t.textMain
                            }`}
                          >
                            {task.title}
                          </p>
                          {task.description && (
                            <p className={`text-xs ${t.textMuted} truncate`}>{task.description}</p>
                          )}
                          <div className="flex items-center gap-4 mt-1">
                            <span className={`text-[9px] ${t.textFaint} uppercase tracking-wider font-bold`}>
                              {task.is_employee_task ? 'Employee Task' : 'HR Task'}
                            </span>
                            {task.due_date && (
                              <span className={`text-[9px] ${t.textFaint} font-mono`}>Due: {task.due_date}</span>
                            )}
                            {task.completed_at && (
                              <span className={`text-[9px] ${isLight ? 'text-emerald-700' : 'text-emerald-400'} font-mono`}>
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
                                className={`p-2 ${t.textMuted} hover:${isLight ? 'text-emerald-700' : 'text-emerald-400'} hover:${isLight ? 'bg-emerald-100' : 'bg-emerald-500/10'} rounded transition-colors`}
                                title="Mark Complete"
                              >
                                <CheckCircle size={16} />
                              </button>
                              <button
                                onClick={() => handleUpdateTask(task.id, 'skipped')}
                                className={`p-2 ${t.textMuted} hover:${t.textMain} hover:${isLight ? 'bg-stone-200' : 'bg-zinc-700'} rounded transition-colors`}
                                title="Skip"
                              >
                                <SkipForward size={16} />
                              </button>
                            </>
                          )}
                          {task.status !== 'pending' && (
                            <button
                              onClick={() => handleUpdateTask(task.id, 'pending')}
                              className={`p-2 ${t.textMuted} hover:${isLight ? 'text-amber-700' : 'text-amber-400'} hover:${isLight ? 'bg-amber-100' : 'bg-amber-500/10'} rounded transition-colors`}
                              title="Reopen"
                            >
                              <Clock size={16} />
                            </button>
                          )}
                          <button
                            onClick={() => handleDeleteTask(task.id)}
                            className={`p-2 ${t.textMuted} hover:${isLight ? 'text-red-700' : 'text-red-400'} hover:${isLight ? 'bg-red-100' : 'bg-red-500/10'} rounded transition-colors`}
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

      {/* Place on Leave Modal */}
      {showPlaceOnLeaveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setShowPlaceOnLeaveModal(false)}>
          <div className={`w-full max-w-md ${t.modalBg} shadow-2xl overflow-hidden`} onClick={(e) => e.stopPropagation()}>
            <div className={`flex items-center justify-between p-6 border-b ${t.border}`}>
              <h3 className={`text-lg font-bold ${t.textMain} uppercase tracking-tight`}>Place on Leave</h3>
              <button onClick={() => setShowPlaceOnLeaveModal(false)} className={`${t.textMuted} hover:${t.textMain} transition-colors`}><X size={20} /></button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Leave Type</label>
                <select
                  value={placeOnLeaveForm.leave_type}
                  onChange={(e) => setPlaceOnLeaveForm({ ...placeOnLeaveForm, leave_type: e.target.value as typeof LEAVE_TYPES[number] })}
                  className={`w-full mt-1 px-3 py-2 ${t.inputCls}`}
                >
                  {LEAVE_TYPES.map((lt) => (
                    <option key={lt} value={lt}>{lt.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Start Date</label>
                <input type="date" value={placeOnLeaveForm.start_date} onChange={(e) => setPlaceOnLeaveForm({ ...placeOnLeaveForm, start_date: e.target.value })} className={`w-full mt-1 px-3 py-2 ${t.inputCls}`} />
              </div>
              <div>
                <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>End Date (optional)</label>
                <input type="date" value={placeOnLeaveForm.end_date} onChange={(e) => setPlaceOnLeaveForm({ ...placeOnLeaveForm, end_date: e.target.value })} className={`w-full mt-1 px-3 py-2 ${t.inputCls}`} />
              </div>
              <div>
                <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Expected Return Date (optional)</label>
                <input type="date" value={placeOnLeaveForm.expected_return_date} onChange={(e) => setPlaceOnLeaveForm({ ...placeOnLeaveForm, expected_return_date: e.target.value })} className={`w-full mt-1 px-3 py-2 ${t.inputCls}`} />
              </div>
              <div>
                <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Reason (optional)</label>
                <textarea value={placeOnLeaveForm.reason} onChange={(e) => setPlaceOnLeaveForm({ ...placeOnLeaveForm, reason: e.target.value })} rows={2} className={`w-full mt-1 px-3 py-2 ${t.inputCls} resize-none`} />
              </div>
            </div>
            <div className={`p-6 border-t ${t.border} flex justify-end gap-3`}>
              <button onClick={() => setShowPlaceOnLeaveModal(false)} className={`px-4 py-2 ${t.textMuted} hover:${t.textMain} text-[10px] font-bold uppercase tracking-wider`}>Cancel</button>
              <button
                onClick={handlePlaceOnLeave}
                disabled={leaveActionLoading || !placeOnLeaveForm.start_date}
                className={`px-6 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl disabled:opacity-50`}
              >
                {leaveActionLoading ? 'Placing...' : 'Place on Leave'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Extend Leave Modal */}
      {showExtendLeaveModal && activeLeaverequest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setShowExtendLeaveModal(false)}>
          <div className={`w-full max-w-md ${t.modalBg} shadow-2xl overflow-hidden`} onClick={(e) => e.stopPropagation()}>
            <div className={`flex items-center justify-between p-6 border-b ${t.border}`}>
              <h3 className={`text-lg font-bold ${t.textMain} uppercase tracking-tight`}>Extend Leave</h3>
              <button onClick={() => setShowExtendLeaveModal(false)} className={`${t.textMuted} hover:${t.textMain} transition-colors`}><X size={20} /></button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>New End Date</label>
                <input type="date" value={extendLeaveForm.end_date} onChange={(e) => setExtendLeaveForm({ ...extendLeaveForm, end_date: e.target.value })} className={`w-full mt-1 px-3 py-2 ${t.inputCls}`} />
              </div>
              <div>
                <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>New Expected Return Date (optional)</label>
                <input type="date" value={extendLeaveForm.expected_return_date} onChange={(e) => setExtendLeaveForm({ ...extendLeaveForm, expected_return_date: e.target.value })} className={`w-full mt-1 px-3 py-2 ${t.inputCls}`} />
              </div>
              <div>
                <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Notes (optional)</label>
                <textarea value={extendLeaveForm.notes} onChange={(e) => setExtendLeaveForm({ ...extendLeaveForm, notes: e.target.value })} rows={2} className={`w-full mt-1 px-3 py-2 ${t.inputCls} resize-none`} />
              </div>
            </div>
            <div className={`p-6 border-t ${t.border} flex justify-end gap-3`}>
              <button onClick={() => setShowExtendLeaveModal(false)} className={`px-4 py-2 ${t.textMuted} hover:${t.textMain} text-[10px] font-bold uppercase tracking-wider`}>Cancel</button>
              <button
                onClick={handleExtendLeave}
                disabled={leaveActionLoading || !extendLeaveForm.end_date}
                className={`px-6 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl disabled:opacity-50`}
              >
                {leaveActionLoading ? 'Extending...' : 'Extend Leave'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Return Check-in Modal */}
      {showReturnCheckinModal && activeLeaverequest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setShowReturnCheckinModal(false)}>
          <div className={`w-full max-w-md ${t.modalBg} shadow-2xl overflow-hidden`} onClick={(e) => e.stopPropagation()}>
            <div className={`flex items-center justify-between p-6 border-b ${t.border}`}>
              <h3 className={`text-lg font-bold ${t.textMain} uppercase tracking-tight`}>Return Check-in</h3>
              <button onClick={() => setShowReturnCheckinModal(false)} className={`${t.textMuted} hover:${t.textMain} transition-colors`}><X size={20} /></button>
            </div>
            <div className="p-6 space-y-4">
              <p className={`text-sm ${t.textDim}`}>
                Is <span className={t.textMain}>{employee.first_name}</span> returning
                {activeLeaverequest.expected_return_date ? ` on ${activeLeaverequest.expected_return_date}` : ' as scheduled'}?
              </p>
              {leaveEligibility?.protection && (
                <div className={`p-3 rounded-lg ${isLight ? 'bg-blue-50 border border-blue-200' : 'bg-blue-900/20 border border-blue-500/20'}`}>
                  <p className={`text-[10px] ${isLight ? 'text-blue-700' : 'text-blue-400'}`}>
                    <Shield size={10} className="inline mr-1" />
                    {leaveEligibility.protection.weeks_remaining?.toFixed(1)} protected weeks remaining
                  </p>
                </div>
              )}
              <div className="flex gap-3">
                <button
                  onClick={() => setReturnCheckinForm({ ...returnCheckinForm, returning: true })}
                  className={`flex-1 py-2 text-[10px] font-bold uppercase tracking-wider rounded-xl border transition-colors ${returnCheckinForm.returning ? (isLight ? 'bg-emerald-100 border-emerald-400 text-emerald-700' : 'bg-emerald-900/30 border-emerald-500/40 text-emerald-400') : `${t.border} ${t.textMuted}`}`}
                >
                  Yes, Returning
                </button>
                <button
                  onClick={() => setReturnCheckinForm({ ...returnCheckinForm, returning: false })}
                  className={`flex-1 py-2 text-[10px] font-bold uppercase tracking-wider rounded-xl border transition-colors ${!returnCheckinForm.returning ? (isLight ? 'bg-amber-100 border-amber-400 text-amber-700' : 'bg-amber-900/30 border-amber-500/40 text-amber-400') : `${t.border} ${t.textMuted}`}`}
                >
                  Not Returning
                </button>
              </div>
              {!returnCheckinForm.returning && (
                <>
                  <div className="flex gap-3">
                    <button
                      onClick={() => setReturnCheckinForm({ ...returnCheckinForm, action: 'extend' })}
                      className={`flex-1 py-2 text-[10px] font-bold uppercase tracking-wider rounded-xl border transition-colors ${returnCheckinForm.action === 'extend' ? (isLight ? 'bg-blue-100 border-blue-400 text-blue-700' : 'bg-blue-900/30 border-blue-500/40 text-blue-400') : `${t.border} ${t.textMuted}`}`}
                    >
                      Extend Leave
                    </button>
                    <button
                      onClick={() => setReturnCheckinForm({ ...returnCheckinForm, action: 'new_leave' })}
                      className={`flex-1 py-2 text-[10px] font-bold uppercase tracking-wider rounded-xl border transition-colors ${returnCheckinForm.action === 'new_leave' ? (isLight ? 'bg-blue-100 border-blue-400 text-blue-700' : 'bg-blue-900/30 border-blue-500/40 text-blue-400') : `${t.border} ${t.textMuted}`}`}
                    >
                      New Leave
                    </button>
                  </div>
                  {returnCheckinForm.action === 'new_leave' && (
                    <div>
                      <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>New Leave Type</label>
                      <select
                        value={returnCheckinForm.new_leave_type}
                        onChange={(e) => setReturnCheckinForm({ ...returnCheckinForm, new_leave_type: e.target.value as typeof LEAVE_TYPES[number] })}
                        className={`w-full mt-1 px-3 py-2 ${t.inputCls}`}
                      >
                        {LEAVE_TYPES.map((lt) => (
                          <option key={lt} value={lt}>{lt.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div>
                    <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>
                      {returnCheckinForm.action === 'extend' ? 'New End Date' : 'New Start Date'}
                    </label>
                    <input
                      type="date"
                      value={returnCheckinForm.new_end_date}
                      onChange={(e) => setReturnCheckinForm({ ...returnCheckinForm, new_end_date: e.target.value })}
                      className={`w-full mt-1 px-3 py-2 ${t.inputCls}`}
                    />
                  </div>
                </>
              )}
              <div>
                <label className={`text-[9px] ${t.textMuted} uppercase tracking-wider font-bold`}>Notes (optional)</label>
                <textarea value={returnCheckinForm.notes} onChange={(e) => setReturnCheckinForm({ ...returnCheckinForm, notes: e.target.value })} rows={2} className={`w-full mt-1 px-3 py-2 ${t.inputCls} resize-none`} />
              </div>
            </div>
            <div className={`p-6 border-t ${t.border} flex justify-end gap-3`}>
              <button onClick={() => setShowReturnCheckinModal(false)} className={`px-4 py-2 ${t.textMuted} hover:${t.textMain} text-[10px] font-bold uppercase tracking-wider`}>Cancel</button>
              <button
                onClick={handleReturnCheckin}
                disabled={leaveActionLoading}
                className={`px-6 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl disabled:opacity-50`}
              >
                {leaveActionLoading ? 'Processing...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Assign Tasks Modal */}
      {showAssignModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className={`w-full max-w-lg ${t.modalBg} max-h-[80vh] flex flex-col shadow-2xl overflow-hidden`} onClick={(e) => e.stopPropagation()}>
            <div className={`flex items-center justify-between p-6 border-b ${t.border}`}>
              <h3 className={`text-xl font-bold ${t.textMain} uppercase tracking-tight`}>Add Tasks</h3>
              <button onClick={() => setShowAssignModal(false)} className={`${t.textMuted} hover:${t.textMain} transition-colors`}>
                <X size={20} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              <p className={`text-[10px] font-bold uppercase tracking-wider ${t.textMuted}`}>Select templates to assign</p>
              <div className="space-y-2">
                {templates.map((template) => (
                  <label
                    key={template.id}
                    className={`flex items-center gap-3 p-4 border rounded-xl cursor-pointer transition-colors ${
                      selectedTemplates.includes(template.id)
                        ? `${isLight ? 'border-zinc-900 bg-stone-200/50' : 'border-white/30 bg-white/5'}`
                        : `${t.border} ${isLight ? 'hover:bg-stone-200/30' : 'hover:bg-white/5'}`
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
                      className="w-4 h-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900"
                    />
                    <div className="flex-1">
                      <p className={`text-sm font-bold ${t.textMain}`}>{template.title}</p>
                      <p className={`text-[10px] ${t.textMuted} uppercase tracking-wider mt-0.5`}>
                        {template.category} - Due in {template.due_days} days
                      </p>
                    </div>
                  </label>
                ))}
              </div>
            </div>
            <div className={`p-6 border-t ${t.border} flex justify-end gap-3`}>
              <button
                onClick={() => setShowAssignModal(false)}
                className={`px-4 py-2 ${t.textMuted} hover:${t.textMain} text-[10px] font-bold uppercase tracking-wider transition-colors`}
              >
                Cancel
              </button>
              <button
                onClick={handleAssignSelected}
                disabled={selectedTemplates.length === 0}
                className={`px-6 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl disabled:opacity-50 transition-colors`}
              >
                Assign ({selectedTemplates.length})
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
    </div>
  );
}
