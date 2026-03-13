import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, X, Mail, Upload, ClipboardCheck, Download, CheckCircle, AlertTriangle } from 'lucide-react';
import { getAccessToken, provisioning, onboardingDraft } from '../../api/client';
import { useIsLightMode } from '../../hooks/useIsLightMode';
import type { GoogleWorkspaceConnectionStatus } from '../../types';
import OnboardingAgentConsole from '../../components/OnboardingAgentConsole';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

/* ────────── Types ────────── */

interface NewEmployee {
  work_email: string;
  personal_email: string;
  first_name: string;
  last_name: string;
  office_location: string;
  work_state: string;
  employment_type: string;
  start_date: string;
  pay_classification: string;
  pay_rate: string;
  work_city: string;
  work_zip: string;
  job_title: string;
  department: string;
}

type EmailEntryMode = 'generated' | 'existing';
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
  pay_classification: string;
  pay_rate: string;
  work_city: string;
  work_zip: string;
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

/* ────────── Utility functions ────────── */

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
    pay_classification: '',
    pay_rate: '',
    work_city: '',
    work_zip: '',
  };
}

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';

  if (contentType.includes('application/json')) {
    const payload = await response.json().catch(() => null);
    if (payload && typeof payload === 'object') {
      const data = payload as { detail?: unknown; message?: unknown; error?: unknown };
      const candidate = data.detail ?? data.message ?? data.error;
      if (typeof candidate === 'string' && candidate.trim()) {
        return candidate;
      }
    }
  }

  const text = (await response.text().catch(() => '')).trim();
  if (!text || /^internal server error$/i.test(text)) {
    return fallback;
  }

  return text;
}

/* ────────── Theme ────────── */

const LT = {
  card: 'bg-stone-100 rounded-2xl',
  innerEl: 'bg-stone-200/60 rounded-xl border border-stone-200',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 text-stone-500 hover:text-zinc-900 hover:border-stone-400',
  btnSecondaryActive: 'border-stone-400 text-zinc-900 bg-stone-200',
  modalBg: 'bg-stone-100 border border-stone-200 shadow-2xl rounded-2xl',
  modalHeader: 'border-b border-stone-200',
  modalFooter: 'border-t border-stone-200',
  inputCls: 'bg-white border border-stone-300 text-zinc-900 text-sm rounded-xl focus:outline-none focus:border-stone-400 placeholder:text-stone-400 transition-colors',
  batchInputCls: 'bg-white border border-stone-300 text-zinc-900 rounded-lg',
  alertWarn: 'border border-amber-300 bg-amber-50',
  alertWarnText: 'text-amber-700',
  alertError: 'bg-red-50 border border-red-300',
  alertErrorText: 'text-red-700',
  wizardActive: 'border-zinc-900 text-zinc-50 bg-zinc-900',
  wizardInactive: 'border-stone-300 text-stone-400',
  separator: 'bg-stone-300',
  closeBtnCls: 'text-stone-400 hover:text-zinc-900 transition-colors',
  cancelBtn: 'text-stone-500 hover:text-zinc-900',
  genPreview: 'bg-stone-200/60 border border-stone-300 text-stone-600',
  tableHeader: 'bg-stone-200 text-stone-500',
  resultSuccess: 'border border-emerald-300 bg-emerald-50',
  resultFail: 'border border-red-300 bg-red-50',
  uploadZone: 'border-stone-400 bg-white hover:border-stone-500',
  uploadZoneDrag: 'border-emerald-500 bg-emerald-50',
  uploadZoneDone: 'border-emerald-400 bg-emerald-50',
  resultCard: 'bg-white border border-stone-200',
} as const;

const DK = {
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  innerEl: 'bg-zinc-900/40 rounded-xl border border-white/10',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  btnPrimary: 'bg-zinc-100 text-zinc-900 hover:bg-white',
  btnSecondary: 'border border-white/10 text-zinc-500 hover:text-zinc-100 hover:border-white/20',
  btnSecondaryActive: 'border-white/20 text-zinc-100 bg-zinc-800',
  modalBg: 'bg-zinc-900 border border-white/10 shadow-2xl rounded-2xl',
  modalHeader: 'border-b border-white/10',
  modalFooter: 'border-t border-white/10',
  inputCls: 'bg-zinc-800 border border-white/10 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-white/20 placeholder:text-zinc-600 transition-colors',
  batchInputCls: 'bg-zinc-800 border border-white/10 text-zinc-100 rounded-lg',
  alertWarn: 'border border-amber-500/30 bg-amber-950/30',
  alertWarnText: 'text-amber-400',
  alertError: 'bg-red-950/30 border border-red-500/30',
  alertErrorText: 'text-red-400',
  wizardActive: 'border-zinc-100 text-zinc-900 bg-zinc-100',
  wizardInactive: 'border-zinc-700 text-zinc-600',
  separator: 'bg-zinc-700',
  closeBtnCls: 'text-zinc-500 hover:text-zinc-100 transition-colors',
  cancelBtn: 'text-zinc-500 hover:text-zinc-100',
  genPreview: 'bg-zinc-800/60 border border-white/10 text-zinc-400',
  tableHeader: 'bg-zinc-800 text-zinc-500',
  resultSuccess: 'border border-emerald-500/30 bg-emerald-950/40',
  resultFail: 'border border-red-500/30 bg-red-950/40',
  uploadZone: 'border-zinc-600 bg-zinc-800 hover:border-zinc-500',
  uploadZoneDrag: 'border-emerald-500/50 bg-emerald-950/20',
  uploadZoneDone: 'border-emerald-500/40 bg-emerald-950/20',
  resultCard: 'bg-zinc-800 border border-white/10',
} as const;

/* ────────── US States ────────── */

