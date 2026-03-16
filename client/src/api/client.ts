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
  window.location.href = '/login'
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
      if (!retry.ok) throw new Error(`${retry.status} ${retry.statusText}`)
      return retry.json()
    }

    _logout()
    throw new Error('Session expired')
  }

  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
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
}
