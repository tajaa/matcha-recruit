import { api } from './client'
import type {
  MWThread,
  MWThreadDetail,
  MWCreateResponse,
  MWSendResponse,
  MWStreamEvent,
} from '../types/matcha-work'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

// ── Threads ──

export function listThreads(status?: string) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return api.get<MWThread[]>(`/matcha-work/threads${qs}`)
}

export function getThread(id: string) {
  return api.get<MWThreadDetail>(`/matcha-work/threads/${id}`)
}

export function createThread(title?: string, initial_message?: string) {
  return api.post<MWCreateResponse>('/matcha-work/threads', {
    title,
    initial_message,
  })
}

// ── Thread actions ──

export function pinThread(id: string, is_pinned = true) {
  return api.post<MWThread>(`/matcha-work/threads/${id}/pin`, { is_pinned })
}

export function setNodeMode(id: string, node_mode: boolean) {
  return api.post<MWThread>(`/matcha-work/threads/${id}/node-mode`, { node_mode })
}

export function archiveThread(id: string) {
  return api.delete(`/matcha-work/threads/${id}`)
}

export function updateTitle(id: string, title: string) {
  return api.patch<MWThread>(`/matcha-work/threads/${id}`, { title })
}

// ── PDF ──

export function getPdf(id: string, version?: number) {
  const qs = version != null ? `?version=${version}` : ''
  return api.get<{ pdf_url: string; version: number }>(
    `/matcha-work/threads/${id}/pdf${qs}`
  )
}

export function getPdfProxyUrl(id: string, version?: number) {
  const qs = version != null ? `?version=${version}` : ''
  return `${BASE}/matcha-work/threads/${id}/pdf/proxy${qs}`
}

// ── SSE streaming ──

export function sendMessageStream(
  threadId: string,
  content: string,
  callbacks: {
    onEvent: (event: MWStreamEvent) => void
    onComplete: (data: MWSendResponse) => void
    onError: (err: string) => void
  },
): AbortController {
  const ctrl = new AbortController()
  const token = localStorage.getItem('matcha_access_token')

  fetch(`${BASE}/matcha-work/threads/${threadId}/messages/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ content }),
    signal: ctrl.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const text = await res.text().catch(() => res.statusText)
        callbacks.onError(`${res.status}: ${text}`)
        return
      }

      const reader = res.body?.getReader()
      if (!reader) {
        callbacks.onError('No response body')
        return
      }

      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })

        const lines = buf.split('\n')
        buf = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (raw === '[DONE]') return

          try {
            const event: MWStreamEvent = JSON.parse(raw)
            callbacks.onEvent(event)
            if (event.type === 'complete') {
              callbacks.onComplete(event.data)
              return
            }
            if (event.type === 'error') {
              callbacks.onError(event.message)
              return
            }
          } catch {
            /* skip malformed */
          }
        }
      }
    })
    .catch((e) => {
      if (e.name !== 'AbortError') {
        callbacks.onError(e instanceof Error ? e.message : 'Stream failed')
      }
    })

  return ctrl
}
