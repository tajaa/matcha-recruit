import type {
  Company,
  CompanyCreate,
  RankedCandidate,
  ReachOutDraft,
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
  TestAccountRegister,
  TestAccountProvisionResponse,
  CurrentUserResponse,
  BrokerBrandingRuntime,
  BrokerClientSetup,
  BrokerClientSetupListResponse,
  BrokerClientSetupCreateRequest,
  BrokerClientSetupUpdateRequest,
  BrokerPortfolioReportResponse,
  GoogleWorkspaceConnectionRequest,
  GoogleWorkspaceConnectionStatus,
  SlackConnectionRequest,
  SlackConnectionStatus,
  SlackOAuthStartResponse,
  ProvisioningRunStatus,
  EmployeeGoogleWorkspaceProvisioningStatus,
  EmployeeSlackProvisioningStatus,
  ProvisioningRunListItem,
  OnboardingAnalytics,
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
  ProjectApplication,
  PublicProjectDetail,
  ApplicationStatus,
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
  ERCaseNote,
  ERCaseNoteCreate,
  ERDocument,
  ERDocumentType,
  ERDocumentUploadResponse,
  TimelineAnalysis,
  DiscrepancyAnalysis,
  PolicyCheckAnalysis,
  EvidenceSearchResponse,
  ERSuggestedGuidanceResponse,
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
  HandbookListItem,
  HandbookDetail,
  HandbookCreate,
  HandbookUpdate,
  CompanyHandbookProfile,
  HandbookChangeRequest,
  HandbookGuidedDraftRequest,
  HandbookGuidedDraftResponse,
  HandbookWizardDraft,
  HandbookWizardDraftState,
  HandbookDistributionResult,
  HandbookDistributionRecipient,
  HandbookAcknowledgementSummary,
  HandbookFreshnessCheck,
  HandbookReference,
  OfferLetter,
  OfferLetterCreate,
  OfferGuidanceRequest,
  OfferGuidanceResponse,
  OfferLetterUpdate,
    BlogPost,
    BlogPostCreate,
    BlogPostUpdate,
    BlogStatus,
    BlogListResponse,
    BlogComment,
    BlogCommentCreate,
    CommentStatus,
  // Poster types
  PosterTemplateListResponse,
  PosterOrder,
  PosterOrderListResponse,
  PosterOrderCreate,
  PosterOrderUpdate,
  AvailablePoster,
  RiskAssessmentResult,
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

const API_BASE = import.meta.env.VITE_API_URL || '/api';

// Token storage helpers
const TOKEN_KEY = 'matcha_access_token';
const REFRESH_KEY = 'matcha_refresh_token';

type ApiErrorPayload = {
  detail?: unknown;
  message?: unknown;
  error?: unknown;
};

export class ApiRequestError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.payload = payload;
  }
}

