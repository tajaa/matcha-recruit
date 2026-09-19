// Cappe API client — a parallel, self-contained auth/fetch layer for the Cappe
// product. Keyed on its OWN tab-session tokens (cappe_*) and base path
// (/api/cappe), so a Cappe session and a matcha session coexist in one browser
// without colliding. Mirrors api/client.ts's 401 refresh-and-retry.

import type {
  CappeDirectoryCategories,
  CappeDirectoryPage,
  CappeDirectoryQuery,
  PublicCreatorPage,
  PublicCreatorProfile,
} from './types'
import { creatorPaths } from './creators/creatorPaths'

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

// One-shot migration off persistent origin storage, run at module load rather
// than inside the getter — a getter that mutates storage ran a removeItem pair
// on every single request.
try {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
} catch { /* storage may be blocked */ }

export function getCappeToken(): string | null {
  try { return sessionStorage.getItem(ACCESS_KEY) } catch { return null }
}

export function getCappeRefreshToken(): string | null {
  try { return sessionStorage.getItem(REFRESH_KEY) } catch { return null }
}

export function setCappeTokens(access: string, refresh: string) {
  try {
    sessionStorage.setItem(ACCESS_KEY, access)
    sessionStorage.setItem(REFRESH_KEY, refresh)
  } catch { /* storage may be blocked */ }
}

export function clearCappeTokens() {
  try {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
    sessionStorage.removeItem(ACCESS_KEY)
    sessionStorage.removeItem(REFRESH_KEY)
  } catch { /* storage may be blocked */ }
}

/** Why a refresh attempt ended.
 *
 *  The distinction is the whole point: `'dead'` means the server told us this
 *  session is over, and only that justifies throwing the user out. `'transport'`
 *  means we never got an answer — offline, a dropped connection, a 502 from the
 *  edge — and logging out there discards unsaved work (a half-written page in
 *  the editor) over a blip that would have healed on retry. */
export type CappeRefreshOutcome = 'ok' | 'dead' | 'transport'

let _refreshing: Promise<CappeRefreshOutcome> | null = null

async function _tryRefresh(): Promise<CappeRefreshOutcome> {
  const refreshToken = getCappeRefreshToken()
  if (!refreshToken) return 'dead'
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    // Only the server rejecting the refresh token itself ends the session.
    // A 429 (the endpoint is rate-limited 60/hr/IP) or a 5xx is transient.
    if (!res.ok) return res.status === 401 || res.status === 403 ? 'dead' : 'transport'
    const data = await res.json()
    if (!data?.access_token || !data?.refresh_token) return 'transport'
    setCappeTokens(data.access_token, data.refresh_token)
    return 'ok'
  } catch {
    return 'transport'
  }
}

/** Single-flight refresh. Concurrent callers (several requests 401ing at once,
 *  or a request and an SSE stream) share one in-flight attempt. */
export function refreshCappeSession(): Promise<CappeRefreshOutcome> {
  if (!_refreshing) {
    _refreshing = _tryRefresh().finally(() => { _refreshing = null })
  }
  return _refreshing
}

export const CAPPE_NETWORK_ERROR = 'Network error — your changes are still here. Check your connection and try again.'

/** Thrown instead of logging out when a refresh could not reach the server. */
function _networkError(): CappeApiError {
  return new CappeApiError(CAPPE_NETWORK_ERROR, 'network')
}

// Creator/brand sessions live under /gummfit/creators/* (and the legacy
// /cappe/creator/* aliases). Bouncing one of those to the business login is a
// dead end — that form does not accept a creator or brand account.
const CREATOR_AREA = /(^|\/)(gummfit\/)?creators?(\/|$)/
const BRAND_AREA = /\/creators\/brands(\/|$)/
const BUSINESS_LOGIN = '/cappe/login'

function _loginPathFor(pathname: string): string {
  if (BRAND_AREA.test(pathname)) return creatorPaths.brandLogin
  if (CREATOR_AREA.test(pathname)) return creatorPaths.login
  return BUSINESS_LOGIN
}

const _LOGIN_PATHS = new Set<string>([BUSINESS_LOGIN, creatorPaths.login, creatorPaths.brandLogin])

function _logout() {
  clearCappeTokens()
  const path = window.location.pathname
  // Already sitting on a login screen — redirecting would loop.
  if (_LOGIN_PATHS.has(path)) return
  window.location.href = _loginPathFor(path)
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
  // Decode inside its own try: a malformed token just falls through to the
  // request, which will 401 and take the normal path. The refresh below must
  // stay OUTSIDE it — its network error is a real error to propagate, not
  // something to swallow as "unparseable token".
  let expiresIn: number | null = null
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    expiresIn = payload.exp - Date.now() / 1000
  } catch { /* malformed token — let the request fail normally */ }
  if (expiresIn === null || expiresIn >= 60) return token

  const outcome = await refreshCappeSession()
  if (outcome === 'dead') { _logout(); return null }
  // Couldn't reach the server: surface it instead of ending the session.
  if (outcome === 'transport') throw _networkError()
  return getCappeToken()
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
  const token = getCappeToken()
  const res = await fetch(`${BASE}${path}`, { ...init, headers: _buildHeaders(init, token) })

  if (res.status === 401 && token) {
    const outcome = await refreshCappeSession()
    if (outcome === 'ok') {
      const newToken = getCappeToken()
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
    // Only a server-side rejection of the refresh token ends the session.
    if (outcome === 'dead') { _logout(); throw new Error('Session expired') }
    throw _networkError()
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
    const token = getCappeToken()
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: _buildHeaders({ body: body ? JSON.stringify(body) : undefined }, token),
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText || 'Preview failed'}`)
    return res.text()
  },
  // Authed GET of a binary (e.g. a receipt PDF) → saves it via a synthetic
  // download link. `window.open` on a blob: URL is what a pop-up blocker
  // stops by default (the open happens after an await, so it no longer counts
  // as user-initiated) — the user clicked "Receipt" and nothing happened,
  // with no error to show. An anchor click is not pop-up-blocked.
  openBlob: async (path: string, filename = 'download'): Promise<void> => {
    const token = getCappeToken()
    const res = await fetch(`${BASE}${path}`, { headers: _buildHeaders(undefined, token) })
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      throw new Error(body?.detail || `${res.status} ${res.statusText || 'Download failed'}`)
    }
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
    // Revoked on the next tick, not immediately: Safari reads the blob after
    // the click handler returns.
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
