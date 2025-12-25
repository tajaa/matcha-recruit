import type {
  Company,
  CompanyCreate,
  Interview,
  InterviewCreate,
  InterviewStart,
  ConversationAnalysis,
  ScreeningAnalysis,
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
  JobSearchRequest,
  JobSearchResponse,
  SavedJob,
  SavedJobCreate,
  TokenResponse,
  LoginRequest,
  ClientRegister,
  CandidateRegister,
  CurrentUserResponse,
  Project,
  ProjectCreate,
  ProjectUpdate,
  ProjectCandidate,
  ProjectCandidateAdd,
  ProjectCandidateBulkAdd,
  ProjectCandidateUpdate,
  ProjectStats,
  ProjectStatus,
  CandidateStage,
  Outreach,
  OutreachSendRequest,
  OutreachSendResult,
  OutreachPublicInfo,
  OutreachInterestResponse,
  OutreachInterviewStart,
  OutreachStatus,
  ScreeningPublicInfo,
  PublicJobDetail,
  JobListResponse,
  ApplicationSubmitResponse,
} from '../types';

const API_BASE = 'http://localhost:8001/api';

// Token storage helpers
const TOKEN_KEY = 'matcha_access_token';
const REFRESH_KEY = 'matcha_refresh_token';

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_KEY, refreshToken);
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) return false;

    const data: TokenResponse = await response.json();
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAccessToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    // Try to refresh token
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      // Retry original request with new token
      (headers as Record<string, string>)['Authorization'] = `Bearer ${getAccessToken()}`;
      const retryResponse = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
      });
      if (!retryResponse.ok) {
        const error = await retryResponse.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || 'Request failed');
      }
      return retryResponse.json();
    }
    // Refresh failed, clear tokens and redirect to login
    clearTokens();
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }

  return response.json();
}