function detailToMessage(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (!item) return null;
        if (typeof item === 'string') return item;
        if (typeof item === 'object') {
          const msg = (item as { msg?: unknown }).msg;
          const loc = (item as { loc?: unknown }).loc;
          if (typeof msg === 'string' && Array.isArray(loc) && loc.length > 0) {
            return `${loc.join('.')}: ${msg}`;
          }
          if (typeof msg === 'string') return msg;
        }
        return null;
      })
      .filter((value): value is string => Boolean(value));
    if (parts.length > 0) return parts.join(' | ');
    return null;
  }
  if (typeof detail === 'object') {
    const msg = (detail as { msg?: unknown }).msg;
    if (typeof msg === 'string') return msg;
    const message = (detail as { message?: unknown }).message;
    if (typeof message === 'string') return message;
    try {
      return JSON.stringify(detail);
    } catch {
      return null;
    }
  }
  return null;
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback;
  const typed = payload as ApiErrorPayload;
  return (
    detailToMessage(typed.detail) ||
    detailToMessage(typed.message) ||
    detailToMessage(typed.error) ||
    fallback
  );
}

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
        throw new ApiRequestError(
          extractErrorMessage(error, 'Request failed'),
          retryResponse.status,
          error
        );
      }
      if (retryResponse.status === 204 || retryResponse.status === 205) {
        return undefined as T;
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
    throw new ApiRequestError(
      extractErrorMessage(error, 'Request failed'),
      response.status,
      error
    );
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
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
      throw new Error(extractErrorMessage(error, 'Login failed'));
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
      throw new Error(extractErrorMessage(error, 'Registration failed'));
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
      throw new Error(extractErrorMessage(error, 'Registration failed'));
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
      throw new Error(extractErrorMessage(error, 'Registration failed'));
    }

    const result: TokenResponse = await response.json();
    setTokens(result.access_token, result.refresh_token);
    return result;
  },

  me: () => request<CurrentUserResponse>('/auth/me'),

  acceptBrokerTerms: (terms_version?: string) =>
    request<{ status: string; broker_id: string; terms_version: string; accepted_at: string }>(
      '/auth/broker/accept-terms',
      {
        method: 'POST',
        body: JSON.stringify({ terms_version }),
      }
    ),

  getBrokerBranding: async (brokerKey: string): Promise<BrokerBrandingRuntime> => {
    const response = await fetch(`${API_BASE}/auth/broker-branding/${encodeURIComponent(brokerKey.trim().toLowerCase())}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Broker branding lookup failed' }));
      throw new Error(extractErrorMessage(error, 'Broker branding lookup failed'));
    }
    return response.json();
  },
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

export const brokerPortal = {
  listSetups: (statusFilter?: string) => {
    const query = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : '';
    return request<BrokerClientSetupListResponse>(`/brokers/client-setups${query}`);
  },

  createSetup: (data: BrokerClientSetupCreateRequest) =>
    request<{
      status: string;
      setup: BrokerClientSetup;
      invite_email_sent?: boolean;
      invite_email_error?: string;
    }>('/brokers/client-setups', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateSetup: (setupId: string, data: BrokerClientSetupUpdateRequest) =>
    request<{ status: string; setup: BrokerClientSetup }>(`/brokers/client-setups/${setupId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  sendInvite: (setupId: string, expiresDays = 14) =>
    request<{
      status: string;
      setup: BrokerClientSetup;
      invite_email_sent?: boolean;
      invite_email_error?: string;
    }>(`/brokers/client-setups/${setupId}/send-invite`, {
      method: 'POST',
      body: JSON.stringify({ expires_days: expiresDays }),
    }),

  cancelSetup: (setupId: string) =>
    request<{ status: string }>(`/brokers/client-setups/${setupId}/cancel`, {
      method: 'POST',
    }),

  expireStale: () =>
    request<{ status: string; expired_count: number }>('/brokers/client-setups/expire-stale', {
      method: 'POST',
    }),

  getPortfolioReport: () =>
    request<BrokerPortfolioReportResponse>('/brokers/reporting/portfolio'),

  getReferredClients: () =>
    request<{
      broker_slug: string;
      total: number;
      clients: {
        company_id: string;
        company_name: string;
        industry: string | null;
        company_size: string | null;
        company_status: string;
        link_status: string;
        linked_at: string | null;
        activated_at: string | null;
        active_employee_count: number;
        enabled_feature_count: number;
      }[];
    }>('/brokers/referred-clients'),
};

export const provisioning = {
  getGoogleWorkspaceStatus: () =>
    request<GoogleWorkspaceConnectionStatus>('/provisioning/google-workspace/status'),

  connectGoogleWorkspace: (data: GoogleWorkspaceConnectionRequest) =>
    request<GoogleWorkspaceConnectionStatus>('/provisioning/google-workspace/connect', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getSlackStatus: () =>
    request<SlackConnectionStatus>('/provisioning/slack/status'),

  connectSlack: (data: SlackConnectionRequest) =>
    request<SlackConnectionStatus>('/provisioning/slack/connect', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  startSlackOAuth: () =>
    request<SlackOAuthStartResponse>('/provisioning/slack/oauth/start', {
      method: 'POST',
    }),

  provisionEmployeeGoogleWorkspace: (employeeId: string) =>
    request<ProvisioningRunStatus>(`/provisioning/employees/${employeeId}/google-workspace`, {
      method: 'POST',
    }),

  getEmployeeGoogleWorkspaceStatus: (employeeId: string) =>
    request<EmployeeGoogleWorkspaceProvisioningStatus>(`/provisioning/employees/${employeeId}/google-workspace`),

  retryRun: (runId: string) =>
    request<ProvisioningRunStatus>(`/provisioning/runs/${runId}/retry`, {
      method: 'POST',
    }),

  provisionEmployeeSlack: (employeeId: string) =>
    request<ProvisioningRunStatus>(`/provisioning/employees/${employeeId}/slack`, {
      method: 'POST',
    }),

  getEmployeeSlackStatus: (employeeId: string) =>
    request<EmployeeSlackProvisioningStatus>(`/provisioning/employees/${employeeId}/slack`),

  listRuns: (params?: { provider?: string; status?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.provider) qs.set('provider', params.provider);
    if (params?.status) qs.set('status', params.status);
    if (params?.limit != null) qs.set('limit', String(params.limit));
    const query = qs.toString();
    return request<ProvisioningRunListItem[]>(`/provisioning/runs${query ? `?${query}` : ''}`);
  },
};

export interface OnboardingNotificationSettings {
  email_enabled: boolean;
  hr_escalation_emails: string[];
  reminder_days_before_due: number;
  escalate_to_manager_after_days: number;
  escalate_to_hr_after_days: number;
  timezone: string;
}

export interface OnboardingTemplate {
  id: string;
  org_id: string;
  title: string;
  description: string | null;
  category: string;
  is_employee_task: boolean;
  due_days: number;
  is_active: boolean;
  sort_order: number;
  link_type: string | null;
  link_id: string | null;
  link_label: string | null;
  link_url: string | null;
  created_at: string;
  updated_at: string;
}

export const onboarding = {
  getAnalytics: () => request<OnboardingAnalytics>('/onboarding/analytics'),
  getNotificationSettings: () =>
    request<OnboardingNotificationSettings>('/onboarding/notification-settings'),
  updateNotificationSettings: (data: Partial<OnboardingNotificationSettings>) =>
    request<OnboardingNotificationSettings>('/onboarding/notification-settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // All templates (for "add from template" picker)
  getTemplates: () =>
    request<OnboardingTemplate[]>('/onboarding/templates'),

  // Priority templates (category='priority')
  getPriorityTemplates: () =>
    request<OnboardingTemplate[]>('/onboarding/templates?category=priority'),
  createPriorityTemplate: (data: {
    title: string;
    description?: string;
    due_days?: number;
    link_type?: string | null;
    link_id?: string | null;
    link_label?: string | null;
    link_url?: string | null;
  }) =>
    request<OnboardingTemplate>('/onboarding/templates', {
      method: 'POST',
      body: JSON.stringify({ ...data, category: 'priority', is_employee_task: true, sort_order: 0 }),
    }),
  updatePriorityTemplate: (id: string, data: Partial<{
    title: string;
    description: string;
    due_days: number;
    is_active: boolean;
    link_type: string | null;
    link_id: string | null;
    link_label: string | null;
    link_url: string | null;
  }>) =>
    request<OnboardingTemplate>(`/onboarding/templates/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deletePriorityTemplate: (id: string) =>
    request<{ message: string }>(`/onboarding/templates/${id}`, { method: 'DELETE' }),
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

// Reach-out email (Candidate Rankings → agentic email draft + send)
export const reachOut = {
  draft: (companyId: string, candidateId: string) =>
    request<ReachOutDraft>(
      `/companies/${companyId}/candidates/${candidateId}/draft-reach-out`,
      { method: 'POST' }
    ),

  send: (
    companyId: string,
    candidateId: string,
    data: { to_email: string; subject: string; body: string }
  ) =>
    request<{ success: boolean; message: string }>(
      `/companies/${companyId}/candidates/${candidateId}/send-reach-out`,
      { method: 'POST', body: JSON.stringify(data) }
    ),
};

// Rankings
export const rankings = {
  run: (companyId: string, candidateIds?: string[]) =>
    request<{ status: string; count: number; rankings: RankedCandidate[] }>(
      `/companies/${companyId}/rankings/run`,
      {
        method: 'POST',
        body: JSON.stringify(candidateIds ? { candidate_ids: candidateIds } : {}),
      }
    ),

  list: (companyId: string) =>
    request<RankedCandidate[]>(`/companies/${companyId}/rankings`),
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

  // Public applications management
  listApplications: (projectId: string, status?: ApplicationStatus) => {
    const params = status ? `?status=${status}` : '';
    return request<ProjectApplication[]>(`/projects/${projectId}/applications${params}`);
  },

  acceptApplication: (projectId: string, applicationId: string) =>
    request<{ status: string; screening_invite_sent: boolean }>(
      `/projects/${projectId}/applications/${applicationId}/accept`,
      { method: 'POST' }
    ),

  rejectApplication: (projectId: string, applicationId: string) =>
    request<{ status: string }>(
      `/projects/${projectId}/applications/${applicationId}/reject`,
      { method: 'POST' }
    ),

  bulkAcceptRecommended: (projectId: string) =>
    request<{ accepted: number; skipped: number; errors: string[] }>(
      `/projects/${projectId}/applications/bulk-accept-recommended`,
      { method: 'POST' }
    ),

  closeProject: (projectId: string) =>
    request<{ status: string; message: string }>(
      `/projects/${projectId}/close`,
      { method: 'POST' }
    ),
};

// Public Projects API (no auth required — for public apply page)
export const publicProjects = {
  getDetail: async (projectId: string): Promise<PublicProjectDetail> => {
    const response = await fetch(`${API_BASE}/public/projects/${projectId}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Project not found' }));
      throw new Error(error.detail || 'Project not found');
    }
    return response.json();
  },

  apply: async (projectId: string, formData: FormData): Promise<{ success: boolean; message: string; application_id: string }> => {
    const response = await fetch(`${API_BASE}/public/projects/${projectId}/apply`, {
      method: 'POST',
      body: formData,
      // Do NOT set Content-Type — browser sets multipart boundary automatically
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Application failed' }));
      throw new Error(error.detail || 'Application failed');
    }
    return response.json();
  },
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

  start: async (token: string): Promise<OutreachInterviewStart> => {
    const response = await fetch(`${API_BASE}/screening/${token}/start`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getAccessToken()}`,
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
export type TutorSessionMode = 'interview_prep' | 'language_test' | 'culture' | 'screening' | 'candidate';

export interface TutorSessionCreate {
  mode: TutorSessionMode;
  company_id?: string; // Required for culture/screening/candidate
  language?: 'en' | 'es';
  duration_minutes?: 2 | 5 | 8;
  interview_role?: string;  // For interview_prep: role being practiced for (e.g., "CTO")
  is_practice?: boolean;
}

export interface TutorSessionStart {
  interview_id: string;
  websocket_url: string;
  ws_auth_token?: string | null;
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
  listSessions: (filters?: { mode?: 'interview_prep' | 'language_test' | 'company_tool' | 'culture' | 'screening' | 'candidate'; company_id?: string; limit?: number; offset?: number }) => {
    const params = new URLSearchParams();
    if (filters?.mode) params.append('mode', filters.mode);
    if (filters?.company_id) params.append('company_id', filters.company_id);
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

  getAggregateMetrics: (company_id?: string) => {
    const params = new URLSearchParams();
    if (company_id) params.append('company_id', company_id);
    const query = params.toString();
    return request<TutorMetricsAggregate>(`/tutor/metrics/aggregate${query ? `?${query}` : ''}`);
  },

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
  const apiBase = import.meta.env.VITE_API_URL || '/api';
  if (apiBase.startsWith('http://') || apiBase.startsWith('https://')) {
    const wsBase = apiBase.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
    return `${wsBase}/ws/interview/${interviewId}`;
  }

  const wsOrigin = window.location.origin.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
  return `${wsOrigin}/ws/interview/${interviewId}`;
}

// Public Jobs API (no auth required)
const JOBS_BASE = `${import.meta.env.VITE_API_URL || '/api'}/job-board`;

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

  // Notes
  listCaseNotes: (caseId: string): Promise<ERCaseNote[]> =>
    request<ERCaseNote[]>(`/er/cases/${caseId}/notes`),

  createCaseNote: (caseId: string, data: ERCaseNoteCreate): Promise<ERCaseNote> =>
    request<ERCaseNote>(`/er/cases/${caseId}/notes`, {
      method: 'POST',
      body: JSON.stringify(data),
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

  getTimeline: (caseId: string): Promise<{ analysis: TimelineAnalysis; source_documents: string[]; generated_at: string | null }> =>
    request<{ analysis: TimelineAnalysis; source_documents: string[]; generated_at: string | null }>(`/er/cases/${caseId}/analysis/timeline`),

  generateDiscrepancies: (caseId: string): Promise<ERTaskStatus> =>
    request<ERTaskStatus>(`/er/cases/${caseId}/analysis/discrepancies`, {
      method: 'POST',
    }),

  getDiscrepancies: (caseId: string): Promise<{ analysis: DiscrepancyAnalysis; source_documents: string[]; generated_at: string | null }> =>
    request<{ analysis: DiscrepancyAnalysis; source_documents: string[]; generated_at: string | null }>(`/er/cases/${caseId}/analysis/discrepancies`),

  runPolicyCheck: (caseId: string): Promise<ERTaskStatus> =>
    request<ERTaskStatus>(`/er/cases/${caseId}/analysis/policy-check`, {
      method: 'POST',
    }),

  getPolicyCheck: (caseId: string): Promise<{ analysis: PolicyCheckAnalysis; source_documents: string[]; generated_at: string | null }> =>
    request<{ analysis: PolicyCheckAnalysis; source_documents: string[]; generated_at: string | null }>(`/er/cases/${caseId}/analysis/policy-check`),

  generateSuggestedGuidance: (caseId: string): Promise<ERSuggestedGuidanceResponse> =>
    request<ERSuggestedGuidanceResponse>(`/er/cases/${caseId}/guidance/suggested`, {
      method: 'POST',
    }),

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

// Admin Handbook References API
export const adminHandbookReferences = {
  list: (path: string = '') =>
    request<HandbookReference[]>(`/admin/handbook-references?path=${encodeURIComponent(path)}`),

  getContent: (path: string) =>
    request<{ content: string; name: string }>(`/admin/handbook-references/content?path=${encodeURIComponent(path)}`),

  getFileUrl: (path: string) =>
    `${API_BASE}/admin/handbook-references/file?path=${encodeURIComponent(path)}&token=${getAccessToken()}`,
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
import type {
  BusinessRegistration,
  BusinessRegistrationListResponse,
  BusinessRegistrationStatus,
  BusinessRegistrationUpdateRequest,
  CompanyWithFeatures,
  EnabledFeatures,
} from '../types';

export const adminBusinessRegistrations = {
  list: (status?: BusinessRegistrationStatus): Promise<BusinessRegistrationListResponse> => {
    const params = status ? `?status=${status}` : '';
    return request<BusinessRegistrationListResponse>(`/admin/business-registrations${params}`);
  },

  get: (companyId: string): Promise<BusinessRegistration> =>
    request<BusinessRegistration>(`/admin/business-registrations/${companyId}`),

  update: (companyId: string, data: BusinessRegistrationUpdateRequest): Promise<BusinessRegistration> =>
    request<BusinessRegistration>(`/admin/business-registrations/${companyId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

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

export const adminTestAccounts = {
  create: (data: TestAccountRegister): Promise<TestAccountProvisionResponse> =>
    request<TestAccountProvisionResponse>('/auth/register/test-account', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// Admin Business Invites API
import type { BusinessInvite } from '../types';

export const adminBusinessInvites = {
  create: (note?: string, expiresDays?: number): Promise<BusinessInvite> =>
    request<BusinessInvite>('/admin/business-invites', {
      method: 'POST',
      body: JSON.stringify({ note, expires_days: expiresDays }),
    }),

  list: (): Promise<{ invites: BusinessInvite[]; total: number }> =>
    request<{ invites: BusinessInvite[]; total: number }>('/admin/business-invites'),

  cancel: (inviteId: string): Promise<{ status: string; message: string }> =>
    request<{ status: string; message: string }>(`/admin/business-invites/${inviteId}`, {
      method: 'DELETE',
    }),
};

export const businessInviteApi = {
  validate: (token: string): Promise<{ valid: boolean; expires_at: string; note: string | null }> =>
    request<{ valid: boolean; expires_at: string; note: string | null }>(`/auth/business-invite/${token}`),
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

// Admin Broker Management
export interface AdminBroker {
  id: string;
  name: string;
  slug: string;
  status: 'pending' | 'active' | 'suspended' | 'terminated';
  support_routing: 'broker_first' | 'matcha_first' | 'shared';
  billing_mode: 'direct' | 'reseller' | 'hybrid';
  invoice_owner: 'matcha' | 'broker';
  terms_required_version: string;
  branding_mode: 'direct' | 'co_branded' | 'white_label';
  active_member_count: number;
  active_company_count: number;
  active_contract: {
    id: string | null;
    currency: string | null;
    base_platform_fee: number | null;
    pepm_rate: number | null;
    minimum_monthly_commit: number | null;
  } | null;
  created_at: string | null;
}

export interface AdminBrokerCreateRequest {
  broker_name: string;
  owner_email: string;
  owner_name: string;
  owner_password?: string;
  slug?: string;
  support_routing?: string;
  billing_mode?: string;
  invoice_owner?: string;
  terms_required_version?: string;
}

export const adminBrokers = {
  list: (): Promise<{ brokers: AdminBroker[]; total: number }> =>
    request('/admin/brokers'),

  create: (data: AdminBrokerCreateRequest): Promise<{ broker_id: string; owner_id: string; contract_id: string }> =>
    request('/admin/brokers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (brokerId: string, data: {
    status?: string;
    support_routing?: string;
    terms_required_version?: string;
  }): Promise<{ id: string; name: string; status: string; support_routing: string }> =>
    request(`/admin/brokers/${brokerId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
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
  inherits_from_parent: boolean;
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

export interface JurisdictionDeleteResponse {
  status: string;
  id: string;
  city: string;
  state: string;
  detached_children: number;
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

  delete: (id: string): Promise<JurisdictionDeleteResponse> =>
    request<JurisdictionDeleteResponse>(`/admin/jurisdictions/${id}`, { method: 'DELETE' }),

  check: async (id: string): Promise<Response> => {
    const token = getAccessToken();
    const response = await fetch(`/api/admin/jurisdictions/${id}/check`, {
      method: 'POST',
      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    });
    if (!response.ok) throw new Error('Failed to start jurisdiction check');
    return response;
  },

  checkTopMetros: async (): Promise<Response> => {
    const token = getAccessToken();
    const response = await fetch('/api/admin/jurisdictions/top-metros/check', {
      method: 'POST',
      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    });
    if (!response.ok) throw new Error('Failed to start top-metro batch check');
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

export const handbooks = {
  list: () =>
    request<HandbookListItem[]>(`/handbooks`),

  getProfile: () =>
    request<CompanyHandbookProfile>(`/handbooks/profile`),

  updateProfile: (data: CompanyHandbookProfile) =>
    request<CompanyHandbookProfile>(`/handbooks/profile`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  generateGuidedDraft: (data: HandbookGuidedDraftRequest) =>
    request<HandbookGuidedDraftResponse>(`/handbooks/guided-draft`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getWizardDraft: () =>
    request<HandbookWizardDraft | null>(`/handbooks/wizard-draft`),

  saveWizardDraft: (state: HandbookWizardDraftState) =>
    request<HandbookWizardDraft>(`/handbooks/wizard-draft`, {
      method: 'PUT',
      body: JSON.stringify({ state }),
    }),

  clearWizardDraft: () =>
    request<{ deleted: boolean }>(`/handbooks/wizard-draft`, {
      method: 'DELETE',
    }),

  uploadFile: async (file: File): Promise<{ url: string; filename: string }> => {
    const formData = new FormData();
    formData.append('file', file);

    const token = getAccessToken();
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/handbooks/upload`, {
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

  create: (data: HandbookCreate) =>
    request<HandbookDetail>(`/handbooks`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  get: (id: string) =>
    request<HandbookDetail>(`/handbooks/${id}`),

  update: (id: string, data: HandbookUpdate) =>
    request<HandbookDetail>(`/handbooks/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  publish: (id: string) =>
    request<{ id: string; status: string; active_version: number; published_at: string | null }>(`/handbooks/${id}/publish`, {
      method: 'POST',
    }),

  archive: (id: string) =>
    request<{ message: string }>(`/handbooks/${id}/archive`, {
      method: 'POST',
    }),

  listChanges: (id: string) =>
    request<HandbookChangeRequest[]>(`/handbooks/${id}/changes`),

  acceptChange: (id: string, changeId: string) =>
    request<HandbookChangeRequest>(`/handbooks/${id}/changes/${changeId}/accept`, {
      method: 'POST',
    }),

  rejectChange: (id: string, changeId: string) =>
    request<HandbookChangeRequest>(`/handbooks/${id}/changes/${changeId}/reject`, {
      method: 'POST',
    }),

  distribute: (id: string, employeeIds?: string[]) =>
    request<HandbookDistributionResult>(`/handbooks/${id}/distribute`, {
      method: 'POST',
      body: employeeIds ? JSON.stringify({ employee_ids: employeeIds }) : undefined,
    }),

  listDistributionRecipients: (id: string) =>
    request<HandbookDistributionRecipient[]>(`/handbooks/${id}/distribution-recipients`),

  acknowledgements: (id: string) =>
    request<HandbookAcknowledgementSummary>(`/handbooks/${id}/acknowledgements`),

  getLatestFreshnessCheck: (id: string) =>
    request<HandbookFreshnessCheck | null>(`/handbooks/${id}/freshness-check/latest`),

  runFreshnessCheck: (id: string) =>
    request<HandbookFreshnessCheck>(`/handbooks/${id}/freshness-check`, {
      method: 'POST',
    }),

  downloadPdf: async (id: string, title: string): Promise<void> => {
    const token = getAccessToken();
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/handbooks/${id}/pdf`, {
      method: 'GET',
      headers,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Failed to download handbook' }));
      throw new Error(err.detail || 'Failed to download handbook');
    }

    const blob = await response.blob();
    const contentDisposition = response.headers.get('Content-Disposition') || '';
    const filenameMatch = contentDisposition.match(/filename\*?=(?:UTF-8''|")?([^\";]+)/i);
    const responseFilename = filenameMatch
      ? decodeURIComponent(filenameMatch[1].replace(/"/g, '').trim())
      : null;

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = responseFilename || `${title.replace(/\s+/g, '-').toLowerCase() || 'handbook'}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  },
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

  getPlusRecommendation: (data: OfferGuidanceRequest) =>
    request<OfferGuidanceResponse>('/offer-letters/plus/recommendation', {
      method: 'POST',
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

  sendRange: (id: string, data: { candidate_email: string; salary_range_min: number; salary_range_max: number }) =>
    request<OfferLetter>(`/offer-letters/${id}/send-range`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  reNegotiate: (id: string, data?: { salary_range_min?: number; salary_range_max?: number }) =>
    request<OfferLetter>(`/offer-letters/${id}/re-negotiate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data || {}),
    }),
};

// Public request helper (no auth header)
async function publicRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw { status: response.status, detail: error.detail || 'Request failed' };
  }
  return response.json();
}

export interface CandidateOfferView {
  id: string;
  position_title: string;
  company_name: string;
  company_logo_url?: string | null;
  employment_type?: string | null;
  location?: string | null;
  salary_range_min: number;
  salary_range_max: number;
  benefits_medical: boolean;
  benefits_dental: boolean;
  benefits_vision: boolean;
  benefits_401k: boolean;
  benefits_401k_match?: string | null;
  benefits_pto_vacation: boolean;
  benefits_pto_sick: boolean;
  benefits_holidays: boolean;
  benefits_other?: string | null;
  start_date?: string | null;
  expiration_date?: string | null;
  range_match_status: string;
  negotiation_round: number;
  max_negotiation_rounds: number;
  matched_salary?: number | null;
}

export interface RangeNegotiateResult {
  result: 'matched' | 'no_match_low' | 'no_match_high';
  matched_salary?: number | null;
}

export const getCandidateOffer = (token: string): Promise<CandidateOfferView> =>
  publicRequest<CandidateOfferView>(`/offer-letters/candidate/${token}`);

export const submitCandidateRange = (token: string, data: { range_min: number; range_max: number }): Promise<RangeNegotiateResult> =>
  publicRequest<RangeNegotiateResult>(`/offer-letters/candidate/${token}/submit-range`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

// =============================================================================
// LEADS AGENT API
// =============================================================================

export const leadsAgent = {
  search: (params: SearchRequest & { preview?: boolean }) => {
    const preview = params.preview ? '?preview=true' : '';
    const { preview: previewFlag, ...body } = params;
    void previewFlag;
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

// --- Poster Management ---

const adminPosters = {
  listTemplates: () =>
    request<PosterTemplateListResponse>('/admin/posters/templates'),

  generateTemplate: (jurisdictionId: string) =>
    request<{ status: string; template_id?: string; pdf_url?: string; version?: number }>(
      `/admin/posters/templates/${jurisdictionId}`,
      { method: 'POST' }
    ),

  listOrders: (status?: string) => {
    const params = status ? `?status=${status}` : '';
    return request<PosterOrderListResponse>(`/admin/posters/orders${params}`);
  },

  getOrder: (orderId: string) =>
    request<PosterOrder>(`/admin/posters/orders/${orderId}`),

  updateOrder: (orderId: string, data: PosterOrderUpdate) =>
    request<{ status: string; order_id: string }>(`/admin/posters/orders/${orderId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  generateAll: () =>
    request<{ generated: number; failed: number; total_missing: number }>(
      '/admin/posters/generate-all',
      { method: 'POST' }
    ),
};

const posters = {
  getAvailable: () =>
    request<AvailablePoster[]>('/compliance/posters/available'),

  createOrder: (data: PosterOrderCreate) =>
    request<{ id: string; status: string; created_at: string; message: string }>(
      '/compliance/posters/orders',
      { method: 'POST', body: JSON.stringify(data) }
    ),

  listOrders: () =>
    request<PosterOrderListResponse>('/compliance/posters/orders'),

  getOrder: (orderId: string) =>
    request<PosterOrder>(`/compliance/posters/orders/${orderId}`),

  getPreview: (templateId: string) =>
    request<{ pdf_url: string; title: string }>(`/compliance/posters/preview/${templateId}`),
};

export type InternalMobilityOpportunityType = 'role' | 'project';
export type InternalMobilityOpportunityStatus = 'draft' | 'active' | 'closed';
export type InternalMobilityApplicationStatus =
  'new' | 'in_review' | 'shortlisted' | 'aligned' | 'closed';

export interface InternalMobilityOpportunity {
  id: string;
  org_id: string;
  type: InternalMobilityOpportunityType;
  position_id: string | null;
  title: string;
  department: string | null;
  description: string | null;
  required_skills: string[];
  preferred_skills: string[];
  duration_weeks: number | null;
  status: InternalMobilityOpportunityStatus;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface InternalMobilityOpportunityCreate {
  type: InternalMobilityOpportunityType;
  position_id?: string | null;
  title: string;
  department?: string | null;
  description?: string | null;
  required_skills?: string[];
  preferred_skills?: string[];
  duration_weeks?: number | null;
  status?: InternalMobilityOpportunityStatus;
}

export interface InternalMobilityOpportunityUpdate {
  type?: InternalMobilityOpportunityType;
  position_id?: string | null;
  title?: string;
  department?: string | null;
  description?: string | null;
  required_skills?: string[];
  preferred_skills?: string[];
  duration_weeks?: number | null;
  status?: InternalMobilityOpportunityStatus;
}

export interface InternalMobilityApplicationAdmin {
  id: string;
  employee_id: string;
  employee_name: string;
  employee_email: string;
  opportunity_id: string;
  opportunity_title: string;
  opportunity_type: InternalMobilityOpportunityType;
  status: InternalMobilityApplicationStatus;
  employee_notes: string | null;
  submitted_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  manager_notified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InternalMobilityApplicationUpdate {
  status?: InternalMobilityApplicationStatus;
  manager_notified?: boolean;
}

function withCompanyScope(path: string, companyId?: string): string {
  if (!companyId) return path;
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}company_id=${encodeURIComponent(companyId)}`;
}

export const internalMobilityAdmin = {
  createOpportunity: (
    data: InternalMobilityOpportunityCreate,
    companyId?: string,
  ): Promise<InternalMobilityOpportunity> =>
    request<InternalMobilityOpportunity>(withCompanyScope('/internal-mobility/opportunities', companyId), {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listOpportunities: (params?: {
    status?: InternalMobilityOpportunityStatus;
    type?: InternalMobilityOpportunityType;
    limit?: number;
    offset?: number;
    company_id?: string;
  }): Promise<InternalMobilityOpportunity[]> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.append('status', params.status);
    if (params?.type) searchParams.append('type', params.type);
    if (typeof params?.limit === 'number') searchParams.append('limit', String(params.limit));
    if (typeof params?.offset === 'number') searchParams.append('offset', String(params.offset));
    if (params?.company_id) searchParams.append('company_id', params.company_id);
    const query = searchParams.toString();
    return request<InternalMobilityOpportunity[]>(
      `/internal-mobility/opportunities${query ? `?${query}` : ''}`
    );
  },

  updateOpportunity: (
    opportunityId: string,
    data: InternalMobilityOpportunityUpdate,
    companyId?: string,
  ): Promise<InternalMobilityOpportunity> =>
    request<InternalMobilityOpportunity>(withCompanyScope(`/internal-mobility/opportunities/${opportunityId}`, companyId), {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  listApplications: (params?: {
    status?: InternalMobilityApplicationStatus;
    limit?: number;
    offset?: number;
    company_id?: string;
  }): Promise<InternalMobilityApplicationAdmin[]> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.append('status', params.status);
    if (typeof params?.limit === 'number') searchParams.append('limit', String(params.limit));
    if (typeof params?.offset === 'number') searchParams.append('offset', String(params.offset));
    if (params?.company_id) searchParams.append('company_id', params.company_id);
    const query = searchParams.toString();
    return request<InternalMobilityApplicationAdmin[]>(
      `/internal-mobility/applications${query ? `?${query}` : ''}`
    );
  },

  updateApplication: (
    applicationId: string,
    data: InternalMobilityApplicationUpdate,
    companyId?: string,
  ): Promise<InternalMobilityApplicationAdmin> =>
    request<InternalMobilityApplicationAdmin>(withCompanyScope(`/internal-mobility/applications/${applicationId}`, companyId), {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};

// HR News types
export interface HRNewsArticle {
  id: string;
  title: string;
  description: string | null;
  link: string | null;
  author: string | null;
  pub_date: string | null;
  source_name: string | null;
  image_url: string | null;
  created_at: string | null;
}

export interface HRNewsListResponse {
  articles: HRNewsArticle[];
  total: number;
  sources: string[];
  limit: number;
  offset: number;
}

export interface HRNewsRefreshResponse {
  status: string;
  message?: string;
  new_articles: number;
  feeds?: { source: string; new: number; error?: string }[];
}

export const adminNews = {
  list: (params?: { source?: string; limit?: number; offset?: number }): Promise<HRNewsListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.source) searchParams.append('source', params.source);
    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.offset) searchParams.append('offset', params.offset.toString());
    const query = searchParams.toString();
    return request<HRNewsListResponse>(`/admin/news/articles${query ? `?${query}` : ''}`);
  },

  refresh: (): Promise<HRNewsRefreshResponse> =>
    request<HRNewsRefreshResponse>('/admin/news/refresh', { method: 'POST' }),
};

// Matcha Work API (chat-driven offer letter generation)
import type {
  MWElement,
  MWTaskType,
  MWThread,
  MWThreadDetail,
  MWBillingBalanceResponse,
  MWBillingTransactionsResponse,
  MWCheckoutResponse,
  MWCreditPack,
  MWSubscription,
  MWCreateThreadResponse,
  MWSendMessageResponse,
  MWDocumentVersion,
  MWFinalizeResponse,
  MWSaveDraftResponse,
  MWMessageStreamEvent,
  MWUsageSummaryResponse,
  MWReviewRequestStatus,
  MWSendReviewRequestsResponse,
  MWSendHandbookSignaturesResponse,
  MWGeneratePresentationResponse,
  MWPublicReviewRequest,
  MWPublicReviewSubmitResponse,
} from '../types/matcha-work';

export const matchaWork = {
  createThread: (
    data: { title?: string; initial_message?: string; task_type?: MWTaskType }
  ): Promise<MWCreateThreadResponse> =>
    request<MWCreateThreadResponse>('/matcha-work/threads', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listThreads: (params?: { status?: string; limit?: number; offset?: number }): Promise<MWThread[]> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.append('status', params.status);
    if (params?.limit) searchParams.append('limit', String(params.limit));
    if (params?.offset) searchParams.append('offset', String(params.offset));
    const query = searchParams.toString();
    return request<MWThread[]>(`/matcha-work/threads${query ? `?${query}` : ''}`);
  },

  listElements: (params?: { status?: string; limit?: number; offset?: number }): Promise<MWElement[]> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.append('status', params.status);
    if (params?.limit) searchParams.append('limit', String(params.limit));
    if (params?.offset) searchParams.append('offset', String(params.offset));
    const query = searchParams.toString();
    return request<MWElement[]>(`/matcha-work/elements${query ? `?${query}` : ''}`);
  },

  getThread: (threadId: string): Promise<MWThreadDetail> =>
    request<MWThreadDetail>(`/matcha-work/threads/${threadId}`),

  sendMessage: (threadId: string, content: string): Promise<MWSendMessageResponse> =>
    request<MWSendMessageResponse>(`/matcha-work/threads/${threadId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),

  sendMessageStream: async (
    threadId: string,
    content: string,
    onEvent: (event: MWMessageStreamEvent) => void,
    signal?: AbortSignal
  ): Promise<void> => {
    const runRequest = async (): Promise<Response> => {
      const token = getAccessToken();
      return fetch(`${API_BASE}/matcha-work/threads/${threadId}/messages/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ content }),
        signal,
      });
    };

    let response = await runRequest();
    if (response.status === 401) {
      const refreshed = await tryRefreshToken();
      if (refreshed) {
        response = await runRequest();
      } else {
        clearTokens();
        window.location.href = '/login';
        throw new Error('Session expired');
      }
    }

    if (!response.ok || !response.body) {
      const error = await response.json().catch(() => ({ detail: 'Failed to stream message' }));
      throw new ApiRequestError(
        extractErrorMessage(error, 'Failed to stream message'),
        response.status,
        error
      );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const processLine = (line: string) => {
      const trimmed = line.trim();
      if (!trimmed.startsWith('data: ')) return;
      const payload = trimmed.slice(6);
      if (payload === '[DONE]') return;
      try {
        const event = JSON.parse(payload) as MWMessageStreamEvent;
        onEvent(event);
      } catch {
        // Ignore malformed SSE payload chunks.
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        processLine(line);
      }
    }

    if (buffer.trim()) {
      processLine(buffer);
    }
  },

  getVersions: (threadId: string): Promise<MWDocumentVersion[]> =>
    request<MWDocumentVersion[]>(`/matcha-work/threads/${threadId}/versions`),

  revert: (threadId: string, version: number): Promise<MWSendMessageResponse> =>
    request<MWSendMessageResponse>(`/matcha-work/threads/${threadId}/revert`, {
      method: 'POST',
      body: JSON.stringify({ version }),
    }),

  finalize: (threadId: string): Promise<MWFinalizeResponse> =>
    request<MWFinalizeResponse>(`/matcha-work/threads/${threadId}/finalize`, {
      method: 'POST',
    }),

  saveDraft: (threadId: string): Promise<MWSaveDraftResponse> =>
    request<MWSaveDraftResponse>(`/matcha-work/threads/${threadId}/save-draft`, {
      method: 'POST',
    }),

  getPdf: (threadId: string, version?: number): Promise<{ pdf_url: string; version: number }> => {
    const query = version != null ? `?version=${version}` : '';
    return request<{ pdf_url: string; version: number }>(
      `/matcha-work/threads/${threadId}/pdf${query}`
    );
  },

  getUsageSummary: (periodDays = 30): Promise<MWUsageSummaryResponse> =>
    request<MWUsageSummaryResponse>(`/matcha-work/usage/summary?period_days=${periodDays}`),

  getBillingBalance: (): Promise<MWBillingBalanceResponse> =>
    request<MWBillingBalanceResponse>('/matcha-work/billing/balance'),

  getCreditPacks: (): Promise<MWCreditPack[]> =>
    request<MWCreditPack[]>('/matcha-work/billing/packs'),

  createCheckout: (
    packId: string,
    autoRenew = false,
    successUrl?: string,
    cancelUrl?: string
  ): Promise<MWCheckoutResponse> =>
    request<MWCheckoutResponse>('/matcha-work/billing/checkout', {
      method: 'POST',
      body: JSON.stringify({
        pack_id: packId,
        auto_renew: autoRenew,
        success_url: successUrl,
        cancel_url: cancelUrl,
      }),
    }),

  getSubscription: (): Promise<MWSubscription> =>
    request<MWSubscription>('/matcha-work/billing/subscription'),

  cancelSubscription: (): Promise<{ canceled: boolean; message: string }> =>
    request<{ canceled: boolean; message: string }>('/matcha-work/billing/subscription', {
      method: 'DELETE',
    }),

  getBillingTransactions: (params?: { limit?: number; offset?: number }): Promise<MWBillingTransactionsResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.append('limit', String(params.limit));
    if (params?.offset) searchParams.append('offset', String(params.offset));
    const query = searchParams.toString();
    return request<MWBillingTransactionsResponse>(`/matcha-work/billing/transactions${query ? `?${query}` : ''}`);
  },

  listReviewRequests: (threadId: string): Promise<MWReviewRequestStatus[]> =>
    request<MWReviewRequestStatus[]>(`/matcha-work/threads/${threadId}/review-requests`),

  sendReviewRequests: (
    threadId: string,
    data: { recipient_emails?: string[]; custom_message?: string }
  ): Promise<MWSendReviewRequestsResponse> =>
    request<MWSendReviewRequestsResponse>(`/matcha-work/threads/${threadId}/review-requests/send`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  sendHandbookSignatures: (
    threadId: string,
    data: { handbook_id: string; employee_ids?: string[] }
  ): Promise<MWSendHandbookSignaturesResponse> =>
    request<MWSendHandbookSignaturesResponse>(`/matcha-work/threads/${threadId}/handbook/send-signatures`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  generatePresentation: (threadId: string): Promise<MWGeneratePresentationResponse> =>
    request<MWGeneratePresentationResponse>(`/matcha-work/threads/${threadId}/presentation/generate`, {
      method: 'POST',
    }),

  downloadPresentationPdf: async (threadId: string, title: string): Promise<void> => {
    const token = getAccessToken();
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/matcha-work/threads/${threadId}/presentation/pdf`, {
      method: 'GET',
      headers,
    });

    if (!response.ok) {
      throw new Error('Failed to download presentation PDF');
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title.replace(/\s+/g, '-').toLowerCase() || 'presentation'}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  },

  archiveThread: (threadId: string): Promise<void> =>
    request<void>(`/matcha-work/threads/${threadId}`, { method: 'DELETE' }),

  pinThread: (threadId: string, isPinned: boolean): Promise<MWThread> =>
    request<MWThread>(`/matcha-work/threads/${threadId}/pin`, {
      method: 'POST',
      body: JSON.stringify({ is_pinned: isPinned }),
    }),

  updateTitle: (threadId: string, title: string): Promise<MWThread> =>
    request<MWThread>(`/matcha-work/threads/${threadId}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),

  uploadLogo: async (threadId: string, file: File): Promise<{ logo_url: string }> => {
    const formData = new FormData();
    formData.append('file', file);

    const token = getAccessToken();
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}/matcha-work/threads/${threadId}/logo`, {
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

export const matchaWorkPublic = {
  getReviewRequest: async (token: string): Promise<MWPublicReviewRequest> => {
    const response = await fetch(`${API_BASE}/matcha-work/public/review-requests/${encodeURIComponent(token)}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Review request not found' }));
      throw new Error(extractErrorMessage(error, 'Review request not found'));
    }
    return response.json();
  },

  submitReviewRequest: async (
    token: string,
    data: { feedback: string; rating?: number }
  ): Promise<MWPublicReviewSubmitResponse> => {
    const response = await fetch(
      `${API_BASE}/matcha-work/public/review-requests/${encodeURIComponent(token)}/submit`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }
    );
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to submit review response' }));
      throw new Error(extractErrorMessage(error, 'Failed to submit review response'));
    }
    return response.json();
  },
};

// Risk Assessment API
export const riskAssessment = {
  get: (): Promise<RiskAssessmentResult> =>
    request('/risk-assessment'),
  getRecommendations: (): Promise<RiskAssessmentResult> =>
    request('/risk-assessment?include_recommendations=true'),
};

// Combined API object for convenient imports
export const api = {
  auth,

  companies,
  provisioning,
  onboarding,
  interviews,
  candidates,
  reachOut,
  rankings,
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
  adminHandbookReferences,
  blogs,
  policies,
  handbooks,
  offerLetters,
  leadsAgent,
  aiChat,
  adminPosters,
  posters,
  internalMobilityAdmin,
  adminNews,
  riskAssessment,
};

export const onboardingDraft = {
  get: (): Promise<{ draft_state: Record<string, unknown> } | null> =>
    request('/employees/onboarding-draft'),
  save: (state: Record<string, unknown>): Promise<{ draft_state: Record<string, unknown>; updated_at: string }> =>
    request('/employees/onboarding-draft', {
      method: 'PUT',
      body: JSON.stringify({ state }),
    }),
  clear: (): Promise<{ deleted: boolean }> =>
    request('/employees/onboarding-draft', { method: 'DELETE' }),
};

export const adminPlatformSettings = {
  get: (): Promise<{ 
    visible_features: string[]; 
    matcha_work_model_mode: string;
    jurisdiction_research_model_mode: string;
  }> =>
    request('/admin/platform-settings'),
  update: (visible_features: string[]): Promise<{ visible_features: string[] }> =>
    request('/admin/platform-settings/features', {
      method: 'PUT',
      body: JSON.stringify({ visible_features }),
    }),
  updateMatchaWorkModelMode: (mode: 'light' | 'heavy'): Promise<{ matcha_work_model_mode: string }> =>
    request('/admin/platform-settings/matcha-work-model-mode', {
      method: 'PUT',
      body: JSON.stringify({ mode }),
    }),
  updateJurisdictionResearchModelMode: (mode: 'light' | 'heavy'): Promise<{ jurisdiction_research_model_mode: string }> =>
    request('/admin/platform-settings/jurisdiction-research-model-mode', {
      method: 'PUT',
      body: JSON.stringify({ mode }),
    }),
};
