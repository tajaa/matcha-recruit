import { reportApiError } from './errorReporter'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

let _refreshing: Promise<boolean> | null = null

async function _tryRefresh(): Promise<boolean> {
  const refreshToken = localStorage.getItem('matcha_refresh_token')
  if (!refreshToken) return false

  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })

    if (!res.ok) return false

    const data = await res.json()
    localStorage.setItem('matcha_access_token', data.access_token)
    localStorage.setItem('matcha_refresh_token', data.refresh_token)
    return true
  } catch {
    return false
  }
}

function _logout() {
  localStorage.removeItem('matcha_access_token')
  localStorage.removeItem('matcha_refresh_token')
  // Best-effort cleanup of the shared channel WS. Lazy-imported to avoid
  // a circular dependency between api/client.ts and api/channelSocket.ts.
  import('./channelSocket').then((m) => m.disconnectSharedChannelSocket()).catch(() => {})
  // Guard against a redirect loop: a failed refresh fired from the login page
  // itself would otherwise reassign location to /login repeatedly.
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

/** Proactively refresh token if it expires within 60s. Use before SSE/WebSocket where 401 retry isn't possible. */
export async function ensureFreshToken(): Promise<string | null> {
  const token = localStorage.getItem('matcha_access_token')
  if (!token) return null

  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    const expiresIn = payload.exp - Date.now() / 1000
    if (expiresIn < 60) {
      if (!_refreshing) {
        _refreshing = _tryRefresh().finally(() => { _refreshing = null })
      }
      const ok = await _refreshing
      if (!ok) { _logout(); return null }
      return localStorage.getItem('matcha_access_token')
    }
  } catch { /* malformed token, proceed */ }

  return token
}

function _buildHeaders(init?: RequestInit, token?: string | null): HeadersInit {
  const isFormData = init?.body instanceof FormData
  return {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...init?.headers,
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem('matcha_access_token')
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: _buildHeaders(init, token),
  })

  if (res.status === 401 && token) {
    // Deduplicate concurrent refresh attempts
    if (!_refreshing) {
      _refreshing = _tryRefresh().finally(() => { _refreshing = null })
    }

    const ok = await _refreshing
    if (ok) {
      // Retry with new token
      const newToken = localStorage.getItem('matcha_access_token')
      const retry = await fetch(`${BASE}${path}`, {
        ...init,
        headers: _buildHeaders(init, newToken),
      })
      if (!retry.ok) {
        // A 401 on the retry means the freshly-refreshed token is also
        // rejected — the session is truly dead. Clear it and bounce to login
        // rather than leaving the app in a half-authed state.
        if (retry.status === 401) {
          _logout()
          throw new Error('Session expired')
        }
        const retryBody = await retry.json().catch(() => null)
        const msg = retryBody?.detail || `${retry.status} ${retry.statusText}`
        // 401/403 are auth conditions (handled by refresh/logout), not bugs —
        // don't pollute the error reporter with them.
        if (path !== '/client-errors' && retry.status !== 401 && retry.status !== 403) {
          reportApiError({ endpoint: path, status: retry.status, message: msg, body: retryBody })
        }
        throw new Error(msg)
      }
      return retry.json()
    }

    _logout()
    throw new Error('Session expired')
  }

  if (!res.ok) {
    // Attempt JSON first (our APIs always return {detail: ...} on error).
    // Fall back to a short status string — never leak a full HTML error page
    // (e.g. nginx/Vite 502 during a backend restart) into the UI as a message.
    const errBody = await res.json().catch(() => null)
    let msg: string
    if (errBody?.detail) {
      msg = typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail)
    } else if (res.status >= 500) {
      msg = res.status === 502 || res.status === 503 || res.status === 504
        ? 'Server temporarily unavailable — retry in a moment.'
        : `Server error (${res.status})`
    } else {
      msg = `${res.status} ${res.statusText || 'Request failed'}`
    }
    // Skip 401/403 — auth conditions, not application errors (the no-token
    // case lands here since the refresh path above requires an existing token).
    if (path !== '/client-errors' && res.status !== 401 && res.status !== 403) {
      reportApiError({ endpoint: path, status: res.status, message: msg, body: errBody })
    }
    throw new Error(msg)
  }
  if (res.status === 204) return null as T
  return res.json()
}