// Auth API
export const auth = {
  login: async (data: LoginRequest): Promise<TokenResponse> => {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(error.detail || 'Login failed');
    }

    const result: TokenResponse = await response.json();
    setTokens(result.access_token, result.refresh_token);
    return result;
  },

  logout: async (): Promise<void> => {
    try {
      await request('/auth/logout', { method: 'POST' });
    } finally {
      clearTokens();
    }
  },

  registerClient: async (data: ClientRegister): Promise<TokenResponse> => {
    const response = await fetch(`${API_BASE}/auth/register/client`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Registration failed' }));
      throw new Error(error.detail || 'Registration failed');
    }

    const result: TokenResponse = await response.json();
    setTokens(result.access_token, result.refresh_token);
    return result;
  },

  registerCandidate: async (data: CandidateRegister): Promise<TokenResponse> => {
    const response = await fetch(`${API_BASE}/auth/register/candidate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Registration failed' }));
      throw new Error(error.detail || 'Registration failed');
    }

    const result: TokenResponse = await response.json();
    setTokens(result.access_token, result.refresh_token);
    return result;
  },

  me: () => request<CurrentUserResponse>('/auth/me'),
};

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

  getAnalysis: (id: string) =>
    request<ConversationAnalysis>(`/interviews/${id}/analysis`),

  generateAnalysis: (id: string) =>
    request<ConversationAnalysis | ScreeningAnalysis>(`/interviews/${id}/analyze`, {
      method: 'POST',
    }),
};

// Candidates
export interface CandidateFilters {
  search?: string;
  skills?: string;  // Comma-separated
  min_experience?: number;
  max_experience?: number;
  education?: string;
}

export const candidates = {
  list: (filters?: CandidateFilters) => {
    const params = new URLSearchParams();
    if (filters?.search) params.append('search', filters.search);
    if (filters?.skills) params.append('skills', filters.skills);
    if (filters?.min_experience !== undefined) params.append('min_experience', String(filters.min_experience));
    if (filters?.max_experience !== undefined) params.append('max_experience', String(filters.max_experience));
    if (filters?.education) params.append('education', filters.education);
    const query = params.toString();
    return request<Candidate[]>(`/candidates${query ? `?${query}` : ''}`);
  },

  get: (id: string) => request<CandidateDetail>(`/candidates/${id}`),

  upload: async (file: File): Promise<Candidate> => {
    const formData = new FormData();
    formData.append('file', file);

    const headers: HeadersInit = {};
    const token = getAccessToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/candidates/upload`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail || 'Upload failed');
    }

    return response.json();
  },

  bulkUpload: async (files: File[]): Promise<BulkImportResult> => {
    const formData = new FormData();
    files.forEach(file => {
      formData.append('files', file);
    });

    const headers: HeadersInit = {};
    const token = getAccessToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/candidates/bulk-upload`, {
      method: 'POST',
      headers,
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

  toggleJobBoard: (positionId: string, showOnJobBoard: boolean) =>
    request<Position>(`/positions/${positionId}/job-board?show_on_job_board=${showOnJobBoard}`, {
      method: 'PATCH',
    }),

  createFromSavedJob: (savedJobId: string, companyId: string) =>
    request<Position>(`/positions/from-saved-job/${savedJobId}`, {
      method: 'POST',
      body: JSON.stringify({ company_id: companyId }),
    }),

  createFromSavedOpening: (savedOpeningId: string, companyId: string) =>
    request<Position>(`/positions/from-saved-opening/${savedOpeningId}`, {
      method: 'POST',
      body: JSON.stringify({ company_id: companyId }),
    }),
};

// Bulk Import
export const bulkImport = {
  companies: async (file: File): Promise<BulkImportResult> => {
    const formData = new FormData();
    formData.append('file', file);

    const headers: HeadersInit = {};
    const token = getAccessToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/bulk/companies`, {
      method: 'POST',
      headers,
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

    const headers: HeadersInit = {};
    const token = getAccessToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/bulk/positions`, {
      method: 'POST',
      headers,
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

// Job Search (external jobs via SearchAPI)
export const jobSearch = {
  search: (params: JobSearchRequest) =>
    request<JobSearchResponse>('/jobs/search', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  // Saved Jobs
  save: (job: SavedJobCreate) =>
    request<SavedJob>('/jobs/saved', {
      method: 'POST',
      body: JSON.stringify(job),
    }),

  listSaved: () => request<SavedJob[]>('/jobs/saved'),

  getSavedIds: () => request<string[]>('/jobs/saved/ids'),

  getSaved: (jobId: string) => request<SavedJob>(`/jobs/saved/${jobId}`),

  deleteSaved: (jobId: string) =>
    request<{ status: string }>(`/jobs/saved/${jobId}`, {
      method: 'DELETE',
    }),

  toggleJobBoard: (jobId: string, showOnJobBoard: boolean) =>
    request<{ status: string; show_on_job_board: boolean }>(`/jobs/saved/${jobId}/job-board?show_on_job_board=${showOnJobBoard}`, {
      method: 'PATCH',
    }),
};

// =============================================================================
// OPENINGS - Company Watchlist + Niche Sources
// =============================================================================

// Tracked Companies (Company Watchlist)
export interface TrackedCompanyCreate {
  name: string;
  career_url: string;
  industry?: string;
}

export interface TrackedCompany {
  id: string;
  name: string;
  career_url: string;
  industry: string | null;
  last_scraped_at: string | null;
  job_count: number;
  new_job_count: number;
  created_at: string;
}

export interface TrackedCompanyJob {
  id: string;
  company_id: string;
  company_name: string;
  title: string;
  location: string | null;
  department: string | null;
  apply_url: string;
  is_new: boolean;
  first_seen_at: string;
}

export interface RefreshResult {
  companies_refreshed: number;
  new_jobs_found: number;
  total_jobs: number;
}

// Niche Job Sources
export interface JobSource {
  id: string;
  name: string;
  description: string;
  industries: string[];
}

export interface SourceSearchRequest {
  sources: string[];
  query?: string;
  location?: string;
  limit?: number;
}

export interface ScrapedJob {
  title: string;
  company_name: string;
  location: string | null;
  department: string | null;
  salary: string | null;
  apply_url: string;
  source_url: string;
  source_name: string;
}

export interface SourceSearchResult {
  jobs: ScrapedJob[];
  sources_searched: number;
  sources_failed: number;
}

// Saved Openings
export interface SavedOpeningCreate {
  title: string;
  company_name: string;
  location?: string;
  department?: string;
  apply_url: string;
  source_url?: string;
  industry?: string;
  notes?: string;
}

export interface SavedOpening {
  id: string;
  title: string;
  company_name: string;
  location: string | null;
  department: string | null;
  apply_url: string;
  source_url: string | null;
  industry: string | null;
  notes: string | null;
  created_at: string;
}

export const openings = {
  // Tracked Companies (Watchlist)
  addCompany: (data: TrackedCompanyCreate) =>
    request<TrackedCompany>('/openings/companies', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listCompanies: () => request<TrackedCompany[]>('/openings/companies'),

  deleteCompany: (id: string) =>
    request<{ status: string }>(`/openings/companies/${id}`, {
      method: 'DELETE',
    }),

  getCompanyJobs: (companyId: string) =>
    request<TrackedCompanyJob[]>(`/openings/companies/${companyId}/jobs`),

  refreshCompanies: () =>
    request<RefreshResult>('/openings/companies/refresh', {
      method: 'POST',
    }),

  markCompanySeen: (companyId: string) =>
    request<{ status: string }>(`/openings/companies/${companyId}/mark-seen`, {
      method: 'POST',
    }),

  // Niche Job Sources
  listSources: () => request<JobSource[]>('/openings/sources'),

  searchSources: (params: SourceSearchRequest) =>
    request<SourceSearchResult>('/openings/sources/search', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  // Saved openings
  save: (opening: SavedOpeningCreate) =>
    request<SavedOpening>('/openings/saved', {
      method: 'POST',
      body: JSON.stringify(opening),
    }),

  listSaved: () => request<SavedOpening[]>('/openings/saved'),

  getSavedUrls: () => request<string[]>('/openings/saved/urls'),

  deleteSaved: (id: string) =>
    request<{ status: string }>(`/openings/saved/${id}`, {
      method: 'DELETE',
    }),

  toggleJobBoard: (id: string, showOnJobBoard: boolean) =>
    request<{ status: string; show_on_job_board: boolean }>(`/openings/saved/${id}/job-board?show_on_job_board=${showOnJobBoard}`, {
      method: 'PATCH',
    }),
};

// Settings/Account API
export const settings = {
  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ status: string }>('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    }),

  changeEmail: (password: string, newEmail: string) =>
    request<{
      status: string;
      access_token: string;
      refresh_token: string;
      expires_in: number;
    }>('/auth/change-email', {
      method: 'POST',
      body: JSON.stringify({
        password,
        new_email: newEmail,
      }),
    }),

  updateProfile: (data: { name?: string; phone?: string }) =>
    request<{ status: string }>('/auth/profile', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
};

// Projects API
export interface ProjectFilters {
  status?: ProjectStatus;
}

export const projects = {
  list: (filters?: ProjectFilters) => {
    const params = new URLSearchParams();
    if (filters?.status) params.append('status', filters.status);
    const query = params.toString();
    return request<Project[]>(`/projects${query ? `?${query}` : ''}`);
  },

  get: (id: string) => request<Project>(`/projects/${id}`),

  create: (data: ProjectCreate) =>
    request<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: ProjectUpdate) =>
    request<Project>(`/projects/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<{ status: string }>(`/projects/${id}`, {
      method: 'DELETE',
    }),

  // Project candidates
  addCandidate: (projectId: string, data: ProjectCandidateAdd) =>
    request<ProjectCandidate>(`/projects/${projectId}/candidates`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  bulkAddCandidates: (projectId: string, data: ProjectCandidateBulkAdd) =>
    request<{ added: number; skipped: number }>(`/projects/${projectId}/candidates/bulk`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listCandidates: (projectId: string, stage?: CandidateStage) => {
    const params = stage ? `?stage=${stage}` : '';
    return request<ProjectCandidate[]>(`/projects/${projectId}/candidates${params}`);
  },

  updateCandidate: (projectId: string, candidateId: string, data: ProjectCandidateUpdate) =>
    request<ProjectCandidate>(`/projects/${projectId}/candidates/${candidateId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  removeCandidate: (projectId: string, candidateId: string) =>
    request<{ status: string }>(`/projects/${projectId}/candidates/${candidateId}`, {
      method: 'DELETE',
    }),

  getStats: (projectId: string) =>
    request<ProjectStats>(`/projects/${projectId}/stats`),

  // Outreach
  sendOutreach: (projectId: string, data: OutreachSendRequest) =>
    request<OutreachSendResult>(`/projects/${projectId}/outreach`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listOutreach: (projectId: string, status?: OutreachStatus) => {
    const params = status ? `?status=${status}` : '';
    return request<Outreach[]>(`/projects/${projectId}/outreach${params}`);
  },

  // Direct screening invites (skips interest step)
  sendScreeningInvite: (projectId: string, data: OutreachSendRequest) =>
    request<OutreachSendResult>(`/projects/${projectId}/screening-invite`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// Outreach API (public endpoints - no auth required)
export const outreach = {
  getInfo: async (token: string): Promise<OutreachPublicInfo> => {
    const response = await fetch(`${API_BASE}/outreach/${token}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to load' }));
      throw new Error(error.detail || 'Failed to load');
    }
    return response.json();
  },

  respond: async (token: string, interested: boolean): Promise<OutreachInterestResponse> => {
    const response = await fetch(`${API_BASE}/outreach/${token}/respond?interested=${interested}`, {
      method: 'POST',
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to respond' }));
      throw new Error(error.detail || 'Failed to respond');
    }
    return response.json();
  },

  startInterview: async (token: string): Promise<OutreachInterviewStart> => {
    const response = await fetch(`${API_BASE}/outreach/${token}/start-interview`, {
      method: 'POST',
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to start interview' }));
      throw new Error(error.detail || 'Failed to start interview');
    }
    return response.json();
  },
};

// Screening API (direct screening invites - requires auth to start)
export const screening = {
  getInfo: async (token: string): Promise<ScreeningPublicInfo> => {
    const response = await fetch(`${API_BASE}/screening/${token}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to load' }));
      throw new Error(error.detail || 'Failed to load');
    }
    return response.json();
  },

  start: async (token: string, userEmail: string): Promise<OutreachInterviewStart> => {
    const response = await fetch(`${API_BASE}/screening/${token}/start?user_email=${encodeURIComponent(userEmail)}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getAccessToken()}`,
        'Content-Type': 'application/json',
      },
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to start screening' }));
      throw new Error(error.detail || 'Failed to start screening');
    }
    return response.json();
  },
};

// Tutor API
export interface TutorSessionCreate {
  mode: 'interview_prep' | 'language_test';
  language?: 'en' | 'es';
}

export interface TutorSessionStart {
  interview_id: string;
  websocket_url: string;
}

export const tutor = {
  createSession: (data: TutorSessionCreate) =>
    request<TutorSessionStart>('/tutor/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// WebSocket URL helper
export function getInterviewWSUrl(interviewId: string): string {
  return `ws://localhost:8001/api/ws/interview/${interviewId}`;
}

// Public Jobs API (no auth required)
const JOBS_BASE = 'http://localhost:8001/api/job-board';

export const publicJobs = {
  list: async (filters?: {
    location?: string;
    department?: string;
    remote?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<JobListResponse> => {
    const params = new URLSearchParams();
    if (filters?.location) params.append('location', filters.location);
    if (filters?.department) params.append('department', filters.department);
    if (filters?.remote !== undefined) params.append('remote', String(filters.remote));
    if (filters?.limit) params.append('limit', String(filters.limit));
    if (filters?.offset) params.append('offset', String(filters.offset));

    const queryString = params.toString();
    const url = queryString ? `${JOBS_BASE}?${queryString}` : JOBS_BASE;

    const response = await fetch(url);
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to load jobs' }));
      throw new Error(error.detail || 'Failed to load jobs');
    }
    return response.json();
  },

  getDetail: async (jobId: string): Promise<PublicJobDetail> => {
    const response = await fetch(`${JOBS_BASE}/${jobId}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Job not found' }));
      throw new Error(error.detail || 'Job not found');
    }
    return response.json();
  },

  apply: async (
    jobId: string,
    data: {
      name: string;
      email: string;
      phone?: string;
      cover_letter?: string;
      source?: string;
      resume: File;
    }
  ): Promise<ApplicationSubmitResponse> => {
    const formData = new FormData();
    formData.append('name', data.name);
    formData.append('email', data.email);
    if (data.phone) formData.append('phone', data.phone);
    if (data.cover_letter) formData.append('cover_letter', data.cover_letter);
    formData.append('source', data.source || 'direct');
    formData.append('resume', data.resume);

    const response = await fetch(`${JOBS_BASE}/${jobId}/apply`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to submit application' }));
      throw new Error(error.detail || 'Failed to submit application');
    }
    return response.json();
  },
};
