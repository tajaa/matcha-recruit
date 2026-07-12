// Broker Pilot API client (Broker Pro). Sessions CRUD + document uploads +
// grounded chat (SSE) + memo generation/download. The chat stream is a raw
// fetch (like legalDefense.ts / IRCopilotPanel) since api/client.ts doesn't
// stream; everything else goes through the typed `api` helper.
import { api, authStreamHeaders } from './client'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

export type SubjectKind = 'company' | 'external'
export type SessionStatus = 'active' | 'closed'
export type DocStatus = 'processing' | 'ready' | 'text_only' | 'failed'
export type DocType =
  | 'loss_run' | 'dec_page' | 'quote' | 'carrier_letter'
  | 'bordereau' | 'policy_form' | 'financials' | 'other'

export type KeyFigure = { label: string; value: string; context?: string }
export type DocExtraction = {
  doc_type: DocType
  title: string | null
  carrier: string | null
  line: string | null
  period_label: string | null
  effective_date: string | null
  summary: string | null
  key_figures: KeyFigure[]
  notable: string[]
} | null

export type PilotDocument = {
  id: string
  session_id: string
  filename: string
  content_type: string | null
  file_size: number | null
  page_count: number | null
  doc_type: DocType | null
  status: DocStatus
  extraction: DocExtraction
  error: string | null
  created_at: string
}

// A starter "mode" — public catalog shape (the server keeps the prompt `focus`
// to itself). `template` on a session is this shape or null (open analysis).
export type PilotTemplate = {
  key: string
  label: string
  description: string
  title: string
  starters: string[]
}

export type EvidenceMapItem = { point: string; cited_ids: string[] }
export type MessageMeta = {
  evidence_map?: EvidenceMapItem[]
  open_questions?: string[]
  dropped_citations?: string[]
} | null

export type PilotMessage = {
  role: 'user' | 'assistant' | 'system'
  content: string
  metadata: MessageMeta
  created_at: string
}

export type PilotPacket = {
  id: string
  filename: string
  citations?: string[]
  file_size: number | null
  generated_at: string
}

export type PilotSession = {
  id: string
  broker_id: string
  subject_kind: SubjectKind
  subject_id: string
  subject_name?: string | null
  title: string
  template_key?: string | null
  template?: PilotTemplate | null
  status: SessionStatus
  created_at: string
  updated_at: string
  closed_at: string | null
  message_count?: number
  document_count?: number
  packet_count?: number
  messages?: PilotMessage[]
  documents?: PilotDocument[]
  packets?: PilotPacket[]
}

export type CorpusRecord = { cid: string; ref: string | null; summary: string; when: string }
export type CorpusSource = { label: string; records: CorpusRecord[] }
export type ContextPreview = {
  sources: Record<string, CorpusSource>
  notes: string[]
  total: number
}

export const listPilotSessions = (filter?: { subject_kind: SubjectKind; subject_id: string }) => {
  const qs = filter ? `?subject_kind=${filter.subject_kind}&subject_id=${filter.subject_id}` : ''
  return api.get<PilotSession[]>(`/broker/pilot/sessions${qs}`)
}
export const listPilotTemplates = () => api.get<PilotTemplate[]>('/broker/pilot/templates')
export const createPilotSession = (body: {
  subject_kind: SubjectKind
  subject_id: string
  title?: string
  template_key?: string
}) => api.post<PilotSession>('/broker/pilot/sessions', body)
export const getPilotSession = (id: string) => api.get<PilotSession>(`/broker/pilot/sessions/${id}`)
export const updatePilotSession = (id: string, body: { title?: string; status?: SessionStatus }) =>
  api.patch<PilotSession>(`/broker/pilot/sessions/${id}`, body)

export const listPilotDocuments = (sessionId: string) =>
  api.get<PilotDocument[]>(`/broker/pilot/sessions/${sessionId}/documents`)
export const uploadPilotDocument = (sessionId: string, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.upload<PilotDocument>(`/broker/pilot/sessions/${sessionId}/documents`, form)
}
export const deletePilotDocument = (sessionId: string, docId: string) =>
  api.delete<{ deleted: boolean }>(`/broker/pilot/sessions/${sessionId}/documents/${docId}`)
export const getPilotDocumentUrl = (sessionId: string, docId: string) =>
  api.get<{ url: string; filename: string }>(
    `/broker/pilot/sessions/${sessionId}/documents/${docId}/download`,
  )

export const getPilotContext = (sessionId: string) =>
  api.get<ContextPreview>(`/broker/pilot/sessions/${sessionId}/context`)

export const generatePilotMemo = (sessionId: string) =>
  api.post<PilotPacket>(`/broker/pilot/sessions/${sessionId}/memo`, {})

// Authed blob download → browser save (api.download handles refresh + retry).
export const downloadPilotPacket = (sessionId: string, packet: PilotPacket) =>
  api.download(`/broker/pilot/sessions/${sessionId}/packets/${packet.id}/download`, packet.filename)

export type ChatResult = {
  assistant_text: string
  evidence_map: EvidenceMapItem[]
  open_questions: string[]
  dropped_citations?: string[]
}
export type ChatHandlers = {
  onStatus?: (message: string) => void
  onResult?: (data: ChatResult) => void
  onError?: (message: string) => void
}

// Grounded chat turn over SSE — raw fetch + ReadableStream (api/client.ts can't
// stream). Mirrors the legalDefense.ts / IRCopilotPanel consumption pattern.
export async function streamPilotChat(sessionId: string, message: string, h: ChatHandlers): Promise<void> {
  // authStreamHeaders proactively refreshes a near-expiry token — a stream
  // can't be replayed after a mid-flight 401.
  const res = await fetch(`${BASE}/broker/pilot/sessions/${sessionId}/chat`, {
    method: 'POST',
    headers: await authStreamHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ message }),
  })
  if (!res.ok || !res.body) {
    h.onError?.(`Chat failed (${res.status})`)
    return
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
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
}
