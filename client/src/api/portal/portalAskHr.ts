import { api } from '../client'
import type { Citation } from '../../components/ui/CitationSources'

// Employee "Ask HR" — grounded policy Q&A for the signed-in employee.
// Backend: server/app/matcha/routes/portal_ask_hr.py (/v1/portal/ask-hr)

export type AskHrSession = {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}

export type AskHrMessageMetadata = {
  citations?: Citation[]
  dropped_citations?: string[]
  open_questions?: string[]
  cannot_answer?: boolean
  /** Present only on a refused turn — the question was routed to HR, not answered. */
  hard_stop_category?: string
}

export type AskHrMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  metadata: AskHrMessageMetadata | null
  created_at: string
}

/** One SSE frame from the chat endpoint. The turn is generated whole and
 *  citation-gated server-side, so `result` arrives once, already clean. */
export type AskHrEvent =
  | { type: 'status'; message: string }
  | { type: 'error'; message: string }
  | {
      type: 'result'
      data: {
        assistant_text: string
        citations?: Citation[]
        dropped_citations?: string[]
        open_questions?: string[]
        cannot_answer?: boolean
        hard_stop?: boolean
        hard_stop_category?: string
      }
    }

export const portalAskHrApi = {
  listSessions: () => api.get<AskHrSession[]>('/v1/portal/ask-hr/sessions'),

  createSession: (title?: string) =>
    api.post<AskHrSession>('/v1/portal/ask-hr/sessions', { title: title ?? null }),

  deleteSession: (id: string) => api.delete<void>(`/v1/portal/ask-hr/sessions/${id}`),

  listMessages: (id: string) =>
    api.get<AskHrMessage[]>(`/v1/portal/ask-hr/sessions/${id}/messages`),

  /** SSE stream. Uses bare fetch rather than the `api` helper because the helper
   *  buffers a JSON body; the token is attached by hand for the same reason
   *  (see the IRCopilotPanel stream handler for the established pattern). */
  async chat(
    sessionId: string,
    message: string,
    onEvent: (ev: AskHrEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const base = import.meta.env.VITE_API_URL || '/api'
    const res = await fetch(`${base}/v1/portal/ask-hr/sessions/${sessionId}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('matcha_access_token') ?? ''}`,
      },
      body: JSON.stringify({ message }),
      signal,
    })
    if (!res.ok || !res.body) {
      onEvent({ type: 'error', message: res.status === 429
        ? 'You have asked a lot of questions in a short time — try again in a little while.'
        : 'Something went wrong. Please try again.' })
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // Frames are newline-delimited `data: ` lines; keep the trailing partial.
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6).trim()
        if (!payload || payload === '[DONE]') continue
        try {
          onEvent(JSON.parse(payload) as AskHrEvent)
        } catch {
          // A malformed frame is not worth failing the whole turn over.
        }
      }
    }
  },
}
