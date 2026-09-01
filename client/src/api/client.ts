import { resetAuthCaches } from './authReset'
import { clearAuthTokens, getAccessToken, getRefreshToken, setAuthTokens } from './authStorage'
import { noteRequestId, reportApiError } from './errorReporter'

export const API_BASE = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

let _refreshing: Promise<boolean> | null = null

async function _tryRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false

  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })

    if (!res.ok) return false

    const data = await res.json()
    setAuthTokens(data.access_token, data.refresh_token, { recordActivity: false })
    return true
  } catch {
    return false
  }
}

const SESSION_EVENT_KEY = 'matcha_session_event'
let _clearingSession = false

function _clearOutboxStorage(token: string | null) {
  try {
    let key = 'channels_outbox_v1'
    if (token) {
      const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
      if (payload?.sub) key += `:${payload.sub}`
    }
    sessionStorage.removeItem(key)
  } catch { /* malformed token or blocked storage */ }
}

async function _clearLocalSession(broadcast = true) {
  if (_clearingSession) return
  _clearingSession = true
  try {
    // Capture the outgoing user's outbox key SYNCHRONOUSLY — the dynamic
    // import below resolves as a microtask, after the token removal a few
    // lines down has already run, so reading the token inside the .then would
    // always see it gone and clear the wrong (unscoped) key.
    const outgoingToken = getAccessToken()
    clearAuthTokens()
    _clearOutboxStorage(outgoingToken)
    resetAuthCaches()
    // Best-effort cleanup of the shared channel WS + its durable outbox. Lazy-
    // imported to avoid a circular dependency between api/client.ts and
    // api/channelSocket.ts.
    await import('../work/api/channelSocket').then((m) => {
      m.disconnectSharedChannelSocket()
      m.clearChannelOutbox(outgoingToken)
    }).catch(() => { /* optional WebSocket cleanup must not block logout */ })
    if (broadcast) {
      try { localStorage.setItem(SESSION_EVENT_KEY, JSON.stringify({ type: 'logout', at: Date.now() })) } catch { /* storage may be blocked */ }
    }
    // Guard against a redirect loop: a failed refresh fired from the login page
    // itself would otherwise reassign location to /login repeatedly.
    if (window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
  } finally {
    // The login page is an SPA route, so the module can survive a subsequent
    // sign-in without a full page reload. Only guard concurrent cleanup calls.
    _clearingSession = false
  }
}

function _logout() {
  void _clearLocalSession()
}

/** Revoke the server session, then clear every local user-scoped surface. */
export async function logoutSession(): Promise<void> {
  try {
    // Refresh first when possible: with a 15-minute access token, a user may
    // click Sign out after it expired. A fresh access token lets the revocation
    // endpoint invalidate the still-live refresh session server-side.
    if (getRefreshToken()) await _tryRefresh()
    const token = getAccessToken()
    if (token) {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        keepalive: true,
      })
    }
  } finally {
    await _clearLocalSession()
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key === SESSION_EVENT_KEY && event.newValue) void _clearLocalSession(false)
  })
}

