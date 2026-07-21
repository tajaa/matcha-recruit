import { api } from '../client'

// pages/admin/Settings.tsx hand-rolled ten `fetch()` calls with its own
// `authHeaders()` reading matcha_access_token straight out of localStorage.
// That skipped api/client.ts's 401-refresh-and-retry, so once the admin's
// access token aged out every call on the page failed — and because the page
// swallows errors (`catch {}`, `if (res.ok)`), the failure rendered as an
// empty settings screen rather than anything diagnosable.

export type TokenQuota = {
  id: string
  user_id: string | null
  company_id: string | null
  user_email: string | null
  company_name: string | null
  token_limit: number
  window_hours: number
  is_active: boolean
}

export type TokenUsage = {
  user_id: string
  email: string
  company_name: string | null
  tokens_used: number
  call_count: number
  cost_dollars: number
  last_active: string
}

export type BetaInvitation = {
  id: string
  email: string
  status: string
  created_at: string | null
  registered_at: string | null
}

export type PlatformSettings = {
  jurisdiction_research_model_mode?: string | null
}

export type BetaInviteResult = {
  sent: number
  skipped?: string[]
}

export const adminSettingsApi = {
  getPlatformSettings: () => api.get<PlatformSettings>('/admin/platform-settings'),

  setResearchModelMode: (mode: string) =>
    api.put<void>('/admin/platform-settings/jurisdiction-research-model-mode', { mode }),

  listQuotas: () => api.get<TokenQuota[]>('/admin/token-quotas'),
  listUsage: () => api.get<TokenUsage[]>('/admin/token-usage'),
  createQuota: (body: Record<string, unknown>) => api.post<TokenQuota>('/admin/token-quotas', body),
  updateQuota: (id: string, updates: Record<string, unknown>) =>
    api.put<TokenQuota>(`/admin/token-quotas/${id}`, updates),
  deleteQuota: (id: string) => api.delete<void>(`/admin/token-quotas/${id}`),

  listBetaInvitations: () => api.get<BetaInvitation[]>('/admin/beta-invitations'),
  sendBetaInvitations: (emails: string[]) =>
    api.post<BetaInviteResult>('/admin/beta-invitations', { emails }),
  revokeBetaInvitation: (id: string) => api.delete<void>(`/admin/beta-invitations/${id}`),
}
