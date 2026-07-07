// Analysis Pilot API client — general-purpose bring-your-own-data analysis.
// Sessions + datasets (CSV/XLSX/PDF upload → deterministic metrics) + saved
// comparisons + grounded chat (SSE, with highlighted-record focus and
// AI-proposed extraction corrections) + analyst report PDF. The chat stream is
// a raw fetch (api/client.ts can't stream), mirroring handbookPilot.ts.
import { api, authStreamHeaders } from './client'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

export type SessionStatus = 'active' | 'closed'
export type DatasetStatus = 'processing' | 'ready' | 'needs_review' | 'failed'
export type SourceKind = 'csv' | 'xlsx' | 'pdf'

export type MetricTile = { label: string; value: string }
export type MetricTable = { title: string; columns: string[]; rows: string[][] }
export type MetricChart = { title: string; svg: string }
export type MetricBlock = {
  label: string
  tiles?: MetricTile[]
  tables?: MetricTable[]
  charts?: MetricChart[]
  records?: Array<{ cid: string; ref: string; summary: string; when: string }>
  values?: Record<string, number>
  datasets?: Array<{ id: string; label: string }>
  notes?: string[]
}

export type ExtractionLineItem = {
  label: string
  values: (number | null)[]
  unit: string | null
  page: number | null
}
export type Extraction = {
  kind: string
  title: string | null
  periods: string[]
  line_items: ExtractionLineItem[]
  notes: string[]
}

export type AnalysisDataset = {
  id: string
  filename: string
  source_kind: SourceKind
  status: DatasetStatus
  row_count: number | null
  column_count: number | null
  error: string | null
  created_at: string
  extraction: Extraction | null
  config: Record<string, unknown>
  mapping: Record<string, string>
  normalized: {
    roles: Record<string, string>
    kind: string | null
    periods: string[] | null
    columns: string[]
    meta: Record<string, unknown>
  }
  metrics: Record<string, MetricBlock>
  // Analyzer-pack warnings (backend strips them out of `metrics`).
  warnings: string[]
}

export type AnalysisComparison = {
  id: string
  title: string
  dataset_ids: string[]
  spec: Record<string, unknown> | null
  result: MetricBlock
  created_at: string
}

// A chat-proposed correction to a document-extracted figure. The AI only
// proposes — applying goes through the normal confirmed PATCH → recompute.
export type ProposedEdit = {
  dataset_id: string
  label: string
  period: string
  current_value: number | null
  proposed_value: number
  reason: string
}

export type AnalysisMessageMeta = {
  analysis_plan?: Array<{ step: string; finding: string; cited_ids: string[] }>
  evidence_map?: Array<{ point: string; cited_ids: string[] }>
  open_questions?: string[]
  dropped_citations?: string[]
  proposed_edits?: ProposedEdit[]
  dropped_edits?: unknown[]
  // cids the user highlighted when sending (user messages only)
  focus?: string[]
} | null

export type AnalysisMessage = {
  role: 'user' | 'assistant' | 'system'
  content: string
  metadata: AnalysisMessageMeta
  created_at: string
}

export type AnalysisPacket = {
  id: string
  filename: string
  citations: string[] | null
  file_size: number | null
  generated_at: string
}

export type AnalysisSession = {
  id: string
  company_id: string
  title: string
  domain: string | null
  goal: string | null
  status: SessionStatus
  created_at: string
  updated_at: string
  closed_at: string | null
  message_count?: number
  message_limit?: number
  dataset_count?: number
  packet_count?: number
  messages?: AnalysisMessage[]
  datasets?: AnalysisDataset[]
  comparisons?: AnalysisComparison[]
  packets?: AnalysisPacket[]
  // Role vocabulary served by the backend (single source of truth).
  canonical_roles?: string[]
}

export type MetricsPreview = {
  sources: Record<string, { label: string; count: number }>
  notes: string[]
  total: number
}

