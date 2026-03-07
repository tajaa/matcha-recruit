const getToken = () => sessionStorage.getItem('agent_token') || ''

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
  const res = await fetch(path, { ...opts, headers })
  if (res.status === 401) {
    sessionStorage.removeItem('agent_token')
    window.location.reload()
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

export interface HealthStatus {
  status: string
  gmail: boolean
  calendar: boolean
  llm: boolean
}

export interface Email {
  id: string
  subject: string
  from: string
  date: string
  body: string
}

export interface ChatMessage {
  role: 'user' | 'agent'
  content: string
}

export interface GmailLabel {
  id: string
  name: string
  type: string
}

export interface FeedItem {
  url: string
  name: string
}

export interface AgentConfig {
  feeds: FeedItem[]
  gmail_label_ids: string[]
  gmail_max_emails: number
  rss_interests: string
  rss_max_entries_per_feed: number
}

export const api = {
  health: () => request<HealthStatus>('/health'),

  chat: (message: string, history: ChatMessage[]) =>
    request<{ response: string }>('/agent/chat', {
      method: 'POST',
      body: JSON.stringify({ message, history: history.slice(-20) }),
    }),

  fetchEmails: (max_results = 10) =>
    request<{ emails: Email[] }>('/agent/email/fetch', {
      method: 'POST',
      body: JSON.stringify({ max_results }),
    }),

  draftReply: (email_id: string, instructions: string) =>
    request<{ draft_id: string; to: string; subject: string; body: string }>(
      '/agent/email/draft',
      {
        method: 'POST',
        body: JSON.stringify({ email_id, instructions }),
      }
    ),

  createEvent: (email_id: string) =>
    request<{ event: Record<string, unknown>; link: string }>(
      '/agent/calendar/create',
      {
        method: 'POST',
        body: JSON.stringify({ email_id }),
      }
    ),

  briefing: () =>
    request<{ file: string | null; content: string }>('/agent/briefing', {
      method: 'POST',
    }),

  getLabels: () => request<{ labels: GmailLabel[] }>('/agent/email/labels'),

  getConfig: () => request<AgentConfig>('/agent/config'),

  updateConfig: (updates: Partial<AgentConfig>) =>
    request<AgentConfig>('/agent/config', {
      method: 'PUT',
      body: JSON.stringify(updates),
    }),
}

export async function tryConnect(secret: string): Promise<HealthStatus> {
  sessionStorage.setItem('agent_token', secret)
  try {
    return await api.health()
  } catch (e) {
    sessionStorage.removeItem('agent_token')
    throw e
  }
}
