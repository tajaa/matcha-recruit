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
  occurrence_dates: string[]
  compliance_check: ComplianceVerdict | null
  advisory_ack_reason: string | null
  situation_narrative: string | null
  created_at: string
  updated_at: string
}

/** A statutory prohibition on this discipline. Not overridable — the server
 *  refuses the write (422) regardless of what the client sends. */
export type ComplianceBlock = {
  code: 'protected_leave_overlap'
  statute: string
  state: string
  detail: string
  source: string
  record_id: string
  dates: string[]
}

/** A risk HR should weigh, not a prohibition. Proceeding requires a logged reason. */
export type ComplianceAdvisory = {
  code:
    | 'leave_overlap_unmapped_state'
    | 'leave_overlap_non_attendance'
    | 'retaliation_timing'
    | 'unmapped_state'
    | 'ai_review'
    | 'ai_review_unavailable'
  detail: string
  source?: string
  record_id?: string | null
  dates?: string[]
  cited_ids?: string[]
}

export type ComplianceVerdict = {
  version: number
  checked_at: string
  work_state: string | null
  state_row: { state: string; statute: string; protection: string; note: string } | null
  blocks: ComplianceBlock[]
  advisories: ComplianceAdvisory[]
}

export type DisciplineDraft = {
  description: string
  expected_improvement: string
  suggested_infraction_type: string | null
  suggested_severity: DisciplineSeverity | null
  evidence_map: { point: string; cited_ids: string[] }[]
  dropped_citations: string[]
  concerns: string[]
  available: boolean
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
  /** When the conduct happened — not when the letter was written. The
   *  compliance gate tests these against protected leave. */
  occurrence_dates?: string[]
  situation?: string
  advisory_ack_reason?: string
}

export type DisciplineDraftInput = {
  employee_id: string
  situation: string
  infraction_type?: string
  severity?: DisciplineSeverity
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

  /** Preview only. `issue` re-runs the same check server-side and is what
   *  actually decides — a stale preview can never let a block through. */
  complianceCheck: (employeeId: string, infractionType: string, occurrenceDates: string[]) => {
    const qs = new URLSearchParams({
      employee_id: employeeId,
      infraction_type: infractionType,
      occurrence_dates: occurrenceDates.join(','),
    })
    return api.get<ComplianceVerdict>(`/discipline/compliance-check?${qs}`)
  },

  draft: (input: DisciplineDraftInput) =>
    api.post<DisciplineDraft>('/discipline/ai/draft', input),

  /** Throws ApiError 422 (`compliance_block`) or 409 (`compliance_advisories`)
   *  with the verdict in `err.body.detail.verdict`. */
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
