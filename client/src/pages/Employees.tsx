import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAccessToken, provisioning } from '../api/client';
import { Plus, X, Mail, AlertTriangle, CheckCircle, UserX, Clock, ChevronRight, HelpCircle, ChevronDown, Settings, ClipboardCheck, Upload, Download } from 'lucide-react';
import { FeatureGuideTrigger } from '../features/feature-guides';
import type { GoogleWorkspaceConnectionStatus } from '../types';
import OnboardingAgentConsole from '../components/OnboardingAgentConsole';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

interface Employee {
  id: string;
  email: string;
  work_email?: string | null;
  personal_email?: string | null;
  first_name: string;
  last_name: string;
  work_state: string | null;
  employment_type: string | null;
  start_date: string | null;
  termination_date: string | null;
  manager_id: string | null;
  manager_name: string | null;
  user_id: string | null;
  invitation_status: string | null;
  created_at: string;
}

interface NewEmployee {
  work_email: string;
  personal_email: string;
  first_name: string;
  last_name: string;
  office_location: string;
  work_state: string;
  employment_type: string;
  start_date: string;
}

type EmailEntryMode = 'generated' | 'existing';
type WorkLocationMode = 'remote' | 'office';
type AddWizardStep = 1 | 2 | 3;
type BatchWizardStep = 1 | 2 | 3;

interface BatchEmployeeRow {
  id: string;
  first_name: string;
  last_name: string;
  work_email: string;
  personal_email: string;
  work_state: string;
  office_location: string;
  employment_type: string;
  start_date: string;
  skip_google_workspace_provisioning: boolean;
}

interface BatchCreateError {
  row_number: number;
  name: string;
  error: string;
}

interface BatchCreateResult {
  created: number;
  failed: number;
  errors: BatchCreateError[];
}

function sanitizeEmailLocalPart(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/['`]/g, '')
    .replace(/[^a-z0-9._-]+/g, '.')
    .replace(/\.+/g, '.')
    .replace(/^[._-]+|[._-]+$/g, '');
}

function buildGeneratedEmailLocalPart(firstName: string, lastName: string): string {
  const first = sanitizeEmailLocalPart(firstName);
  const last = sanitizeEmailLocalPart(lastName);
  if (first && last) return `${first}.${last}`;
  return first || last;
}

function looksLikeEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function createBatchRow(defaultStartDate: string): BatchEmployeeRow {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    first_name: '',
    last_name: '',
    work_email: '',
    personal_email: '',
    work_state: '',
    office_location: '',
    employment_type: 'full_time',
    start_date: defaultStartDate,
    skip_google_workspace_provisioning: true,
  };
}

interface OnboardingProgress {
  employee_id: string;
  total: number;
  completed: number;
  pending: number;
  has_onboarding: boolean;
}

