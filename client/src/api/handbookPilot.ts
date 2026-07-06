// Handbook Pilot API client (Pro + Matcha-X). Sessions CRUD + grounded
// generation chat (SSE) + draft review/edit + promotion into the real
// handbooks / policies tables. The chat stream is a raw fetch (like
// legalDefense.ts / brokerPilot.ts / IRCopilotPanel) since api/client.ts
// doesn't stream; everything else goes through the typed `api` helper.
import { api, authStreamHeaders } from './client'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

export type SessionStatus = 'active' | 'closed'
export type DraftKind = 'handbook_section' | 'policy'
export type DraftStatus = 'pending' | 'promoted' | 'discarded'

export type MessageMeta = {
  open_questions?: string[]
  dropped_citations?: string[]
  draft_ids?: string[]
} | null

export type PilotMessage = {
  role: 'user' | 'assistant' | 'system'
  content: string
  metadata: MessageMeta
  created_at: string
}

export type PilotDraft = {
  id: string
  kind: DraftKind
  title: string
  section_key: string | null
  content: string
  jurisdiction_scope: Record<string, unknown> | null
  citations: string[] | null
  status: DraftStatus
  promoted_ref: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export type PilotSession = {
  id: string
  company_id: string
  title: string
  goal: string | null
  industry: string | null
  scopes?: Array<Record<string, unknown>> | null
  status: SessionStatus
  created_at: string
  updated_at: string
  closed_at: string | null
  message_count?: number
  draft_count?: number
  promoted_count?: number
  messages?: PilotMessage[]
  drafts?: PilotDraft[]
}

export type ContextPreview = {
  sources: Record<string, { label: string; count: number }>
  notes: string[]
  scopes: Array<Record<string, unknown>>
  total: number
}

export type PromoteFailure = { draft_id: string; title: string; error: string }
export type PromoteResult = {
  promoted: number
  handbook: { id: string; title: string } | null
  policies: Array<{ id: string; title: string }>
  failed: PromoteFailure[]
}

export const listPilotSessions = () =>
  api.get<PilotSession[]>('/handbook-pilot/pilot/sessions')
export const createPilotSession = (body: { title: string; goal?: string; industry?: string }) =>
  api.post<PilotSession>('/handbook-pilot/pilot/sessions', body)
export const getPilotSession = (id: string) =>
  api.get<PilotSession>(`/handbook-pilot/pilot/sessions/${id}`)
export const updatePilotSession = (
  id: string,
  body: { title?: string; goal?: string; industry?: string; status?: SessionStatus },
) => api.patch<PilotSession>(`/handbook-pilot/pilot/sessions/${id}`, body)

export const getPilotContext = (sessionId: string) =>
  api.get<ContextPreview>(`/handbook-pilot/pilot/sessions/${sessionId}/context`)

export const updatePilotDraft = (
  draftId: string,
  body: { title?: string; content?: string; section_key?: string },
) => api.patch<PilotDraft>(`/handbook-pilot/pilot/drafts/${draftId}`, body)
export const deletePilotDraft = (draftId: string) =>
  api.delete<{ deleted: boolean }>(`/handbook-pilot/pilot/drafts/${draftId}`)

export const promotePilotDrafts = (
  sessionId: string,
  body: { draft_ids: string[]; handbook_title?: string },
) => api.post<PromoteResult>(`/handbook-pilot/pilot/sessions/${sessionId}/promote`, body)

export type ProposedDraft = {
  kind: DraftKind
  title: string
  section_key: string | null
  content: string
  cited_ids: string[]
}
export type ChatResult = {
  assistant_text: string
  proposed_drafts: ProposedDraft[]
  open_questions: string[]
  dropped_citations?: string[]
}
export type ChatHandlers = {
  onStatus?: (message: string) => void
  onResult?: (data: ChatResult) => void
  onError?: (message: string) => void
}

// Grounded drafting turn over SSE — raw fetch + ReadableStream (api/client.ts
// can't stream). Mirrors the brokerPilot.ts / legalDefense.ts pattern. Pass a
// `signal` to abort the turn (e.g. when the user switches sessions mid-stream);
// an aborted turn resolves quietly rather than surfacing an error.
export async function streamChat(
  sessionId: string,
  message: string,
  h: ChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch(`${BASE}/handbook-pilot/pilot/sessions/${sessionId}/chat`, {
      method: 'POST',
      headers: await authStreamHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ message }),
      signal,
    })
  } catch (e) {
    if (signal?.aborted) return
    h.onError?.('Chat failed — please try again.')
    return
  }
  if (!res.ok || !res.body) {
    h.onError?.(`Chat failed (${res.status})`)
    return
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const events = buf.split('\n\n')
      buf = events.pop() || ''
      for (const ev of events) {
        if (!ev.startsWith('data: ')) continue
        const payload = ev.slice(6)
        if (payload === '[DONE]') return
        try {
          const data = JSON.parse(payload)
          if (data.type === 'status') h.onStatus?.(data.message)
          else if (data.type === 'result') h.onResult?.(data.data)
          else if (data.type === 'error') h.onError?.(data.message)
        } catch {
          /* ignore partial/non-JSON frames */
        }
      }
    }
  } catch (e) {
    if (signal?.aborted) return
    h.onError?.('Chat connection dropped — please try again.')
  }
}