const US_STATES = [
  { value: 'AL', label: 'Alabama' }, { value: 'AK', label: 'Alaska' },
  { value: 'AZ', label: 'Arizona' }, { value: 'AR', label: 'Arkansas' },
  { value: 'CA', label: 'California' }, { value: 'CO', label: 'Colorado' },
  { value: 'CT', label: 'Connecticut' }, { value: 'DE', label: 'Delaware' },
  { value: 'FL', label: 'Florida' }, { value: 'GA', label: 'Georgia' },
  { value: 'HI', label: 'Hawaii' }, { value: 'ID', label: 'Idaho' },
  { value: 'IL', label: 'Illinois' }, { value: 'IN', label: 'Indiana' },
  { value: 'IA', label: 'Iowa' }, { value: 'KS', label: 'Kansas' },
  { value: 'KY', label: 'Kentucky' }, { value: 'LA', label: 'Louisiana' },
  { value: 'ME', label: 'Maine' }, { value: 'MD', label: 'Maryland' },
  { value: 'MA', label: 'Massachusetts' }, { value: 'MI', label: 'Michigan' },
  { value: 'MN', label: 'Minnesota' }, { value: 'MS', label: 'Mississippi' },
  { value: 'MO', label: 'Missouri' }, { value: 'MT', label: 'Montana' },
  { value: 'NE', label: 'Nebraska' }, { value: 'NV', label: 'Nevada' },
  { value: 'NH', label: 'New Hampshire' }, { value: 'NJ', label: 'New Jersey' },
  { value: 'NM', label: 'New Mexico' }, { value: 'NY', label: 'New York' },
  { value: 'NC', label: 'North Carolina' }, { value: 'ND', label: 'North Dakota' },
  { value: 'OH', label: 'Ohio' }, { value: 'OK', label: 'Oklahoma' },
  { value: 'OR', label: 'Oregon' }, { value: 'PA', label: 'Pennsylvania' },
  { value: 'RI', label: 'Rhode Island' }, { value: 'SC', label: 'South Carolina' },
  { value: 'SD', label: 'South Dakota' }, { value: 'TN', label: 'Tennessee' },
  { value: 'TX', label: 'Texas' }, { value: 'UT', label: 'Utah' },
  { value: 'VT', label: 'Vermont' }, { value: 'VA', label: 'Virginia' },
  { value: 'WA', label: 'Washington' }, { value: 'WV', label: 'West Virginia' },
  { value: 'WI', label: 'Wisconsin' }, { value: 'WY', label: 'Wyoming' },
  { value: 'DC', label: 'Washington D.C.' },
];

/* ────────── Component ────────── */

interface EmployeeIntakeProps {
  onCreated?: () => void;
}

