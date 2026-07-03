// Legal Pilot API client. Matters CRUD + grounded chat (SSE) + packet
// generation/download/share. The chat stream is a raw fetch (like
// IRCopilotPanel) since api/client.ts doesn't stream; everything else goes
// through the typed `api` helper.
import { api } from './client'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

export type MatterType = 'subpoena' | 'class_action' | 'eeoc_charge' | 'single_plaintiff' | 'audit' | 'other'
export type MatterStatus = 'draft' | 'active' | 'closed'

export type EvidenceRecord = { cid: string; ref: string | null; summary: string; when: string }
export type EvidenceSource = { label: string; records: EvidenceRecord[] }
export type EvidencePreview = { sources: Record<string, EvidenceSource>; notes: string[]; total: number }

export type EvidenceMapItem = { point: string; cited_ids: string[] }
export type MessageMeta = {
  evidence_map?: EvidenceMapItem[]
  open_questions?: string[]
  dropped_citations?: string[]
} | null

export type MatterMessage = {
  role: 'user' | 'assistant' | 'system'
  content: string
  metadata: MessageMeta
  created_at: string
}

export type PacketShareStatus = {
  recipient_email: string | null
  download_count: number
  last_downloaded_at: string | null
  expires_at: string | null
  revoked: boolean
  created_at: string
}

export type Packet = {
  id: string
  kind: 'pdf' | 'zip'
  filename: string
  citations?: string[]
  file_size: number | null
  generated_at: string
  share?: PacketShareStatus | null
}

export type Matter = {
  id: string
  company_id: string
  title: string
  matter_type: MatterType
  allegation: string | null
  defense_theory: string | null
  status: MatterStatus
  evidence_start: string | null
  evidence_end: string | null
  counsel_directed: boolean
  counsel_name: string | null
  counsel_email: string | null
  created_at: string
  updated_at: string
  closed_at: string | null
  packet_count?: number
  messages?: MatterMessage[]
  packets?: Packet[]
}

export type MatterCreate = {
  title: string
  matter_type: MatterType
  allegation?: string | null
  defense_theory?: string | null
  evidence_start?: string | null
  evidence_end?: string | null
  counsel_directed?: boolean
  counsel_name?: string | null
  counsel_email?: string | null
}

export const listMatters = () => api.get<Matter[]>('/legal-pilot/matters')
export const createMatter = (body: MatterCreate) => api.post<Matter>('/legal-pilot/matters', body)
export const getMatter = (id: string) => api.get<Matter>(`/legal-pilot/matters/${id}`)
export const updateMatter = (id: string, body: Partial<MatterCreate> & { status?: MatterStatus }) =>
  api.patch<Matter>(`/legal-pilot/matters/${id}`, body)
export const getEvidence = (id: string) => api.get<EvidencePreview>(`/legal-pilot/matters/${id}/evidence`)
export const generatePacket = (id: string, kind: 'pdf' | 'zip' | 'both') =>
  api.post<{ packets: Packet[] }>(`/legal-pilot/matters/${id}/packet`, { kind })
export const sharePacket = (matterId: string, packetId: string, body: { recipient_email?: string; expires_days?: number }) =>
  api.post<{ token: string; path: string; expires_at: string }>(
    `/legal-pilot/matters/${matterId}/packets/${packetId}/share`, body,
  )

// Authed blob download → browser save (keeps the server filename).
export async function downloadPacket(matterId: string, packet: Packet): Promise<void> {
  const token = localStorage.getItem('matcha_access_token')
  const res = await fetch(`${BASE}/legal-pilot/matters/${matterId}/packets/${packet.id}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`Download failed (${res.status})`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = packet.filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

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
// stream). Mirrors the IRCopilotPanel consumption pattern.
export async function streamChat(matterId: string, message: string, h: ChatHandlers): Promise<void> {
  const token = localStorage.getItem('matcha_access_token')
  const res = await fetch(`${BASE}/legal-pilot/matters/${matterId}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
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