export default function Employees({ mode = 'directory' }: { mode?: 'onboarding' | 'directory' }) {
  const navigate = useNavigate();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [filter, setFilter] = useState<string>(mode === 'directory' ? 'active' : '');
  const [newEmployee, setNewEmployee] = useState<NewEmployee>({
    work_email: '',
    personal_email: '',
    first_name: '',
    last_name: '',
    office_location: '',
    work_state: '',
    employment_type: 'full_time',
    start_date: new Date().toISOString().split('T')[0],
  });
  const [emailEntryMode, setEmailEntryMode] = useState<EmailEntryMode>('existing');
  const [generatedEmailLocalPart, setGeneratedEmailLocalPart] = useState('');
  const [generatedEmailEdited, setGeneratedEmailEdited] = useState(false);
  const [skipGoogleAutoProvision, setSkipGoogleAutoProvision] = useState(false);
  const [workLocationMode, setWorkLocationMode] = useState<WorkLocationMode>('remote');
  const [addWizardStep, setAddWizardStep] = useState<AddWizardStep>(1);

  const [showBatchWizardModal, setShowBatchWizardModal] = useState(false);
  const [batchWizardStep, setBatchWizardStep] = useState<BatchWizardStep>(1);
  const [batchEmailMode, setBatchEmailMode] = useState<EmailEntryMode>('existing');
  const [batchWorkLocationMode, setBatchWorkLocationMode] = useState<WorkLocationMode>('remote');
  const [batchRows, setBatchRows] = useState<BatchEmployeeRow[]>([]);
  const [batchSubmitting, setBatchSubmitting] = useState(false);
  const [batchResult, setBatchResult] = useState<BatchCreateResult | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [invitingId, setInvitingId] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [onboardingProgress, setOnboardingProgress] = useState<Record<string, OnboardingProgress>>({});
  const [agentEmployee, setAgentEmployee] = useState<{
    id: string; name: string; workEmail: string; personalEmail: string;
  } | null>(null);
  const [showSettingsDropdown, setShowSettingsDropdown] = useState(false);
  const [googleWorkspaceStatus, setGoogleWorkspaceStatus] = useState<GoogleWorkspaceConnectionStatus | null>(null);
  const [googleWorkspaceStatusLoading, setGoogleWorkspaceStatusLoading] = useState(false);

  // Bulk upload state
  const [showBulkUploadModal, setShowBulkUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [sendInvitationsOnUpload, setSendInvitationsOnUpload] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [bulkInviting, setBulkInviting] = useState(false);
  const [bulkInviteResult, setBulkInviteResult] = useState<{ sent: number; failed: number } | null>(null);

  const normalizedGoogleDomain = (googleWorkspaceStatus?.domain || '')
    .trim()
    .replace(/^@/, '')
    .toLowerCase();
  const googleDomainAvailable = Boolean(
    normalizedGoogleDomain &&
      googleWorkspaceStatus?.connected &&
      googleWorkspaceStatus.status === 'connected'
  );

  const resetAddEmployeeForm = useCallback(() => {
    setNewEmployee({
      work_email: '',
      personal_email: '',
      first_name: '',
      last_name: '',
      office_location: '',
      work_state: '',
      employment_type: 'full_time',
      start_date: new Date().toISOString().split('T')[0],
    });
    setEmailEntryMode(googleDomainAvailable ? 'generated' : 'existing');
    setGeneratedEmailLocalPart('');
    setGeneratedEmailEdited(false);
    setSkipGoogleAutoProvision(false);
    setWorkLocationMode('remote');
    setAddWizardStep(1);
  }, [googleDomainAvailable]);

  const resetBatchWizard = useCallback(() => {
    const defaultStartDate = new Date().toISOString().split('T')[0];
    setBatchWizardStep(1);
    setBatchEmailMode(googleDomainAvailable ? 'generated' : 'existing');
    setBatchWorkLocationMode('remote');
    setBatchRows([
      createBatchRow(defaultStartDate),
      createBatchRow(defaultStartDate),
      createBatchRow(defaultStartDate),
      createBatchRow(defaultStartDate),
      createBatchRow(defaultStartDate),
    ]);
    setBatchResult(null);
  }, [googleDomainAvailable]);

  const fetchEmployees = async () => {
    try {
      const token = getAccessToken();
      const url = filter
        ? `${API_BASE}/employees?status=${filter}`
        : `${API_BASE}/employees`;

      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to fetch employees');
      }

      const data = await response.json();
      setEmployees(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const fetchOnboardingProgress = async () => {
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/onboarding-progress`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) throw new Error('Failed to fetch onboarding progress');

      const data = await response.json();
      setOnboardingProgress(data);
    } catch (err) {
      console.error('Failed to fetch onboarding progress:', err);
    }
  };

  const fetchGoogleWorkspaceStatus = async () => {
    setGoogleWorkspaceStatusLoading(true);
    try {
      const status = await provisioning.getGoogleWorkspaceStatus();
      setGoogleWorkspaceStatus(status);
    } catch (err) {
      console.error('Failed to fetch Google Workspace provisioning status:', err);
      setGoogleWorkspaceStatus(null);
    } finally {
      setGoogleWorkspaceStatusLoading(false);
    }
  };

  useEffect(() => {
    fetchEmployees();
    fetchOnboardingProgress();
  }, [filter]);

  useEffect(() => {
    fetchGoogleWorkspaceStatus();
  }, []);

  useEffect(() => {
    if (!showAddModal) return;
    setEmailEntryMode(googleDomainAvailable ? 'generated' : 'existing');
    setGeneratedEmailEdited(false);
    setSkipGoogleAutoProvision(false);
    setWorkLocationMode('remote');
    if (!googleDomainAvailable) setGeneratedEmailLocalPart('');
  }, [showAddModal, googleDomainAvailable]);

  useEffect(() => {
    if (!showAddModal || emailEntryMode !== 'generated' || generatedEmailEdited) return;
    const generated = buildGeneratedEmailLocalPart(newEmployee.first_name, newEmployee.last_name);
    setGeneratedEmailLocalPart(generated);
  }, [
    showAddModal,
    emailEntryMode,
    generatedEmailEdited,
    newEmployee.first_name,
    newEmployee.last_name,
  ]);

  const googleAutoProvisionBadge = () => {
    if (googleWorkspaceStatusLoading) {
      return {
        label: 'Loading',
        tone: 'bg-zinc-800 text-zinc-400 border-zinc-700',
      };
    }
    if (
      !googleWorkspaceStatus ||
      !googleWorkspaceStatus.connected ||
      googleWorkspaceStatus.status === 'disconnected'
    ) {
      return {
        label: 'Disconnected',
        tone: 'bg-zinc-800 text-zinc-400 border-zinc-700',
      };
    }
    if (
      googleWorkspaceStatus.status === 'error' ||
      googleWorkspaceStatus.status === 'needs_action'
    ) {
      return {
        label: 'Needs Attention',
        tone: 'bg-red-900/30 text-red-300 border-red-500/30',
      };
    }
    if (googleWorkspaceStatus.auto_provision_on_employee_create) {
      return {
        label: 'ON',
        tone: 'bg-emerald-900/30 text-emerald-300 border-emerald-500/30',
      };
    }
    return {
      label: 'OFF',
      tone: 'bg-amber-900/30 text-amber-300 border-amber-500/30',
    };
  };

  const handleAddEmployee = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const token = getAccessToken();
      const generatedWorkEmail = googleDomainAvailable && generatedEmailLocalPart
        ? `${generatedEmailLocalPart}@${normalizedGoogleDomain}`
        : '';
      const resolvedWorkEmail = (
        emailEntryMode === 'generated' ? generatedWorkEmail : newEmployee.work_email
      )
        .trim()
        .toLowerCase();
      if (!resolvedWorkEmail) {
        throw new Error('Work email is required');
      }
      if (workLocationMode === 'remote' && !newEmployee.work_state) {
        throw new Error('Work state is required for remote employees');
      }
      if (workLocationMode === 'office' && !newEmployee.office_location.trim()) {
        throw new Error('Office/store location is required for on-site employees');
      }

      const payload = {
        email: resolvedWorkEmail,
        work_email: resolvedWorkEmail,
        personal_email: newEmployee.personal_email || undefined,
        first_name: newEmployee.first_name,
        last_name: newEmployee.last_name,
        work_state: workLocationMode === 'remote' ? (newEmployee.work_state || undefined) : undefined,
        address: workLocationMode === 'office' ? (newEmployee.office_location || undefined) : undefined,
        employment_type: newEmployee.employment_type,
        start_date: newEmployee.start_date,
        skip_google_workspace_provisioning:
          emailEntryMode === 'existing' && skipGoogleAutoProvision,
      };
      const response = await fetch(`${API_BASE}/employees`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to add employee');
      }

      const createdEmployee = await response.json();

      setAgentEmployee({
        id: createdEmployee.id,
        name: `${newEmployee.first_name} ${newEmployee.last_name}`,
        workEmail: resolvedWorkEmail,
        personalEmail: newEmployee.personal_email,
      });

      fetchEmployees();
      fetchOnboardingProgress();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSendInvite = async (employeeId: string) => {
    setInvitingId(employeeId);

    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/${employeeId}/invite`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to send invitation');
      }

      fetchEmployees();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setInvitingId(null);
    }
  };

  const handleDownloadTemplate = async () => {
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/bulk-upload/template`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) throw new Error('Failed to download template');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'employee_bulk_upload_template.csv';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download template');
    }
  };

  const handleBulkUpload = async () => {
    if (!uploadFile) return;

    setUploadLoading(true);
    setUploadResult(null);

    try {
      const token = getAccessToken();
      const formData = new FormData();
      formData.append('file', uploadFile);

      const response = await fetch(
        `${API_BASE}/employees/bulk-upload?send_invitations=${sendInvitationsOnUpload}`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
          },
          body: formData,
        }
      );

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to upload CSV');
      }

      const result = await response.json();
      setUploadResult(result);
      fetchEmployees();
      fetchOnboardingProgress();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload CSV');
    } finally {
      setUploadLoading(false);
    }
  };

  const handleFileSelect = (file: File | null) => {
    if (file && file.type === 'text/csv') {
      setUploadFile(file);
      setUploadResult(null);
    } else if (file) {
      setError('Please select a CSV file');
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    handleFileSelect(file);
  };

  const getStatusBadge = (employee: Employee) => {
    if (employee.termination_date) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold bg-zinc-800 text-zinc-400 border border-zinc-700">
          <UserX size={10} /> Terminated
        </span>
      );
    }
    if (employee.user_id) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold bg-emerald-900/30 text-emerald-400 border border-emerald-500/20">
          <CheckCircle size={10} /> Active
        </span>
      );
    }
    if (employee.invitation_status === 'pending') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold bg-amber-900/30 text-amber-400 border border-amber-500/20">
          <Clock size={10} /> Invited
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold bg-zinc-800 text-zinc-500 border border-zinc-700">
        <Mail size={10} /> Not Invited
      </span>
    );
  };

  const US_STATES = [
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
  ];

  const generatedSingleWorkEmail = googleDomainAvailable && generatedEmailLocalPart
    ? `${generatedEmailLocalPart}@${normalizedGoogleDomain}`
    : '';
  const canProceedAddStep1 = Boolean(
    newEmployee.first_name.trim() && newEmployee.last_name.trim()
  );
  const canProceedAddStep2 = emailEntryMode === 'generated'
    ? Boolean(generatedSingleWorkEmail)
    : looksLikeEmail(newEmployee.work_email);
  const hasSingleLocation = workLocationMode === 'remote'
    ? Boolean(newEmployee.work_state)
    : Boolean(newEmployee.office_location.trim());
  const canSubmitSingleWizard = canProceedAddStep1 && canProceedAddStep2 && hasSingleLocation;

  const BATCH_MAX_ROWS = 50;
  const batchRowsWithInput = batchRows.filter((row) =>
    Boolean(
      row.first_name.trim() ||
        row.last_name.trim() ||
        row.work_email.trim() ||
        row.personal_email.trim() ||
        row.work_state.trim() ||
        row.office_location.trim()
    )
  );

  const resolveBatchRowWorkEmail = (row: BatchEmployeeRow): string => {
    if (batchEmailMode === 'generated') {
      const localPart = buildGeneratedEmailLocalPart(row.first_name, row.last_name);
      return localPart && normalizedGoogleDomain ? `${localPart}@${normalizedGoogleDomain}` : '';
    }
    return row.work_email.trim().toLowerCase();
  };

  const batchRowValidationError = (row: BatchEmployeeRow): string | null => {
    if (!row.first_name.trim() || !row.last_name.trim()) return 'First and last name are required';
    if (batchEmailMode === 'generated') {
      if (!googleDomainAvailable) return 'Google Workspace domain is required for generated emails';
      if (!resolveBatchRowWorkEmail(row)) return 'Could not generate work email from name';
    } else if (!looksLikeEmail(row.work_email)) {
      return 'Valid work email is required';
    }

    if (batchWorkLocationMode === 'remote' && !row.work_state.trim()) {
      return 'Work state is required for remote employees';
    }
    if (batchWorkLocationMode === 'office' && !row.office_location.trim()) {
      return 'Office/store is required for on-site employees';
    }
    return null;
  };

  const canProceedBatchStep2 = batchRowsWithInput.length > 0 && batchRowsWithInput.every((row) => !batchRowValidationError(row));

  const updateBatchRowField = <K extends keyof BatchEmployeeRow>(
    rowId: string,
    field: K,
    value: BatchEmployeeRow[K]
  ) => {
    setBatchRows((prev) =>
      prev.map((row) => (row.id === rowId ? { ...row, [field]: value } : row))
    );
  };

  const addBatchRow = () => {
    if (batchRows.length >= BATCH_MAX_ROWS) return;
    const defaultStartDate = new Date().toISOString().split('T')[0];
    setBatchRows((prev) => [...prev, createBatchRow(defaultStartDate)]);
  };

  const removeBatchRow = (rowId: string) => {
    setBatchRows((prev) => {
      const next = prev.filter((row) => row.id !== rowId);
      return next.length > 0 ? next : [createBatchRow(new Date().toISOString().split('T')[0])];
    });
  };

  const handleBatchCreate = async () => {
    if (!canProceedBatchStep2) return;
    setBatchSubmitting(true);
    setBatchResult(null);

    try {
      const token = getAccessToken();
      let created = 0;
      let failed = 0;
      const errors: BatchCreateError[] = [];

      for (let idx = 0; idx < batchRowsWithInput.length; idx += 1) {
        const row = batchRowsWithInput[idx];
        const rowError = batchRowValidationError(row);
        if (rowError) {
          failed += 1;
          errors.push({
            row_number: idx + 1,
            name: `${row.first_name} ${row.last_name}`.trim() || `Row ${idx + 1}`,
            error: rowError,
          });
          continue;
        }

        const resolvedWorkEmail = resolveBatchRowWorkEmail(row);
        const payload = {
          email: resolvedWorkEmail,
          work_email: resolvedWorkEmail,
          personal_email: row.personal_email.trim() || undefined,
          first_name: row.first_name.trim(),
          last_name: row.last_name.trim(),
          work_state: batchWorkLocationMode === 'remote' ? row.work_state.trim() : undefined,
          address: batchWorkLocationMode === 'office' ? row.office_location.trim() : undefined,
          employment_type: row.employment_type,
          start_date: row.start_date,
          skip_google_workspace_provisioning:
            batchEmailMode === 'existing' ? row.skip_google_workspace_provisioning : false,
        };

        try {
          const response = await fetch(`${API_BASE}/employees`, {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
          });

          if (!response.ok) {
            const data = await response.json().catch(() => ({} as { detail?: string }));
            failed += 1;
            errors.push({
              row_number: idx + 1,
              name: `${row.first_name} ${row.last_name}`.trim() || `Row ${idx + 1}`,
              error: data.detail || 'Failed to create employee',
            });
            continue;
          }

          created += 1;
        } catch {
          failed += 1;
          errors.push({
            row_number: idx + 1,
            name: `${row.first_name} ${row.last_name}`.trim() || `Row ${idx + 1}`,
            error: 'Network error while creating employee',
          });
        }
      }

      setBatchResult({ created, failed, errors });
      fetchEmployees();
      fetchOnboardingProgress();
    } finally {
      setBatchSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading directory...</div>
      </div>
    );
  }

  const googleBadge = googleAutoProvisionBadge();

  return (
    <div className="max-w-7xl mx-auto space-y-8 overflow-x-hidden">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 border-b border-white/10 pb-8">
        {mode === 'directory' ? (
          <>
            <div>
              <div className="flex items-center gap-3 justify-center lg:justify-start">
                <h1 className="text-3xl md:text-4xl font-bold tracking-tighter text-white uppercase">Employees</h1>
                <FeatureGuideTrigger guideId="employees" />
              </div>
              <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase text-center lg:text-left">
                Manage your team
              </p>
              <div className="flex justify-center lg:justify-start">
                <button
                  onClick={() => navigate('/app/matcha/onboarding?tab=workspace')}
                  className="mt-4 inline-flex items-center gap-2 border border-white/10 bg-zinc-900/60 px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-zinc-300 hover:text-white hover:border-white/20 transition-colors"
                  title="Open Google Workspace provisioning settings"
                >
                  <span className="text-zinc-500">Google Auto-Provision</span>
                  <span className={`rounded border px-2 py-0.5 ${googleBadge.tone}`}>{googleBadge.label}</span>
                </button>
              </div>
            </div>
            <div className="flex items-center gap-2 sm:gap-3">
              <button
                onClick={() => navigate('/app/matcha/onboarding?tab=employees')}
                className="flex items-center justify-center gap-2 px-4 sm:px-6 py-2 bg-white text-black hover:bg-zinc-200 text-[10px] sm:text-xs font-bold uppercase tracking-wider transition-colors"
              >
                <Plus size={14} />
                Onboard New Employee
              </button>
            </div>
          </>
        ) : (
          <div className="grid grid-cols-2 sm:flex sm:items-center gap-2 sm:gap-3">
            <button
              data-tour="emp-help-btn"
              onClick={() => setShowHelp(!showHelp)}
              className={`flex items-center justify-center gap-2 px-3 sm:px-4 py-2 border text-[10px] sm:text-xs font-bold uppercase tracking-wider transition-colors ${
                showHelp
                  ? 'border-white/30 text-white bg-zinc-800'
                  : 'border-white/10 text-zinc-400 hover:text-white hover:border-white/20'
              }`}
            >
              <HelpCircle size={14} />
              <span>Help</span>
              <ChevronDown size={12} className={`transition-transform ${showHelp ? 'rotate-180' : ''}`} />
            </button>

            <div className="relative">
              <button
                onClick={() => setShowSettingsDropdown(!showSettingsDropdown)}
                className={`w-full flex items-center justify-center gap-2 px-3 sm:px-4 py-2 border text-[10px] sm:text-xs font-bold uppercase tracking-wider transition-colors ${
                  showSettingsDropdown
                    ? 'border-white/30 text-white bg-zinc-800'
                    : 'border-white/10 text-zinc-400 hover:text-white hover:border-white/20'
                }`}
              >
                <Settings size={14} />
                <span>Tools</span>
              </button>
              {showSettingsDropdown && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowSettingsDropdown(false)}
                  />
                  <div className="absolute right-0 mt-2 w-56 bg-zinc-900 border border-white/10 shadow-xl z-20">
                    <button
                      onClick={() => {
                        setShowSettingsDropdown(false);
                        navigate('/app/matcha/onboarding-templates');
                      }}
                      className="w-full flex items-center gap-3 px-4 py-3 text-left text-xs font-medium text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors"
                    >
                      <ClipboardCheck size={14} />
                      Onboarding Templates
                    </button>
                  </div>
                </>
              )}
            </div>

            <button
              data-tour="emp-bulk-btn"
              onClick={() => setShowBulkUploadModal(true)}
              className="flex items-center justify-center gap-2 px-3 sm:px-4 py-2 border border-white/10 text-zinc-400 hover:text-white hover:border-white/20 text-[10px] sm:text-xs font-bold uppercase tracking-wider transition-colors"
            >
              <Upload size={14} />
              <span>Bulk CSV</span>
            </button>

            <button
              onClick={() => {
                resetBatchWizard();
                setShowBatchWizardModal(true);
              }}
              className="flex items-center justify-center gap-2 px-3 sm:px-4 py-2 border border-white/10 text-zinc-400 hover:text-white hover:border-white/20 text-[10px] sm:text-xs font-bold uppercase tracking-wider transition-colors"
            >
              <ClipboardCheck size={14} />
              <span>Batch Wizard</span>
            </button>

            <button
              data-tour="emp-add-btn"
              onClick={() => {
                resetAddEmployeeForm();
                setShowAddModal(true);
              }}
              className="flex items-center justify-center gap-2 px-4 sm:px-6 py-2 bg-white text-black hover:bg-zinc-200 text-[10px] sm:text-xs font-bold uppercase tracking-wider transition-colors"
            >
              <Plus size={14} />
              Add Employee
            </button>
          </div>
        )}
      </div>

      {mode === 'onboarding' && (
        <div className="border border-white/10 bg-zinc-900/40 p-4 text-[11px] text-zinc-300 space-y-1">
          <p className="uppercase tracking-wider text-zinc-400">Onboarding flows</p>
          <p>
            Use <span className="text-white">Add Employee</span> for one hire,{' '}
            <span className="text-white">Batch Wizard</span> for up to 50 hires, or{' '}
            <span className="text-white">Bulk CSV</span> when you already have a spreadsheet.
          </p>
        </div>
      )}

      {/* Help Panel */}
      {/* ... keeping help panel same as it uses grid-cols-1 md:grid-cols-2 already */}

      {/* Error message */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded p-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
             <AlertTriangle className="text-red-400 shrink-0" size={16} />
             <p className="text-sm text-red-400 font-mono">{error}</p>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-xs text-red-400 hover:text-red-300 uppercase tracking-wider font-bold shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Filter tabs */}
      <div data-tour="emp-tabs" className="border-b border-white/10 -mx-4 px-4 sm:mx-0 sm:px-0">
        <nav className="-mb-px flex space-x-8 overflow-x-auto pb-px no-scrollbar">
          {[
            { value: '', label: 'All' },
            { value: 'active', label: 'Active' },
            { value: 'invited', label: 'Pending Invite' },
            { value: 'terminated', label: 'Terminated' },
          ].map((tab) => (
            <button
              key={tab.value}
              onClick={() => setFilter(tab.value)}
              className={`pb-4 px-1 border-b-2 text-xs font-bold uppercase tracking-wider transition-colors whitespace-nowrap ${
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

      {/* Employee list */}
      {employees.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-white/10 bg-white/5">
          <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
            <Plus size={24} className="text-zinc-600" />
          </div>
          {mode === 'directory' ? (
            <>
              <h3 className="text-white text-sm font-bold mb-1 uppercase tracking-wide">No employees found</h3>
              <p className="text-zinc-500 text-xs mb-6 font-mono uppercase">Onboard employees first to see them here.</p>
              <button
                onClick={() => navigate('/app/matcha/onboarding?tab=employees')}
                className="flex items-center gap-2 mx-auto px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
              >
                <Plus size={14} />
                Onboard New Employee
              </button>
            </>
          ) : (
            <>
              <h3 className="text-white text-sm font-bold mb-1 uppercase tracking-wide">Onboard your first employee</h3>
              <p className="text-zinc-500 text-xs mb-6 font-mono uppercase">Your directory is empty. Start your onboarding process now.</p>
              <button
                onClick={() => {
                  resetAddEmployeeForm();
                  setShowAddModal(true);
                }}
                className="flex items-center gap-2 mx-auto px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
              >
                <Plus size={14} />
                Add Employee
              </button>
            </>
          )}
        </div>
      ) : (
        <div data-tour="emp-list" className="space-y-px bg-white/10 border border-white/10">
           {/* Table Header */}
           <div className="hidden md:flex items-center gap-4 py-3 px-6 bg-zinc-950 text-[10px] text-zinc-500 uppercase tracking-widest border-b border-white/10">
              <div className="flex-1">Name / Email</div>
              <div className="w-32 text-right">Work State</div>
              <div className="w-32 text-right">Type</div>
              <div className="w-36 text-right">Onboarding</div>
              <div className="w-32 text-right">Status</div>
              <div className="w-32"></div>
           </div>

          {employees.map((employee) => (
            <div
              key={employee.id}
              onClick={() => navigate(`/app/matcha/employees/${employee.id}`)}
              className="group bg-zinc-950 hover:bg-zinc-900 transition-colors p-4 md:px-6 flex flex-col lg:flex-row lg:items-center gap-4 cursor-pointer"
            >
              <div className="flex items-center min-w-0 flex-1">
                <div className="flex-shrink-0">
                  <div className="h-10 w-10 rounded bg-zinc-800 border border-zinc-700 flex items-center justify-center text-white font-bold text-xs">
                    {employee.first_name[0]}{employee.last_name[0]}
                  </div>
                </div>
                <div className="ml-4 min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-bold text-white truncate group-hover:text-zinc-200">
                      {employee.first_name} {employee.last_name}
                    </p>
                  </div>
                  <p className="text-xs text-zinc-500 font-mono truncate">
                    {employee.work_email || employee.email}
                  </p>
                  {employee.personal_email && (
                    <p className="text-[10px] text-zinc-600 truncate">
                      Personal: {employee.personal_email}
                    </p>
                  )}
                </div>
                <div className="lg:hidden">
                   <ChevronRight size={16} className="text-zinc-600" />
                </div>
              </div>

              <div className="grid grid-cols-2 sm:flex sm:items-center justify-between lg:justify-end gap-x-4 gap-y-3 lg:gap-8 w-full lg:w-auto border-t border-white/5 pt-4 lg:border-0 lg:pt-0">
                 <div className="lg:text-right">
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider lg:hidden">Location</p>
                    <p className="text-xs text-zinc-400 font-mono">{employee.work_state || '—'}</p>
                 </div>
                 <div className="lg:text-right lg:w-24">
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider lg:hidden">Type</p>
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider truncate">
                      {employee.employment_type?.replace('_', ' ') || '—'}
                    </p>
                 </div>
                 <div data-tour="emp-onboarding-col" className="lg:w-36 flex flex-col lg:items-end lg:justify-end">
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider lg:hidden mb-1">Onboarding</p>
                    {onboardingProgress[employee.id]?.has_onboarding ? (
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-emerald-500 rounded-full transition-all"
                            style={{
                              width: `${(onboardingProgress[employee.id].completed / onboardingProgress[employee.id].total) * 100}%`,
                            }}
                          />
                        </div>
                        <span className="text-[10px] text-zinc-400 font-mono">
                          {onboardingProgress[employee.id].completed}/{onboardingProgress[employee.id].total}
                        </span>
                      </div>
                    ) : (
                      <span className="text-[10px] text-zinc-600 uppercase tracking-wider">Not started</span>
                    )}
                 </div>
                 <div className="flex flex-col lg:items-end lg:justify-end lg:w-32">
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider lg:hidden mb-1">Status</p>
                    {getStatusBadge(employee)}
                 </div>

                 <div className="col-span-2 sm:col-auto lg:w-32 flex lg:justify-end mt-2 sm:mt-0">
                    {!employee.user_id && !employee.termination_date && (
                      <button
                        data-tour="emp-invite-btn"
                        onClick={(e) => { e.stopPropagation(); handleSendInvite(employee.id); }}
                        disabled={invitingId === employee.id}
                        className="flex-1 lg:flex-none inline-flex items-center justify-center px-3 py-1.5 border border-white/10 text-[10px] font-bold uppercase tracking-wider rounded text-zinc-300 hover:text-white hover:border-white/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed bg-zinc-900"
                      >
                        {invitingId === employee.id ? (
                          <span className="animate-pulse">Sending...</span>
                        ) : employee.invitation_status === 'pending' ? (
                          'Resend Invite'
                        ) : (
                          'Send Invite'
                        )}
                      </button>
                    )}
                 </div>
                 <div className="hidden lg:flex w-8 justify-end">
                    <ChevronRight size={16} className="text-zinc-600 group-hover:text-zinc-400" />
                 </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Employee Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
            <div className="w-full max-w-lg bg-zinc-950 border border-zinc-800 shadow-2xl rounded-sm flex flex-col" onClick={(e) => e.stopPropagation()}>
              {agentEmployee ? (
                <OnboardingAgentConsole
                  employeeId={agentEmployee.id}
                  employeeName={agentEmployee.name}
                  companyName=""
                  workEmail={agentEmployee.workEmail}
                  personalEmail={agentEmployee.personalEmail}
                  googleEnabled={googleDomainAvailable}
                  onAddAnother={() => {
                    setAgentEmployee(null);
                    resetAddEmployeeForm();
                  }}
                  onViewProfile={(id) => {
                    setShowAddModal(false);
                    setAgentEmployee(null);
                    navigate(`/app/matcha/employees/${id}`);
                  }}
                  onClose={() => {
                    setShowAddModal(false);
                    setAgentEmployee(null);
                    resetAddEmployeeForm();
                  }}
                />
              ) : (
              <>
              <div className="flex items-center justify-between p-6 border-b border-white/10">
                  <h3 className="text-xl font-bold text-white uppercase tracking-tight">Add Personnel</h3>
                  <button
                    onClick={() => {
                      setShowAddModal(false);
                      resetAddEmployeeForm();
                    }}
                    className="text-zinc-500 hover:text-white transition-colors"
                  >
                    <X size={20} />
                  </button>
              </div>

              <form onSubmit={handleAddEmployee} className="flex-1 overflow-y-auto p-8">
                <div className="space-y-6">
                  <div className="rounded border border-white/10 bg-zinc-900/40 p-3">
                    <p className="text-[10px] uppercase tracking-wider text-zinc-400">
                      Step {addWizardStep} of 3
                    </p>
                    <p className="text-xs text-zinc-300 mt-1">
                      {addWizardStep === 1 &&
                        'Start with name and optional personal email. Work email setup comes next.'}
                      {addWizardStep === 2 &&
                        'Choose generated or existing work email. Generated mode uses your configured Google domain.'}
                      {addWizardStep === 3 &&
                        'Set remote state or office/store, confirm details, then create the employee.'}
                    </p>
                  </div>

                  <div className="flex items-center gap-3">
                    {[1, 2, 3].map((step) => (
                      <div key={step} className="flex items-center gap-3">
                        <div
                          className={`h-6 w-6 rounded-full border text-[10px] font-bold flex items-center justify-center ${
                            addWizardStep >= step
                              ? 'border-white text-white bg-zinc-800'
                              : 'border-zinc-700 text-zinc-600'
                          }`}
                        >
                          {step}
                        </div>
                        {step < 3 && <div className="h-px w-8 bg-zinc-800" />}
                      </div>
                    ))}
                  </div>

                  {addWizardStep === 1 && (
                    <div className="space-y-6">
                      <p className="text-[11px] text-zinc-500">
                        Required now: first and last name.
                      </p>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                            First Name <span className="text-red-500">*</span>
                          </label>
                          <input
                            type="text"
                            required
                            value={newEmployee.first_name}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, first_name: e.target.value })
                            }
                            className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                            Last Name <span className="text-red-500">*</span>
                          </label>
                          <input
                            type="text"
                            required
                            value={newEmployee.last_name}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, last_name: e.target.value })
                            }
                            className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                          Personal Email (Optional)
                        </label>
                        <input
                          type="email"
                          value={newEmployee.personal_email}
                          onChange={(e) =>
                            setNewEmployee({ ...newEmployee, personal_email: e.target.value })
                          }
                          className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                          placeholder="johnny_bravo@gmail.com"
                        />
                      </div>
                    </div>
                  )}

                  {addWizardStep === 2 && (
                    <div className="space-y-6">
                      <p className="text-[11px] text-zinc-500">
                        Choose generated email for new Workspace accounts, or existing email for already provisioned employees.
                      </p>
                      <div className="space-y-3">
                        <label className="block text-[10px] uppercase tracking-wider text-zinc-500">
                          Work Email Setup <span className="text-red-500">*</span>
                        </label>

                        {googleDomainAvailable ? (
                          <div className="space-y-3 rounded border border-white/10 bg-zinc-900/40 p-3">
                            <label className="flex items-start gap-3 cursor-pointer">
                              <input
                                type="radio"
                                name="email_entry_mode"
                                checked={emailEntryMode === 'generated'}
                                onChange={() => {
                                  setEmailEntryMode('generated');
                                  setSkipGoogleAutoProvision(false);
                                  if (!generatedEmailEdited) {
                                    setGeneratedEmailLocalPart(
                                      buildGeneratedEmailLocalPart(newEmployee.first_name, newEmployee.last_name)
                                    );
                                  }
                                }}
                                className="mt-0.5"
                              />
                              <div className="space-y-0.5">
                                <p className="text-xs text-zinc-200 font-medium">Generate from first + last name</p>
                                <p className="text-[11px] text-zinc-500">
                                  Domain detected from Google Workspace: <span className="text-zinc-300">@{normalizedGoogleDomain}</span>
                                </p>
                              </div>
                            </label>

                            <label className="flex items-start gap-3 cursor-pointer">
                              <input
                                type="radio"
                                name="email_entry_mode"
                                checked={emailEntryMode === 'existing'}
                                onChange={() => {
                                  setEmailEntryMode('existing');
                                  setSkipGoogleAutoProvision(true);
                                  if (!newEmployee.work_email && generatedEmailLocalPart) {
                                    setNewEmployee({
                                      ...newEmployee,
                                      work_email: `${generatedEmailLocalPart}@${normalizedGoogleDomain}`,
                                    });
                                  }
                                }}
                                className="mt-0.5"
                              />
                              <div className="space-y-0.5">
                                <p className="text-xs text-zinc-200 font-medium">Use existing work email</p>
                                <p className="text-[11px] text-zinc-500">
                                  Use this when the employee already has a company mailbox.
                                </p>
                              </div>
                            </label>
                          </div>
                        ) : (
                          <p className="text-[11px] text-zinc-500">
                            Configure Google Workspace domain in onboarding settings to auto-generate work emails.
                          </p>
                        )}
                      </div>

                      <div>
                        {emailEntryMode === 'generated' && googleDomainAvailable ? (
                          <div className="space-y-2">
                            <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                              Work Email Username <span className="text-red-500">*</span>
                            </label>
                            <div className="flex items-center border border-zinc-800 bg-zinc-900">
                              <input
                                type="text"
                                required
                                value={generatedEmailLocalPart}
                                onChange={(e) => {
                                  setGeneratedEmailEdited(true);
                                  setGeneratedEmailLocalPart(sanitizeEmailLocalPart(e.target.value));
                                }}
                                className="w-full px-3 py-2 bg-transparent text-white text-sm focus:outline-none placeholder-zinc-700"
                                placeholder="firstname.lastname"
                              />
                              <span className="px-3 py-2 text-sm text-zinc-400 border-l border-zinc-800">
                                @{normalizedGoogleDomain}
                              </span>
                            </div>
                            <p className="text-[11px] text-zinc-500">
                              Final email: <span className="text-zinc-300">{generatedEmailLocalPart || 'firstname.lastname'}@{normalizedGoogleDomain}</span>
                            </p>
                          </div>
                        ) : (
                          <div className="space-y-2">
                            <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                              Work Email <span className="text-red-500">*</span>
                            </label>
                            <input
                              type="email"
                              required
                              value={newEmployee.work_email}
                              onChange={(e) =>
                                setNewEmployee({ ...newEmployee, work_email: e.target.value })
                              }
                              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                              placeholder="johnny.bravo@energyco.com"
                            />
                            {googleDomainAvailable && (
                              <label className="inline-flex items-center gap-2 text-[11px] text-zinc-400">
                                <input
                                  type="checkbox"
                                  checked={skipGoogleAutoProvision}
                                  onChange={(e) => setSkipGoogleAutoProvision(e.target.checked)}
                                />
                                Skip Google auto-provisioning (employee already has Workspace account)
                              </label>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {addWizardStep === 3 && (
                    <div className="space-y-6">
                      <p className="text-[11px] text-zinc-500">
                        Final step: define where they work and verify a quick summary before creating.
                      </p>
                      <div className="space-y-2">
                        <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                          Work Location
                        </label>
                        <div className="grid grid-cols-2 gap-2">
                          <button
                            type="button"
                            onClick={() => setWorkLocationMode('remote')}
                            className={`border px-3 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${
                              workLocationMode === 'remote'
                                ? 'border-white/30 bg-zinc-800 text-white'
                                : 'border-zinc-800 text-zinc-500 hover:text-zinc-300'
                            }`}
                          >
                            Remote
                          </button>
                          <button
                            type="button"
                            onClick={() => setWorkLocationMode('office')}
                            className={`border px-3 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${
                              workLocationMode === 'office'
                                ? 'border-white/30 bg-zinc-800 text-white'
                                : 'border-zinc-800 text-zinc-500 hover:text-zinc-300'
                            }`}
                          >
                            Office / Store
                          </button>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          {workLocationMode === 'remote' ? (
                            <>
                              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                                Work State <span className="text-red-500">*</span>
                              </label>
                              <select
                                value={newEmployee.work_state}
                                onChange={(e) =>
                                  setNewEmployee({ ...newEmployee, work_state: e.target.value })
                                }
                                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors"
                              >
                                <option value="">Select state</option>
                                {US_STATES.map((state) => (
                                  <option key={state} value={state}>
                                    {state}
                                  </option>
                                ))}
                              </select>
                            </>
                          ) : (
                            <>
                              <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                                Office / Store <span className="text-red-500">*</span>
                              </label>
                              <input
                                type="text"
                                value={newEmployee.office_location}
                                onChange={(e) =>
                                  setNewEmployee({ ...newEmployee, office_location: e.target.value })
                                }
                                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                                placeholder="Downtown HQ"
                              />
                            </>
                          )}
                        </div>
                        <div>
                          <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                            Employment Type
                          </label>
                          <select
                            value={newEmployee.employment_type}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, employment_type: e.target.value })
                            }
                            className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors"
                          >
                            <option value="full_time">Full Time</option>
                            <option value="part_time">Part Time</option>
                            <option value="contractor">Contractor</option>
                            <option value="intern">Intern</option>
                          </select>
                        </div>
                      </div>

                      <div>
                        <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                          Start Date
                        </label>
                        <input
                          type="date"
                          value={newEmployee.start_date}
                          onChange={(e) =>
                            setNewEmployee({ ...newEmployee, start_date: e.target.value })
                          }
                          className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors [color-scheme:dark]"
                        />
                      </div>

                      <div className="rounded border border-white/10 bg-zinc-900/40 p-3 text-[11px] text-zinc-400 space-y-1">
                        <p>
                          <span className="text-zinc-200">Work email:</span>{' '}
                          {emailEntryMode === 'generated' ? generatedSingleWorkEmail : newEmployee.work_email}
                        </p>
                        <p>
                          <span className="text-zinc-200">Location:</span>{' '}
                          {workLocationMode === 'remote'
                            ? `Remote (${newEmployee.work_state || 'state required'})`
                            : `Office/Store (${newEmployee.office_location || 'location required'})`}
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-8 flex justify-end gap-3 pt-6 border-t border-white/10">
                  <button
                    type="button"
                    onClick={() => {
                      setShowAddModal(false);
                      resetAddEmployeeForm();
                    }}
                    className="px-4 py-2 text-zinc-500 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors"
                  >
                    Cancel
                  </button>
                  {addWizardStep > 1 && (
                    <button
                      type="button"
                      onClick={() => setAddWizardStep((prev) => (prev - 1) as AddWizardStep)}
                      className="px-4 py-2 border border-white/10 text-zinc-300 hover:text-white hover:border-white/20 text-xs font-bold uppercase tracking-wider transition-colors"
                    >
                      Back
                    </button>
                  )}
                  {addWizardStep < 3 && (
                    <button
                      type="button"
                      onClick={() => setAddWizardStep((prev) => (prev + 1) as AddWizardStep)}
                      disabled={(addWizardStep === 1 && !canProceedAddStep1) || (addWizardStep === 2 && !canProceedAddStep2)}
                      className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Next
                    </button>
                  )}
                  {addWizardStep === 3 && (
                    <button
                      type="submit"
                      disabled={submitting || !canSubmitSingleWizard}
                      className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {submitting ? 'Adding...' : 'Add Employee'}
                    </button>
                  )}
                </div>
              </form>
              </>
              )}
            </div>
        </div>
      )}

      {/* Batch Wizard Modal */}
      {showBatchWizardModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-6xl bg-zinc-950 border border-zinc-800 shadow-2xl rounded-sm max-h-[90vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <div>
                <h3 className="text-xl font-bold text-white uppercase tracking-tight">Batch Onboarding Wizard</h3>
                <p className="text-xs text-zinc-500 mt-1">Create up to 50 employees in one guided flow</p>
              </div>
              <button
                onClick={() => {
                  setShowBatchWizardModal(false);
                  setBatchResult(null);
                }}
                className="text-zinc-500 hover:text-white transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              <div className="rounded border border-white/10 bg-zinc-900/40 p-3">
                <p className="text-[10px] uppercase tracking-wider text-zinc-400">
                  Step {batchWizardStep} of 3
                </p>
                <p className="text-xs text-zinc-300 mt-1">
                  {batchWizardStep === 1 &&
                    'Set defaults for email and location handling. These apply to every row in step 2.'}
                  {batchWizardStep === 2 &&
                    'Enter up to 50 rows. Only rows with data are submitted, and invalid rows are blocked.'}
                  {batchWizardStep === 3 &&
                    'Review counts and submit. Any failed rows will be listed with row-level errors.'}
                </p>
              </div>

              <div className="flex items-center gap-3">
                {[1, 2, 3].map((step) => (
                  <div key={step} className="flex items-center gap-3">
                    <div
                      className={`h-6 w-6 rounded-full border text-[10px] font-bold flex items-center justify-center ${
                        batchWizardStep >= step
                          ? 'border-white text-white bg-zinc-800'
                          : 'border-zinc-700 text-zinc-600'
                      }`}
                    >
                      {step}
                    </div>
                    {step < 3 && <div className="h-px w-8 bg-zinc-800" />}
                  </div>
                ))}
              </div>

              {batchWizardStep === 1 && (
                <div className="space-y-6">
                  <div className="space-y-2">
                    <label className="block text-[10px] uppercase tracking-wider text-zinc-500">
                      Work Email Mode
                    </label>
                    {googleDomainAvailable ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        <button
                          type="button"
                          onClick={() => setBatchEmailMode('generated')}
                          className={`border p-3 text-left transition-colors ${
                            batchEmailMode === 'generated'
                              ? 'border-white/30 bg-zinc-800'
                              : 'border-zinc-800 hover:border-zinc-700'
                          }`}
                        >
                          <p className="text-xs font-bold text-zinc-200 uppercase tracking-wider">Generate From Name</p>
                          <p className="text-[11px] text-zinc-500 mt-1">Uses @{normalizedGoogleDomain}</p>
                        </button>
                        <button
                          type="button"
                          onClick={() => setBatchEmailMode('existing')}
                          className={`border p-3 text-left transition-colors ${
                            batchEmailMode === 'existing'
                              ? 'border-white/30 bg-zinc-800'
                              : 'border-zinc-800 hover:border-zinc-700'
                          }`}
                        >
                          <p className="text-xs font-bold text-zinc-200 uppercase tracking-wider">Existing Work Emails</p>
                          <p className="text-[11px] text-zinc-500 mt-1">For already-provisioned mailboxes</p>
                        </button>
                      </div>
                    ) : (
                      <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3 text-[11px] text-zinc-500">
                        Google Workspace domain is not configured, so batch mode uses existing work emails.
                      </div>
                    )}
                  </div>

                  <div className="space-y-2">
                    <label className="block text-[10px] uppercase tracking-wider text-zinc-500">
                      Work Location Mode
                    </label>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setBatchWorkLocationMode('remote')}
                        className={`border p-3 text-left transition-colors ${
                          batchWorkLocationMode === 'remote'
                            ? 'border-white/30 bg-zinc-800'
                            : 'border-zinc-800 hover:border-zinc-700'
                        }`}
                      >
                        <p className="text-xs font-bold text-zinc-200 uppercase tracking-wider">Remote</p>
                        <p className="text-[11px] text-zinc-500 mt-1">Each employee must include a work state</p>
                      </button>
                      <button
                        type="button"
                        onClick={() => setBatchWorkLocationMode('office')}
                        className={`border p-3 text-left transition-colors ${
                          batchWorkLocationMode === 'office'
                            ? 'border-white/30 bg-zinc-800'
                            : 'border-zinc-800 hover:border-zinc-700'
                        }`}
                      >
                        <p className="text-xs font-bold text-zinc-200 uppercase tracking-wider">Office / Store</p>
                        <p className="text-[11px] text-zinc-500 mt-1">Each employee must include office/store location</p>
                      </button>
                    </div>
                  </div>

                  <div className="rounded border border-white/10 bg-zinc-900/40 p-3 text-[11px] text-zinc-500 space-y-1">
                    <p>Step 2 lets you enter up to 50 rows.</p>
                    <p>Only non-empty rows are processed.</p>
                    <p>Use Add Row for more lines, and remove any line with the X action.</p>
                  </div>
                </div>
              )}

              {batchWizardStep === 2 && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs text-zinc-500 uppercase tracking-wider">
                      Rows: {batchRows.length}/{BATCH_MAX_ROWS}
                    </p>
                    <button
                      type="button"
                      onClick={addBatchRow}
                      disabled={batchRows.length >= BATCH_MAX_ROWS}
                      className="inline-flex items-center gap-2 px-3 py-1.5 border border-white/10 text-zinc-300 hover:text-white hover:border-white/20 text-[10px] font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Plus size={12} />
                      Add Row
                    </button>
                  </div>

                  <div className="overflow-auto border border-white/10">
                    <table className="min-w-[1200px] w-full text-xs">
                      <thead className="bg-zinc-900/80 text-zinc-500 uppercase tracking-wider text-[10px]">
                        <tr>
                          <th className="px-2 py-2 text-left">#</th>
                          <th className="px-2 py-2 text-left">First</th>
                          <th className="px-2 py-2 text-left">Last</th>
                          <th className="px-2 py-2 text-left">{batchEmailMode === 'generated' ? 'Generated Email' : 'Work Email'}</th>
                          <th className="px-2 py-2 text-left">Personal Email</th>
                          <th className="px-2 py-2 text-left">{batchWorkLocationMode === 'remote' ? 'State' : 'Office/Store'}</th>
                          <th className="px-2 py-2 text-left">Type</th>
                          <th className="px-2 py-2 text-left">Start</th>
                          {batchEmailMode === 'existing' && <th className="px-2 py-2 text-left">Skip Google</th>}
                          <th className="px-2 py-2 text-left">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {batchRows.map((row, idx) => {
                          const rowEmailPreview = resolveBatchRowWorkEmail(row);
                          const rowError = row.first_name || row.last_name || row.work_email || row.personal_email || row.work_state || row.office_location
                            ? batchRowValidationError(row)
                            : null;
                          return (
                            <tr key={row.id} className="border-t border-white/5 align-top">
                              <td className="px-2 py-2 text-zinc-500">{idx + 1}</td>
                              <td className="px-2 py-2">
                                <input
                                  type="text"
                                  value={row.first_name}
                                  onChange={(e) => updateBatchRowField(row.id, 'first_name', e.target.value)}
                                  className="w-full px-2 py-1.5 bg-zinc-900 border border-zinc-800 text-white"
                                />
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  type="text"
                                  value={row.last_name}
                                  onChange={(e) => updateBatchRowField(row.id, 'last_name', e.target.value)}
                                  className="w-full px-2 py-1.5 bg-zinc-900 border border-zinc-800 text-white"
                                />
                              </td>
                              <td className="px-2 py-2">
                                {batchEmailMode === 'generated' ? (
                                  <div className="px-2 py-1.5 bg-zinc-900 border border-zinc-800 text-zinc-300 min-w-[220px]">
                                    {rowEmailPreview || 'auto-generated from name'}
                                  </div>
                                ) : (
                                  <input
                                    type="email"
                                    value={row.work_email}
                                    onChange={(e) => updateBatchRowField(row.id, 'work_email', e.target.value)}
                                    className="w-full px-2 py-1.5 bg-zinc-900 border border-zinc-800 text-white"
                                  />
                                )}
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  type="email"
                                  value={row.personal_email}
                                  onChange={(e) => updateBatchRowField(row.id, 'personal_email', e.target.value)}
                                  className="w-full px-2 py-1.5 bg-zinc-900 border border-zinc-800 text-white"
                                />
                              </td>
                              <td className="px-2 py-2">
                                {batchWorkLocationMode === 'remote' ? (
                                  <select
                                    value={row.work_state}
                                    onChange={(e) => updateBatchRowField(row.id, 'work_state', e.target.value)}
                                    className="w-full px-2 py-1.5 bg-zinc-900 border border-zinc-800 text-white"
                                  >
                                    <option value="">State</option>
                                    {US_STATES.map((state) => (
                                      <option key={state} value={state}>
                                        {state}
                                      </option>
                                    ))}
                                  </select>
                                ) : (
                                  <input
                                    type="text"
                                    value={row.office_location}
                                    onChange={(e) => updateBatchRowField(row.id, 'office_location', e.target.value)}
                                    className="w-full px-2 py-1.5 bg-zinc-900 border border-zinc-800 text-white"
                                    placeholder="Downtown HQ"
                                  />
                                )}
                              </td>
                              <td className="px-2 py-2">
                                <select
                                  value={row.employment_type}
                                  onChange={(e) => updateBatchRowField(row.id, 'employment_type', e.target.value)}
                                  className="w-full px-2 py-1.5 bg-zinc-900 border border-zinc-800 text-white"
                                >
                                  <option value="full_time">Full Time</option>
                                  <option value="part_time">Part Time</option>
                                  <option value="contractor">Contractor</option>
                                  <option value="intern">Intern</option>
                                </select>
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  type="date"
                                  value={row.start_date}
                                  onChange={(e) => updateBatchRowField(row.id, 'start_date', e.target.value)}
                                  className="w-full px-2 py-1.5 bg-zinc-900 border border-zinc-800 text-white [color-scheme:dark]"
                                />
                              </td>
                              {batchEmailMode === 'existing' && (
                                <td className="px-2 py-2">
                                  <input
                                    type="checkbox"
                                    checked={row.skip_google_workspace_provisioning}
                                    onChange={(e) =>
                                      updateBatchRowField(
                                        row.id,
                                        'skip_google_workspace_provisioning',
                                        e.target.checked
                                      )
                                    }
                                  />
                                </td>
                              )}
                              <td className="px-2 py-2">
                                <button
                                  type="button"
                                  onClick={() => removeBatchRow(row.id)}
                                  className="text-zinc-500 hover:text-red-400"
                                  aria-label="Remove row"
                                >
                                  <X size={14} />
                                </button>
                                {rowError && (
                                  <p className="mt-2 text-[10px] text-red-400 whitespace-nowrap">{rowError}</p>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {batchWizardStep === 3 && (
                <div className="space-y-4">
                  <div className="rounded border border-white/10 bg-zinc-900/40 p-4 text-xs text-zinc-400 space-y-1">
                    <p>
                      Ready to create <span className="text-zinc-200 font-semibold">{batchRowsWithInput.length}</span> employees.
                    </p>
                    <p>Email mode: <span className="text-zinc-200">{batchEmailMode === 'generated' ? 'Generated' : 'Existing'}</span></p>
                    <p>Location mode: <span className="text-zinc-200">{batchWorkLocationMode === 'remote' ? 'Remote (state)' : 'Office/Store'}</span></p>
                  </div>

                  {batchResult && (
                    <div className="space-y-3">
                      <div className="grid grid-cols-2 gap-3">
                        <div className="border border-emerald-500/20 bg-emerald-500/5 p-3">
                          <p className="text-2xl font-bold text-emerald-400">{batchResult.created}</p>
                          <p className="text-[10px] text-zinc-500 uppercase tracking-wider">Created</p>
                        </div>
                        <div className="border border-red-500/20 bg-red-500/5 p-3">
                          <p className="text-2xl font-bold text-red-400">{batchResult.failed}</p>
                          <p className="text-[10px] text-zinc-500 uppercase tracking-wider">Failed</p>
                        </div>
                      </div>
                      {batchResult.errors.length > 0 && (
                        <div className="max-h-56 overflow-y-auto space-y-2 border border-red-500/20 bg-red-500/5 p-3">
                          {batchResult.errors.map((err) => (
                            <div key={`${err.row_number}-${err.name}`} className="text-xs">
                              <p className="text-red-300">
                                Row {err.row_number} {err.name ? `(${err.name})` : ''}
                              </p>
                              <p className="text-zinc-500">{err.error}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="p-6 border-t border-white/10 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setShowBatchWizardModal(false);
                  setBatchResult(null);
                }}
                className="px-4 py-2 text-zinc-500 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors"
              >
                Cancel
              </button>
              {batchWizardStep > 1 && !batchSubmitting && (
                <button
                  type="button"
                  onClick={() => setBatchWizardStep((prev) => (prev - 1) as BatchWizardStep)}
                  className="px-4 py-2 border border-white/10 text-zinc-300 hover:text-white hover:border-white/20 text-xs font-bold uppercase tracking-wider transition-colors"
                >
                  Back
                </button>
              )}
              {batchWizardStep < 3 && (
                <button
                  type="button"
                  onClick={() => setBatchWizardStep((prev) => (prev + 1) as BatchWizardStep)}
                  disabled={
                    (batchWizardStep === 1 && batchEmailMode === 'generated' && !googleDomainAvailable) ||
                    (batchWizardStep === 2 && !canProceedBatchStep2)
                  }
                  className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              )}
              {batchWizardStep === 3 && !batchResult && (
                <button
                  type="button"
                  onClick={handleBatchCreate}
                  disabled={batchSubmitting || !canProceedBatchStep2}
                  className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {batchSubmitting ? 'Creating...' : `Create ${batchRowsWithInput.length} Employees`}
                </button>
              )}
              {batchWizardStep === 3 && batchResult && (
                <button
                  type="button"
                  onClick={() => {
                    setShowBatchWizardModal(false);
                    setBatchResult(null);
                  }}
                  className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
                >
                  Done
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Bulk Upload Modal */}
      {showBulkUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-2xl bg-zinc-950 border border-zinc-800 shadow-2xl rounded-sm max-h-[90vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <div>
                <h3 className="text-xl font-bold text-white uppercase tracking-tight">Bulk Upload Employees</h3>
                <p className="text-xs text-zinc-500 mt-1">Upload a CSV file to add multiple employees at once</p>
              </div>
              <button
                onClick={() => {
                  setShowBulkUploadModal(false);
                  setUploadFile(null);
                  setUploadResult(null);
                }}
                className="text-zinc-500 hover:text-white transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6">
              {!uploadResult ? (
                <div className="space-y-6">
                  {/* Download Template Button */}
                  <div className="bg-zinc-900/50 border border-zinc-800 p-4 rounded">
                    <div className="flex items-start gap-3">
                      <Download className="text-emerald-400 mt-0.5" size={16} />
                      <div className="flex-1">
                        <h4 className="text-sm font-bold text-white uppercase tracking-wide mb-1">Step 1: Download Template</h4>
                        <p className="text-xs text-zinc-400 mb-3">
                          Get the CSV template with the correct format and column headers.
                        </p>
                        <button
                          onClick={handleDownloadTemplate}
                          className="inline-flex items-center gap-2 px-4 py-2 border border-white/10 text-zinc-300 hover:text-white hover:border-white/20 text-xs font-bold uppercase tracking-wider transition-colors"
                        >
                          <Download size={12} />
                          Download Template
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Upload Area */}
                  <div className="bg-zinc-900/50 border border-zinc-800 p-4 rounded">
                    <div className="flex items-start gap-3 mb-4">
                      <Upload className="text-emerald-400 mt-0.5" size={16} />
                      <div className="flex-1">
                        <h4 className="text-sm font-bold text-white uppercase tracking-wide mb-1">Step 2: Upload CSV</h4>
                        <p className="text-xs text-zinc-400">
                          Drag and drop your CSV file or click to browse.
                        </p>
                      </div>
                    </div>

                    <div
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                      className={`border-2 border-dashed rounded p-8 text-center transition-colors ${
                        isDragging
                          ? 'border-emerald-500 bg-emerald-500/5'
                          : uploadFile
                          ? 'border-emerald-500/30 bg-emerald-500/5'
                          : 'border-zinc-700 bg-zinc-900/30 hover:border-zinc-600'
                      }`}
                    >
                      {uploadFile ? (
                        <div className="space-y-3">
                          <CheckCircle className="w-10 h-10 text-emerald-400 mx-auto" />
                          <div>
                            <p className="text-sm font-medium text-white">{uploadFile.name}</p>
                            <p className="text-xs text-zinc-500 mt-1">
                              {(uploadFile.size / 1024).toFixed(2)} KB
                            </p>
                          </div>
                          <button
                            onClick={() => setUploadFile(null)}
                            className="text-xs text-zinc-400 hover:text-white uppercase tracking-wider"
                          >
                            Remove File
                          </button>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <Upload className="w-10 h-10 text-zinc-600 mx-auto" />
                          <div>
                            <p className="text-sm font-medium text-zinc-300">Drop your CSV file here</p>
                            <p className="text-xs text-zinc-500 mt-1">or</p>
                          </div>
                          <label className="inline-block">
                            <input
                              type="file"
                              accept=".csv"
                              onChange={(e) => handleFileSelect(e.target.files?.[0] || null)}
                              className="hidden"
                            />
                            <span className="inline-flex items-center gap-2 px-4 py-2 border border-white/10 text-zinc-300 hover:text-white hover:border-white/20 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer">
                              Browse Files
                            </span>
                          </label>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Options */}
                  {uploadFile && (
                    <div className="bg-zinc-900/50 border border-zinc-800 p-4 rounded">
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          id="send-invites"
                          checked={sendInvitationsOnUpload}
                          onChange={(e) => setSendInvitationsOnUpload(e.target.checked)}
                          className="w-4 h-4 rounded border-zinc-700 bg-zinc-900 text-emerald-500 focus:ring-emerald-500 focus:ring-offset-0"
                        />
                        <label htmlFor="send-invites" className="text-sm text-white cursor-pointer">
                          Send invitation emails automatically
                        </label>
                      </div>
                      <p className="text-xs text-zinc-500 mt-2 ml-7">
                        Employees will receive an email to set up their account and access the portal.
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                /* Upload Results */
                <div className="space-y-4">
                  <div className="bg-zinc-900/50 border border-zinc-800 p-6 rounded">
                    <div className="flex items-center gap-3 mb-4">
                      <CheckCircle className="text-emerald-400" size={24} />
                      <div>
                        <h4 className="text-lg font-bold text-white uppercase tracking-wide">Upload Complete</h4>
                        <p className="text-xs text-zinc-400 mt-1">
                          {uploadResult.created} of {uploadResult.total_rows} employees created successfully
                        </p>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-4 mt-6">
                      <div className="bg-zinc-900 border border-zinc-800 p-4 rounded text-center">
                        <div className="text-2xl font-bold text-emerald-400">{uploadResult.created}</div>
                        <div className="text-xs text-zinc-500 uppercase tracking-wider mt-1">Created</div>
                      </div>
                      <div className="bg-zinc-900 border border-zinc-800 p-4 rounded text-center">
                        <div className="text-2xl font-bold text-red-400">{uploadResult.failed}</div>
                        <div className="text-xs text-zinc-500 uppercase tracking-wider mt-1">Failed</div>
                      </div>
                      <div className="bg-zinc-900 border border-zinc-800 p-4 rounded text-center">
                        <div className="text-2xl font-bold text-zinc-400">{uploadResult.total_rows}</div>
                        <div className="text-xs text-zinc-500 uppercase tracking-wider mt-1">Total</div>
                      </div>
                    </div>
                  </div>

                  {uploadResult.errors && uploadResult.errors.length > 0 && (
                    <div className="bg-red-500/5 border border-red-500/20 rounded p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <AlertTriangle className="text-red-400" size={16} />
                        <h5 className="text-sm font-bold text-red-400 uppercase tracking-wide">
                          Errors ({uploadResult.errors.length})
                        </h5>
                      </div>
                      <div className="space-y-2 max-h-60 overflow-y-auto">
                        {uploadResult.errors.map((err: any, idx: number) => (
                          <div key={idx} className="bg-zinc-950/50 border border-red-500/10 p-3 rounded text-xs">
                            <div className="flex items-center gap-2 text-red-400 font-medium mb-1">
                              <span>Row {err.row}</span>
                              {err.email && <span className="text-zinc-600">•</span>}
                              {err.email && <span className="text-zinc-400 font-mono">{err.email}</span>}
                            </div>
                            <p className="text-zinc-500">{err.error}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Send Invitations button — shown when auto-send was off and employees were created */}
                  {!sendInvitationsOnUpload && uploadResult.created > 0 && uploadResult.employee_ids?.length > 0 && (
                    <div className="bg-zinc-900/50 border border-zinc-800 p-4 rounded">
                      {bulkInviteResult ? (
                        <div className="flex items-center gap-3">
                          <CheckCircle className="text-emerald-400" size={18} />
                          <div>
                            <p className="text-sm text-white font-medium">
                              {bulkInviteResult.sent} invitation{bulkInviteResult.sent !== 1 ? 's' : ''} sent
                            </p>
                            {bulkInviteResult.failed > 0 && (
                              <p className="text-xs text-red-400 mt-1">
                                {bulkInviteResult.failed} failed to send
                              </p>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm text-white font-medium">Send invitation emails?</p>
                            <p className="text-xs text-zinc-500 mt-1">
                              Invite {uploadResult.created} new employee{uploadResult.created !== 1 ? 's' : ''} to set up their portal accounts
                            </p>
                          </div>
                          <button
                            onClick={async () => {
                              setBulkInviting(true);
                              try {
                                const token = getAccessToken();
                                const res = await fetch(`${API_BASE}/employees/bulk-invite`, {
                                  method: 'POST',
                                  headers: {
                                    Authorization: `Bearer ${token}`,
                                    'Content-Type': 'application/json',
                                  },
                                  body: JSON.stringify(uploadResult.employee_ids),
                                });
                                if (res.ok) {
                                  const data = await res.json();
                                  setBulkInviteResult({ sent: data.sent, failed: data.failed });
                                }
                              } catch (err) {
                                console.error('Bulk invite failed:', err);
                              } finally {
                                setBulkInviting(false);
                              }
                            }}
                            disabled={bulkInviting}
                            className="flex items-center gap-2 px-4 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 shrink-0"
                          >
                            {bulkInviting ? (
                              <>
                                <span className="w-3 h-3 border-2 border-black/20 border-t-black rounded-full animate-spin" />
                                Sending...
                              </>
                            ) : (
                              <>
                                <Mail size={14} />
                                Send Invitations
                              </>
                            )}
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  <button
                    onClick={() => {
                      setShowBulkUploadModal(false);
                      setUploadFile(null);
                      setUploadResult(null);
                      setBulkInviteResult(null);
                    }}
                    className="w-full px-4 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
                  >
                    Done
                  </button>
                </div>
              )}
            </div>

            {!uploadResult && uploadFile && (
              <div className="p-6 border-t border-white/10 flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowBulkUploadModal(false);
                    setUploadFile(null);
                    setUploadResult(null);
                  }}
                  className="px-4 py-2 text-zinc-500 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleBulkUpload}
                  disabled={uploadLoading || !uploadFile}
                  className="flex items-center gap-2 px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {uploadLoading ? (
                    <>
                      <span className="w-3 h-3 border-2 border-black/20 border-t-black rounded-full animate-spin" />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload size={14} />
                      Upload Employees
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
