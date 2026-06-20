// Labor Relations API client — CBA store, clause library, grievance workflow.
// Typed wrappers over the `/labor/*` backend (gated by `labor_relations`).

import { api } from './client'

const BASE = (import.meta.env.VITE_API_URL as string | undefined) || '/api'

// ── Types ────────────────────────────────────────────────────────────────────

export type CBAStatus = 'draft' | 'active' | 'expired' | 'superseded' | 'in_negotiation'
export type ExtractionStatus = 'pending' | 'processing' | 'complete' | 'failed' | 'skipped'
export type DayBasis = 'calendar' | 'working'

export type ClauseCategory =
  | 'wages' | 'hours' | 'seniority' | 'grievance_procedure' | 'discipline' | 'just_cause'
  | 'overtime' | 'benefits' | 'union_security' | 'management_rights' | 'health_safety'
  | 'layoff_recall' | 'holidays_leave' | 'other'

export type GrievanceType =
  | 'discipline' | 'discharge' | 'contract_interpretation' | 'pay_wages' | 'seniority'
  | 'overtime' | 'working_conditions' | 'health_safety' | 'management_rights'
  | 'past_practice' | 'other'

export type GrievanceStatus =
  | 'draft' | 'filed' | 'in_progress' | 'advanced' | 'resolved' | 'withdrawn'
  | 'denied' | 'arbitration' | 'settled'

export type GrievanceResolution =
  | 'granted' | 'denied' | 'partially_granted' | 'withdrawn' | 'settled'
  | 'arbitrated_win' | 'arbitrated_loss'

export type StepStatus =
  | 'pending' | 'active' | 'responded' | 'advanced' | 'resolved' | 'skipped' | 'missed_deadline'

export type StepOutcome = 'granted' | 'denied' | 'partially_granted' | 'advanced'

export type GrievanceStepConfigItem = {
  step: number
  name: string
  file_within_days: number
  respond_within_days: number
  day_basis: DayBasis
}

export type CBA = {
  id: string
  company_id: string
  union_name: string
  union_local: string | null
  bargaining_unit_desc: string | null
  effective_date: string | null
  expiration_date: string | null
  status: CBAStatus
  document_filename: string | null
  document_storage_path?: string | null
  extracted_text?: string | null
  extraction_status: ExtractionStatus
  renewal_alert_days: number
  grievance_steps_confirmed: boolean
  grievance_step_config?: GrievanceStepConfigItem[]
  created_at: string
  updated_at: string
}

export type Clause = {
  id: string
  cba_id: string
  article_number: string | null
  title: string | null
  clause_text: string
  category: ClauseCategory | null
  source: 'manual' | 'ai_extracted'
  ai_confidence: number | null
  sort_order: number
}

export type CBADetail = CBA & { clauses: Clause[] }

export type GrievanceStep = {
  id: string
  step_number: number
  step_name: string
  status: StepStatus
  filed_at: string | null
  deadline_to_respond: string | null
  deadline_to_advance: string | null
  response_received_at: string | null
  management_response: string | null
  union_position: string | null
  outcome: StepOutcome | null
  deadline_alert_sent: boolean
}

export type EmployeeRef = {
  id: string
  first_name: string | null
  last_name: string | null
  job_title?: string | null
  department?: string | null
}

export type Grievance = {
  id: string
  grievance_number: string
  title: string
  description: string | null
  status: GrievanceStatus
  grievance_type: GrievanceType | null
  current_step: number
  cba_id: string | null
  grievant_employee_id: string | null
  is_class_grievance: boolean
  steward_employee_id: string | null
  steward_name_external: string | null
  incident_date: string | null
  filed_date: string | null
  resolution: GrievanceResolution | null
  resolution_summary: string | null
  resolved_at: string | null
  assigned_to: string | null
  documents?: Array<Record<string, unknown>>
  created_at: string
  updated_at: string
  grievant_first_name?: string | null
  grievant_last_name?: string | null
}

export type GrievanceDetail = Grievance & {
  steps: GrievanceStep[]
  violated_clauses: Clause[]
  grievant: EmployeeRef | null
  cba: Pick<CBA, 'id' | 'union_name' | 'union_local' | 'status' | 'grievance_steps_confirmed'> | null
  used_fallback_steps?: boolean
}

export type GrievanceDashboard = {
  by_status: Record<string, number>
  by_step: Record<string, number>
  overdue: Array<{
    id: string
    grievance_number: string
    title: string
    current_step: number
    step_number: number
    step_name: string
    deadline_to_respond: string
  }>
  expiring_cbas: Array<{ id: string; union_name: string; expiration_date: string }>
}

// ── CBA + clauses ────────────────────────────────────────────────────────────

