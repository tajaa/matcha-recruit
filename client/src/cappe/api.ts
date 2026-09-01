// Cappe API client — a parallel, self-contained auth/fetch layer for the Cappe
// product. Keyed on its OWN localStorage tokens (cappe_*) and base path
// (/api/cappe), so a Cappe session and a matcha session coexist in one browser
// without colliding. Mirrors api/client.ts's 401 refresh-and-retry.

import type {
  CappeDirectoryCategories,
  CappeDirectoryPage,
  CappeDirectoryQuery,
  PublicCreatorPage,
  PublicCreatorProfile,
} from './types'

const BASE = `${import.meta.env.VITE_API_URL ?? '/api'}/cappe`

// Backend 409s carry a structured `{code, message}` detail for a few
// conditions callers need to branch on (e.g. payouts_not_ready) rather than
// just display — regexing .message is a copy-edit away from silently
// breaking that branch, so preserve `code` through the error.
export class CappeApiError extends Error {
  code?: string
  constructor(message: string, code?: string) {
    super(message)
    this.code = code
  }
}

function _errorDetailCode(detail: unknown): string | undefined {
  return detail && typeof detail === 'object' && 'code' in detail && typeof (detail as { code: unknown }).code === 'string'
    ? (detail as { code: string }).code
    : undefined
}

const ACCESS_KEY = 'cappe_access_token'
const REFRESH_KEY = 'cappe_refresh_token'

export function getCappeToken(): string | null {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  return sessionStorage.getItem(ACCESS_KEY)
}

export function setCappeTokens(access: string, refresh: string) {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  sessionStorage.setItem(ACCESS_KEY, access)
  sessionStorage.setItem(REFRESH_KEY, refresh)
}

export function clearCappeTokens() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  sessionStorage.removeItem(ACCESS_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
}

let _refreshing: Promise<boolean> | null = null

async function _tryRefresh(): Promise<boolean> {
  const refreshToken = sessionStorage.getItem(REFRESH_KEY)
  if (!refreshToken) return false
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) return false
    const data = await res.json()
    setCappeTokens(data.access_token, data.refresh_token)
    return true
  } catch {
    return false
  }
}

function _logout() {
  clearCappeTokens()
  if (window.location.pathname !== '/cappe/login') {
    window.location.href = '/cappe/login'
  }
}

/** Refresh proactively if the token expires within 60s.
 *
 *  Use before opening an SSE stream (Merlin's agent turn): a stream can't
 *  replay a mid-flight 401 the way `request()` does — the body is already
 *  half-consumed and gone — so the token has to be good before it opens.
 *  Mirrors `api/client.ts:ensureFreshToken` on the cappe token pair. */
export async function ensureFreshCappeToken(): Promise<string | null> {
  const token = getCappeToken()
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
      return getCappeToken()
    }
  } catch { /* malformed token — let the request fail normally */ }
  return token
}

/** Auth headers for a stream, with the token refreshed first. */
export async function cappeStreamHeaders(
  extra?: Record<string, string>,
): Promise<Record<string, string>> {
  const token = await ensureFreshCappeToken()
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(extra ?? {}) }
}

export const cappeApiBase = BASE

