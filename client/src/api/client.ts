import type {
  Company,
  CompanyCreate,
  Interview,
  InterviewCreate,
  InterviewStart,
  Candidate,
  CandidateDetail,
  MatchResult,
  Position,
  PositionCreate,
  PositionUpdate,
  PositionMatchResult,
  BulkImportResult,
  ExperienceLevel,
  RemotePolicy,
  PositionStatus,
} from '../types';

const API_BASE = 'http://localhost:8000/api';

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }

  return response.json();
}

// Companies
export const companies = {
  list: () => request<Company[]>('/companies'),

  get: (id: string) => request<Company>(`/companies/${id}`),

  create: (data: CompanyCreate) =>
    request<Company>('/companies', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<{ status: string }>(`/companies/${id}`, {
      method: 'DELETE',
    }),

  aggregateCulture: (id: string) =>
    request<{ status: string; profile: Record<string, unknown> }>(
      `/companies/${id}/aggregate-culture`,
      { method: 'POST' }
    ),
};

// Interviews
export const interviews = {
  list: (companyId: string) =>
    request<Interview[]>(`/companies/${companyId}/interviews`),

  get: (id: string) => request<Interview>(`/interviews/${id}`),

  create: (companyId: string, data: Omit<InterviewCreate, 'company_id'>) =>
    request<InterviewStart>(`/companies/${companyId}/interviews`, {
      method: 'POST',
      body: JSON.stringify({ ...data, company_id: companyId }),
    }),
};

// Candidates
export const candidates = {
  list: () => request<Candidate[]>('/candidates'),

  get: (id: string) => request<CandidateDetail>(`/candidates/${id}`),

  upload: async (file: File): Promise<Candidate> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/candidates/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail || 'Upload failed');
    }

    return response.json();
  },

  delete: (id: string) =>
    request<{ status: string }>(`/candidates/${id}`, {
      method: 'DELETE',
    }),
};

// Matching
export const matching = {
  run: (companyId: string, candidateIds?: string[]) =>
    request<{ status: string; matches: MatchResult[] }>(
      `/companies/${companyId}/match`,
      {
        method: 'POST',
        body: JSON.stringify(candidateIds ? { candidate_ids: candidateIds } : {}),
      }
    ),

  list: (companyId: string) =>
    request<MatchResult[]>(`/companies/${companyId}/matches`),
};

// Positions
export interface PositionFilters {
  status?: PositionStatus;
  experience_level?: ExperienceLevel;
  remote_policy?: RemotePolicy;
  search?: string;
}

export const positions = {
  list: (filters?: PositionFilters) => {
    const params = new URLSearchParams();
    if (filters?.status) params.append('status', filters.status);
    if (filters?.experience_level) params.append('experience_level', filters.experience_level);
    if (filters?.remote_policy) params.append('remote_policy', filters.remote_policy);
    if (filters?.search) params.append('search', filters.search);
    const query = params.toString();
    return request<Position[]>(`/positions${query ? `?${query}` : ''}`);
  },

  get: (id: string) => request<Position>(`/positions/${id}`),

  create: (data: PositionCreate) =>
    request<Position>('/positions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: PositionUpdate) =>
    request<Position>(`/positions/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<{ status: string }>(`/positions/${id}`, {
      method: 'DELETE',
    }),

  listByCompany: (companyId: string, status?: PositionStatus) => {
    const params = status ? `?status=${status}` : '';
    return request<Position[]>(`/positions/company/${companyId}${params}`);
  },

  match: (positionId: string, candidateIds?: string[]) =>
    request<{ status: string; matches: PositionMatchResult[] }>(
      `/positions/${positionId}/match`,
      {
        method: 'POST',
        body: JSON.stringify(candidateIds ? { candidate_ids: candidateIds } : {}),
      }
    ),

  getMatches: (positionId: string) =>
    request<PositionMatchResult[]>(`/positions/${positionId}/matches`),
};

// Bulk Import
export const bulkImport = {
  companies: async (file: File): Promise<BulkImportResult> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/bulk/companies`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Import failed' }));
      throw new Error(error.detail || 'Import failed');
    }

    return response.json();
  },

  positions: async (file: File): Promise<BulkImportResult> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/bulk/positions`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Import failed' }));
      throw new Error(error.detail || 'Import failed');
    }

    return response.json();
  },

  downloadTemplate: (type: 'companies' | 'positions') =>
    `${API_BASE}/bulk/templates/${type}`,
};

// WebSocket URL helper
export function getInterviewWSUrl(interviewId: string): string {
  return `ws://localhost:8000/api/ws/interview/${interviewId}`;
}
