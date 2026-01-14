import { getAccessToken } from './client';

async function fetchWithAuth(url: string, options: RequestInit = {}) {
  const token = getAccessToken();

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

export const portalApi = {
  // Dashboard
  getDashboard: () => fetchWithAuth('/api/v1/portal/me'),

  // Profile
  updateProfile: (data: { phone?: string; address?: string; emergency_contact?: object }) =>
    fetchWithAuth('/api/v1/portal/me', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Tasks
  getTasks: () => fetchWithAuth('/api/v1/portal/me/tasks'),

  // PTO
  getPTOSummary: () => fetchWithAuth('/api/v1/portal/me/pto'),

  submitPTORequest: (data: {
    start_date: string;
    end_date: string;
    hours: number;
    reason?: string;
    request_type?: string;
  }) =>
    fetchWithAuth('/api/v1/portal/me/pto/request', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  cancelPTORequest: (requestId: string) =>
    fetchWithAuth(`/api/v1/portal/me/pto/request/${requestId}`, {
      method: 'DELETE',
    }),

  // Documents
  getDocuments: (status?: string) => {
    const params = status ? `?status_filter=${status}` : '';
    return fetchWithAuth(`/api/v1/portal/me/documents${params}`);
  },

  getDocument: (documentId: string) =>
    fetchWithAuth(`/api/v1/portal/me/documents/${documentId}`),

  signDocument: (documentId: string, signatureData: string) =>
    fetchWithAuth(`/api/v1/portal/me/documents/${documentId}/sign`, {
      method: 'POST',
      body: JSON.stringify({ signature_data: signatureData }),
    }),

  // Policies
  searchPolicies: (query?: string) => {
    const params = query ? `?q=${encodeURIComponent(query)}` : '';
    return fetchWithAuth(`/api/v1/portal/policies${params}`);
  },

  getPolicy: (policyId: string) =>
    fetchWithAuth(`/api/v1/portal/policies/${policyId}`),
};