// --- Sessions ---
export const listAnalysisSessions = () => api.get<AnalysisSession[]>('/analysis-pilot/pilot/sessions')
export const createAnalysisSession = (body: { title: string; domain?: string; goal?: string }) =>
  api.post<AnalysisSession>('/analysis-pilot/pilot/sessions', body)
export const getAnalysisSession = (id: string) =>
  api.get<AnalysisSession>(`/analysis-pilot/pilot/sessions/${id}`)
export const updateAnalysisSession = (
  id: string,
  body: { title?: string; goal?: string; status?: SessionStatus },
) => api.patch<AnalysisSession>(`/analysis-pilot/pilot/sessions/${id}`, body)

// --- Datasets ---
export const uploadDataset = (sessionId: string, file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<AnalysisDataset>(`/analysis-pilot/pilot/sessions/${sessionId}/datasets`, fd)
}
export const patchDataset = (
  sessionId: string,
  datasetId: string,
  body: {
    mapping?: Record<string, string>
    column_kinds?: Record<string, 'level' | 'returns'>
    periods_per_year?: number
    risk_free?: number
    kind?: string
    extraction?: Extraction
    // Tabular only: override the layout heuristic (re-parses the stored file).
    orientation?: 'columns' | 'rows'
    // PDF only: re-run the Gemini extraction (recovery after a failed upload).
    reextract?: boolean
  },
) => api.patch<AnalysisDataset>(`/analysis-pilot/pilot/sessions/${sessionId}/datasets/${datasetId}`, body)
export const deleteDataset = (sessionId: string, datasetId: string) =>
  api.delete<{ deleted: boolean }>(`/analysis-pilot/pilot/sessions/${sessionId}/datasets/${datasetId}`)

// --- Comparisons ---
export const createComparison = (
  sessionId: string,
  body: { title: string; dataset_ids: string[]; spec?: Record<string, unknown> },
) => api.post<AnalysisComparison>(`/analysis-pilot/pilot/sessions/${sessionId}/comparisons`, body)

// --- Corpus preview ---
export const getAnalysisMetrics = (sessionId: string) =>
  api.get<MetricsPreview>(`/analysis-pilot/pilot/sessions/${sessionId}/metrics`)

// --- Report ---
export const generateReport = (
  sessionId: string,
  body: { comparison_id?: string } = {},
) => api.post<AnalysisPacket>(`/analysis-pilot/pilot/sessions/${sessionId}/report`, body)
export const downloadPacket = (sessionId: string, packet: AnalysisPacket) =>
  api.download(`/analysis-pilot/pilot/sessions/${sessionId}/packets/${packet.id}/download`, packet.filename)

// --- Grounded chat (SSE) ---
export type ChatResult = {
  assistant_text: string
  evidence_map: Array<{ point: string; cited_ids: string[] }>
  open_questions: string[]
  dropped_citations?: string[]
  proposed_edits?: ProposedEdit[]
  dropped_edits?: unknown[]
}
export type ChatHandlers = {
  onStatus?: (message: string) => void
  onResult?: (data: ChatResult) => void
  onError?: (message: string) => void
}

export async function streamChat(
  sessionId: string,
  message: string,
  h: ChatHandlers,
  signal?: AbortSignal,
  focus?: string[],
): Promise<void> {
  let res: Response
  try {
    res = await fetch(`${BASE}/analysis-pilot/pilot/sessions/${sessionId}/chat`, {
      method: 'POST',
      headers: await authStreamHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(focus && focus.length ? { message, focus } : { message }),
      signal,
    })
  } catch {
    if (signal?.aborted) return
    h.onError?.('Chat failed — please try again.')
    return
  }
  if (!res.ok || !res.body) {
    // Surface the backend's message (e.g. the session conversation-limit cap)
    // instead of a bare status code.
    let detail = ''
    try {
      const body = await res.json()
      detail = typeof body?.detail === 'string' ? body.detail : ''
    } catch {
      /* non-JSON error body */
    }
    h.onError?.(detail || `Chat failed (${res.status})`)
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
  } catch {
    if (signal?.aborted) return
    h.onError?.('Chat connection dropped — please try again.')
  }
}
