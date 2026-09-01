// Tell-Us API client — self-contained auth/fetch layer keyed on its OWN
// localStorage tokens (tellus_*) and base path (/api/tellus). Mirrors the
// matcha/cappe client's 401 refresh-and-retry. A Tell-Us session coexists with
// a matcha or cappe session in one browser without colliding.

const BASE = `${import.meta.env.VITE_API_URL ?? '/api'}/tellus`

const ACCESS_KEY = 'tellus_access_token'
const REFRESH_KEY = 'tellus_refresh_token'

// One-shot migration off persistent origin storage, run at module load rather
// than inside the getter — a getter that mutates storage ran a removeItem pair
// on every single request.
try {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
} catch { /* storage may be blocked */ }

export function getTellusToken(): string | null {
  try { return sessionStorage.getItem(ACCESS_KEY) } catch { return null }
}

export function getTellusRefreshToken(): string | null {
  try { return sessionStorage.getItem(REFRESH_KEY) } catch { return null }
}

export function setTellusTokens(access: string, refresh: string) {
  try {
    sessionStorage.setItem(ACCESS_KEY, access)
    sessionStorage.setItem(REFRESH_KEY, refresh)
  } catch { /* storage may be blocked */ }
}

export function clearTellusTokens() {
  try {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
    sessionStorage.removeItem(ACCESS_KEY)
    sessionStorage.removeItem(REFRESH_KEY)
  } catch { /* storage may be blocked */ }
}

let _refreshing: Promise<boolean> | null = null

async function _tryRefresh(): Promise<boolean> {
  const refreshToken = getTellusRefreshToken()
  if (!refreshToken) return false
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) return false
    const data = await res.json()
    setTellusTokens(data.access_token, data.refresh_token)
    return true
  } catch {
    return false
  }
}

function _logout() {
  clearTellusTokens()
  if (window.location.pathname !== '/tellus/login') {
    const rel = window.location.pathname.replace(/^\/tellus/, '') + window.location.search
    window.location.href = '/tellus/login?returnTo=' + encodeURIComponent(rel)
  }
}

function _headers(init?: RequestInit, token?: string | null): HeadersInit {
  const isFormData = init?.body instanceof FormData
  return {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...init?.headers,
  }
}

export class ApiError extends Error {
  status: number
  // Backend error shape is {detail: {code, message, ...extra}} for structured
  // errors (see PromoError in server/app/tellus/services/promo_service.py)
  // or {detail: "plain string"} for FastAPI's default. code/detail are only
  // populated for the structured form — callers that need to branch on the
  // specific failure (e.g. Scan.tsx distinguishing already_redeemed from
  // expired) need these; a bare .message can't be pattern-matched safely.
  code?: string
  detail?: Record<string, unknown>
  constructor(message: string, status: number, code?: string, detail?: Record<string, unknown>) {
    super(message)
    this.status = status
    this.code = code
    this.detail = detail
  }
}

async function _apiError(res: Response): Promise<ApiError> {
  const body = await res.json().catch(() => null)
  const d = body?.detail
  // FastAPI's own request-validation shape is an ARRAY of error objects, and it
  // is `typeof 'object'` — so this must come first, or the branch below
  // JSON.stringify's a raw [{"type":"greater_than_equal","loc":[...]}] blob
  // into the UI. Surface the offending field's message instead.
  if (Array.isArray(d)) {
    const first = d[0] as { msg?: unknown; loc?: unknown[] } | undefined
    const msg = typeof first?.msg === 'string' ? first.msg : 'Some fields need fixing.'
    const loc = Array.isArray(first?.loc) ? first.loc : []
    const field = loc.length ? String(loc[loc.length - 1]) : ''
    return new ApiError(field ? `${field}: ${msg}` : msg, res.status)
  }
  if (d && typeof d === 'object') {
    const message = typeof d.message === 'string' ? d.message : JSON.stringify(d)
    const code = typeof d.code === 'string' ? d.code : undefined
    return new ApiError(message, res.status, code, d as Record<string, unknown>)
  }
  if (typeof d === 'string') return new ApiError(d, res.status)
  if (res.status >= 500) return new ApiError('Server error — try again in a moment.', res.status)
  return new ApiError(`${res.status} ${res.statusText || 'Request failed'}`, res.status)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getTellusToken()
  const res = await fetch(`${BASE}${path}`, { ...init, headers: _headers(init, token) })

  if (res.status === 401 && token) {
    if (!_refreshing) {
      _refreshing = _tryRefresh().finally(() => { _refreshing = null })
    }
    const ok = await _refreshing
    if (ok) {
      const newToken = getTellusToken()
      const retry = await fetch(`${BASE}${path}`, { ...init, headers: _headers(init, newToken) })
      if (!retry.ok) {
        if (retry.status === 401) { _logout(); throw new ApiError('Session expired', 401) }
        throw await _apiError(retry)
      }
      if (retry.status === 204) return null as T
      return retry.json()
    }
    _logout()
    throw new ApiError('Session expired', 401)
  }

  if (!res.ok) throw await _apiError(res)
  if (res.status === 204) return null as T
  return res.json()
}

// Unauthenticated GET (public token-resolved resources, e.g. the intake config).
export async function tellusPublicGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw await _apiError(res)
  return res.json()
}

// Unauthenticated POST (signup/login/verify) — never attaches/refreshes a token.
export async function tellusPublicPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await _apiError(res)
  if (res.status === 204) return null as T
  return res.json()
}

// Public GET that optionally carries the Tell-Us token if the user is logged
// in — e.g. /b/{slug}, whose liked_by_me only resolves for a bearer the
// backend can actually decode. Unlike tellusApi.get, never 401-redirects: a
// missing/expired token just means anonymous, not a session to recover.
export async function tellusMaybeAuthGet<T>(path: string): Promise<T> {
  const token = getTellusToken()
  const res = await fetch(`${BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw await _apiError(res)
  return res.json()
}

// Public POST that optionally carries the Tell-Us token if the user is logged
// in (feedback submit: anonymous by default, attributed when signed in).
export async function tellusMaybeAuthPost<T>(path: string, body: unknown): Promise<T> {
  const token = getTellusToken()
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await _apiError(res)
  return res.json()
}

export const tellusApi = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  // Multipart upload — body passed through raw; _headers() already skips
  // Content-Type for FormData so the browser sets the boundary itself.
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form }),
}

export { _logout as tellusLogout }
