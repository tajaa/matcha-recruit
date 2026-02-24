import { useState, useEffect, useRef, useCallback } from 'react';
import { getAccessToken, onboardingDraft } from '../../api/client';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

type EmailEntryMode = 'generated' | 'existing';
type WorkLocationMode = 'remote' | 'office';
type BatchWizardStep = 1 | 2 | 3;

export interface BatchEmployeeRow {
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

export interface BatchCreateError {
  row_number: number;
  name: string;
  error: string;
}

export interface BatchCreateResult {
  created: number;
  failed: number;
  errors: BatchCreateError[];
}

function buildGeneratedEmailLocalPart(firstName: string, lastName: string): string {
  const sanitizeEmailLocalPart = (value: string): string => {
    return value
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .trim()
      .replace(/['`]/g, '')
      .replace(/[^a-z0-9._-]+/g, '.')
      .replace(/\.+/g, '.')
      .replace(/^[._-]+|[._-]+$/g, '');
  };
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

export function useBatchWizard(googleDomainAvailable: boolean, normalizedGoogleDomain: string) {
  const [showBatchWizardModal, setShowBatchWizardModal] = useState(false);
  const [batchWizardStep, setBatchWizardStep] = useState<BatchWizardStep>(1);
  const [batchEmailMode, setBatchEmailMode] = useState<EmailEntryMode>('existing');
  const [batchWorkLocationMode, setBatchWorkLocationMode] = useState<WorkLocationMode>('remote');
  const [batchRows, setBatchRows] = useState<BatchEmployeeRow[]>([]);
  const [batchSubmitting, setBatchSubmitting] = useState(false);
  const [batchResult, setBatchResult] = useState<BatchCreateResult | null>(null);
  const [draftLoaded, setDraftLoaded] = useState(false);
  const [draftDirty, setDraftDirty] = useState(false);
  const [draftSaving, setDraftSaving] = useState(false);
  const draftSnapshotRef = useRef<string>('');

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

  // Dirty detection for batch wizard draft
  useEffect(() => {
    if (!draftLoaded) return;
    const current = JSON.stringify({ batchRows, emailMode: batchEmailMode, workLocationMode: batchWorkLocationMode, wizardStep: batchWizardStep });
    setDraftDirty(current !== draftSnapshotRef.current);
  }, [batchRows, batchEmailMode, batchWorkLocationMode, batchWizardStep, draftLoaded]);

  // Autosave batch wizard draft with 5-second debounce
  const DRAFT_AUTOSAVE_MS = 5000;
  useEffect(() => {
    if (!draftLoaded || !draftDirty) return;
    const timer = setTimeout(async () => {
      setDraftSaving(true);
      try {
        const state = { batchRows, emailMode: batchEmailMode, workLocationMode: batchWorkLocationMode, wizardStep: batchWizardStep };
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
  }, [draftLoaded, draftDirty, batchRows, batchEmailMode, batchWorkLocationMode, batchWizardStep]);

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

  const handleBatchCreate = async (onRefetch: () => void) => {
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
      onRefetch();
      // Clear the draft after a successful batch submission
      try { await onboardingDraft.clear(); } catch { /* ignore */ }
      draftSnapshotRef.current = '';
      setDraftDirty(false);
    } finally {
      setBatchSubmitting(false);
    }
  };

  return {
    showBatchWizardModal,
    setShowBatchWizardModal,
    batchWizardStep,
    setBatchWizardStep,
    batchEmailMode,
    setBatchEmailMode,
    batchWorkLocationMode,
    setBatchWorkLocationMode,
    batchRows,
    batchSubmitting,
    batchResult,
    draftLoaded,
    setDraftLoaded,
    draftDirty,
    draftSaving,
    resetBatchWizard,
    updateBatchRowField,
    addBatchRow,
    removeBatchRow,
    handleBatchCreate,
    canProceedBatchStep2,
    batchRowValidationError,
  };
}
