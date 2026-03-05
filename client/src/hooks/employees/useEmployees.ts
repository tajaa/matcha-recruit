import { useState, useEffect, useCallback, useRef } from 'react';
import { getAccessToken } from '../../api/client';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

export interface Employee {
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
  job_title: string | null;
  department: string | null;
  pay_classification: string | null;
  pay_rate: number | null;
  work_city: string | null;
  created_at: string;
}

export interface OnboardingProgress {
  employee_id: string;
  total: number;
  completed: number;
  pending: number;
  has_onboarding: boolean;
}

export interface EmployeeFilters {
  status?: string;
  search?: string;
  department?: string;
  employment_type?: string;
  work_state?: string;
  work_city?: string;
  manager_id?: string;
}

export function useEmployees(filters: EmployeeFilters) {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [onboardingProgress, setOnboardingProgress] = useState<Record<string, OnboardingProgress>>({});
  const abortRef = useRef<AbortController | null>(null);

  const fetchEmployees = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const token = getAccessToken();
      const params = new URLSearchParams();
      if (filters.status) params.set('status', filters.status);
      if (filters.search) params.set('search', filters.search);
      if (filters.department) params.set('department', filters.department);
      if (filters.employment_type) params.set('employment_type', filters.employment_type);
      if (filters.work_state) params.set('work_state', filters.work_state);
      if (filters.work_city) params.set('work_city', filters.work_city);
      if (filters.manager_id) params.set('manager_id', filters.manager_id);

      const qs = params.toString();
      const url = `${API_BASE}/employees${qs ? `?${qs}` : ''}`;

      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to fetch employees');
      }

      const data = await response.json();
      setEmployees(data);
      setError(null);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [filters.status, filters.search, filters.department, filters.employment_type, filters.work_state, filters.work_city, filters.manager_id]);

  const fetchOnboardingProgress = async () => {
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/onboarding-progress`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) throw new Error('Failed to fetch onboarding progress');

      const data = await response.json();
      setOnboardingProgress(data);
    } catch (err) {
      console.error('Failed to fetch onboarding progress:', err);
    }
  };

  useEffect(() => {
    setLoading(true);
    fetchEmployees();
    fetchOnboardingProgress();
  }, [fetchEmployees]);

  const refetch = async () => {
    setLoading(true);
    await fetchEmployees();
    await fetchOnboardingProgress();
  };

  return { employees, loading, error, onboardingProgress, refetch };
}
