import { useState, useEffect, useCallback } from 'react';
import { getAccessToken } from '../../api/client';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

type EmailEntryMode = 'generated' | 'existing';
type WorkLocationMode = 'remote' | 'office';
type AddWizardStep = 1 | 2 | 3;

export interface NewEmployee {
  work_email: string;
  personal_email: string;
  first_name: string;
  last_name: string;
  office_location: string;
  work_state: string;
  employment_type: string;
  start_date: string;
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

export function useEmployeeForm(googleDomainAvailable: boolean, onSuccess: (employee: any) => void, onRefetch: () => void) {
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
  const [emailEntryMode, setEmailEntryMode] = useState<EmailEntryMode>(googleDomainAvailable ? 'generated' : 'existing');
  const [generatedEmailLocalPart, setGeneratedEmailLocalPart] = useState('');
  const [generatedEmailEdited, setGeneratedEmailEdited] = useState(false);
  const [skipGoogleAutoProvision, setSkipGoogleAutoProvision] = useState(false);
  const [workLocationMode, setWorkLocationMode] = useState<WorkLocationMode>('remote');
  const [addWizardStep, setAddWizardStep] = useState<AddWizardStep>(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    setError(null);
  }, [googleDomainAvailable]);

  // Auto-derive email when in generated mode
  useEffect(() => {
    if (!emailEntryMode || emailEntryMode !== 'generated' || generatedEmailEdited) return;
    const generated = buildGeneratedEmailLocalPart(newEmployee.first_name, newEmployee.last_name);
    setGeneratedEmailLocalPart(generated);
  }, [emailEntryMode, generatedEmailEdited, newEmployee.first_name, newEmployee.last_name]);

  const generatedSingleWorkEmail = googleDomainAvailable && generatedEmailLocalPart
    ? `${generatedEmailLocalPart}@${(googleDomainAvailable ? '' : '').replace(/^@/, '').toLowerCase()}`
    : '';

  const canProceedAddStep1 = Boolean(newEmployee.first_name.trim() && newEmployee.last_name.trim());
  const canProceedAddStep2 = emailEntryMode === 'generated'
    ? Boolean(generatedSingleWorkEmail)
    : looksLikeEmail(newEmployee.work_email);
  const hasSingleLocation = workLocationMode === 'remote'
    ? Boolean(newEmployee.work_state)
    : Boolean(newEmployee.office_location.trim());
  const canSubmitSingleWizard = canProceedAddStep1 && canProceedAddStep2 && hasSingleLocation;

  const handleAddEmployee = async (normalizedGoogleDomain: string) => {
    setSubmitting(true);
    setError(null);

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
      onSuccess({
        id: createdEmployee.id,
        name: `${newEmployee.first_name} ${newEmployee.last_name}`,
        workEmail: resolvedWorkEmail,
        personalEmail: newEmployee.personal_email,
      });
      onRefetch();
      resetAddEmployeeForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  return {
    newEmployee,
    setNewEmployee,
    emailEntryMode,
    setEmailEntryMode,
    generatedEmailLocalPart,
    setGeneratedEmailLocalPart,
    generatedEmailEdited,
    setGeneratedEmailEdited,
    skipGoogleAutoProvision,
    setSkipGoogleAutoProvision,
    workLocationMode,
    setWorkLocationMode,
    addWizardStep,
    setAddWizardStep,
    submitting,
    error,
    resetAddEmployeeForm,
    handleAddEmployee,
    canProceedAddStep1,
    canProceedAddStep2,
    hasSingleLocation,
    canSubmitSingleWizard,
  };
}
