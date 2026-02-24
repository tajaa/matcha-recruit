import { useState, useEffect } from 'react';
import { getAccessToken } from '../../api/client';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

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
  created_at: string;
}

export interface OnboardingProgress {
  employee_id: string;
  total: number;
  completed: number;
  pending: number;
  has_onboarding: boolean;
}

export function useEmployees(filter: string) {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [onboardingProgress, setOnboardingProgress] = useState<Record<string, OnboardingProgress>>({});

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

  useEffect(() => {
    fetchEmployees();
    fetchOnboardingProgress();
  }, [filter]);

  const refetch = async () => {
    setLoading(true);
    await fetchEmployees();
    await fetchOnboardingProgress();
  };

  return { employees, loading, error, onboardingProgress, refetch };
}
