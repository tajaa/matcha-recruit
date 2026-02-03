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
  BusinessRegister,
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
  TutorSessionSummary,
  TutorSessionDetail,
  TutorMetricsAggregate,
  TutorProgressResponse,
  TutorSessionComparison,
  TutorVocabularyStats,
  // Beta access types
  CandidateBetaListResponse,
  CandidateSessionSummary,
  // ER Copilot types
  ERCase,
  ERCaseCreate,
  ERCaseUpdate,
  ERCaseListResponse,
  ERCaseStatus,
  ERDocument,
  ERDocumentType,
  ERDocumentUploadResponse,
  TimelineAnalysis,
  DiscrepancyAnalysis,
  PolicyCheckAnalysis,
  EvidenceSearchResponse,
  ERTaskStatus,
  ERAuditLogResponse,
  // IR (Incident Report) types
  IRIncident,
  IRIncidentCreate,
  IRIncidentUpdate,
  IRIncidentListResponse,
  IRIncidentType,
  IRSeverity,
  IRStatus,
  IRDocument,
  IRDocumentType,
  IRDocumentUploadResponse,
  IRAnalyticsSummary,
  IRTrendsAnalysis,
  IRLocationAnalysis,
  IRCategorizationAnalysis,
  IRSeverityAnalysis,
  IRRootCauseAnalysis,
  IRRecommendationsAnalysis,
  IRSimilarIncidentsAnalysis,
  IRAuditLogResponse,
  // Policy types
  Policy,
  PolicyCreate,
  PolicyUpdate,
  PolicySignature,
  SignatureRequest,
  OfferLetter,
  OfferLetterCreate,
  OfferLetterUpdate,
    BlogPost,
    BlogPostCreate,
    BlogPostUpdate,
    BlogStatus,
    BlogListResponse,
    BlogComment,
    BlogCommentCreate,
    CommentStatus,
  } from '../types';
