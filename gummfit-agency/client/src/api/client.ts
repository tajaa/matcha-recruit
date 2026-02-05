import type {
  Creator,
  CreatorUpdate,
  CreatorPublic,
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

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8003/api';

// Token storage helpers
const TOKEN_KEY = 'gummfit_access_token';
const REFRESH_KEY = 'gummfit_refresh_token';

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

// Types
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: {
    id: string;
    email: string;
    role: string;
    is_active: boolean;
    created_at: string;
    last_login: string | null;
  };
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface CreatorRegister {
  email: string;
  password: string;
  display_name: string;
  bio?: string;
  niches?: string[];
  social_handles?: Record<string, string>;
}

export interface AgencyRegister {
  email: string;
  password: string;
  agency_name: string;
  agency_type: string;
  description?: string;
  website_url?: string;
  industries?: string[];
}

export interface CurrentUserResponse {
  user: {
    id: string;
    email: string;
    role: string;
  };
  profile: {
    display_name?: string;
    agency_name?: string;
    [key: string]: unknown;
  } | null;
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
    const refreshed = await tryRefreshToken();
    if (refreshed) {
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

// =============================================================================
// AUTH API
// =============================================================================

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

  me: async () => {
    const data = await request<CurrentUserResponse>('/auth/me');
    // Flatten into a shape consumers expect
    const displayName = data.profile?.display_name || data.profile?.agency_name || data.user.email;
    return {
      id: data.user.id,
      email: data.user.email,
      role: data.user.role,
      full_name: displayName,
      profile: data.profile,
    };
  },

  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ status: string }>('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),

  changeEmail: (password: string, newEmail: string) =>
    request<{ status: string; access_token: string; refresh_token: string }>('/auth/change-email', {
      method: 'POST',
      body: JSON.stringify({ password, new_email: newEmail }),
    }),
};

// =============================================================================
// CREATOR API
// =============================================================================

export const creators = {
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
      headers: { Authorization: `Bearer ${getAccessToken()}` },
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

  listPlatformConnections: () =>
    request<PlatformConnection[]>('/creators/me/platforms'),

  disconnectPlatform: (platform: string) =>
    request<{ status: string }>(`/creators/me/platforms/${platform}`, { method: 'DELETE' }),

  createRevenueStream: (data: RevenueStreamCreate) =>
    request<RevenueStream>('/creators/me/revenue-streams', { method: 'POST', body: JSON.stringify(data) }),

  listRevenueStreams: (activeOnly = true) =>
    request<RevenueStream[]>(`/creators/me/revenue-streams?active_only=${activeOnly}`),

  updateRevenueStream: (streamId: string, data: RevenueStreamUpdate) =>
    request<RevenueStream>(`/creators/me/revenue-streams/${streamId}`, { method: 'PUT', body: JSON.stringify(data) }),

  deleteRevenueStream: (streamId: string) =>
    request<{ status: string }>(`/creators/me/revenue-streams/${streamId}`, { method: 'DELETE' }),

  createRevenueEntry: (data: RevenueEntryCreate) =>
    request<RevenueEntry>('/creators/me/revenue', { method: 'POST', body: JSON.stringify(data) }),

  listRevenueEntries: (params?: { start_date?: string; end_date?: string; stream_id?: string; limit?: number; offset?: number }) => {
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
    request<RevenueEntry>(`/creators/me/revenue/${entryId}`, { method: 'PUT', body: JSON.stringify(data) }),

  deleteRevenueEntry: (entryId: string) =>
    request<{ status: string }>(`/creators/me/revenue/${entryId}`, { method: 'DELETE' }),

  createExpense: (data: ExpenseCreate) =>
    request<Expense>('/creators/me/expenses', { method: 'POST', body: JSON.stringify(data) }),

  listExpenses: (params?: { start_date?: string; end_date?: string; category?: string; limit?: number; offset?: number }) => {
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
    request<Expense>(`/creators/me/expenses/${expenseId}`, { method: 'PUT', body: JSON.stringify(data) }),

  deleteExpense: (expenseId: string) =>
    request<{ status: string }>(`/creators/me/expenses/${expenseId}`, { method: 'DELETE' }),

  uploadReceipt: async (expenseId: string, file: File): Promise<{ status: string; receipt_url: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const token = getAccessToken();
    const headers: HeadersInit = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const response = await fetch(`${API_BASE}/creators/me/expenses/${expenseId}/receipt`, { method: 'POST', headers, body: formData });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail || 'Upload failed');
    }
    return response.json();
  },

  getDashboard: () => request<RevenueOverview>('/creators/me/dashboard'),
};

// =============================================================================
// AGENCY API
// =============================================================================

export const agencies = {
  getMyAgency: () => request<AgencyWithMembership>('/agencies/me'),

  updateMyAgency: (data: AgencyUpdate) =>
    request<Agency>('/agencies/me', { method: 'PUT', body: JSON.stringify(data) }),

  getPublicAgency: (slug: string) =>
    request<AgencyPublic>(`/agencies/public/${slug}`),

  listMembers: () => request<AgencyMember[]>('/agencies/me/members'),

  inviteMember: (data: AgencyMemberInvite) =>
    request<AgencyMember>('/agencies/me/members', { method: 'POST', body: JSON.stringify(data) }),

  updateMember: (memberId: string, data: AgencyMemberUpdate) =>
    request<AgencyMember>(`/agencies/me/members/${memberId}`, { method: 'PUT', body: JSON.stringify(data) }),

  removeMember: (memberId: string) =>
    request<{ status: string }>(`/agencies/me/members/${memberId}`, { method: 'DELETE' }),

  searchCreators: (params?: { query?: string; niches?: string; min_followers?: number; verified_only?: boolean; limit?: number; offset?: number }) => {
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

// =============================================================================
// DEALS API
// =============================================================================

export const deals = {
  browseMarketplace: (params?: { niches?: string; min_compensation?: number; max_compensation?: number; platforms?: string; limit?: number; offset?: number }) => {
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

  getMarketplaceDeal: (dealId: string) => request<BrandDealPublic>(`/deals/marketplace/${dealId}`),

  createDeal: (data: BrandDealCreate) => request<BrandDeal>('/deals/agency/deals', { method: 'POST', body: JSON.stringify(data) }),
  listAgencyDeals: (status?: string) => request<BrandDeal[]>(`/deals/agency/deals${status ? `?status=${status}` : ''}`),
  getAgencyDeal: (dealId: string) => request<BrandDeal>(`/deals/agency/deals/${dealId}`),
  updateDeal: (dealId: string, data: BrandDealUpdate) => request<BrandDeal>(`/deals/agency/deals/${dealId}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteDeal: (dealId: string) => request<{ status: string }>(`/deals/agency/deals/${dealId}`, { method: 'DELETE' }),

  applyToDeal: (dealId: string, data: DealApplicationCreate) => request<DealApplication>(`/deals/apply/${dealId}`, { method: 'POST', body: JSON.stringify(data) }),
  listMyApplications: (status?: string) => request<DealApplication[]>(`/deals/my-applications${status ? `?status=${status}` : ''}`),
  updateMyApplication: (applicationId: string, data: DealApplicationUpdate) => request<DealApplication>(`/deals/my-applications/${applicationId}`, { method: 'PUT', body: JSON.stringify(data) }),
  withdrawApplication: (applicationId: string) => request<{ status: string }>(`/deals/my-applications/${applicationId}/withdraw`, { method: 'POST' }),

  listDealApplications: (dealId: string, status?: string) => request<DealApplication[]>(`/deals/agency/deals/${dealId}/applications${status ? `?status=${status}` : ''}`),
  updateApplicationStatus: (applicationId: string, data: ApplicationStatusUpdate) => request<DealApplication>(`/deals/agency/applications/${applicationId}/status`, { method: 'PUT', body: JSON.stringify(data) }),

  createContract: (applicationId: string, data: ContractCreate) => request<DealContract>(`/deals/agency/applications/${applicationId}/contract`, { method: 'POST', body: JSON.stringify(data) }),
  listMyContracts: (status?: string) => request<DealContract[]>(`/deals/my-contracts${status ? `?status=${status}` : ''}`),
  listAgencyContracts: (status?: string) => request<DealContract[]>(`/deals/agency/contracts${status ? `?status=${status}` : ''}`),
  updateContractStatus: (contractId: string, data: ContractStatusUpdate) => request<{ status: string; new_status: string }>(`/deals/agency/contracts/${contractId}/status`, { method: 'PUT', body: JSON.stringify(data) }),

  addPayment: (contractId: string, data: PaymentCreate) => request<ContractPayment>(`/deals/agency/contracts/${contractId}/payments`, { method: 'POST', body: JSON.stringify(data) }),
  listPayments: (contractId: string) => request<ContractPayment[]>(`/deals/contracts/${contractId}/payments`),
  updatePayment: (paymentId: string, data: PaymentUpdate) => request<ContractPayment>(`/deals/agency/payments/${paymentId}`, { method: 'PUT', body: JSON.stringify(data) }),
};

// =============================================================================
// CAMPAIGNS API
// =============================================================================

export const campaigns = {
  create: (data: CampaignCreate) => request<Campaign>('/campaigns/agency/campaigns', { method: 'POST', body: JSON.stringify(data) }),
  list: (status?: string) => request<Campaign[]>(`/campaigns/agency/campaigns${status ? `?status=${status}` : ''}`),
  get: (campaignId: string) => request<CampaignWithOffers>(`/campaigns/agency/campaigns/${campaignId}`),
  update: (campaignId: string, data: CampaignUpdate) => request<Campaign>(`/campaigns/agency/campaigns/${campaignId}`, { method: 'PUT', body: JSON.stringify(data) }),
  publish: (campaignId: string) => request<{ status: string; offers_sent: number }>(`/campaigns/agency/campaigns/${campaignId}/publish`, { method: 'POST' }),
  cancel: (campaignId: string) => request<{ status: string }>(`/campaigns/agency/campaigns/${campaignId}/cancel`, { method: 'POST' }),
  delete: (campaignId: string) => request<{ status: string }>(`/campaigns/agency/campaigns/${campaignId}`, { method: 'DELETE' }),

  addOffer: (campaignId: string, data: CampaignOfferCreate) => request<CampaignOffer>(`/campaigns/agency/campaigns/${campaignId}/offers`, { method: 'POST', body: JSON.stringify(data) }),
  addBulkOffers: (campaignId: string, offers: CampaignOfferCreate[]) => request<CampaignOffer[]>(`/campaigns/agency/campaigns/${campaignId}/offers/bulk`, { method: 'POST', body: JSON.stringify({ offers }) }),
  removeOffer: (campaignId: string, creatorId: string) => request<{ status: string }>(`/campaigns/agency/campaigns/${campaignId}/offers/${creatorId}`, { method: 'DELETE' }),

  listPayments: (campaignId: string) => request<CampaignPayment[]>(`/campaigns/agency/campaigns/${campaignId}/payments`),
  releasePayment: (paymentId: string, notes?: string) => request<{ status: string }>(`/campaigns/agency/payments/${paymentId}/release`, { method: 'POST', body: JSON.stringify({ notes }) }),

  getStats: () => request<CampaignDashboardStats>('/campaigns/agency/campaigns/stats'),

  listMyOffers: (status?: string) => request<CreatorOffer[]>(`/campaigns/creators/me/offers${status ? `?status=${status}` : ''}`),
  getMyOffer: (offerId: string) => request<CreatorOffer>(`/campaigns/creators/me/offers/${offerId}`),
  acceptOffer: (offerId: string, notes?: string) => request<{ status: string; upfront_amount: number; message: string }>(`/campaigns/creators/me/offers/${offerId}/accept`, { method: 'POST', body: JSON.stringify({ notes }) }),
  declineOffer: (offerId: string, reason?: string) => request<{ status: string }>(`/campaigns/creators/me/offers/${offerId}/decline`, { method: 'POST', body: JSON.stringify({ reason }) }),
  counterOffer: (offerId: string, counterAmount: number, notes?: string) => request<{ status: string; counter_amount: number }>(`/campaigns/creators/me/offers/${offerId}/counter`, { method: 'POST', body: JSON.stringify({ counter_amount: counterAmount, notes }) }),

  listMyPayments: (status?: string) => request<CampaignPayment[]>(`/campaigns/creators/me/payments${status ? `?status=${status}` : ''}`),
  getMyStats: () => request<CreatorCampaignStats>('/campaigns/creators/me/campaigns/stats'),

  createAffiliateLink: (data: AffiliateLinkCreate) => request<AffiliateLink>('/campaigns/affiliate/links', { method: 'POST', body: JSON.stringify(data) }),
  listAffiliateLinks: () => request<AffiliateLink[]>('/campaigns/affiliate/links'),
  getAffiliateLinkStats: (linkId: string) => request<AffiliateStats>(`/campaigns/affiliate/links/${linkId}/stats`),

  getValuation: (creatorId: string) => request<CreatorValuation>(`/campaigns/creators/${creatorId}/valuation`),
  refreshMyValuation: (includePlatformData?: boolean) => request<CreatorValuation>('/campaigns/creators/me/valuation/refresh', { method: 'POST', body: JSON.stringify({ include_platform_data: includePlatformData ?? true }) }),

  listTemplates: () => request<ContractTemplate[]>('/campaigns/contracts/templates'),
  createTemplate: (data: ContractTemplateCreate) => request<ContractTemplate>('/campaigns/contracts/templates', { method: 'POST', body: JSON.stringify(data) }),
  updateTemplate: (templateId: string, data: ContractTemplateUpdate) => request<ContractTemplate>(`/campaigns/contracts/templates/${templateId}`, { method: 'PUT', body: JSON.stringify(data) }),
  generateContract: (campaignId: string, creatorId: string) => request<GeneratedContract>(`/campaigns/agency/campaigns/${campaignId}/contract/generate?creator_id=${creatorId}`, { method: 'POST' }),
};

// =============================================================================
// GUMFIT ADMIN API
// =============================================================================

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
  getStats: () => request<GumFitStats>('/gumfit/stats'),

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
    request<{ success: boolean; is_verified: boolean }>(`/gumfit/creators/${creatorId}/verify?verified=${verified}`, { method: 'PATCH' }),

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
    request<{ success: boolean; is_verified: boolean }>(`/gumfit/agencies/${agencyId}/verify?verified=${verified}`, { method: 'PATCH' }),

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
    request<{ success: boolean; is_active: boolean }>(`/gumfit/users/${userId}/active?is_active=${isActive}`, { method: 'PATCH' }),

  listInvites: (params?: { search?: string; invite_status?: 'pending' | 'accepted' | 'expired'; skip?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.search) query.set('search', params.search);
    if (params?.invite_status) query.set('invite_status', params.invite_status);
    if (params?.skip !== undefined) query.set('skip', String(params.skip));
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const queryStr = query.toString();
    return request<{ invites: GumFitInvite[]; total: number }>(`/gumfit/invites${queryStr ? `?${queryStr}` : ''}`);
  },

  sendInvite: (data: GumFitInviteCreate) => request<GumFitInvite>('/gumfit/invites', { method: 'POST', body: JSON.stringify(data) }),
  resendInvite: (inviteId: string) => request<{ success: boolean; expires_at: string }>(`/gumfit/invites/${inviteId}/resend`, { method: 'POST' }),

  listAssets: (params?: { category?: string; search?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.category) query.set('category', params.category);
    if (params?.search) query.set('search', params.search);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.offset !== undefined) query.set('offset', String(params.offset));
    const queryStr = query.toString();
    return request<{ assets: GumFitAsset[]; total: number }>(`/gumfit/assets${queryStr ? `?${queryStr}` : ''}`);
  },

  getAsset: (assetId: string) => request<GumFitAsset>(`/gumfit/assets/${assetId}`),

  uploadAsset: async (file: File, name: string, category: string = 'general', altText?: string): Promise<GumFitAsset> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    formData.append('category', category);
    if (altText) formData.append('alt_text', altText);
    const token = getAccessToken();
    const headers: HeadersInit = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const response = await fetch(`${API_BASE}/gumfit/assets/upload`, { method: 'POST', headers, body: formData });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail || 'Upload failed');
    }
    return response.json();
  },

  updateAsset: (assetId: string, update: GumFitAssetUpdate) =>
    request<GumFitAsset>(`/gumfit/assets/${assetId}`, { method: 'PATCH', body: JSON.stringify(update) }),

  deleteAsset: (assetId: string) =>
    request<{ status: string; id: string }>(`/gumfit/assets/${assetId}`, { method: 'DELETE' }),

  listAssetCategories: () =>
    request<{ categories: GumFitAssetCategory[] }>('/gumfit/assets/categories/list'),
};

// =============================================================================
// UNIFIED API EXPORT
// =============================================================================

export const api = {
  auth,
  creators,
  agencies,
  deals,
  campaigns,
  gumfit,
};