/** Proactively refresh token if it expires within 60s. Use before SSE/WebSocket where 401 retry isn't possible. */
export async function ensureFreshToken(): Promise<string | null> {
  const token = getAccessToken()
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
      return getAccessToken()
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

/** Thrown on any non-ok response from request(). Carries the HTTP status
 *  alongside the message so callers can branch on status (e.g. 429) instead
 *  of pattern-matching the message string. */
// Expected client-input/business-rule/auth statuses — reporting these floods
// the server_error_reports table with things like "Employee is already
// scheduled during this time" (409) that aren't bugs, or 401/403 (auth
// conditions handled by refresh/logout below, not application errors).
// Report only 5xx, network failures (status 0), and anything unexpected.
const _EXPECTED_STATUSES = new Set([400, 401, 402, 403, 404, 409, 410, 422, 429])
export function _shouldReportStatus(status: number): boolean {
  return status === 0 || status >= 500 || !_EXPECTED_STATUSES.has(status)
}

export class ApiError extends Error {
  status: number
  body: unknown
  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getAccessToken()
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: _buildHeaders(init, token),
  })
  noteRequestId(res.headers.get('x-request-id'))

  if (res.status === 401 && token) {
    // Deduplicate concurrent refresh attempts
    if (!_refreshing) {
      _refreshing = _tryRefresh().finally(() => { _refreshing = null })
    }

    const ok = await _refreshing
    if (ok) {
      // Retry with new token
      const newToken = getAccessToken()
      const retry = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers: _buildHeaders(init, newToken),
      })
      noteRequestId(retry.headers.get('x-request-id'))
      if (!retry.ok) {
        // A 401 on the retry means the freshly-refreshed token is also
        // rejected — the session is truly dead. Clear it and bounce to login
        // rather than leaving the app in a half-authed state.
        if (retry.status === 401) {
          _logout()
          throw new Error('Session expired')
        }
        const retryBody = await retry.json().catch(() => null)
        const msg = (typeof retryBody?.detail === 'string' ? retryBody.detail : retryBody?.detail?.message)
          || `${retry.status} ${retry.statusText}`
        if (path !== '/client-errors' && _shouldReportStatus(retry.status)) {
          reportApiError({ endpoint: path, status: retry.status, message: msg, body: retryBody })
        }
        throw new ApiError(msg, retry.status, retryBody)
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
      // Structured details ({code, message, …} — e.g. the 429/402 token
      // quota/budget gates) carry a human `.message`; prefer it over the
      // raw JSON dump.
      msg = typeof errBody.detail === 'string' ? errBody.detail
        : typeof errBody.detail?.message === 'string' ? errBody.detail.message
        : JSON.stringify(errBody.detail)
    } else if (res.status >= 500) {
      msg = res.status === 502 || res.status === 503 || res.status === 504
        ? 'Server temporarily unavailable — retry in a moment.'
        : `Server error (${res.status})`
    } else {
      msg = `${res.status} ${res.statusText || 'Request failed'}`
    }
    if (path !== '/client-errors' && _shouldReportStatus(res.status)) {
      reportApiError({ endpoint: path, status: res.status, message: msg, body: errBody })
    }
    throw new ApiError(msg, res.status, errBody)
  }
  if (res.status === 204) return null as T
  return res.json()
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
  noteRequestId(res.headers.get('x-request-id'))
  if (res.status !== 401 || !token) return res
  if (!_refreshing) {
    _refreshing = _tryRefresh().finally(() => { _refreshing = null })
  }
  const ok = await _refreshing
  if (!ok) { _logout(); return res }
  const retry = await fetch(url, withAuth(getAccessToken()))
  noteRequestId(retry.headers.get('x-request-id'))
  return retry
}

/** Trigger a browser download from a binary Response.
 *
 * The anchor must be attached to the document before `.click()` — an
 * untethered anchor's click doesn't reliably register as a real download
 * gesture in Chrome, which then shows a phantom "Unconfirmed" entry and can
 * save a second, truncated copy of the file instead of the real one. */
async function _saveBlobResponse(res: Response, path: string, filename?: string): Promise<void> {
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename ?? path.split('/').pop() ?? 'download'
  document.body.appendChild(a)
  a.click()
  a.remove()
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
  // GET returning raw text (e.g. the admin traffic report HTML).
  getText: async (path: string) => {
    const res = await _fetchWithRefresh(`${API_BASE}${path}`)
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.text()
  },
  download: async (path: string, filename?: string) => {
    const res = await _fetchWithRefresh(`${API_BASE}${path}`)
    if (!res.ok) {
      const errBody = await res.json().catch(() => null)
      const msg = errBody?.detail
        ? typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail)
        : `${res.status} ${res.statusText}`
      throw new ApiError(msg, res.status, errBody)
    }
    await _saveBlobResponse(res, path, filename)
  },
  // POST a JSON body and download the binary response as a file.
  downloadPost: async (path: string, body: unknown, filename?: string) => {
    const res = await _fetchWithRefresh(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    await _saveBlobResponse(res, path, filename)
  },
}
