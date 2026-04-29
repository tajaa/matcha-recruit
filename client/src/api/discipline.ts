import { api } from './client'

export type DisciplineSeverity = 'minor' | 'moderate' | 'severe' | 'immediate_written'
export type DisciplineLevel =
  | 'verbal_warning'
  | 'written_warning'
  | 'pip'
  | 'final_warning'
  | 'suspension'
export type DisciplineStatus =
  | 'draft'
  | 'pending_meeting'
  | 'pending_signature'
  | 'active'
  | 'completed'
  | 'expired'
  | 'escalated'
export type DisciplineSignatureStatus =
  | 'pending'
  | 'requested'
  | 'signed'
  | 'refused'
  | 'physical_uploaded'

export type DisciplineRecord = {
  id: string
  employee_id: string
  company_id: string
  discipline_type: DisciplineLevel
  issued_date: string
  issued_by: string
  description: string | null
  expected_improvement: string | null
  review_date: string | null
  status: DisciplineStatus
  outcome_notes: string | null
  documents: unknown[]
  infraction_type: string
  severity: DisciplineSeverity
  lookback_months: number
  expires_at: string | null
  escalated_from_id: string | null
  override_level: boolean
  override_reason: string | null
  signature_status: DisciplineSignatureStatus
  signature_requested_at: string | null
  signature_completed_at: string | null
  signature_envelope_id: string | null
  signed_pdf_storage_path: string | null
  meeting_held_at: string | null
  created_at: string
  updated_at: string
}

export type DisciplineRecommendation = {
  recommended_level: DisciplineLevel
  termination_review: boolean
  reasoning: { text: string; discipline_id?: string }[]
  supersedes: string[]
  lookback_months: number
  expires_at_preview: string
  override_available: boolean
  auto_to_written_triggered: boolean
  policy_mapping: {
    infraction_type: string
    label: string
    default_severity: DisciplineSeverity
    auto_to_written: boolean
    notify_grandparent_manager: boolean
  }
}

export type DisciplinePolicy = {
  id: string
  company_id: string
  infraction_type: string
  label: string
  default_severity: DisciplineSeverity
  lookback_months_minor: number
  lookback_months_moderate: number
  lookback_months_severe: number
  auto_to_written: boolean
  notify_grandparent_manager: boolean
  created_at: string
  updated_at: string
}

export type DisciplineAuditEntry = {
  id: string
  discipline_id: string
  actor_user_id: string | null
  action: string
  details: Record<string, unknown>
  created_at: string
}

export type DisciplineRecommendInput = {
  employee_id: string
  infraction_type: string
  severity: DisciplineSeverity
}

export type DisciplineIssueInput = DisciplineRecommendInput & {
  discipline_type: DisciplineLevel
  issued_date: string
  description?: string
  expected_improvement?: string
  review_date?: string
  documents?: unknown[]
  override_level?: boolean
  override_reason?: string
}

export type DisciplinePolicyUpsertInput = {
  label?: string
  default_severity?: DisciplineSeverity
  lookback_months_minor?: number
  lookback_months_moderate?: number
  lookback_months_severe?: number
  auto_to_written?: boolean
  notify_grandparent_manager?: boolean
}

export const disciplineApi = {
  recommend: (input: DisciplineRecommendInput) =>
    api.post<DisciplineRecommendation>('/discipline/recommend', input),

  issue: (input: DisciplineIssueInput) =>
    api.post<DisciplineRecord>('/discipline/records', input),

  list: (status?: DisciplineStatus) => {
    const qs = status ? `?status=${encodeURIComponent(status)}` : ''
    return api.get<DisciplineRecord[]>(`/discipline/records${qs}`)
  },

  listForEmployee: (employeeId: string) =>
    api.get<DisciplineRecord[]>(`/discipline/records/employee/${employeeId}`),

  get: (recordId: string) => api.get<DisciplineRecord>(`/discipline/records/${recordId}`),

  auditLog: (recordId: string) =>
    api.get<DisciplineAuditEntry[]>(`/discipline/records/${recordId}/audit-log`),

  markMeetingHeld: (recordId: string) =>
    api.patch<DisciplineRecord>(`/discipline/records/${recordId}/meeting-held`),

  requestSignature: (recordId: string) =>
    api.post<DisciplineRecord>(`/discipline/records/${recordId}/signature/request`),

  refuse: (recordId: string, notes: string) =>
    api.post<DisciplineRecord>(`/discipline/records/${recordId}/signature/refuse`, { notes }),

  uploadPhysical: (recordId: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.upload<DisciplineRecord>(
      `/discipline/records/${recordId}/signature/upload-physical`,
      fd,
    )
  },

  downloadLetter: (recordId: string) =>
    api.download(`/discipline/records/${recordId}/letter`, `discipline-${recordId}.pdf`),

  listPolicies: () => api.get<DisciplinePolicy[]>('/discipline/policies'),

  upsertPolicy: (infractionType: string, body: DisciplinePolicyUpsertInput) =>
    api.put<DisciplinePolicy>(`/discipline/policies/${encodeURIComponent(infractionType)}`, body),
}
