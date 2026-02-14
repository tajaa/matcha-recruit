import { getAccessToken } from './client';

export type AccommodationStatus =
  | 'requested'
  | 'interactive_process'
  | 'medical_review'
  | 'approved'
  | 'denied'
  | 'implemented'
  | 'review'
  | 'closed';

export type DisabilityCategory =
  | 'physical'
  | 'cognitive'
  | 'sensory'
  | 'mental_health'
  | 'chronic_illness'
  | 'pregnancy'
  | 'other';

export type AccommodationDocumentType =
  | 'medical_certification'
  | 'accommodation_request_form'
  | 'interactive_process_notes'
  | 'job_description'
  | 'hardship_analysis'
  | 'approval_letter'
  | 'other';

export interface AccommodationCase {
  id: string;
  case_number: string;
  org_id: string;
  employee_id: string;
  linked_leave_id: string | null;
  title: string;
  description: string | null;
  disability_category: DisabilityCategory | null;
  status: AccommodationStatus;
  requested_accommodation: string | null;
  approved_accommodation: string | null;
  denial_reason: string | null;
  undue_hardship_analysis: string | null;
  assigned_to: string | null;
  created_by: string | null;
  document_count: number;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface AccommodationCaseListResponse {
  cases: AccommodationCase[];
  total: number;
}

export interface AccommodationCaseCreate {
  employee_id: string;
  title: string;
  description?: string;
  disability_category?: DisabilityCategory;
  requested_accommodation?: string;
  linked_leave_id?: string;
}

export interface AccommodationCaseUpdate {
  title?: string;
  description?: string;
  status?: AccommodationStatus;
  disability_category?: DisabilityCategory;
  requested_accommodation?: string;
  approved_accommodation?: string;
  denial_reason?: string;
  assigned_to?: string;
}

export interface AccommodationDocument {
  id: string;
  case_id: string;
  document_type: string;
  filename: string;
  file_path: string;
  mime_type: string | null;
  file_size: number | null;
  uploaded_by: string | null;
  created_at: string;
}

export interface AccommodationAnalysis {
  analysis_type: string;
  analysis_data: Record<string, unknown>;
  generated_by: string | null;
  generated_at: string;
}

export interface AuditLogEntry {
  id: string;
  case_id: string | null;
  user_id: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface AuditLogResponse {
  entries: AuditLogEntry[];
  total: number;
}

export interface EmployeeOption {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
}

async function requestWithAuth<T>(url: string, options: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
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

export const accommodationsApi = {
  listCases: (params?: { status?: AccommodationStatus; employee_id?: string }) => {
    const search = new URLSearchParams();
    if (params?.status) search.set('status', params.status);
    if (params?.employee_id) search.set('employee_id', params.employee_id);
    const query = search.toString() ? `?${search.toString()}` : '';
    return requestWithAuth<AccommodationCaseListResponse>(`/api/accommodations${query}`);
  },

  getCase: (caseId: string) =>
    requestWithAuth<AccommodationCase>(`/api/accommodations/${caseId}`),

  createCase: (payload: AccommodationCaseCreate) =>
    requestWithAuth<AccommodationCase>('/api/accommodations', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateCase: (caseId: string, payload: AccommodationCaseUpdate) =>
    requestWithAuth<AccommodationCase>(`/api/accommodations/${caseId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteCase: (caseId: string) =>
    requestWithAuth<{ status: string; case_id: string }>(`/api/accommodations/${caseId}`, {
      method: 'DELETE',
    }),

  uploadDocument: (caseId: string, file: File, document_type: AccommodationDocumentType = 'other') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', document_type);
    return requestWithAuth<AccommodationDocument>(`/api/accommodations/${caseId}/documents`, {
      method: 'POST',
      body: formData,
    });
  },

  listDocuments: (caseId: string) =>
    requestWithAuth<AccommodationDocument[]>(`/api/accommodations/${caseId}/documents`),

  deleteDocument: (caseId: string, docId: string) =>
    requestWithAuth<{ status: string; document_id: string }>(`/api/accommodations/${caseId}/documents/${docId}`, {
      method: 'DELETE',
    }),

  generateSuggestions: (caseId: string) =>
    requestWithAuth<AccommodationAnalysis>(`/api/accommodations/${caseId}/analysis/suggestions`, {
      method: 'POST',
    }),

  getSuggestions: (caseId: string) =>
    requestWithAuth<AccommodationAnalysis>(`/api/accommodations/${caseId}/analysis/suggestions`),

  generateHardship: (caseId: string) =>
    requestWithAuth<AccommodationAnalysis>(`/api/accommodations/${caseId}/analysis/hardship`, {
      method: 'POST',
    }),

  getHardship: (caseId: string) =>
    requestWithAuth<AccommodationAnalysis>(`/api/accommodations/${caseId}/analysis/hardship`),

  generateJobFunctions: (caseId: string) =>
    requestWithAuth<AccommodationAnalysis>(`/api/accommodations/${caseId}/analysis/job-functions`, {
      method: 'POST',
    }),

  getJobFunctions: (caseId: string) =>
    requestWithAuth<AccommodationAnalysis>(`/api/accommodations/${caseId}/analysis/job-functions`),

  getAuditLog: (caseId: string, limit = 100, offset = 0) =>
    requestWithAuth<AuditLogResponse>(`/api/accommodations/${caseId}/audit-log?limit=${limit}&offset=${offset}`),

  listEmployees: () => requestWithAuth<EmployeeOption[]>('/api/accommodations/employees'),
};
