import axios from 'axios'

const TOKEN_KEY = 'oceanlab_access_token'

export function getToken(): string | null {
  localStorage.removeItem(TOKEN_KEY)
  return sessionStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.removeItem(TOKEN_KEY)
  sessionStorage.setItem(TOKEN_KEY, token)
}

export async function login(email: string, password: string): Promise<void> {
  const response = await axios.post('/api/oceanlab/auth/login', { email, password })
  setToken(response.data.access_token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(TOKEN_KEY)
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

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      clearToken()
      window.location.reload()
    }
    return Promise.reject(error)
  },
)