import type {
  HandbookListItem,
  HandbookDetail,
  HandbookCreate,
  HandbookUpdate,
  HandbookChangeRequest,
  HandbookDistributionResult,
  HandbookDistributionRecipient,
  HandbookAcknowledgementSummary,
  HandbookFreshnessCheck,
  HandbookCoverage,
  CompanyHandbookProfile,
  CompanyHandbookProfileInput,
  HandbookGuidedDraftRequest,
  HandbookGuidedDraftResponse,
  HandbookWizardDraft,
  HandbookWizardDraftState,
  HandbookPublishResponse,
  HandbookSection,
} from '../types/handbook'

export const handbooks = {
  list: () => request<HandbookListItem[]>('/handbooks'),
  get: (id: string) => request<HandbookDetail>(`/handbooks/${id}`),
  create: (data: HandbookCreate) =>
    request<HandbookDetail>('/handbooks', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: HandbookUpdate) =>
    request<HandbookDetail>(`/handbooks/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  publish: (id: string) =>
    request<HandbookPublishResponse>(`/handbooks/${id}/publish`, { method: 'POST' }),
  archive: (id: string) =>
    request<{ message: string }>(`/handbooks/${id}/archive`, { method: 'POST' }),

  getProfile: () => request<CompanyHandbookProfile>('/handbooks/profile'),
  updateProfile: (data: CompanyHandbookProfileInput) =>
    request<CompanyHandbookProfile>('/handbooks/profile', { method: 'PUT', body: JSON.stringify(data) }),
  getAutoScopes: () => request<{ state: string; city: string | null }[]>('/handbooks/auto-scopes'),

  uploadFile: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<{ url: string; filename: string; company_id: string }>('/handbooks/upload', { method: 'POST', body: fd })
  },
  downloadPdf: (id: string, title: string) =>
    api.download(`/handbooks/${id}/pdf`, `${title}.pdf`),

  generateGuidedDraft: (data: HandbookGuidedDraftRequest) =>
    request<HandbookGuidedDraftResponse>('/handbooks/guided-draft', { method: 'POST', body: JSON.stringify(data) }),
  getWizardDraft: () => request<HandbookWizardDraft | null>('/handbooks/wizard-draft'),
  saveWizardDraft: (state: HandbookWizardDraftState) =>
    request<HandbookWizardDraft>('/handbooks/wizard-draft', { method: 'PUT', body: JSON.stringify({ state }) }),
  clearWizardDraft: () =>
    request<{ deleted: boolean }>('/handbooks/wizard-draft', { method: 'DELETE' }),

  listChanges: (id: string) =>
    request<HandbookChangeRequest[]>(`/handbooks/${id}/changes`),
  acceptChange: (handbookId: string, changeId: string) =>
    request<HandbookChangeRequest>(`/handbooks/${handbookId}/changes/${changeId}/accept`, { method: 'POST' }),
  rejectChange: (handbookId: string, changeId: string) =>
    request<HandbookChangeRequest>(`/handbooks/${handbookId}/changes/${changeId}/reject`, { method: 'POST' }),

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
    request<HandbookFreshnessCheck>(`/handbooks/${id}/freshness-check`, { method: 'POST' }),

  getCoverage: (id: string) =>
    request<HandbookCoverage>(`/handbooks/${id}/coverage`),
  markSectionReviewed: (handbookId: string, sectionId: string) =>
    request<HandbookSection>(`/handbooks/${handbookId}/sections/${sectionId}/mark-reviewed`, { method: 'POST' }),
}

import type { PolicyResponse } from '../types/policy'

export const policies = {
  list: (status?: string, category?: string) => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (category) params.set('category', category)
    const qs = params.toString()
    return request<PolicyResponse[]>(`/policies${qs ? `?${qs}` : ''}`)
  },
  get: (id: string) => request<PolicyResponse>(`/policies/${id}`),
  create: (data: FormData) =>
    request<PolicyResponse>('/policies', { method: 'POST', body: data }),
  update: (id: string, data: Record<string, unknown>) =>
    request<PolicyResponse>(`/policies/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (id: string) => request<void>(`/policies/${id}`, { method: 'DELETE' }),
}

/** Headers for SSE/streaming fetches that can't use request()'s 401 retry
 *  (a half-consumed stream can't be replayed): proactively refresh the token
 *  if it's near expiry, then attach it. ensureFreshToken logs out on failure. */
export async function authStreamHeaders(
  extra?: Record<string, string>,
): Promise<Record<string, string>> {
  const token = await ensureFreshToken()
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(extra ?? {}) }
}

