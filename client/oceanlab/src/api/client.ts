import axios from 'axios'

const TOKEN_KEY = 'oceanlab_access_token'
const REFRESH_KEY = 'oceanlab_refresh_token'

// One-shot migration off persistent origin storage, at module load rather than
// inside the getter — a getter that mutates storage ran a removeItem pair on
// every single request.
try {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
} catch { /* storage may be blocked */ }

export function getToken(): string | null {
  try { return sessionStorage.getItem(TOKEN_KEY) } catch { return null }
}

export function getRefreshToken(): string | null {
  try { return sessionStorage.getItem(REFRESH_KEY) } catch { return null }
}

export function setToken(token: string, refreshToken?: string): void {
  try {
    sessionStorage.setItem(TOKEN_KEY, token)
    if (refreshToken) sessionStorage.setItem(REFRESH_KEY, refreshToken)
  } catch { /* storage may be blocked */ }
}

export async function login(email: string, password: string): Promise<void> {
  const response = await axios.post('/api/oceanlab/auth/login', { email, password })
  setToken(response.data.access_token, response.data.refresh_token)
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(REFRESH_KEY)
  } catch { /* storage may be blocked */ }
}

export async function logout(): Promise<void> {
  try { await apiClient.post('/auth/logout') } finally { clearToken() }
}

export const apiClient = axios.create({
  baseURL: '/api/oceanlab',
})

apiClient.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/* Access tokens are 15 minutes (server/app/config.py). Without this, every
 * Oceanlab admin was bounced to the token gate a quarter-hour into any session,
 * because the 401 handler below only cleared the token and reloaded.
 *
 * Oceanlab has no refresh route of its own, but its login mints CORE tokens
 * (server/app/oceanlab/routers/auth.py calls create_access_token /
 * create_refresh_token), so the core route accepts them directly. */
let _refreshing: Promise<boolean> | null = null

async function _tryRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false
  try {
    const res = await axios.post('/api/auth/refresh', { refresh_token: refreshToken })
    if (!res.data?.access_token) return false
    setToken(res.data.access_token, res.data.refresh_token)
    return true
  } catch {
    return false
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error?.config
    // `_retried` stops a refreshed-but-still-401 response (revoked session,
    // deactivated admin) from looping.
    if (error?.response?.status === 401 && config && !config._retried) {
      config._retried = true
      if (!_refreshing) {
        _refreshing = _tryRefresh().finally(() => { _refreshing = null })
      }
      if (await _refreshing) {
        config.headers = { ...config.headers, Authorization: `Bearer ${getToken()}` }
        return apiClient.request(config)
      }
      clearToken()
      window.location.reload()
    }
    return Promise.reject(error)
  },
)
