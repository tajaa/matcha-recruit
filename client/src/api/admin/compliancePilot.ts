// Compliance Pilot API client (admin). Sessions CRUD + grounded chat (SSE) +
// action run/poll/approve. Chat streams via api/sse.ts (api/client.ts can't
// stream); everything else goes through the typed `api` helper.
import { api } from '../client'
import {
  streamPilotChat as sharedStreamPilotChat,
  type ChatHandlers as SharedChatHandlers,
} from '../sse'

export type PilotMode = 'research' | 'ask' | 'check_sources' | 'scope'

export type PilotTemplate = {
  key: PilotMode
  label: string
  description: string
  title: string
  starters: string[]
}

export type Citation = { point: string; cited_ids: string[] }

// A proposal, resolved server-side against the DB (concrete coordinate + preview).
export type ResearchProposal = {
  kind: 'research'
  state: string
  city: string | null
  city_found: boolean
  rationale: string
  industry_tag: string
  categories: string[]
  category_labels?: string[]
  category_count: number
  coverage: { covered: number; empty: number; unchecked: number }
  existing_active_rows: number
}
export type CheckSourcesProposal = {
  kind: 'check_sources'
  state: string
  city: string | null
  city_found: boolean
  rationale: string
  chain_ids: string[]
  source_urls: number
}
export type Proposal = ResearchProposal | CheckSourcesProposal

export type MessageMeta = {
  citations?: Citation[]
  proposal?: Proposal | null
  proposal_errors?: string[]
  dropped_citations?: string[]
}

export type PilotMessage = {
  role: 'user' | 'assistant' | 'system'
  content: string
  metadata: MessageMeta | null
  created_at: string
}

export type ActionKind = 'research' | 'approve' | 'check_sources'
export type ActionStatus = 'running' | 'done' | 'failed'

// One discovered policy in a research run — with provenance + the codify gate.
export type StagedRow = {
  id: string
  title: string
  jurisdiction_level: string
  regulation_key: string | null
  category: string
  source_url: string | null
  source_domain_class: 'primary' | 'secondary_official' | 'aggregator' | 'unknown' | 'missing'
  source_url_status: string | null
  research_citation: string | null
  state: string | null
  city: string | null
  gate_ok: boolean
  gate_reason: string | null
}

export type ApproveRowResult = {
  id: string
  title: string
  activated?: boolean
  codified: boolean
  statute_citation: string | null
  citation_url: string | null
  gate_reason?: string | null
  state: string | null
  city: string | null
}

export type PilotAction = {
  id: string
  session_id?: string
  kind: ActionKind
  params: Record<string, unknown> | null
  status: ActionStatus
  progress: { phase?: string; message?: string; categories?: number } | null
  result: Record<string, unknown> | null
  staged_ids: string[]
  started_at: string
  finished_at: string | null
}

export type PilotSession = {
  id: string
  title: string
  mode: PilotMode
  status: 'active' | 'closed'
  created_at: string
  updated_at: string
  template?: PilotTemplate | null
  message_count?: number
  messages?: PilotMessage[]
  actions?: PilotAction[]
}

export const listTemplates = () => api.get<PilotTemplate[]>('/admin/pilot/templates')
export const listSessions = () => api.get<PilotSession[]>('/admin/pilot/sessions')
export const getSession = (id: string) => api.get<PilotSession>(`/admin/pilot/sessions/${id}`)
export const createSession = (mode: PilotMode, title?: string) =>
  api.post<PilotSession>('/admin/pilot/sessions', { mode, title })
export const closeSession = (id: string) =>
  api.patch<PilotSession>(`/admin/pilot/sessions/${id}`, { status: 'closed' })

export type ActionCreateBody = {
  kind: 'research' | 'check_sources'
  state: string
  city: string | null
  industry_tag?: string
  categories?: string[]
}
export const createAction = (sessionId: string, body: ActionCreateBody) =>
  api.post<{ action_id: string }>(`/admin/pilot/sessions/${sessionId}/actions`, body)
export const getAction = (id: string) => api.get<PilotAction>(`/admin/pilot/actions/${id}`)
export const approveAction = (id: string, ids?: string[]) =>
  api.post<{ action_id: string; activated: number; codified: number; uncodified: number;
             already_live: number; results: ApproveRowResult[] }>(
    `/admin/pilot/actions/${id}/approve`, ids ? { ids } : {})

export type ChatResult = {
  assistant_text: string
  citations: Citation[]
  proposal: Proposal | null
  proposal_errors?: string[]
}
export type ChatHandlers = SharedChatHandlers<ChatResult>

export async function streamPilotChat(sessionId: string, message: string, h: ChatHandlers): Promise<void> {
  await sharedStreamPilotChat<ChatResult>(`/admin/pilot/sessions/${sessionId}/chat`, { message }, h)
}
