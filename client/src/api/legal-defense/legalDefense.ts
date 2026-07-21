// Legal Pilot API client. Matters CRUD + grounded chat (SSE) + packet
// generation/download/share. The chat stream goes through api/sse.ts (which
// api/client.ts can't do); everything else uses the typed `api` helper.
import { api } from '../client'
import {
  streamPilotChat as sharedStreamPilotChat,
  type ChatHandlers as SharedChatHandlers,
} from '../sse'

export type MatterType = 'subpoena' | 'class_action' | 'eeoc_charge' | 'single_plaintiff' | 'audit' | 'other'
export type MatterStatus = 'draft' | 'active' | 'closed'

export type EvidenceRecord = { cid: string; ref: string | null; summary: string; when: string; when_iso?: string | null }
export type EvidenceSource = { label: string; records: EvidenceRecord[] }
export type JurisdictionChainLink = { id: string; level: string; display_name: string }
export type LegalContext = {
  jurisdiction_id: string
  chain: JurisdictionChainLink[]
  state: string | null
  location_name: string | null
}
/** Values accepted by `legal_matters.subject_theory`. `null` derives the subject
 *  from the allegation; `'all'` forces every subject into the corpus. */
export type SubjectTheory = 'wage_hour' | 'eeo' | 'safety' | 'all'

/** The subject the backend scoped evidence to — derived from the matter's
 *  allegation text, or read from its stored `subject_theory` override.
 *  Null = no subject filter applied. */
export type MatterTheory = { slug: string; label: string; overridden: boolean }

export type EvidencePreview = {
  sources: Record<string, EvidenceSource>
  notes: string[]
  total: number
  legal_context?: LegalContext | null
  theory?: MatterTheory | null
}

/** The sources a subject filter actually narrows. Training, policy
 *  acknowledgments and accommodations are deliberately never subject-filtered
 *  (they're the exculpatory half of the record), so an empty one of those must
 *  not be blamed on the subject. Mirrors `_THEORIES` in the service. */
export const SUBJECT_FILTERED_SOURCES = new Set([
  'incidents', 'er_cases', 'compliance', 'compliance_alerts', 'discipline',
])

export type EvidenceMapItem = { point: string; cited_ids: string[] }
export type MessageMeta = {
  evidence_map?: EvidenceMapItem[]
  open_questions?: string[]
  dropped_citations?: string[]
  /** Asks directed at the ADMIN — documents or facts still needed to complete
   *  the case file. Distinct from `open_questions`, which is for counsel. On a
   *  gathering turn the server withholds the analysis blocks, so these arrive
   *  with `evidence_map` and `open_questions` empty. */
  intake_requests?: string[]
  ready_for_analysis?: boolean
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
  location_id: string | null
  jurisdiction_state: string | null
  /** null = derive the evidence subject from the allegation. */
  subject_theory: SubjectTheory | null
  response_deadline: string | null
  deadline_note: string | null
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
  /** null (or omitted) derives the evidence subject from the allegation. */
  subject_theory?: SubjectTheory | null
  evidence_start?: string | null
  evidence_end?: string | null
  counsel_directed?: boolean
  counsel_name?: string | null
  counsel_email?: string | null
  location_id?: string | null
  jurisdiction_state?: string | null
  response_deadline?: string | null
  deadline_note?: string | null
}

export type IntakeDraft = {
  matter_type: MatterType
  title: string | null
  allegation: string | null
  plaintiff: string | null
  defendant: string | null
  jurisdiction_state: string | null
  evidence_start: string | null
  evidence_end: string | null
  response_deadline: string | null
  available: boolean
}
export const parseIntakeDocument = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<IntakeDraft>('/legal-pilot/intake/parse', fd)
}

export const listMatters = () => api.get<Matter[]>('/legal-pilot/matters')
export const createMatter = (body: MatterCreate) => api.post<Matter>('/legal-pilot/matters', body)
export const getMatter = (id: string) => api.get<Matter>(`/legal-pilot/matters/${id}`)
export const updateMatter = (id: string, body: Partial<MatterCreate> & { status?: MatterStatus }) =>
  api.patch<Matter>(`/legal-pilot/matters/${id}`, body)
export const getEvidence = (id: string) => api.get<EvidencePreview>(`/legal-pilot/matters/${id}/evidence`)
export const generatePacket = (id: string, kind: 'pdf' | 'zip' | 'both', includeResearch = false) =>
  api.post<{ packets: Packet[] }>(`/legal-pilot/matters/${id}/packet`, { kind, include_research: includeResearch })
export const sharePacket = (matterId: string, packetId: string, body: { recipient_email?: string; expires_days?: number }) =>
  api.post<{ token: string; path: string; expires_at: string }>(
    `/legal-pilot/matters/${matterId}/packets/${packetId}/share`, body,
  )

// Authed blob download → browser save (keeps the server filename).
// api.download handles proactive refresh + 401 retry.
export function downloadPacket(matterId: string, packet: Packet): Promise<void> {
  return api.download(
    `/legal-pilot/matters/${matterId}/packets/${packet.id}/download`,
    packet.filename,
  )
}

export type ResearchCase = {
  id: string
  case_name: string
  citation: string | null
  court: string
  date_filed: string | null
  url: string
  snippet?: string | null
}
export type ResearchGuidance = {
  summary: string
  key_authorities: { name: string; url: string; publisher?: string; relevance?: string }[]
}
export type ResearchRow = {
  id: string
  status: 'running' | 'complete' | 'failed'
  query: string | null
  jurisdiction_state: string | null
  cases: ResearchCase[] | null
  guidance: ResearchGuidance | null
  error: string | null
  created_at: string
  completed_at: string | null
}
export const runResearch = (matterId: string, includeGuidance = true) =>
  api.post<ResearchRow>(`/legal-pilot/matters/${matterId}/research`, { include_guidance: includeGuidance })
export const listResearch = (matterId: string) =>
  api.get<ResearchRow[]>(`/legal-pilot/matters/${matterId}/research`)

export type ChatResult = {
  assistant_text: string
  evidence_map: EvidenceMapItem[]
  open_questions: string[]
  dropped_citations?: string[]
  intake_requests?: string[]
  ready_for_analysis?: boolean
}
export type ChatHandlers = SharedChatHandlers<ChatResult>

// Grounded chat turn over SSE. Pass a `signal` to abort the turn (e.g. when the
// user switches matters mid-stream); an aborted turn resolves quietly.
export async function streamChat(
  matterId: string,
  message: string,
  h: ChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  await sharedStreamPilotChat<ChatResult>(
    `/legal-pilot/matters/${matterId}/chat`,
    { message },
    h,
    { signal },
  )
}
