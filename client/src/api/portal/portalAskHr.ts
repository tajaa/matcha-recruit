import { api } from '../client'
import { postSSE, SSEHttpError } from '../sse'
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

  /** SSE stream via postSSE — the `api` helper buffers a JSON body and so can't
   *  stream. Auth rides authStreamHeaders (proactive refresh), not a hand-read
   *  token: a stream can't replay a mid-flight 401. */
  async chat(
    sessionId: string,
    message: string,
    onEvent: (ev: AskHrEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    try {
      await postSSE(
        `/v1/portal/ask-hr/sessions/${sessionId}/chat`,
        { message },
        (data) => { onEvent(data as AskHrEvent) },
        { signal },
      )
    } catch (e) {
      if (signal?.aborted) return
      const status = e instanceof SSEHttpError ? e.status : 0
      onEvent({ type: 'error', message: status === 429
        ? 'You have asked a lot of questions in a short time — try again in a little while.'
        : 'Something went wrong. Please try again.' })
    }
  },
}