export function EmployeeIntake({ onCreated }: EmployeeIntakeProps) {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  // Error state
  const [error, setError] = useState<string | null>(null);

  // Google Workspace status
  const [googleWorkspaceStatus, setGoogleWorkspaceStatus] = useState<GoogleWorkspaceConnectionStatus | null>(null);

  // Add Employee state
  const [showAddModal, setShowAddModal] = useState(false);
  const [newEmployee, setNewEmployee] = useState<NewEmployee>({
    work_email: '',
    personal_email: '',
    first_name: '',
    last_name: '',
    office_location: '',
    work_state: '',
    employment_type: 'full_time',
    start_date: new Date().toISOString().split('T')[0],
    pay_classification: '',
    pay_rate: '',
    work_city: '',
    work_zip: '',
    job_title: '',
    department: '',
  });
  const [emailEntryMode, setEmailEntryMode] = useState<EmailEntryMode>('existing');
  const [generatedEmailLocalPart, setGeneratedEmailLocalPart] = useState('');
  const [generatedEmailEdited, setGeneratedEmailEdited] = useState(false);
  const [skipGoogleAutoProvision, setSkipGoogleAutoProvision] = useState(false);
  const [addWizardStep, setAddWizardStep] = useState<AddWizardStep>(1);
  const [submitting, setSubmitting] = useState(false);
  const [agentEmployee, setAgentEmployee] = useState<{
    id: string; name: string; workEmail: string; personalEmail: string;
  } | null>(null);

  // Batch Wizard state
  const [showBatchWizardModal, setShowBatchWizardModal] = useState(false);
  const [batchWizardStep, setBatchWizardStep] = useState<BatchWizardStep>(1);
  const [batchEmailMode, setBatchEmailMode] = useState<EmailEntryMode>('existing');
  const [batchRows, setBatchRows] = useState<BatchEmployeeRow[]>([]);
  const [batchSubmitting, setBatchSubmitting] = useState(false);
  const [batchResult, setBatchResult] = useState<BatchCreateResult | null>(null);
  const [draftLoaded, setDraftLoaded] = useState(false);
  const [draftDirty, setDraftDirty] = useState(false);
  const [draftSaving, setDraftSaving] = useState(false);
  const draftSnapshotRef = useRef<string>('');

  // Bulk Upload state
  const [showBulkUploadModal, setShowBulkUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [sendInvitationsOnUpload, setSendInvitationsOnUpload] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [bulkInviting, setBulkInviting] = useState(false);
  const [bulkInviteResult, setBulkInviteResult] = useState<{ sent: number; failed: number } | null>(null);

  // Computed
  const normalizedGoogleDomain = (googleWorkspaceStatus?.domain || '')
    .trim()
    .replace(/^@/, '')
    .toLowerCase();
  const googleDomainAvailable = Boolean(
    normalizedGoogleDomain &&
      googleWorkspaceStatus?.connected &&
      googleWorkspaceStatus.status === 'connected'
  );

  /* ────────── Google Workspace fetch ────────── */

  const fetchGoogleWorkspaceStatus = async () => {
    try {
      const status = await provisioning.getGoogleWorkspaceStatus();
      setGoogleWorkspaceStatus(status);
    } catch (err) {
      console.error('Failed to fetch Google Workspace provisioning status:', err);
      setGoogleWorkspaceStatus(null);
    }
  };

  useEffect(() => {
    fetchGoogleWorkspaceStatus();
  }, []);

  /* ────────── Add Employee helpers ────────── */

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
      pay_classification: '',
      pay_rate: '',
      work_city: '',
      work_zip: '',
      job_title: '',
      department: '',
    });
    setEmailEntryMode(googleDomainAvailable ? 'generated' : 'existing');
    setGeneratedEmailLocalPart('');
    setGeneratedEmailEdited(false);
    setSkipGoogleAutoProvision(false);
    setAddWizardStep(1);
  }, [googleDomainAvailable]);

  useEffect(() => {
    if (!showAddModal) return;
    setEmailEntryMode(googleDomainAvailable ? 'generated' : 'existing');
    setGeneratedEmailEdited(false);
    setSkipGoogleAutoProvision(false);
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

  const generatedSingleWorkEmail = googleDomainAvailable && generatedEmailLocalPart
    ? `${generatedEmailLocalPart}@${normalizedGoogleDomain}`
    : '';
  const canProceedAddStep1 = Boolean(
    newEmployee.first_name.trim() && newEmployee.last_name.trim()
  );
  const canProceedAddStep2 = emailEntryMode === 'generated'
    ? Boolean(generatedSingleWorkEmail)
    : looksLikeEmail(newEmployee.work_email);
  const hasSingleLocation = Boolean(newEmployee.work_state);
  const canSubmitSingleWizard = canProceedAddStep1 && canProceedAddStep2 && hasSingleLocation;

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
      if (!newEmployee.work_state) {
        throw new Error('Work state is required');
      }

      const payload = {
        email: resolvedWorkEmail,
        work_email: resolvedWorkEmail,
        personal_email: newEmployee.personal_email || undefined,
        first_name: newEmployee.first_name,
        last_name: newEmployee.last_name,
        work_state: newEmployee.work_state || undefined,
        address: newEmployee.office_location || undefined,
        employment_type: newEmployee.employment_type,
        start_date: newEmployee.start_date,
        skip_google_workspace_provisioning:
          emailEntryMode === 'existing' && skipGoogleAutoProvision,
        pay_classification: newEmployee.pay_classification || undefined,
        pay_rate: newEmployee.pay_rate ? parseFloat(newEmployee.pay_rate) : undefined,
        work_city: newEmployee.work_city || undefined,
        work_zip: newEmployee.work_zip || undefined,
        job_title: newEmployee.job_title || undefined,
        department: newEmployee.department || undefined,
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
        throw new Error(await readErrorMessage(response, 'Failed to add employee'));
      }

      const createdEmployee = await response.json();

      setAgentEmployee({
        id: createdEmployee.id,
        name: `${newEmployee.first_name} ${newEmployee.last_name}`,
        workEmail: resolvedWorkEmail,
        personalEmail: newEmployee.personal_email,
      });

      onCreated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  /* ────────── Batch Wizard helpers ────────── */

  const resetBatchWizard = useCallback(() => {
    const defaultStartDate = new Date().toISOString().split('T')[0];
    setBatchWizardStep(1);
    setBatchEmailMode(googleDomainAvailable ? 'generated' : 'existing');
    setBatchRows([
      createBatchRow(defaultStartDate),
      createBatchRow(defaultStartDate),
      createBatchRow(defaultStartDate),
      createBatchRow(defaultStartDate),
      createBatchRow(defaultStartDate),
    ]);
    setBatchResult(null);
  }, [googleDomainAvailable]);

  // Dirty detection for batch wizard draft
  useEffect(() => {
    if (!draftLoaded) return;
    const current = JSON.stringify({ batchRows, emailMode: batchEmailMode, wizardStep: batchWizardStep });
    setDraftDirty(current !== draftSnapshotRef.current);
  }, [batchRows, batchEmailMode, batchWizardStep, draftLoaded]);

  // Autosave batch wizard draft with 5-second debounce
  const DRAFT_AUTOSAVE_MS = 5000;
  useEffect(() => {
    if (!draftLoaded || !draftDirty) return;
    const timer = setTimeout(async () => {
      setDraftSaving(true);
      try {
        const state = { batchRows, emailMode: batchEmailMode, wizardStep: batchWizardStep };
        await onboardingDraft.save(state as unknown as Record<string, unknown>);
        draftSnapshotRef.current = JSON.stringify(state);
        setDraftDirty(false);
      } catch {
        // silently fail autosave
      } finally {
        setDraftSaving(false);
      }
    }, DRAFT_AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [draftLoaded, draftDirty, batchRows, batchEmailMode, batchWizardStep]);

  const BATCH_MAX_ROWS = 50;
  const batchRowsWithInput = batchRows.filter((row) =>
    Boolean(
      row.first_name.trim() ||
        row.last_name.trim() ||
        row.work_email.trim() ||
        row.personal_email.trim() ||
        row.work_state.trim()
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

    if (!row.work_state.trim()) {
      return 'Work state is required';
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
          work_state: row.work_state.trim() || undefined,
          address: row.office_location.trim() || undefined,
          employment_type: row.employment_type,
          start_date: row.start_date,
          skip_google_workspace_provisioning:
            batchEmailMode === 'existing' ? row.skip_google_workspace_provisioning : false,
          pay_classification: row.pay_classification || undefined,
          pay_rate: row.pay_rate ? parseFloat(row.pay_rate) : undefined,
          work_city: row.work_city || undefined,
          work_zip: row.work_zip || undefined,
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
            failed += 1;
            errors.push({
              row_number: idx + 1,
              name: `${row.first_name} ${row.last_name}`.trim() || `Row ${idx + 1}`,
              error: await readErrorMessage(response, 'Failed to create employee'),
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
      onCreated?.();
      // Clear the draft after a successful batch submission
      try { await onboardingDraft.clear(); } catch { /* ignore */ }
      draftSnapshotRef.current = '';
      setDraftDirty(false);
    } finally {
      setBatchSubmitting(false);
    }
  };

  const handleOpenBatchWizard = async () => {
    resetBatchWizard();
    setDraftLoaded(false);
    setDraftDirty(false);
    setShowBatchWizardModal(true);
    try {
      const draft = await onboardingDraft.get();
      if (draft?.draft_state && Array.isArray((draft.draft_state as Record<string, unknown>).batchRows) && ((draft.draft_state as Record<string, unknown>).batchRows as unknown[]).length > 0) {
        const s = draft.draft_state as Record<string, unknown>;
        setBatchRows(s.batchRows as BatchEmployeeRow[]);
        setBatchEmailMode((s.emailMode as EmailEntryMode) ?? 'existing');
        setBatchWizardStep((s.wizardStep as BatchWizardStep) ?? 1);
      }
      draftSnapshotRef.current = JSON.stringify(draft?.draft_state ?? {});
    } catch {
      draftSnapshotRef.current = '';
    }
    setDraftLoaded(true);
  };

  /* ────────── Bulk Upload helpers ────────── */

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
        throw new Error(await readErrorMessage(response, 'Failed to upload CSV'));
      }

      const result = await response.json();
      setUploadResult(result);
      onCreated?.();
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

  /* ────────── Render ────────── */

  return (
    <div className="space-y-4">
      {/* Intro text */}
      <div className={`${isLight ? 'bg-stone-200/60 border border-stone-200' : 'bg-zinc-900'} rounded-2xl p-5 text-[11px] ${t.textDim} space-y-1`}>
        <p className={`uppercase tracking-wider ${t.textMuted}`}>Onboarding flows</p>
        <p>
          Use <span className={`${t.textMain} font-medium`}>Add Employee</span> for one hire,{' '}
          <span className={`${t.textMain} font-medium`}>Batch Wizard</span> for up to 50 hires, or{' '}
          <span className={`${t.textMain} font-medium`}>Bulk CSV</span> when you already have a spreadsheet.
        </p>
      </div>

      {/* Error message */}
      {error && (
        <div className={`${t.alertError} rounded-xl p-4 flex items-center justify-between gap-4`}>
          <div className="flex items-center gap-3">
            <AlertTriangle className={t.alertErrorText} size={16} />
            <p className={`text-sm ${t.alertErrorText} font-mono`}>{error}</p>
          </div>
          <button
            onClick={() => setError(null)}
            className={`text-xs ${t.alertErrorText} uppercase tracking-wider font-bold shrink-0`}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <button
          onClick={() => { resetAddEmployeeForm(); setShowAddModal(true); }}
          className={`flex items-center justify-center gap-2 px-4 sm:px-6 py-2.5 ${t.btnPrimary} text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
        >
          <Plus size={14} /> Add Employee
        </button>
        <button
          onClick={handleOpenBatchWizard}
          className={`flex items-center justify-center gap-2 px-3 sm:px-4 py-2.5 ${t.btnSecondary} text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
        >
          <ClipboardCheck size={14} /> Batch Wizard
        </button>
        <button
          onClick={() => setShowBulkUploadModal(true)}
          className={`flex items-center justify-center gap-2 px-3 sm:px-4 py-2.5 ${t.btnSecondary} text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
        >
          <Upload size={14} /> Bulk CSV
        </button>
      </div>

      {/* ────────── Add Employee Modal ────────── */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className={`w-full max-w-lg ${t.modalBg} max-h-[90vh] overflow-hidden flex flex-col`} onClick={(e) => e.stopPropagation()}>
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
                  onViewProfile={(_id) => {
                    setShowAddModal(false);
                    setAgentEmployee(null);
                  }}
                  onClose={() => {
                    setShowAddModal(false);
                    setAgentEmployee(null);
                    resetAddEmployeeForm();
                  }}
                />
              ) : (
              <>
              <div className={`flex items-center justify-between p-6 ${t.modalHeader}`}>
                  <h3 className={`text-xl font-bold ${t.textMain} uppercase tracking-tight`}>Add Personnel</h3>
                  <button
                    onClick={() => {
                      setShowAddModal(false);
                      resetAddEmployeeForm();
                    }}
                    className={t.closeBtnCls}
                  >
                    <X size={20} />
                  </button>
              </div>

              <form onSubmit={handleAddEmployee} className="flex-1 overflow-y-auto p-8">
                <div className="space-y-6">
                  <div className={`${t.innerEl} p-3`}>
                    <p className={`text-[10px] uppercase tracking-wider ${t.textMuted}`}>
                      Step {addWizardStep} of 3
                    </p>
                    <p className={`text-xs ${t.textDim} mt-1`}>
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
                            addWizardStep >= step ? t.wizardActive : t.wizardInactive
                          }`}
                        >
                          {step}
                        </div>
                        {step < 3 && <div className={`h-px w-8 ${t.separator}`} />}
                      </div>
                    ))}
                  </div>

                  {addWizardStep === 1 && (
                    <div className="space-y-6">
                      <p className={`text-[11px] ${t.textMuted}`}>
                        Required now: first and last name.
                      </p>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            First Name <span className="text-red-500">*</span>
                          </label>
                          <input
                            type="text"
                            required
                            value={newEmployee.first_name}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, first_name: e.target.value })
                            }
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                          />
                        </div>
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            Last Name <span className="text-red-500">*</span>
                          </label>
                          <input
                            type="text"
                            required
                            value={newEmployee.last_name}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, last_name: e.target.value })
                            }
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                          />
                        </div>
                      </div>

                      <div>
                        <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                          Personal Email (Optional)
                        </label>
                        <input
                          type="email"
                          value={newEmployee.personal_email}
                          onChange={(e) =>
                            setNewEmployee({ ...newEmployee, personal_email: e.target.value })
                          }
                          className={`w-full px-3 py-2 ${t.inputCls}`}
                          placeholder="johnny_bravo@gmail.com"
                        />
                      </div>
                    </div>
                  )}

                  {addWizardStep === 2 && (
                    <div className="space-y-6">
                      <p className={`text-[11px] ${t.textMuted}`}>
                        Choose generated email for new Workspace accounts, or existing email for already provisioned employees.
                      </p>
                      <div className="space-y-3">
                        <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted}`}>
                          Work Email Setup <span className="text-red-500">*</span>
                        </label>

                        {googleDomainAvailable ? (
                          <div className={`space-y-3 ${t.innerEl} p-3`}>
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
                                <p className={`text-xs ${t.textMain} font-medium`}>Generate from first + last name</p>
                                <p className={`text-[11px] ${t.textMuted}`}>
                                  Domain detected from Google Workspace: <span className={t.textMain}>@{normalizedGoogleDomain}</span>
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
                                <p className={`text-xs ${t.textMain} font-medium`}>Use existing work email</p>
                                <p className={`text-[11px] ${t.textMuted}`}>
                                  Use this when the employee already has a company mailbox.
                                </p>
                              </div>
                            </label>
                          </div>
                        ) : (
                          <p className={`text-[11px] ${t.textMuted}`}>
                            Configure Google Workspace domain in onboarding settings to auto-generate work emails.
                          </p>
                        )}
                      </div>

                      <div>
                        {emailEntryMode === 'generated' && googleDomainAvailable ? (
                          <div className="space-y-2">
                            <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                              Work Email Username <span className="text-red-500">*</span>
                            </label>
                            <div className={`flex items-center ${t.inputCls} overflow-hidden`}>
                              <input
                                type="text"
                                required
                                value={generatedEmailLocalPart}
                                onChange={(e) => {
                                  setGeneratedEmailEdited(true);
                                  setGeneratedEmailLocalPart(sanitizeEmailLocalPart(e.target.value));
                                }}
                                className={`w-full px-3 py-2 bg-transparent ${t.textMain} text-sm focus:outline-none`}
                                placeholder="firstname.lastname"
                              />
                              <span className={`px-3 py-2 text-sm ${t.textMuted} border-l ${t.border}`}>
                                @{normalizedGoogleDomain}
                              </span>
                            </div>
                            <p className={`text-[11px] ${t.textMuted}`}>
                              Final email: <span className={t.textMain}>{generatedEmailLocalPart || 'firstname.lastname'}@{normalizedGoogleDomain}</span>
                            </p>
                          </div>
                        ) : (
                          <div className="space-y-2">
                            <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                              Work Email <span className="text-red-500">*</span>
                            </label>
                            <input
                              type="email"
                              required
                              value={newEmployee.work_email}
                              onChange={(e) =>
                                setNewEmployee({ ...newEmployee, work_email: e.target.value })
                              }
                              className={`w-full px-3 py-2 ${t.inputCls}`}
                              placeholder="johnny.bravo@energyco.com"
                            />
                            {googleDomainAvailable && (
                              <label className={`inline-flex items-center gap-2 text-[11px] ${t.textMuted}`}>
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
                      <p className={`text-[11px] ${t.textMuted}`}>
                        Final step: define where they work and verify a quick summary before creating.
                      </p>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            State <span className="text-red-500">*</span>
                          </label>
                          <select
                            value={newEmployee.work_state}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, work_state: e.target.value })
                            }
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                          >
                            <option value="">Select state</option>
                            {US_STATES.map((s) => (
                              <option key={s.value} value={s.value}>{s.label}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            City <span className="text-red-400">*</span>
                          </label>
                          <input
                            type="text"
                            value={newEmployee.work_city}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, work_city: e.target.value })
                            }
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                            placeholder="San Francisco"
                          />
                        </div>
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            Zip Code <span className="text-red-400">*</span>
                          </label>
                          <input
                            type="text"
                            value={newEmployee.work_zip}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, work_zip: e.target.value })
                            }
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                            placeholder="94105"
                            maxLength={10}
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            Office / Building (optional)
                          </label>
                          <input
                            type="text"
                            value={newEmployee.office_location}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, office_location: e.target.value })
                            }
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                            placeholder="Downtown HQ, Floor 3"
                          />
                        </div>
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            Employment Type
                          </label>
                          <select
                            value={newEmployee.employment_type}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, employment_type: e.target.value })
                            }
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                          >
                            <option value="full_time">Full Time</option>
                            <option value="part_time">Part Time</option>
                            <option value="contractor">Contractor</option>
                            <option value="intern">Intern</option>
                          </select>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            Job Title
                          </label>
                          <input
                            type="text"
                            value={newEmployee.job_title}
                            onChange={(e) => setNewEmployee({ ...newEmployee, job_title: e.target.value })}
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                            placeholder="Software Engineer"
                          />
                        </div>
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            Department
                          </label>
                          <input
                            type="text"
                            value={newEmployee.department}
                            onChange={(e) => setNewEmployee({ ...newEmployee, department: e.target.value })}
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                            placeholder="Engineering"
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            Pay Classification
                          </label>
                          <select
                            value={newEmployee.pay_classification}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, pay_classification: e.target.value })
                            }
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                          >
                            <option value="">Not specified</option>
                            <option value="hourly">Hourly</option>
                            <option value="exempt">Exempt (Salaried)</option>
                          </select>
                        </div>
                        {newEmployee.pay_classification && (
                          <div>
                            <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                              {newEmployee.pay_classification === 'hourly' ? 'Hourly Rate ($)' : 'Annual Salary ($)'}
                            </label>
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              value={newEmployee.pay_rate}
                              onChange={(e) =>
                                setNewEmployee({ ...newEmployee, pay_rate: e.target.value })
                              }
                              className={`w-full px-3 py-2 ${t.inputCls}`}
                              placeholder={newEmployee.pay_classification === 'hourly' ? '18.50' : '65000'}
                            />
                          </div>
                        )}
                      </div>

                      <div>
                        <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                          Start Date
                        </label>
                        <input
                          type="date"
                          value={newEmployee.start_date}
                          onChange={(e) =>
                            setNewEmployee({ ...newEmployee, start_date: e.target.value })
                          }
                          className={`w-full px-3 py-2 ${t.inputCls}`}
                        />
                      </div>

                      <div className={`${t.innerEl} p-3 text-[11px] ${t.textMuted} space-y-1`}>
                        <p>
                          <span className={t.textMain}>Work email:</span>{' '}
                          {emailEntryMode === 'generated' ? generatedSingleWorkEmail : newEmployee.work_email}
                        </p>
                        <p>
                          <span className={t.textMain}>Location:</span>{' '}
                          {newEmployee.work_state
                            ? `${newEmployee.work_city ? `${newEmployee.work_city}, ` : ''}${US_STATES.find(s => s.value === newEmployee.work_state)?.label || newEmployee.work_state}${newEmployee.work_zip ? ` ${newEmployee.work_zip}` : ''}${newEmployee.office_location ? ` (${newEmployee.office_location})` : ''}`
                            : 'state, city & zip required'}
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {error && (
                  <div className={`${t.alertError} rounded-xl p-3 flex items-center gap-3 mt-4`}>
                    <AlertTriangle className={t.alertErrorText} size={14} />
                    <p className={`text-xs ${t.alertErrorText} font-mono flex-1`}>{error}</p>
                    <button onClick={() => setError(null)} className={`text-[10px] ${t.alertErrorText} uppercase tracking-wider font-bold shrink-0`}>
                      Dismiss
                    </button>
                  </div>
                )}

                <div className={`mt-8 flex justify-end gap-3 pt-6 ${t.modalFooter}`}>
                  <button
                    type="button"
                    onClick={() => {
                      setShowAddModal(false);
                      resetAddEmployeeForm();
                    }}
                    className={`px-4 py-2 ${t.cancelBtn} text-xs font-bold uppercase tracking-wider transition-colors`}
                  >
                    Cancel
                  </button>
                  {addWizardStep > 1 && (
                    <button
                      type="button"
                      onClick={() => setAddWizardStep((prev) => (prev - 1) as AddWizardStep)}
                      className={`px-4 py-2 ${t.btnSecondary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
                    >
                      Back
                    </button>
                  )}
                  {addWizardStep < 3 && (
                    <button
                      type="button"
                      onClick={() => setAddWizardStep((prev) => (prev + 1) as AddWizardStep)}
                      disabled={(addWizardStep === 1 && !canProceedAddStep1) || (addWizardStep === 2 && !canProceedAddStep2)}
                      className={`px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed`}
                    >
                      Next
                    </button>
                  )}
                  {addWizardStep === 3 && (
                    <button
                      type="submit"
                      disabled={submitting || !canSubmitSingleWizard}
                      className={`px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed`}
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

      {/* ────────── Batch Wizard Modal ────────── */}
      {showBatchWizardModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className={`w-full max-w-6xl ${t.modalBg} max-h-[90vh] overflow-hidden flex flex-col`} onClick={(e) => e.stopPropagation()}>
            <div className={`flex items-center justify-between p-6 ${t.modalHeader}`}>
              <div>
                <h3 className={`text-xl font-bold ${t.textMain} uppercase tracking-tight`}>Batch Onboarding Wizard</h3>
                <div className="flex items-center gap-3 mt-1">
                  <p className={`text-xs ${t.textMuted}`}>Create up to 50 employees in one guided flow</p>
                  {draftLoaded && (
                    <span className={`text-[10px] uppercase tracking-wider ${draftSaving ? t.textMuted : t.textFaint}`}>
                      {draftSaving ? 'Saving...' : draftDirty ? '' : 'Draft saved'}
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={async () => {
                  try { await onboardingDraft.clear(); } catch { /* ignore */ }
                  draftSnapshotRef.current = '';
                  setDraftDirty(false);
                  setDraftLoaded(false);
                  setShowBatchWizardModal(false);
                  setBatchResult(null);
                }}
                className={`${t.closeBtnCls}`}
              >
                <X size={20} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              <div className={`${t.innerEl} p-3`}>
                <p className={`text-[10px] uppercase tracking-wider ${t.textMuted}`}>
                  Step {batchWizardStep} of 3
                </p>
                <p className={`text-xs ${t.textDim} mt-1`}>
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
                          ? 'border-zinc-900 text-zinc-50 bg-zinc-900'
                          : t.wizardInactive
                      }`}
                    >
                      {step}
                    </div>
                    {step < 3 && <div className={`h-px w-8 ${t.separator}`} />}
                  </div>
                ))}
              </div>

              {batchWizardStep === 1 && (
                <div className="space-y-6">
                  <div className="space-y-2">
                    <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted}`}>
                      Work Email Mode
                    </label>
                    {googleDomainAvailable ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        <button
                          type="button"
                          onClick={() => setBatchEmailMode('generated')}
                          className={`border p-3 text-left rounded-xl transition-colors ${
                            batchEmailMode === 'generated'
                              ? 'border-zinc-900 bg-zinc-900 text-zinc-50'
                              : t.btnSecondary
                          }`}
                        >
                          <p className={`text-xs font-bold uppercase tracking-wider ${batchEmailMode === 'generated' ? 'text-zinc-50' : t.textMain}`}>Generate From Name</p>
                          <p className={`text-[11px] mt-1 ${batchEmailMode === 'generated' ? 'text-zinc-400' : t.textMuted}`}>Uses @{normalizedGoogleDomain}</p>
                        </button>
                        <button
                          type="button"
                          onClick={() => setBatchEmailMode('existing')}
                          className={`border p-3 text-left rounded-xl transition-colors ${
                            batchEmailMode === 'existing'
                              ? 'border-zinc-900 bg-zinc-900 text-zinc-50'
                              : t.btnSecondary
                          }`}
                        >
                          <p className={`text-xs font-bold uppercase tracking-wider ${batchEmailMode === 'existing' ? 'text-zinc-50' : t.textMain}`}>Existing Work Emails</p>
                          <p className={`text-[11px] mt-1 ${batchEmailMode === 'existing' ? 'text-zinc-400' : t.textMuted}`}>For already-provisioned mailboxes</p>
                        </button>
                      </div>
                    ) : (
                      <div className={`${t.innerEl} p-3 text-[11px] ${t.textMuted}`}>
                        Google Workspace domain is not configured, so batch mode uses existing work emails.
                      </div>
                    )}
                  </div>

                  <div className={`${t.innerEl} p-3 text-[11px] ${t.textMuted} space-y-1`}>
                    <p>Step 2 lets you enter up to 50 rows.</p>
                    <p>Only non-empty rows are processed.</p>
                    <p>Use Add Row for more lines, and remove any line with the X action.</p>
                  </div>
                </div>
              )}

              {batchWizardStep === 2 && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className={`text-xs ${t.textMuted} uppercase tracking-wider`}>
                      Rows: {batchRows.length}/{BATCH_MAX_ROWS}
                    </p>
                    <button
                      type="button"
                      onClick={addBatchRow}
                      disabled={batchRows.length >= BATCH_MAX_ROWS}
                      className={`inline-flex items-center gap-2 px-3 py-1.5 ${t.btnSecondary} text-[10px] font-bold uppercase tracking-wider rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed`}
                    >
                      <Plus size={12} />
                      Add Row
                    </button>
                  </div>

                  <div className={`overflow-auto border ${t.border} rounded-xl`}>
                    <table className="min-w-[1200px] w-full text-xs">
                      <thead className={`${t.tableHeader} uppercase tracking-wider text-[10px]`}>
                        <tr>
                          <th className="px-2 py-2 text-left">#</th>
                          <th className="px-2 py-2 text-left">First</th>
                          <th className="px-2 py-2 text-left">Last</th>
                          <th className="px-2 py-2 text-left">{batchEmailMode === 'generated' ? 'Generated Email' : 'Work Email'}</th>
                          <th className="px-2 py-2 text-left">Personal Email</th>
                          <th className="px-2 py-2 text-left">State</th>
                          <th className="px-2 py-2 text-left">City</th>
                          <th className="px-2 py-2 text-left">Zip</th>
                          <th className="px-2 py-2 text-left">Type</th>
                          <th className="px-2 py-2 text-left">Start</th>
                          {batchEmailMode === 'existing' && <th className="px-2 py-2 text-left">Skip Google</th>}
                          <th className="px-2 py-2 text-left">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {batchRows.map((row, idx) => {
                          const rowEmailPreview = resolveBatchRowWorkEmail(row);
                          const rowError = row.first_name || row.last_name || row.work_email || row.personal_email || row.work_state
                            ? batchRowValidationError(row)
                            : null;
                          return (
                            <tr key={row.id} className={`border-t ${t.border} align-top`}>
                              <td className={`px-2 py-2 ${t.textMuted}`}>{idx + 1}</td>
                              <td className="px-2 py-2">
                                <input
                                  type="text"
                                  value={row.first_name}
                                  onChange={(e) => updateBatchRowField(row.id, 'first_name', e.target.value)}
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                />
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  type="text"
                                  value={row.last_name}
                                  onChange={(e) => updateBatchRowField(row.id, 'last_name', e.target.value)}
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                />
                              </td>
                              <td className="px-2 py-2">
                                {batchEmailMode === 'generated' ? (
                                  <div className={`px-2 py-1.5 ${t.genPreview} rounded-lg min-w-[220px]`}>
                                    {rowEmailPreview || 'auto-generated from name'}
                                  </div>
                                ) : (
                                  <input
                                    type="email"
                                    value={row.work_email}
                                    onChange={(e) => updateBatchRowField(row.id, 'work_email', e.target.value)}
                                    className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                  />
                                )}
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  type="email"
                                  value={row.personal_email}
                                  onChange={(e) => updateBatchRowField(row.id, 'personal_email', e.target.value)}
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                />
                              </td>
                              <td className="px-2 py-2">
                                <select
                                  value={row.work_state}
                                  onChange={(e) => updateBatchRowField(row.id, 'work_state', e.target.value)}
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                >
                                  <option value="">State</option>
                                  {US_STATES.map((s) => (
                                    <option key={s.value} value={s.value}>{s.value}</option>
                                  ))}
                                </select>
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  type="text"
                                  value={row.work_city}
                                  onChange={(e) => updateBatchRowField(row.id, 'work_city', e.target.value)}
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                  placeholder="City"
                                />
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  type="text"
                                  value={row.work_zip}
                                  onChange={(e) => updateBatchRowField(row.id, 'work_zip', e.target.value)}
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                  placeholder="Zip"
                                  maxLength={10}
                                />
                              </td>
                              <td className="px-2 py-2">
                                <select
                                  value={row.employment_type}
                                  onChange={(e) => updateBatchRowField(row.id, 'employment_type', e.target.value)}
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
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
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
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
                                  className={`${t.textFaint} hover:text-red-500`}
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
                  <div className={`${t.innerEl} p-4 text-xs ${t.textMuted} space-y-1`}>
                    <p>
                      Ready to create <span className={`${t.textMain} font-semibold`}>{batchRowsWithInput.length}</span> employees.
                    </p>
                    <p>Email mode: <span className={t.textMain}>{batchEmailMode === 'generated' ? 'Generated' : 'Existing'}</span></p>
                    <p>Each row includes <span className={t.textMain}>state + city</span> for compliance</p>
                  </div>

                  {batchResult && (
                    <div className="space-y-3">
                      <div className="grid grid-cols-2 gap-3">
                        <div className="border border-emerald-300 bg-emerald-50 p-3 rounded-xl">
                          <p className="text-2xl font-bold text-emerald-700">{batchResult.created}</p>
                          <p className={`text-[10px] ${t.textMuted} uppercase tracking-wider`}>Created</p>
                        </div>
                        <div className="border border-red-300 bg-red-50 p-3 rounded-xl">
                          <p className="text-2xl font-bold text-red-700">{batchResult.failed}</p>
                          <p className={`text-[10px] ${t.textMuted} uppercase tracking-wider`}>Failed</p>
                        </div>
                      </div>
                      {batchResult.errors.length > 0 && (
                        <div className="max-h-56 overflow-y-auto space-y-2 border border-red-300 bg-red-50 p-3 rounded-xl">
                          {batchResult.errors.map((err) => (
                            <div key={`${err.row_number}-${err.name}`} className="text-xs">
                              <p className="text-red-700">
                                Row {err.row_number} {err.name ? `(${err.name})` : ''}
                              </p>
                              <p className={t.textMuted}>{err.error}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className={`p-6 ${t.modalFooter} flex justify-end gap-3`}>
              <button
                type="button"
                onClick={async () => {
                  try { await onboardingDraft.clear(); } catch { /* ignore */ }
                  draftSnapshotRef.current = '';
                  setDraftDirty(false);
                  setDraftLoaded(false);
                  setShowBatchWizardModal(false);
                  setBatchResult(null);
                }}
                className={`px-4 py-2 ${t.cancelBtn} text-xs font-bold uppercase tracking-wider transition-colors`}
              >
                Cancel
              </button>
              {batchWizardStep > 1 && !batchSubmitting && (
                <button
                  type="button"
                  onClick={() => setBatchWizardStep((prev) => (prev - 1) as BatchWizardStep)}
                  className={`px-4 py-2 ${t.btnSecondary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
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
                  className={`px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed`}
                >
                  Next
                </button>
              )}
              {batchWizardStep === 3 && !batchResult && (
                <button
                  type="button"
                  onClick={handleBatchCreate}
                  disabled={batchSubmitting || !canProceedBatchStep2}
                  className={`px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed`}
                >
                  {batchSubmitting ? 'Creating...' : `Create ${batchRowsWithInput.length} Employees`}
                </button>
              )}
              {batchWizardStep === 3 && batchResult && (
                <button
                  type="button"
                  onClick={() => {
                    setDraftLoaded(false);
                    setShowBatchWizardModal(false);
                    setBatchResult(null);
                  }}
                  className={`px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
                >
                  Done
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ────────── Bulk Upload Modal ────────── */}
      {showBulkUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className={`w-full max-w-2xl ${t.modalBg} max-h-[90vh] overflow-hidden flex flex-col`} onClick={(e) => e.stopPropagation()}>
            <div className={`flex items-center justify-between p-6 ${t.modalHeader}`}>
              <div>
                <h3 className={`text-xl font-bold ${t.textMain} uppercase tracking-tight`}>Bulk Upload Employees</h3>
                <p className={`text-xs ${t.textMuted} mt-1`}>Upload a CSV file to add multiple employees at once</p>
              </div>
              <button
                onClick={() => {
                  setShowBulkUploadModal(false);
                  setUploadFile(null);
                  setUploadResult(null);
                }}
                className={`${t.closeBtnCls}`}
              >
                <X size={20} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6">
              {!uploadResult ? (
                <div className="space-y-6">
                  {/* Download Template Button */}
                  <div className={`${t.innerEl} p-4`}>
                    <div className="flex items-start gap-3">
                      <Download className="text-emerald-600 mt-0.5" size={16} />
                      <div className="flex-1">
                        <h4 className={`text-sm font-bold ${t.textMain} uppercase tracking-wide mb-1`}>Step 1: Download Template</h4>
                        <p className={`text-xs ${t.textMuted} mb-3`}>
                          Get the CSV template with the correct format and column headers.
                        </p>
                        <button
                          onClick={handleDownloadTemplate}
                          className={`inline-flex items-center gap-2 px-4 py-2 ${t.btnSecondary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
                        >
                          <Download size={12} />
                          Download Template
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Upload Area */}
                  <div className={`${t.innerEl} p-4`}>
                    <div className="flex items-start gap-3 mb-4">
                      <Upload className="text-emerald-600 mt-0.5" size={16} />
                      <div className="flex-1">
                        <h4 className={`text-sm font-bold ${t.textMain} uppercase tracking-wide mb-1`}>Step 2: Upload CSV</h4>
                        <p className={`text-xs ${t.textMuted}`}>
                          Drag and drop your CSV file or click to browse.
                        </p>
                      </div>
                    </div>

                    <div
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                      className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
                        isDragging ? t.uploadZoneDrag : uploadFile ? t.uploadZoneDone : t.uploadZone
                      }`}
                    >
                      {uploadFile ? (
                        <div className="space-y-3">
                          <CheckCircle className="w-10 h-10 text-emerald-600 mx-auto" />
                          <div>
                            <p className={`text-sm font-medium ${t.textMain}`}>{uploadFile.name}</p>
                            <p className={`text-xs ${t.textMuted} mt-1`}>
                              {(uploadFile.size / 1024).toFixed(2)} KB
                            </p>
                          </div>
                          <button
                            onClick={() => setUploadFile(null)}
                            className={`text-xs ${t.cancelBtn} uppercase tracking-wider`}
                          >
                            Remove File
                          </button>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <Upload className={`w-10 h-10 ${t.textDim} mx-auto`} />
                          <div>
                            <p className={`text-sm font-medium ${t.textDim}`}>Drop your CSV file here</p>
                            <p className={`text-xs ${t.textMuted} mt-1`}>or</p>
                          </div>
                          <label className="inline-block">
                            <input
                              type="file"
                              accept=".csv"
                              onChange={(e) => handleFileSelect(e.target.files?.[0] || null)}
                              className="hidden"
                            />
                            <span className={`inline-flex items-center gap-2 px-4 py-2 ${t.btnSecondary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors cursor-pointer`}>
                              Browse Files
                            </span>
                          </label>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Options */}
                  {uploadFile && (
                    <div className={`${t.innerEl} p-4`}>
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          id="intake-send-invites"
                          checked={sendInvitationsOnUpload}
                          onChange={(e) => setSendInvitationsOnUpload(e.target.checked)}
                          className={`w-4 h-4 rounded ${isLight ? 'border-stone-300 bg-white' : 'border-zinc-600 bg-zinc-700'} text-emerald-600 focus:ring-emerald-500 focus:ring-offset-0`}
                        />
                        <label htmlFor="intake-send-invites" className={`text-sm ${t.textMain} cursor-pointer`}>
                          Send invitation emails automatically
                        </label>
                      </div>
                      <p className={`text-xs ${t.textMuted} mt-2 ml-7`}>
                        Employees will receive an email to set up their account and access the portal.
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                /* Upload Results */
                <div className="space-y-4">
                  <div className={`${t.innerEl} p-6`}>
                    <div className="flex items-center gap-3 mb-4">
                      <CheckCircle className="text-emerald-600" size={24} />
                      <div>
                        <h4 className={`text-lg font-bold ${t.textMain} uppercase tracking-wide`}>Upload Complete</h4>
                        <p className={`text-xs ${t.textMuted} mt-1`}>
                          {uploadResult.created} of {uploadResult.total_rows} employees created successfully
                        </p>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-4 mt-6">
                      <div className={`${t.resultCard} p-4 rounded-xl text-center`}>
                        <div className="text-2xl font-bold text-emerald-600">{uploadResult.created}</div>
                        <div className={`text-xs ${t.textMuted} uppercase tracking-wider mt-1`}>Created</div>
                      </div>
                      <div className={`${t.resultCard} p-4 rounded-xl text-center`}>
                        <div className="text-2xl font-bold text-red-600">{uploadResult.failed}</div>
                        <div className={`text-xs ${t.textMuted} uppercase tracking-wider mt-1`}>Failed</div>
                      </div>
                      <div className={`${t.resultCard} p-4 rounded-xl text-center`}>
                        <div className={`text-2xl font-bold ${t.textDim}`}>{uploadResult.total_rows}</div>
                        <div className={`text-xs ${t.textMuted} uppercase tracking-wider mt-1`}>Total</div>
                      </div>
                    </div>
                    {uploadResult.credentials_created > 0 && (
                      <div className={`flex items-center gap-2 mt-4 px-1`}>
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0" />
                        <p className={`text-xs ${t.textMuted}`}>
                          <span className="font-semibold text-emerald-600">{uploadResult.credentials_created}</span> credential record{uploadResult.credentials_created !== 1 ? 's' : ''} created
                        </p>
                      </div>
                    )}
                  </div>

                  {uploadResult.errors && uploadResult.errors.length > 0 && (
                    <div className={`${t.alertError} rounded-xl p-4`}>
                      <div className="flex items-center gap-2 mb-3">
                        <AlertTriangle className={t.alertErrorText} size={16} />
                        <h5 className={`text-sm font-bold ${t.alertErrorText} uppercase tracking-wide`}>
                          Errors ({uploadResult.errors.length})
                        </h5>
                      </div>
                      <div className="space-y-2 max-h-60 overflow-y-auto">
                        {uploadResult.errors.map((err: any, idx: number) => (
                          <div key={idx} className={`${t.resultCard} p-3 rounded-lg text-xs`}>
                            <div className={`flex items-center gap-2 ${t.alertErrorText} font-medium mb-1`}>
                              <span>Row {err.row}</span>
                              {err.email && <span className={t.textFaint}>.</span>}
                              {err.email && <span className={`${t.textDim} font-mono`}>{err.email}</span>}
                            </div>
                            <p className={t.textMuted}>{err.error}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Send Invitations button -- shown when auto-send was off and employees were created */}
                  {!sendInvitationsOnUpload && uploadResult.created > 0 && uploadResult.employee_ids?.length > 0 && (
                    <div className={`${t.innerEl} p-4`}>
                      {bulkInviteResult ? (
                        <div className="flex items-center gap-3">
                          <CheckCircle className="text-emerald-600" size={18} />
                          <div>
                            <p className={`text-sm ${t.textMain} font-medium`}>
                              {bulkInviteResult.sent} invitation{bulkInviteResult.sent !== 1 ? 's' : ''} sent
                            </p>
                            {bulkInviteResult.failed > 0 && (
                              <p className="text-xs text-red-600 mt-1">
                                {bulkInviteResult.failed} failed to send
                              </p>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center justify-between">
                          <div>
                            <p className={`text-sm ${t.textMain} font-medium`}>Send invitation emails?</p>
                            <p className={`text-xs ${t.textMuted} mt-1`}>
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
                            className={`flex items-center gap-2 px-4 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-50 shrink-0`}
                          >
                            {bulkInviting ? (
                              <>
                                <span className="w-3 h-3 border-2 border-zinc-50/20 border-t-zinc-50 rounded-full animate-spin" />
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
                    className={`w-full px-4 py-3 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
                  >
                    Done
                  </button>
                </div>
              )}
            </div>

            {!uploadResult && uploadFile && (
              <div className={`p-6 ${t.modalFooter} flex justify-end gap-3`}>
                <button
                  onClick={() => {
                    setShowBulkUploadModal(false);
                    setUploadFile(null);
                    setUploadResult(null);
                  }}
                  className={`px-4 py-2 ${t.cancelBtn} text-xs font-bold uppercase tracking-wider transition-colors`}
                >
                  Cancel
                </button>
                <button
                  onClick={handleBulkUpload}
                  disabled={uploadLoading || !uploadFile}
                  className={`flex items-center gap-2 px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {uploadLoading ? (
                    <>
                      <span className="w-3 h-3 border-2 border-zinc-50/20 border-t-zinc-50 rounded-full animate-spin" />
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
