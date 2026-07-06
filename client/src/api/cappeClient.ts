// Cappe API client — a parallel, self-contained auth/fetch layer for the Cappe
// product. Keyed on its OWN localStorage tokens (cappe_*) and base path
// (/api/cappe), so a Cappe session and a matcha session coexist in one browser
// without colliding. Mirrors api/client.ts's 401 refresh-and-retry.

const BASE = `${import.meta.env.VITE_API_URL ?? '/api'}/cappe`

const ACCESS_KEY = 'cappe_access_token'
const REFRESH_KEY = 'cappe_refresh_token'

export function getCappeToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function setCappeTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearCappeTokens() {
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
        throw new Error(body?.detail || `${retry.status} ${retry.statusText}`)
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
    if (errBody?.detail) {
      const d = errBody.detail
      // detail may be a string, or an object like {message, missing} (publish gate).
      msg = typeof d === 'string' ? d : (d?.message || JSON.stringify(d))
    } else if (res.status >= 500) {
      msg = 'Server error — try again in a moment.'
    } else {
      msg = `${res.status} ${res.statusText || 'Request failed'}`
    }
    throw new Error(msg)
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
