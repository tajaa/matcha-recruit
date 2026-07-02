// Tell-Us API client — self-contained auth/fetch layer keyed on its OWN
// localStorage tokens (tellus_*) and base path (/api/tellus). Mirrors the
// matcha/cappe client's 401 refresh-and-retry. A Tell-Us session coexists with
// a matcha or cappe session in one browser without colliding.

const BASE = `${import.meta.env.VITE_API_URL ?? '/api'}/tellus`

const ACCESS_KEY = 'tellus_access_token'
const REFRESH_KEY = 'tellus_refresh_token'

export function getTellusToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function setTellusTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTellusTokens() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

let _refreshing: Promise<boolean> | null = null

async function _tryRefresh(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_KEY)
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
    window.location.href = '/tellus/login'
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem(ACCESS_KEY)
  const res = await fetch(`${BASE}${path}`, { ...init, headers: _headers(init, token) })

  if (res.status === 401 && token) {
    if (!_refreshing) {
      _refreshing = _tryRefresh().finally(() => { _refreshing = null })
    }
    const ok = await _refreshing
    if (ok) {
      const newToken = localStorage.getItem(ACCESS_KEY)
      const retry = await fetch(`${BASE}${path}`, { ...init, headers: _headers(init, newToken) })
      if (!retry.ok) {
        if (retry.status === 401) { _logout(); throw new Error('Session expired') }
        throw new Error(await _errMsg(retry))
      }
      if (retry.status === 204) return null as T
      return retry.json()
    }
    _logout()
    throw new Error('Session expired')
  }

  if (!res.ok) throw new Error(await _errMsg(res))
  if (res.status === 204) return null as T
  return res.json()
}

async function _errMsg(res: Response): Promise<string> {
  const body = await res.json().catch(() => null)
  if (body?.detail) {
    const d = body.detail
    return typeof d === 'string' ? d : (d?.message || JSON.stringify(d))
  }
  if (res.status >= 500) return 'Server error — try again in a moment.'
  return `${res.status} ${res.statusText || 'Request failed'}`
}

// Unauthenticated GET (public token-resolved resources, e.g. the intake config).
export async function tellusPublicGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(await _errMsg(res))
  return res.json()
}

// Unauthenticated POST (signup/login/verify) — never attaches/refreshes a token.
export async function tellusPublicPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await _errMsg(res))
  return res.json()
}

// Public POST that optionally carries the Tell-Us token if the user is logged
// in (feedback submit: anonymous by default, attributed when signed in).
export async function tellusMaybeAuthPost<T>(path: string, body: unknown): Promise<T> {
  const token = localStorage.getItem(ACCESS_KEY)
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await _errMsg(res))
  return res.json()
}

export const tellusApi = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

export { _logout as tellusLogout }