/** Fetch returning the raw Response (for blobs/streams), with the same
 *  proactive-refresh + single 401 refresh-and-retry that request() applies. */
async function _fetchWithRefresh(url: string, init: RequestInit = {}): Promise<Response> {
  const token = await ensureFreshToken()
  const withAuth = (t: string | null): RequestInit => ({
    ...init,
    headers: { ...(t ? { Authorization: `Bearer ${t}` } : {}), ...init.headers },
  })
  const res = await fetch(url, withAuth(token))
  if (res.status !== 401 || !token) return res
  if (!_refreshing) {
    _refreshing = _tryRefresh().finally(() => { _refreshing = null })
  }
  const ok = await _refreshing
  if (!ok) { _logout(); return res }
  return fetch(url, withAuth(localStorage.getItem('matcha_access_token')))
}

/** Trigger a browser download from a binary Response. */
async function _saveBlobResponse(res: Response, path: string, filename?: string): Promise<void> {
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename ?? path.split('/').pop() ?? 'download'
  a.click()
  URL.revokeObjectURL(url)
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, formData: FormData) =>
    request<T>(path, { method: 'POST', body: formData }),
  download: async (path: string, filename?: string) => {
    const res = await _fetchWithRefresh(`${BASE}${path}`)
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    await _saveBlobResponse(res, path, filename)
  },
  // POST a JSON body and download the binary response as a file.
  downloadPost: async (path: string, body: unknown, filename?: string) => {
    const res = await _fetchWithRefresh(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    await _saveBlobResponse(res, path, filename)
  },
}

export function uploadAvatar(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<{ avatar_url: string }>('/auth/avatar', fd)
}

// ---------------------------------------------------------------------------
// Landing media
// ---------------------------------------------------------------------------

export type LandingSizzleVideo = { id: string; title: string; caption?: string; url: string | null }
export type LandingCustomerLogo = { name: string; url: string }
export type LandingTestimonial = { quote: string; author: string; title: string }

export type LandingMedia = {
  hero_video_url: string | null
  hero_poster_url: string | null
  sizzle_videos: LandingSizzleVideo[]
  customer_logos: LandingCustomerLogo[]
  testimonials: LandingTestimonial[]
}

export const landingMedia = {
  getPublic: async (): Promise<LandingMedia> => {
    const res = await fetch(`${BASE}/landing-media`)
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.json()
  },
  getAdmin: () => request<LandingMedia>('/admin/landing-media'),
  save: (data: LandingMedia) =>
    request<{ ok: boolean; value: LandingMedia }>('/admin/landing-media', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  upload: (file: File, kind: 'video' | 'image') => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('kind', kind)
    return api.upload<{ url: string; filename: string; content_type: string; size: number }>(
      '/admin/landing-media/upload',
      fd,
    )
  },
}