export const laborApi = {
  listCbas: (status?: CBAStatus) =>
    api.get<{ cbas: CBA[] }>(`/labor/cbas${status ? `?status=${status}` : ''}`),
  createCba: (body: Partial<CBA> & { union_name: string }) => api.post<CBA>('/labor/cbas', body),
  getCba: (id: string) => api.get<CBADetail>(`/labor/cbas/${id}`),
  updateCba: (id: string, body: Record<string, unknown>) => api.patch<CBA>(`/labor/cbas/${id}`, body),
  deleteCba: (id: string) => api.delete<void>(`/labor/cbas/${id}`),
  uploadCbaDocument: (id: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.upload<CBA>(`/labor/cbas/${id}/document`, fd)
  },
  getCbaDocumentUrl: (id: string) =>
    api.get<{ url: string; filename: string | null }>(`/labor/cbas/${id}/document`),
  extractClauses: (id: string) =>
    api.post<{ status: string; cba_id: string }>(`/labor/cbas/${id}/extract-clauses`),
  listClauses: (id: string) => api.get<{ clauses: Clause[] }>(`/labor/cbas/${id}/clauses`),
  createClause: (cbaId: string, body: Partial<Clause> & { clause_text: string }) =>
    api.post<Clause>(`/labor/cbas/${cbaId}/clauses`, body),
  updateClause: (cbaId: string, clauseId: string, body: Record<string, unknown>) =>
    api.patch<Clause>(`/labor/cbas/${cbaId}/clauses/${clauseId}`, body),
  deleteClause: (cbaId: string, clauseId: string) =>
    api.delete<void>(`/labor/cbas/${cbaId}/clauses/${clauseId}`),

  // ── Grievances ─────────────────────────────────────────────────────────────
  listGrievances: (params?: {
    status?: GrievanceStatus
    grievance_type?: GrievanceType
    employee_id?: string
    cba_id?: string
    overdue?: boolean
  }) => {
    const q = new URLSearchParams()
    if (params?.status) q.set('status', params.status)
    if (params?.grievance_type) q.set('grievance_type', params.grievance_type)
    if (params?.employee_id) q.set('employee_id', params.employee_id)
    if (params?.cba_id) q.set('cba_id', params.cba_id)
    if (params?.overdue) q.set('overdue', 'true')
    const qs = q.toString()
    return api.get<{ grievances: Grievance[] }>(`/labor/grievances${qs ? `?${qs}` : ''}`)
  },
  dashboard: () => api.get<GrievanceDashboard>('/labor/grievances/dashboard'),
  createGrievance: (body: Record<string, unknown>) =>
    api.post<GrievanceDetail>('/labor/grievances', body),
  getGrievance: (id: string) => api.get<GrievanceDetail>(`/labor/grievances/${id}`),
  updateGrievance: (id: string, body: Record<string, unknown>) =>
    api.patch<GrievanceDetail>(`/labor/grievances/${id}`, body),
  fileGrievance: (id: string) => api.post<GrievanceDetail>(`/labor/grievances/${id}/file`),
  respondStep: (id: string, stepNumber: number, body: Record<string, unknown>) =>
    api.post<GrievanceDetail>(`/labor/grievances/${id}/steps/${stepNumber}/respond`, body),
  advanceGrievance: (id: string, body?: Record<string, unknown>) =>
    api.post<GrievanceDetail>(`/labor/grievances/${id}/advance`, body ?? {}),
  resolveGrievance: (id: string, body: { resolution: GrievanceResolution; resolution_summary?: string }) =>
    api.post<GrievanceDetail>(`/labor/grievances/${id}/resolve`, body),
  withdrawGrievance: (id: string, body?: { reason?: string }) =>
    api.post<GrievanceDetail>(`/labor/grievances/${id}/withdraw`, body ?? {}),
  setViolatedClauses: (id: string, clauseIds: string[]) =>
    api.post<GrievanceDetail>(`/labor/grievances/${id}/clauses`, { clause_ids: clauseIds }),
  auditLog: (id: string) =>
    api.get<{ audit_log: Array<Record<string, unknown>> }>(`/labor/grievances/${id}/audit-log`),
  uploadGrievanceDocument: (id: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.upload<GrievanceDetail>(`/labor/grievances/${id}/documents`, fd)
  },
  getGrievanceDocumentUrl: (id: string, docId: string) =>
    api.get<{ url: string; filename: string | null }>(`/labor/grievances/${id}/documents/${docId}/url`),
}

// ── Merit assessment (SSE stream) ────────────────────────────────────────────

export async function streamGrievanceMerit(
  grievanceId: string,
  handlers: { onDelta: (text: string) => void; onError?: (msg: string) => void; signal?: AbortSignal },
): Promise<void> {
  const token = localStorage.getItem('matcha_access_token')
  const res = await fetch(`${BASE}/labor/grievances/${grievanceId}/assess-merit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    signal: handlers.signal,
  })
  if (!res.ok || !res.body) {
    handlers.onError?.(`Assessment failed (${res.status})`)
    return
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''
    for (const ev of events) {
      const line = ev.trim()
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6)
      if (payload === '[DONE]') return
      try {
        const obj = JSON.parse(payload) as { delta?: string; error?: string }
        if (obj.error) handlers.onError?.(obj.error)
        else if (obj.delta) handlers.onDelta(obj.delta)
      } catch {
        // ignore malformed keep-alive lines
      }
    }
  }
}