import type {
  Lead,
  LeadWithContacts,
  LeadUpdate,
  Contact,
  ContactCreate,
  LeadEmail,
  EmailStatus,
  EmailUpdate,
  LeadStatus,
  LeadPriority,
  SearchRequest,
  SearchResult,
} from '../types/leads';
import type {
  Campaign,
  CampaignCreate,
  CampaignUpdate,
  CampaignWithOffers,
  CampaignOffer,
  CampaignOfferCreate,
  CreatorOffer,
  CampaignPayment,
  AffiliateLink,
  AffiliateLinkCreate,
  AffiliateStats,
  CreatorValuation,
  ContractTemplate,
  ContractTemplateCreate,
  ContractTemplateUpdate,
  GeneratedContract,
  CampaignDashboardStats,
  CreatorCampaignStats,
} from '../types/campaigns';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

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

  registerBusiness: async (data: BusinessRegister): Promise<TokenResponse> => {
    const response = await fetch(`${API_BASE}/auth/register/business`, {
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

  update: (id: string, data: Partial<CompanyCreate>) =>
    request<Company>(`/companies/${id}`, {
      method: 'PATCH',
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

  // Self-service endpoints for logged-in candidates
  updateMyResume: async (file: File): Promise<Candidate> => {
    const formData = new FormData();
    formData.append('file', file);

    const headers: HeadersInit = {};
    const token = getAccessToken();

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    } else {
      throw new Error('Not logged in. Please refresh the page and try again.');
    }

    const response = await fetch(`${API_BASE}/candidates/me/resume`, {
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

  updateMyProfile: (data: { name?: string; phone?: string; skills?: string; summary?: string }) =>
    request<Candidate>('/candidates/me/profile', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  listForCompany: () =>
    request<{id: string, name: string, email: string}[]>(`/candidates/company`),
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
    const response = await fetch(`${API_BASE}/screening/${token}/start`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getAccessToken()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ user_email: userEmail }),
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
  duration_minutes?: 2 | 5 | 8;
  interview_role?: string;  // For interview_prep: role being practiced for (e.g., "CTO")
}

export interface TutorSessionStart {
  interview_id: string;
  websocket_url: string;
  max_session_duration_seconds: number;
}

export const tutor = {
  createSession: (data: TutorSessionCreate) =>
    request<TutorSessionStart>('/tutor/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// Tutor Metrics API (admin only)
export const tutorMetrics = {
  listSessions: (filters?: { mode?: string; limit?: number; offset?: number }) => {
    const params = new URLSearchParams();
    if (filters?.mode) params.append('mode', filters.mode);
    if (filters?.limit) params.append('limit', filters.limit.toString());
    if (filters?.offset) params.append('offset', filters.offset.toString());
    const query = params.toString();
    return request<TutorSessionSummary[]>(`/tutor/sessions${query ? `?${query}` : ''}`);
  },

  getSession: (id: string) =>
    request<TutorSessionDetail>(`/tutor/sessions/${id}`),

  deleteSession: (id: string) =>
    request<{ status: string; session_id: string }>(`/tutor/sessions/${id}`, {
      method: 'DELETE',
    }),

  getAggregateMetrics: () =>
    request<TutorMetricsAggregate>('/tutor/metrics/aggregate'),

  getProgress: (language?: string, limit: number = 20) => {
    const params = new URLSearchParams();
    if (language) params.append('language', language);
    params.append('limit', limit.toString());
    return request<TutorProgressResponse>(`/tutor/progress?${params.toString()}`);
  },

  getSessionComparison: (sessionId: string) =>
    request<TutorSessionComparison>(`/tutor/sessions/${sessionId}/comparison`),

  getVocabularyStats: (language: string = 'es', limit: number = 10) =>
    request<TutorVocabularyStats>(`/tutor/vocabulary?language=${language}&limit=${limit}`),
};

// WebSocket URL helper
export function getInterviewWSUrl(interviewId: string): string {
  const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';
  const wsBase = apiBase.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
  return `${wsBase}/ws/interview/${interviewId}`;
}

// Public Jobs API (no auth required)
const JOBS_BASE = `${import.meta.env.VITE_API_URL || 'http://localhost:8001/api'}/job-board`;

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

// ER Copilot API
export const erCopilot = {
  // Cases
  listCases: (status?: ERCaseStatus): Promise<ERCaseListResponse> => {
    const params = status ? `?status=${status}` : '';
    return request<ERCaseListResponse>(`/er/cases${params}`);
  },

  getCase: (id: string): Promise<ERCase> => request<ERCase>(`/er/cases/${id}`),

  createCase: (data: ERCaseCreate): Promise<ERCase> =>
    request<ERCase>('/er/cases', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateCase: (id: string, data: ERCaseUpdate): Promise<ERCase> =>
    request<ERCase>(`/er/cases/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteCase: (id: string): Promise<{ status: string; case_id: string }> =>
    request<{ status: string; case_id: string }>(`/er/cases/${id}`, {
      method: 'DELETE',
    }),

  // Documents
  uploadDocument: async (
    caseId: string,
    file: File,
    documentType: ERDocumentType
  ): Promise<ERDocumentUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', documentType);

    const token = getAccessToken();
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/er/cases/${caseId}/documents`, {
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

  listDocuments: (caseId: string): Promise<ERDocument[]> =>
    request<ERDocument[]>(`/er/cases/${caseId}/documents`),

  getDocument: (caseId: string, docId: string): Promise<ERDocument> =>
    request<ERDocument>(`/er/cases/${caseId}/documents/${docId}`),

  deleteDocument: (caseId: string, docId: string): Promise<{ status: string; document_id: string }> =>
    request<{ status: string; document_id: string }>(`/er/cases/${caseId}/documents/${docId}`, {
      method: 'DELETE',
    }),

  reprocessDocument: (caseId: string, docId: string): Promise<ERTaskStatus> =>
    request<ERTaskStatus>(`/er/cases/${caseId}/documents/${docId}/reprocess`, {
      method: 'POST',
    }),

  reprocessAllDocuments: (caseId: string): Promise<{
    status: string;
    message: string;
    processed: number;
    total?: number;
    results?: Array<{ id: string; filename: string; status: string; error?: string }>;
  }> =>
    request(`/er/cases/${caseId}/documents/reprocess-all`, {
      method: 'POST',
    }),

  // Analysis
  generateTimeline: (caseId: string): Promise<ERTaskStatus> =>
    request<ERTaskStatus>(`/er/cases/${caseId}/analysis/timeline`, {
      method: 'POST',
    }),

  getTimeline: (caseId: string): Promise<{ analysis: TimelineAnalysis; source_documents: string[]; generated_at: string }> =>
    request<{ analysis: TimelineAnalysis; source_documents: string[]; generated_at: string }>(`/er/cases/${caseId}/analysis/timeline`),

  generateDiscrepancies: (caseId: string): Promise<ERTaskStatus> =>
    request<ERTaskStatus>(`/er/cases/${caseId}/analysis/discrepancies`, {
      method: 'POST',
    }),

  getDiscrepancies: (caseId: string): Promise<{ analysis: DiscrepancyAnalysis; source_documents: string[]; generated_at: string }> =>
    request<{ analysis: DiscrepancyAnalysis; source_documents: string[]; generated_at: string }>(`/er/cases/${caseId}/analysis/discrepancies`),

  runPolicyCheck: (caseId: string): Promise<ERTaskStatus> =>
    request<ERTaskStatus>(`/er/cases/${caseId}/analysis/policy-check`, {
      method: 'POST',
    }),

  getPolicyCheck: (caseId: string): Promise<{ analysis: PolicyCheckAnalysis; source_documents: string[]; generated_at: string }> =>
    request<{ analysis: PolicyCheckAnalysis; source_documents: string[]; generated_at: string }>(`/er/cases/${caseId}/analysis/policy-check`),

  searchEvidence: (caseId: string, query: string, topK: number = 5): Promise<EvidenceSearchResponse> =>
    request<EvidenceSearchResponse>(`/er/cases/${caseId}/search`, {
      method: 'POST',
      body: JSON.stringify({ query, top_k: topK }),
    }),

  // Reports
  generateSummary: (caseId: string): Promise<ERTaskStatus> =>
    request<ERTaskStatus>(`/er/cases/${caseId}/reports/summary`, {
      method: 'POST',
    }),

  generateDetermination: (caseId: string, determination: string): Promise<ERTaskStatus> =>
    request<ERTaskStatus>(`/er/cases/${caseId}/reports/determination`, {
      method: 'POST',
      body: JSON.stringify({ determination }),
    }),

  getReport: (caseId: string, reportType: 'summary' | 'determination'): Promise<{ report_type: string; content: string; generated_at: string; source_documents: string[] }> =>
    request<{ report_type: string; content: string; generated_at: string; source_documents: string[] }>(`/er/cases/${caseId}/reports/${reportType}`),

  // Audit Log
  getAuditLog: (caseId: string, limit: number = 100, offset: number = 0): Promise<ERAuditLogResponse> =>
    request<ERAuditLogResponse>(`/er/cases/${caseId}/audit-log?limit=${limit}&offset=${offset}`),
};

// IR (Incident Report) API
export const irIncidents = {
  // Incidents CRUD
  listIncidents: (params?: {
    status?: IRStatus;
    incident_type?: IRIncidentType;
    severity?: IRSeverity;
    location?: string;
    from_date?: string;
    to_date?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }): Promise<IRIncidentListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.append('status', params.status);
    if (params?.incident_type) searchParams.append('incident_type', params.incident_type);
    if (params?.severity) searchParams.append('severity', params.severity);
    if (params?.location) searchParams.append('location', params.location);
    if (params?.from_date) searchParams.append('from_date', params.from_date);
    if (params?.to_date) searchParams.append('to_date', params.to_date);
    if (params?.search) searchParams.append('search', params.search);
    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.offset) searchParams.append('offset', params.offset.toString());
    const query = searchParams.toString();
    return request<IRIncidentListResponse>(`/ir/incidents${query ? `?${query}` : ''}`);
  },

  getIncident: (id: string): Promise<IRIncident> => request<IRIncident>(`/ir/incidents/${id}`),

  createIncident: (data: IRIncidentCreate): Promise<IRIncident> =>
    request<IRIncident>('/ir/incidents', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateIncident: (id: string, data: IRIncidentUpdate): Promise<IRIncident> =>
    request<IRIncident>(`/ir/incidents/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteIncident: (id: string): Promise<{ message: string }> =>
    request<{ message: string }>(`/ir/incidents/${id}`, {
      method: 'DELETE',
    }),

  // Documents
  uploadDocument: async (
    incidentId: string,
    file: File,
    documentType: IRDocumentType
  ): Promise<IRDocumentUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', documentType);

    const token = getAccessToken();
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/ir/incidents/${incidentId}/documents`, {
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

  listDocuments: (incidentId: string): Promise<IRDocument[]> =>
    request<IRDocument[]>(`/ir/incidents/${incidentId}/documents`),

  deleteDocument: (incidentId: string, docId: string): Promise<{ message: string }> =>
    request<{ message: string }>(`/ir/incidents/${incidentId}/documents/${docId}`, {
      method: 'DELETE',
    }),

  // Analytics
  getAnalyticsSummary: (): Promise<IRAnalyticsSummary> =>
    request<IRAnalyticsSummary>('/ir/incidents/analytics/summary'),

  getAnalyticsTrends: (period: 'daily' | 'weekly' | 'monthly' = 'daily', days: number = 30): Promise<IRTrendsAnalysis> =>
    request<IRTrendsAnalysis>(`/ir/incidents/analytics/trends?period=${period}&days=${days}`),

  getAnalyticsLocations: (limit: number = 10): Promise<IRLocationAnalysis> =>
    request<IRLocationAnalysis>(`/ir/incidents/analytics/locations?limit=${limit}`),

  // AI Analysis
  analyzeCategorization: (incidentId: string): Promise<IRCategorizationAnalysis> =>
    request<IRCategorizationAnalysis>(`/ir/incidents/${incidentId}/analyze/categorize`, {
      method: 'POST',
    }),

  analyzeSeverity: (incidentId: string): Promise<IRSeverityAnalysis> =>
    request<IRSeverityAnalysis>(`/ir/incidents/${incidentId}/analyze/severity`, {
      method: 'POST',
    }),

  analyzeRootCause: (incidentId: string): Promise<IRRootCauseAnalysis> =>
    request<IRRootCauseAnalysis>(`/ir/incidents/${incidentId}/analyze/root-cause`, {
      method: 'POST',
    }),

  analyzeRecommendations: (incidentId: string): Promise<IRRecommendationsAnalysis> =>
    request<IRRecommendationsAnalysis>(`/ir/incidents/${incidentId}/analyze/recommendations`, {
      method: 'POST',
    }),

  analyzeSimilarIncidents: (incidentId: string): Promise<IRSimilarIncidentsAnalysis> =>
    request<IRSimilarIncidentsAnalysis>(`/ir/incidents/${incidentId}/analyze/similar`, {
      method: 'POST',
    }),

  clearAnalysisCache: (incidentId: string, analysisType: string): Promise<{ message: string }> =>
    request<{ message: string }>(`/ir/incidents/${incidentId}/analyze/${analysisType}`, {
      method: 'DELETE',
    }),

  // Audit Log
  getAuditLog: (incidentId: string, limit: number = 50, offset: number = 0): Promise<IRAuditLogResponse> =>
    request<IRAuditLogResponse>(`/ir/incidents/${incidentId}/audit-log?limit=${limit}&offset=${offset}`),
};

// Admin Beta Access API
export const adminBeta = {
  listCandidates: (): Promise<CandidateBetaListResponse> =>
    request<CandidateBetaListResponse>('/auth/admin/candidates/beta'),

  toggleBetaAccess: (userId: string, feature: string, enabled: boolean): Promise<{ status: string; beta_features: Record<string, boolean> }> =>
    request<{ status: string; beta_features: Record<string, boolean> }>(`/auth/admin/candidates/${userId}/beta`, {
      method: 'PATCH',
      body: JSON.stringify({ feature, enabled }),
    }),

  awardTokens: (userId: string, amount: number): Promise<{ status: string; new_total: number }> =>
    request<{ status: string; new_total: number }>(`/auth/admin/candidates/${userId}/tokens`, {
      method: 'POST',
      body: JSON.stringify({ amount }),
    }),

  getCandidateSessions: (userId: string): Promise<CandidateSessionSummary[]> =>
    request<CandidateSessionSummary[]>(`/auth/admin/candidates/${userId}/sessions`),

  updateAllowedRoles: (userId: string, roles: string[]): Promise<{ status: string; allowed_interview_roles: string[] }> =>
    request<{ status: string; allowed_interview_roles: string[] }>(`/auth/admin/candidates/${userId}/roles`, {
      method: 'PUT',
      body: JSON.stringify({ roles }),
    }),
};

// Admin Business Registrations API
import type { BusinessRegistration, BusinessRegistrationListResponse, BusinessRegistrationStatus, CompanyWithFeatures, EnabledFeatures } from '../types';

export const adminBusinessRegistrations = {
  list: (status?: BusinessRegistrationStatus): Promise<BusinessRegistrationListResponse> => {
    const params = status ? `?status=${status}` : '';
    return request<BusinessRegistrationListResponse>(`/admin/business-registrations${params}`);
  },

  get: (companyId: string): Promise<BusinessRegistration> =>
    request<BusinessRegistration>(`/admin/business-registrations/${companyId}`),

  approve: (companyId: string): Promise<{ status: string; message: string }> =>
    request<{ status: string; message: string }>(`/admin/business-registrations/${companyId}/approve`, {
      method: 'POST',
    }),

  reject: (companyId: string, reason: string): Promise<{ status: string; message: string }> =>
    request<{ status: string; message: string }>(`/admin/business-registrations/${companyId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
};

// Company Features (Admin)
export const adminCompanyFeatures = {
  list: (): Promise<CompanyWithFeatures[]> =>
    request<CompanyWithFeatures[]>('/admin/company-features'),

  toggle: (companyId: string, feature: string, enabled: boolean): Promise<{ enabled_features: EnabledFeatures }> =>
    request<{ enabled_features: EnabledFeatures }>(`/admin/company-features/${companyId}`, {
      method: 'PATCH',
      body: JSON.stringify({ feature, enabled }),
    }),
};

// Admin Overview
export interface AdminOverviewCompany {
  id: string;
  name: string;
  industry: string | null;
  size: string | null;
  status: string;
  created_at: string | null;
  approved_at: string | null;
  total_employees: number;
  active_employees: number;
  terminated_employees: number;
  pending_employees: number;
}

export interface AdminOverviewTotals {
  total_companies: number;
  total_employees: number;
  active_employees: number;
  pending_employees: number;
  terminated_employees: number;
}

export interface AdminOverviewResponse {
  companies: AdminOverviewCompany[];
  totals: AdminOverviewTotals;
}

export const adminOverview = {
  get: (): Promise<AdminOverviewResponse> =>
    request<AdminOverviewResponse>('/admin/overview'),
};

// Jurisdiction Admin API
export interface JurisdictionLocation {
  id: string;
  name: string | null;
  city: string;
  state: string;
  company_name: string;
  auto_check_enabled: boolean;
  auto_check_interval_days: number;
  next_auto_check: string | null;
  last_compliance_check: string | null;
}

export interface Jurisdiction {
  id: string;
  city: string;
  state: string;
  county: string | null;
  parent_id: string | null;
  parent_city: string | null;
  parent_state: string | null;
  children_count: number;
  requirement_count: number;
  legislation_count: number;
  location_count: number;
  auto_check_count: number;
  last_verified_at: string | null;
  created_at: string | null;
  locations: JurisdictionLocation[];
}

export interface JurisdictionCreate {
  city: string;
  state: string;
  county?: string;
  parent_id?: string;
}

export interface JurisdictionTotals {
  total_jurisdictions: number;
  total_requirements: number;
  total_legislation: number;
}

export interface JurisdictionsResponse {
  jurisdictions: Jurisdiction[];
  totals: JurisdictionTotals;
}

export interface JurisdictionRequirement {
  id: string;
  requirement_key: string;
  category: string;
  jurisdiction_level: string;
  jurisdiction_name: string;
  title: string;
  description: string | null;
  current_value: string | null;
  numeric_value: number | null;
  source_url: string | null;
  source_name: string | null;
  effective_date: string | null;
  expiration_date: string | null;
  previous_value: string | null;
  last_changed_at: string | null;
  last_verified_at: string | null;
  updated_at: string | null;
}

export interface JurisdictionLegislation {
  id: string;
  legislation_key: string;
  category: string | null;
  title: string;
  description: string | null;
  current_status: string;
  expected_effective_date: string | null;
  impact_summary: string | null;
  source_url: string | null;
  source_name: string | null;
  confidence: number | null;
  last_verified_at: string | null;
  updated_at: string | null;
}

export interface JurisdictionDetail {
  id: string;
  city: string;
  state: string;
  county: string | null;
  parent_id: string | null;
  children: { id: string; city: string; state: string }[];
  requirement_count: number;
  legislation_count: number;
  last_verified_at: string | null;
  created_at: string | null;
  requirements: JurisdictionRequirement[];
  legislation: JurisdictionLegislation[];
  locations: JurisdictionLocation[];
}

export const adminJurisdictions = {
  list: (): Promise<JurisdictionsResponse> =>
    request<JurisdictionsResponse>('/admin/jurisdictions'),

  get: (id: string): Promise<JurisdictionDetail> =>
    request<JurisdictionDetail>(`/admin/jurisdictions/${id}`),

  create: (data: JurisdictionCreate): Promise<Jurisdiction> =>
    request<Jurisdiction>('/admin/jurisdictions', { method: 'POST', body: JSON.stringify(data) }),

  check: async (id: string): Promise<Response> => {
    const token = getAccessToken();
    const response = await fetch(`/api/admin/jurisdictions/${id}/check`, {
      method: 'POST',
      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    });
    if (!response.ok) throw new Error('Failed to start jurisdiction check');
    return response;
  },
};

// Scheduler Admin API
export interface SchedulerSetting {
  id: string;
  task_key: string;
  display_name: string;
  description: string | null;
  enabled: boolean;
  max_per_cycle: number;
  created_at: string | null;
  updated_at: string | null;
  stats: Record<string, unknown>;
}

export interface SchedulerStatsOverview {
  total_locations: number;
  auto_check_enabled: number;
  checks_24h: number;
  failed_24h: number;
}

export interface SchedulerLogEntry {
  id: string;
  location_id: string;
  company_id: string;
  location_name: string | null;
  check_type: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  new_count: number;
  updated_count: number;
  alert_count: number;
  error_message: string | null;
}

export interface SchedulerStatsResponse {
  overview: SchedulerStatsOverview;
  recent_logs: SchedulerLogEntry[];
}

export interface SchedulerLocation {
  id: string;
  name: string;
  city: string | null;
  state: string | null;
  auto_check_enabled: boolean;
  auto_check_interval_days: number;
  next_auto_check: string | null;
  last_compliance_check: string | null;
}

export interface SchedulerCompanyLocations {
  company_id: string;
  company_name: string;
  locations: SchedulerLocation[];
}

export const adminSchedulers = {
  list: (): Promise<SchedulerSetting[]> =>
    request<SchedulerSetting[]>('/admin/schedulers'),

  update: (taskKey: string, data: { enabled?: boolean; max_per_cycle?: number }): Promise<SchedulerSetting> =>
    request<SchedulerSetting>(`/admin/schedulers/${taskKey}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  trigger: (taskKey: string): Promise<{ status: string; task_key: string; message: string }> =>
    request<{ status: string; task_key: string; message: string }>(`/admin/schedulers/${taskKey}/trigger`, {
      method: 'POST',
    }),

  stats: (): Promise<SchedulerStatsResponse> =>
    request<SchedulerStatsResponse>('/admin/schedulers/stats'),

  listLocations: (): Promise<SchedulerCompanyLocations[]> =>
    request<SchedulerCompanyLocations[]>('/admin/schedulers/locations'),

  updateLocation: (locationId: string, data: { auto_check_enabled?: boolean; auto_check_interval_days?: number; next_auto_check_minutes?: number }): Promise<SchedulerLocation> =>
    request<SchedulerLocation>(`/admin/schedulers/locations/${locationId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};

// Blog API
export const blogs = {
  list: (options?: { status?: BlogStatus; tag?: string; page?: number; limit?: number }) => {
    const params = new URLSearchParams();
    if (options?.status) params.append('status', options.status);
    if (options?.tag) params.append('tag', options.tag);
    if (options?.page) params.append('page', String(options.page));
    if (options?.limit) params.append('limit', String(options.limit));
    const query = params.toString();
    return request<BlogListResponse>(`/blogs${query ? `?${query}` : ''}`);
  },

  get: (slug: string, sessionId?: string) => {
    const params = new URLSearchParams();
    if (sessionId) params.append('session_id', sessionId);
    const query = params.toString();
    return request<BlogPost>(`/blogs/${slug}${query ? `?${query}` : ''}`);
  },

  toggleLike: (slug: string, sessionId?: string) =>
    request<{ likes_count: number; liked: boolean }>(`/blogs/${slug}/like`, {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    }),

  listComments: (slug: string) =>
    request<BlogComment[]>(`/blogs/${slug}/comments`),

  submitComment: (slug: string, data: BlogCommentCreate) =>
    request<BlogComment>(`/blogs/${slug}/comments`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listPendingComments: () =>
    request<BlogComment[]>(`/blogs/comments/pending`),

  moderateComment: (id: string, status: CommentStatus) =>
    request<BlogComment>(`/blogs/comments/${id}?status=${status}`, {
      method: 'PATCH',
    }),

  create: (data: BlogPostCreate) =>
    request<BlogPost>(`/blogs`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: BlogPostUpdate) =>
    request<BlogPost>(`/blogs/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request(`/blogs/${id}`, {
      method: 'DELETE',
    }),

  uploadImage: async (file: File): Promise<{ url: string }> => {
    const formData = new FormData();
    formData.append('file', file);

    const headers: HeadersInit = {};
    const token = getAccessToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/blogs/upload`, {
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
};

export const policies = {
  list: (status?: string) => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    const query = params.toString();
    return request<Policy[]>(`/policies${query ? `?${query}` : ''}`);
  },

  create: (data: PolicyCreate) =>
    request<Policy>(`/policies`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  get: (id: string) =>
    request<Policy>(`/policies/${id}`),

  update: (id: string, data: PolicyUpdate) =>
    request<Policy>(`/policies/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request(`/policies/${id}`, {
      method: 'DELETE',
    }),

  sendSignatures: (policyId: string, requests: SignatureRequest[]) =>
    request<{message: string, signatures: number}>(`/policies/${policyId}/signatures`, {
      method: 'POST',
      body: JSON.stringify(requests),
    }),

  listSignatures: (policyId: string) =>
    request<PolicySignature[]>(`/policies/${policyId}/signatures`),

  cancelSignature: (signatureId: string) =>
    request(`/policies/signatures/${signatureId}`, {
      method: 'DELETE',
    }),

    resendSignature: (signatureId: string) =>
      request<{message: string}>(`/policies/signatures/${signatureId}/resend`, {
        method: 'POST',
      }),
};

// Offer Letters API
export const offerLetters = {
  list: () => request<OfferLetter[]>('/offer-letters'),

  get: (id: string) => request<OfferLetter>(`/offer-letters/${id}`),

  create: (data: OfferLetterCreate) =>
    request<OfferLetter>('/offer-letters', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: OfferLetterUpdate) =>
    request<OfferLetter>(`/offer-letters/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  uploadLogo: async (offerId: string, file: File): Promise<{ url: string }> => {
    const formData = new FormData();
    formData.append('file', file);

    const token = getAccessToken();
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/offer-letters/${offerId}/logo`, {
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

  downloadPdf: async (offerId: string, candidateName: string): Promise<void> => {
    const token = getAccessToken();
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/offer-letters/${offerId}/pdf`, {
      method: 'GET',
      headers,
    });

    if (!response.ok) {
      throw new Error('Failed to download PDF');
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `offer-letter-${candidateName.replace(/\s+/g, '-')}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  },
};

// =============================================================================
// LEADS AGENT API
// =============================================================================

export const leadsAgent = {
  search: (params: SearchRequest & { preview?: boolean }) => {
    const preview = params.preview ? '?preview=true' : '';
    const { preview: _, ...body } = params as any;
    return request<SearchResult>(`/leads-agent/search${preview}`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  list: (status?: LeadStatus, priority?: LeadPriority) => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (priority) params.append('priority', priority);
    const query = params.toString();
    return request<Lead[]>(`/leads-agent/leads${query ? `?${query}` : ''}`);
  },

  get: (id: string) => request<LeadWithContacts>(`/leads-agent/leads/${id}`),

  update: (id: string, data: LeadUpdate) =>
    request<Lead>(`/leads-agent/leads/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<{ status: string }>(`/leads-agent/leads/${id}`, {
      method: 'DELETE',
    }),

  getPipeline: () => request<Record<string, Lead[]>>('/leads-agent/pipeline'),

  findContacts: (leadId: string) =>
    request<Contact[]>(`/leads-agent/leads/${leadId}/find-contacts`, {
      method: 'POST',
    }),

  researchContact: (leadId: string) =>
    request<Contact | null>(`/leads-agent/leads/${leadId}/research-contact`, {
      method: 'POST',
    }),

  reanalyze: (leadId: string) =>
    request<Lead>(`/leads-agent/leads/${leadId}/analyze`, {
      method: 'POST',
    }),

  rankContacts: (leadId: string) =>
    request<Contact>(`/leads-agent/leads/${leadId}/rank-contacts`, {
      method: 'POST',
    }),

  setPrimaryContact: (leadId: string, contactId: string) =>
    request<Contact>(`/leads-agent/leads/${leadId}/contacts/${contactId}/set-primary`, {
      method: 'POST',
    }),

  addContact: (leadId: string, data: ContactCreate) =>
    request<Contact>(`/leads-agent/leads/${leadId}/contacts`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  draftEmail: (leadId: string, contactId?: string) =>
    request<LeadEmail>(`/leads-agent/leads/${leadId}/draft-email`, {
      method: 'POST',
      body: JSON.stringify({ contact_id: contactId }),
    }),

  listEmails: (status?: EmailStatus, leadId?: string) => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (leadId) params.append('lead_id', leadId);
    const query = params.toString();
    return request<LeadEmail[]>(`/leads-agent/emails${query ? `?${query}` : ''}`);
  },

  updateEmail: (id: string, data: EmailUpdate) =>
    request<LeadEmail>(`/leads-agent/emails/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  approveEmail: (id: string) =>
    request<LeadEmail>(`/leads-agent/emails/${id}/approve`, {
      method: 'POST',
    }),

  sendEmail: (id: string) =>
    request<LeadEmail>(`/leads-agent/emails/${id}/send`, {
      method: 'POST',
    }),

  policies: {
    list: (status?: string) => {
      const params = new URLSearchParams();
      if (status) params.append('status', status);
      const query = params.toString();
      return request<Policy[]>(`/policies${query ? `?${query}` : ''}`);
    },

    create: (data: PolicyCreate) =>
      request<Policy>(`/policies`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),

    get: (id: string) =>
      request<Policy>(`/policies/${id}`),

    update: (id: string, data: PolicyUpdate) =>
      request<Policy>(`/policies/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),

    delete: (id: string) =>
      request(`/policies/${id}`, {
        method: 'DELETE',
      }),

    sendSignatures: (policyId: string, requests: SignatureRequest[]) =>
      request<{message: string, signatures: number}>(`/policies/${policyId}/signatures`, {
        method: 'POST',
        body: JSON.stringify(requests),
      }),

    listSignatures: (policyId: string) =>
      request<PolicySignature[]>(`/policies/${policyId}/signatures`),

    cancelSignature: (signatureId: string) =>
      request(`/policies/signatures/${signatureId}`, {
        method: 'DELETE',
      }),

    resendSignature: (signatureId: string) =>
      request<{message: string}>(`/policies/signatures/${signatureId}/resend`, {
        method: 'POST',
      }),
  },
};

// =============================================================================
// CREATOR PLATFORM API
// =============================================================================

import type {
  Creator,
  CreatorUpdate,
  CreatorPublic,
  CreatorRegister,
  PlatformConnection,
  RevenueStream,
  RevenueStreamCreate,
  RevenueStreamUpdate,
  RevenueEntry,
  RevenueEntryCreate,
  RevenueEntryUpdate,
  Expense,
  ExpenseCreate,
  ExpenseUpdate,
  RevenueOverview,
} from '../types/creator';

import type {
  Agency,
  AgencyUpdate,
  AgencyPublic,
  AgencyRegister,
  AgencyMember,
  AgencyMemberInvite,
  AgencyMemberUpdate,
  AgencyWithMembership,
} from '../types/agency';

import type {
  BrandDeal,
  BrandDealCreate,
  BrandDealUpdate,
  BrandDealPublic,
  DealApplication,
  DealApplicationCreate,
  DealApplicationUpdate,
  ApplicationStatusUpdate,
  DealContract,
  ContractCreate,
  ContractStatusUpdate,
  ContractPayment,
  PaymentCreate,
  PaymentUpdate,
} from '../types/deals';

// Creator API
export const creators = {
  // Profile
  getMyProfile: () => request<Creator>('/creators/me'),

  updateMyProfile: (data: CreatorUpdate) =>
    request<Creator>('/creators/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  uploadProfileImage: async (file: File): Promise<Creator> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(`${API_BASE}/creators/me/profile-image`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${getAccessToken()}`,
      },
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail || 'Upload failed');
    }
    return response.json();
  },

  syncProfileFromPlatforms: () =>
    request<Creator>('/creators/me/sync-profile', { method: 'POST' }),

  getPublicProfile: (creatorId: string) =>
    request<CreatorPublic>(`/creators/public/${creatorId}`),

  search: (params: { query: string; limit?: number }) => {
    const searchParams = new URLSearchParams();
    searchParams.append('query', params.query);
    if (params.limit) searchParams.append('limit', params.limit.toString());
    return request<CreatorPublic[]>(`/agencies/creators/search?${searchParams.toString()}`);
  },

  discover: (params?: {
    niches?: string;
    min_followers?: number;
    max_followers?: number;
    limit?: number;
    offset?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.niches) searchParams.append('niches', params.niches);
    if (params?.min_followers) searchParams.append('min_followers', params.min_followers.toString());
    if (params?.max_followers) searchParams.append('max_followers', params.max_followers.toString());
    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.offset) searchParams.append('offset', params.offset.toString());
    const query = searchParams.toString();
    return request<CreatorPublic[]>(`/creators/discover${query ? `?${query}` : ''}`);
  },

  // Platform connections
  listPlatformConnections: () =>
    request<PlatformConnection[]>('/creators/me/platforms'),

  disconnectPlatform: (platform: string) =>
    request<{ status: string }>(`/creators/me/platforms/${platform}`, {
      method: 'DELETE',
    }),

  // Revenue streams
  createRevenueStream: (data: RevenueStreamCreate) =>
    request<RevenueStream>('/creators/me/revenue-streams', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listRevenueStreams: (activeOnly = true) =>
    request<RevenueStream[]>(`/creators/me/revenue-streams?active_only=${activeOnly}`),

  updateRevenueStream: (streamId: string, data: RevenueStreamUpdate) =>
    request<RevenueStream>(`/creators/me/revenue-streams/${streamId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteRevenueStream: (streamId: string) =>
    request<{ status: string }>(`/creators/me/revenue-streams/${streamId}`, {
      method: 'DELETE',
    }),

  // Revenue entries
  createRevenueEntry: (data: RevenueEntryCreate) =>
    request<RevenueEntry>('/creators/me/revenue', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listRevenueEntries: (params?: {
    start_date?: string;
    end_date?: string;
    stream_id?: string;
    limit?: number;
    offset?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.start_date) searchParams.append('start_date', params.start_date);
    if (params?.end_date) searchParams.append('end_date', params.end_date);
    if (params?.stream_id) searchParams.append('stream_id', params.stream_id);
    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.offset) searchParams.append('offset', params.offset.toString());
    const query = searchParams.toString();
    return request<RevenueEntry[]>(`/creators/me/revenue${query ? `?${query}` : ''}`);
  },

  updateRevenueEntry: (entryId: string, data: RevenueEntryUpdate) =>
    request<RevenueEntry>(`/creators/me/revenue/${entryId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteRevenueEntry: (entryId: string) =>
    request<{ status: string }>(`/creators/me/revenue/${entryId}`, {
      method: 'DELETE',
    }),

  // Expenses
  createExpense: (data: ExpenseCreate) =>
    request<Expense>('/creators/me/expenses', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listExpenses: (params?: {
    start_date?: string;
    end_date?: string;
    category?: string;
    limit?: number;
    offset?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.start_date) searchParams.append('start_date', params.start_date);
    if (params?.end_date) searchParams.append('end_date', params.end_date);
    if (params?.category) searchParams.append('category', params.category);
    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.offset) searchParams.append('offset', params.offset.toString());
    const query = searchParams.toString();
    return request<Expense[]>(`/creators/me/expenses${query ? `?${query}` : ''}`);
  },

  updateExpense: (expenseId: string, data: ExpenseUpdate) =>
    request<Expense>(`/creators/me/expenses/${expenseId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteExpense: (expenseId: string) =>
    request<{ status: string }>(`/creators/me/expenses/${expenseId}`, {
      method: 'DELETE',
    }),

  uploadReceipt: async (expenseId: string, file: File): Promise<{ status: string; receipt_url: string }> => {
    const formData = new FormData();
    formData.append('file', file);

    const token = getAccessToken();
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/creators/me/expenses/${expenseId}/receipt`, {
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

  // Dashboard
  getDashboard: () => request<RevenueOverview>('/creators/me/dashboard'),
};

// Agency API
export const agencies = {
  // Profile
  getMyAgency: () => request<AgencyWithMembership>('/agencies/me'),

  updateMyAgency: (data: AgencyUpdate) =>
    request<Agency>('/agencies/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  getPublicAgency: (slug: string) =>
    request<AgencyPublic>(`/agencies/public/${slug}`),

  // Team management
  listMembers: () => request<AgencyMember[]>('/agencies/me/members'),

  inviteMember: (data: AgencyMemberInvite) =>
    request<AgencyMember>('/agencies/me/members', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateMember: (memberId: string, data: AgencyMemberUpdate) =>
    request<AgencyMember>(`/agencies/me/members/${memberId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  removeMember: (memberId: string) =>
    request<{ status: string }>(`/agencies/me/members/${memberId}`, {
      method: 'DELETE',
    }),

  // Creator discovery
  searchCreators: (params?: {
    query?: string;
    niches?: string;
    min_followers?: number;
    verified_only?: boolean;
    limit?: number;
    offset?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.query) searchParams.append('query', params.query);
    if (params?.niches) searchParams.append('niches', params.niches);
    if (params?.min_followers) searchParams.append('min_followers', params.min_followers.toString());
    if (params?.verified_only) searchParams.append('verified_only', 'true');
    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.offset) searchParams.append('offset', params.offset.toString());
    const query = searchParams.toString();
    return request<CreatorPublic[]>(`/agencies/creators/search${query ? `?${query}` : ''}`);
  },

  getCreatorProfile: (creatorId: string) =>
    request<CreatorPublic>(`/agencies/creators/${creatorId}`),
};

// Deals API
export const deals = {
  // Marketplace (for creators)
  browseMarketplace: (params?: {
    niches?: string;
    min_compensation?: number;
    max_compensation?: number;
    platforms?: string;
    limit?: number;
    offset?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.niches) searchParams.append('niches', params.niches);
    if (params?.min_compensation) searchParams.append('min_compensation', params.min_compensation.toString());
    if (params?.max_compensation) searchParams.append('max_compensation', params.max_compensation.toString());
    if (params?.platforms) searchParams.append('platforms', params.platforms);
    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.offset) searchParams.append('offset', params.offset.toString());
    const query = searchParams.toString();
    return request<BrandDealPublic[]>(`/deals/marketplace${query ? `?${query}` : ''}`);
  },

  getMarketplaceDeal: (dealId: string) =>
    request<BrandDealPublic>(`/deals/marketplace/${dealId}`),

  // Agency deal management
  createDeal: (data: BrandDealCreate) =>
    request<BrandDeal>('/deals/agency/deals', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listAgencyDeals: (status?: string) => {
    const query = status ? `?status=${status}` : '';
    return request<BrandDeal[]>(`/deals/agency/deals${query}`);
  },

  getAgencyDeal: (dealId: string) =>
    request<BrandDeal>(`/deals/agency/deals/${dealId}`),

  updateDeal: (dealId: string, data: BrandDealUpdate) =>
    request<BrandDeal>(`/deals/agency/deals/${dealId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteDeal: (dealId: string) =>
    request<{ status: string }>(`/deals/agency/deals/${dealId}`, {
      method: 'DELETE',
    }),

  // Creator applications
  applyToDeal: (dealId: string, data: DealApplicationCreate) =>
    request<DealApplication>(`/deals/apply/${dealId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listMyApplications: (status?: string) => {
    const query = status ? `?status=${status}` : '';
    return request<DealApplication[]>(`/deals/my-applications${query}`);
  },

  updateMyApplication: (applicationId: string, data: DealApplicationUpdate) =>
    request<DealApplication>(`/deals/my-applications/${applicationId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  withdrawApplication: (applicationId: string) =>
    request<{ status: string }>(`/deals/my-applications/${applicationId}/withdraw`, {
      method: 'POST',
    }),

  // Agency application review
  listDealApplications: (dealId: string, status?: string) => {
    const query = status ? `?status=${status}` : '';
    return request<DealApplication[]>(`/deals/agency/deals/${dealId}/applications${query}`);
  },

  updateApplicationStatus: (applicationId: string, data: ApplicationStatusUpdate) =>
    request<DealApplication>(`/deals/agency/applications/${applicationId}/status`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // Contracts
  createContract: (applicationId: string, data: ContractCreate) =>
    request<DealContract>(`/deals/agency/applications/${applicationId}/contract`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listMyContracts: (status?: string) => {
    const query = status ? `?status=${status}` : '';
    return request<DealContract[]>(`/deals/my-contracts${query}`);
  },

  listAgencyContracts: (status?: string) => {
    const query = status ? `?status=${status}` : '';
    return request<DealContract[]>(`/deals/agency/contracts${query}`);
  },

  updateContractStatus: (contractId: string, data: ContractStatusUpdate) =>
    request<{ status: string; new_status: string }>(`/deals/agency/contracts/${contractId}/status`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // Payments
  addPayment: (contractId: string, data: PaymentCreate) =>
    request<ContractPayment>(`/deals/agency/contracts/${contractId}/payments`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listPayments: (contractId: string) =>
    request<ContractPayment[]>(`/deals/contracts/${contractId}/payments`),

  updatePayment: (paymentId: string, data: PaymentUpdate) =>
    request<ContractPayment>(`/deals/agency/payments/${paymentId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
};

// Auth extensions for creator/agency registration
export const authExtended = {
  registerCreator: async (data: CreatorRegister): Promise<TokenResponse> => {
    const response = await fetch(`${API_BASE}/auth/register/creator`, {
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

  registerAgency: async (data: AgencyRegister): Promise<TokenResponse> => {
    const response = await fetch(`${API_BASE}/auth/register/agency`, {
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
};

// Campaigns API (Limit Order Deal System)
export const campaigns = {
  // Agency Campaign Management
  create: (data: CampaignCreate) =>
    request<Campaign>('/campaigns/agency/campaigns', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  list: (status?: string) => {
    const query = status ? `?status=${status}` : '';
    return request<Campaign[]>(`/campaigns/agency/campaigns${query}`);
  },

  get: (campaignId: string) =>
    request<CampaignWithOffers>(`/campaigns/agency/campaigns/${campaignId}`),

  update: (campaignId: string, data: CampaignUpdate) =>
    request<Campaign>(`/campaigns/agency/campaigns/${campaignId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  publish: (campaignId: string) =>
    request<{ status: string; offers_sent: number }>(`/campaigns/agency/campaigns/${campaignId}/publish`, {
      method: 'POST',
    }),

  cancel: (campaignId: string) =>
    request<{ status: string }>(`/campaigns/agency/campaigns/${campaignId}/cancel`, {
      method: 'POST',
    }),

  delete: (campaignId: string) =>
    request<{ status: string }>(`/campaigns/agency/campaigns/${campaignId}`, {
      method: 'DELETE',
    }),

  // Campaign Offers (Agency side)
  addOffer: (campaignId: string, data: CampaignOfferCreate) =>
    request<CampaignOffer>(`/campaigns/agency/campaigns/${campaignId}/offers`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  addBulkOffers: (campaignId: string, offers: CampaignOfferCreate[]) =>
    request<CampaignOffer[]>(`/campaigns/agency/campaigns/${campaignId}/offers/bulk`, {
      method: 'POST',
      body: JSON.stringify({ offers }),
    }),

  removeOffer: (campaignId: string, creatorId: string) =>
    request<{ status: string }>(`/campaigns/agency/campaigns/${campaignId}/offers/${creatorId}`, {
      method: 'DELETE',
    }),

  // Campaign Payments (Agency side)
  listPayments: (campaignId: string) =>
    request<CampaignPayment[]>(`/campaigns/agency/campaigns/${campaignId}/payments`),

  releasePayment: (paymentId: string, notes?: string) =>
    request<{ status: string }>(`/campaigns/agency/payments/${paymentId}/release`, {
      method: 'POST',
      body: JSON.stringify({ notes }),
    }),

  // Agency Stats
  getStats: () =>
    request<CampaignDashboardStats>('/campaigns/agency/campaigns/stats'),

  // Creator Offer Management
  listMyOffers: (status?: string) => {
    const query = status ? `?status=${status}` : '';
    return request<CreatorOffer[]>(`/campaigns/creators/me/offers${query}`);
  },

  getMyOffer: (offerId: string) =>
    request<CreatorOffer>(`/campaigns/creators/me/offers/${offerId}`),

  acceptOffer: (offerId: string, notes?: string) =>
    request<{ status: string; upfront_amount: number; message: string }>(`/campaigns/creators/me/offers/${offerId}/accept`, {
      method: 'POST',
      body: JSON.stringify({ notes }),
    }),

  declineOffer: (offerId: string, reason?: string) =>
    request<{ status: string }>(`/campaigns/creators/me/offers/${offerId}/decline`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  counterOffer: (offerId: string, counterAmount: number, notes?: string) =>
    request<{ status: string; counter_amount: number }>(`/campaigns/creators/me/offers/${offerId}/counter`, {
      method: 'POST',
      body: JSON.stringify({ counter_amount: counterAmount, notes }),
    }),

  // Creator Payments
  listMyPayments: (status?: string) => {
    const query = status ? `?status=${status}` : '';
    return request<CampaignPayment[]>(`/campaigns/creators/me/payments${query}`);
  },

  // Creator Stats
  getMyStats: () =>
    request<CreatorCampaignStats>('/campaigns/creators/me/campaigns/stats'),

  // Affiliate Links
  createAffiliateLink: (data: AffiliateLinkCreate) =>
    request<AffiliateLink>('/campaigns/affiliate/links', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listAffiliateLinks: () =>
    request<AffiliateLink[]>('/campaigns/affiliate/links'),

  getAffiliateLinkStats: (linkId: string) =>
    request<AffiliateStats>(`/campaigns/affiliate/links/${linkId}/stats`),

  // Creator Valuation
  getValuation: (creatorId: string) =>
    request<CreatorValuation>(`/campaigns/creators/${creatorId}/valuation`),

  refreshMyValuation: (includePlatformData?: boolean) =>
    request<CreatorValuation>('/campaigns/creators/me/valuation/refresh', {
      method: 'POST',
      body: JSON.stringify({ include_platform_data: includePlatformData ?? true }),
    }),

  // Contract Templates
  listTemplates: () =>
    request<ContractTemplate[]>('/campaigns/contracts/templates'),

  createTemplate: (data: ContractTemplateCreate) =>
    request<ContractTemplate>('/campaigns/contracts/templates', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateTemplate: (templateId: string, data: ContractTemplateUpdate) =>
    request<ContractTemplate>(`/campaigns/contracts/templates/${templateId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  generateContract: (campaignId: string, creatorId: string) =>
    request<GeneratedContract>(`/campaigns/agency/campaigns/${campaignId}/contract/generate?creator_id=${creatorId}`, {
      method: 'POST',
    }),
};

// GumFit Admin API
export interface GumFitStats {
  total_creators: number;
  total_agencies: number;
  total_users: number;
  pending_invites: number;
  active_campaigns: number;
  recent_signups: number;
}

export interface GumFitCreator {
  id: string;
  display_name: string;
  email: string;
  profile_image_url: string | null;
  is_verified: boolean;
  is_public: boolean;
  niches: string[];
  total_followers: number;
  created_at: string;
}

export interface GumFitAgency {
  id: string;
  agency_name: string;
  slug: string;
  email: string;
  logo_url: string | null;
  agency_type: string;
  is_verified: boolean;
  industries: string[];
  member_count: number;
  created_at: string;
}

export interface GumFitUser {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
  profile_name: string | null;
}

export interface GumFitInvite {
  id: string;
  email: string;
  invite_type: 'creator' | 'agency';
  status: 'pending' | 'accepted' | 'expired';
  message: string | null;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
}

export interface GumFitInviteCreate {
  email: string;
  invite_type: 'creator' | 'agency';
  message?: string;
}

export interface GumFitAsset {
  id: string;
  name: string;
  url: string;
  category: string;
  file_type: string | null;
  file_size: number | null;
  width: number | null;
  height: number | null;
  alt_text: string | null;
  uploaded_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface GumFitAssetUpdate {
  name?: string;
  category?: string;
  alt_text?: string;
}

export interface GumFitAssetCategory {
  value: string;
  label: string;
}

export const gumfit = {
  // Stats
  getStats: () =>
    request<GumFitStats>('/gumfit/stats'),

  // Creators
  listCreators: (params?: { search?: string; verified?: boolean; skip?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.search) query.set('search', params.search);
    if (params?.verified !== undefined) query.set('verified', String(params.verified));
    if (params?.skip !== undefined) query.set('skip', String(params.skip));
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const queryStr = query.toString();
    return request<{ creators: GumFitCreator[]; total: number }>(`/gumfit/creators${queryStr ? `?${queryStr}` : ''}`);
  },

  toggleCreatorVerification: (creatorId: string, verified: boolean) =>
    request<{ success: boolean; is_verified: boolean }>(`/gumfit/creators/${creatorId}/verify?verified=${verified}`, {
      method: 'PATCH',
    }),

  // Agencies
  listAgencies: (params?: { search?: string; verified?: boolean; skip?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.search) query.set('search', params.search);
    if (params?.verified !== undefined) query.set('verified', String(params.verified));
    if (params?.skip !== undefined) query.set('skip', String(params.skip));
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const queryStr = query.toString();
    return request<{ agencies: GumFitAgency[]; total: number }>(`/gumfit/agencies${queryStr ? `?${queryStr}` : ''}`);
  },

  toggleAgencyVerification: (agencyId: string, verified: boolean) =>
    request<{ success: boolean; is_verified: boolean }>(`/gumfit/agencies/${agencyId}/verify?verified=${verified}`, {
      method: 'PATCH',
    }),

  // Users
  listUsers: (params?: { search?: string; role?: 'creator' | 'agency'; skip?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.search) query.set('search', params.search);
    if (params?.role) query.set('role', params.role);
    if (params?.skip !== undefined) query.set('skip', String(params.skip));
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const queryStr = query.toString();
    return request<{ users: GumFitUser[]; total: number }>(`/gumfit/users${queryStr ? `?${queryStr}` : ''}`);
  },

  toggleUserActive: (userId: string, isActive: boolean) =>
    request<{ success: boolean; is_active: boolean }>(`/gumfit/users/${userId}/active?is_active=${isActive}`, {
      method: 'PATCH',
    }),

  // Invites
  listInvites: (params?: { search?: string; invite_status?: 'pending' | 'accepted' | 'expired'; skip?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.search) query.set('search', params.search);
    if (params?.invite_status) query.set('invite_status', params.invite_status);
    if (params?.skip !== undefined) query.set('skip', String(params.skip));
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const queryStr = query.toString();
    return request<{ invites: GumFitInvite[]; total: number }>(`/gumfit/invites${queryStr ? `?${queryStr}` : ''}`);
  },

  sendInvite: (data: GumFitInviteCreate) =>
    request<GumFitInvite>('/gumfit/invites', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  resendInvite: (inviteId: string) =>
    request<{ success: boolean; expires_at: string }>(`/gumfit/invites/${inviteId}/resend`, {
      method: 'POST',
    }),

  // Assets
  listAssets: (params?: { category?: string; search?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.category) query.set('category', params.category);
    if (params?.search) query.set('search', params.search);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.offset !== undefined) query.set('offset', String(params.offset));
    const queryStr = query.toString();
    return request<{ assets: GumFitAsset[]; total: number }>(`/gumfit/assets${queryStr ? `?${queryStr}` : ''}`);
  },

  getAsset: (assetId: string) =>
    request<GumFitAsset>(`/gumfit/assets/${assetId}`),

  uploadAsset: async (file: File, name: string, category: string = 'general', altText?: string): Promise<GumFitAsset> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    formData.append('category', category);
    if (altText) formData.append('alt_text', altText);

    const token = getAccessToken();
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/gumfit/assets/upload`, {
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

  updateAsset: (assetId: string, update: GumFitAssetUpdate) =>
    request<GumFitAsset>(`/gumfit/assets/${assetId}`, {
      method: 'PATCH',
      body: JSON.stringify(update),
    }),

  deleteAsset: (assetId: string) =>
    request<{ status: string; id: string }>(`/gumfit/assets/${assetId}`, {
      method: 'DELETE',
    }),

  listAssetCategories: () =>
    request<{ categories: GumFitAssetCategory[] }>('/gumfit/assets/categories/list'),
};

// AI Chat API
export const aiChat = {
  createConversation: (title?: string) =>
    request<{ id: string; title: string | null; created_at: string; updated_at: string }>(
      '/chat/ai/conversations',
      { method: 'POST', body: JSON.stringify({ title }) }
    ),

  listConversations: () =>
    request<{ id: string; title: string | null; created_at: string; updated_at: string }[]>(
      '/chat/ai/conversations'
    ),

  getConversation: (id: string) =>
    request<{
      id: string;
      title: string | null;
      created_at: string;
      updated_at: string;
      messages: { id: string; role: string; content: string; created_at: string }[];
    }>(`/chat/ai/conversations/${id}`),

  deleteConversation: (id: string) =>
    request<void>(`/chat/ai/conversations/${id}`, { method: 'DELETE' }),
};

// Combined API object for convenient imports
export const api = {
  auth,
  authExtended,
  companies,
  interviews,
  candidates,
  matching,
  positions,
  bulkImport,
  jobSearch,
  openings,
  settings,
  projects,
  outreach,
  screening,
  tutor,
  tutorMetrics,
  publicJobs,
  erCopilot,
  irIncidents,
  adminBeta,
  adminJurisdictions,
  adminSchedulers,
  blogs,
  policies,
  offerLetters,
  leadsAgent,
  creators,
  agencies,
  deals,
  campaigns,
  gumfit,
  aiChat,
};