function _buildHeaders(init?: RequestInit, token?: string | null): HeadersInit {
  const isFormData = init?.body instanceof FormData
  return {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...init?.headers,
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem(ACCESS_KEY)
  const res = await fetch(`${BASE}${path}`, { ...init, headers: _buildHeaders(init, token) })

  if (res.status === 401 && token) {
    if (!_refreshing) {
      _refreshing = _tryRefresh().finally(() => { _refreshing = null })
    }
    const ok = await _refreshing
    if (ok) {
      const newToken = localStorage.getItem(ACCESS_KEY)
      const retry = await fetch(`${BASE}${path}`, { ...init, headers: _buildHeaders(init, newToken) })
      if (!retry.ok) {
        if (retry.status === 401) { _logout(); throw new Error('Session expired') }
        const body = await retry.json().catch(() => null)
        const d = body?.detail
        const msg = typeof d === 'string' ? d : (d?.message || JSON.stringify(d) || `${retry.status} ${retry.statusText}`)
        throw new CappeApiError(msg, _errorDetailCode(d))
      }
      if (retry.status === 204) return null as T
      return retry.json()
    }
    _logout()
    throw new Error('Session expired')
  }

  if (!res.ok) {
    const errBody = await res.json().catch(() => null)
    let msg: string
    let d: unknown
    if (errBody?.detail) {
      d = errBody.detail
      // detail may be a string, or an object like {message, missing} (publish gate)
      // or {code, message} (a condition callers branch on, e.g. payouts_not_ready).
      msg = typeof d === 'string' ? d : ((d as { message?: string })?.message || JSON.stringify(d))
    } else if (res.status >= 500) {
      msg = 'Server error — try again in a moment.'
    } else {
      msg = `${res.status} ${res.statusText || 'Request failed'}`
    }
    throw new CappeApiError(msg, _errorDetailCode(d))
  }
  if (res.status === 204) return null as T
  return res.json()
}

// Unauthenticated GET (token-resolved public resources, e.g. a client thread).
export async function cappePublicGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const errBody = await res.json().catch(() => null)
    throw new Error(errBody?.detail || `${res.status} ${res.statusText || 'Request failed'}`)
  }
  return res.json()
}

// Unauthenticated POST (signup/login) — never attaches/refreshes a token.
export async function cappePublicPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const errBody = await res.json().catch(() => null)
    throw new Error(
      errBody?.detail
        ? typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail)
        : `${res.status} ${res.statusText || 'Request failed'}`,
    )
  }
  return res.json()
}

export const cappeApi = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  // FormData body: _buildHeaders omits Content-Type so the browser sets the boundary.
  upload: <T>(path: string, formData: FormData) =>
    request<T>(path, { method: 'POST', body: formData }),
  // POST returning raw text (e.g. rendered HTML for the live preview iframe).
  postHtml: async (path: string, body?: unknown): Promise<string> => {
    const token = localStorage.getItem(ACCESS_KEY)
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: _buildHeaders({ body: body ? JSON.stringify(body) : undefined }, token),
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText || 'Preview failed'}`)
    return res.text()
  },
  // Authed GET of a binary (e.g. a receipt PDF) → opens it in a new tab.
  openBlob: async (path: string): Promise<void> => {
    const token = localStorage.getItem(ACCESS_KEY)
    const res = await fetch(`${BASE}${path}`, { headers: _buildHeaders(undefined, token) })
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      throw new Error(body?.detail || `${res.status} ${res.statusText || 'Download failed'}`)
    }
    const url = URL.createObjectURL(await res.blob())
    window.open(url, '_blank', 'noopener')
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  },
}

export { _logout as cappeLogout }

// --- Discover directory (public) ---------------------------------------------
// These go through cappePublicGet, NOT cappeApi.get: Discover is browsed by
// anonymous visitors, and the authed helper attaches a token and redirects to
// /cappe/login on a 401 — which would bounce a logged-out visitor out of the
// directory they were reading.

export function cappeDirectoryQueryString(query: CappeDirectoryQuery): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export function fetchCappeDirectory(query: CappeDirectoryQuery = {}) {
  return cappePublicGet<CappeDirectoryPage>(`/public/directory${cappeDirectoryQueryString(query)}`)
}

export function fetchCappeDirectoryCategories() {
  return cappePublicGet<CappeDirectoryCategories>('/public/directory/categories')
}

// --- Creator marketplace directory (public) -----------------------------------

export type PublicCreatorQuery = {
  niche?: string
  platform?: string
  min_followers?: number
  max_rate_cents?: number
  location?: string
  q?: string
  verified_only?: boolean
  limit?: number
  offset?: number
}

function _publicCreatorQueryString(query: PublicCreatorQuery): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '' || value === false) continue
    params.set(key, String(value))
  }
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export function fetchPublicCreators(query: PublicCreatorQuery = {}) {
  return cappePublicGet<PublicCreatorPage>(`/public/creators${_publicCreatorQueryString(query)}`)
}

export function fetchPublicCreator(handle: string) {
  return cappePublicGet<PublicCreatorProfile>(`/public/creators/${encodeURIComponent(handle)}`)
}
