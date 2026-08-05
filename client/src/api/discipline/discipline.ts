import { api } from '../client'

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
  | 'denied'
export type DisciplineApprovalStatus =
  | 'not_required'
  | 'pending'
  | 'approved'
  | 'denied'
  | 'changes_requested'
export type DenyDisposition = 'reject' | 'revise'
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
  remedial_requirement_id: string | null
  approval_status: DisciplineApprovalStatus
  approval_requested_at: string | null
  approved_by: string | null
  approval_decided_at: string | null
  denial_reason: string | null
  source_incident_id: string | null
  template_id: string | null
  pending_remedial_requirement_id: string | null
  created_at: string
  updated_at: string
  /** Only present on GET /discipline/records/{id} — the linked training
   *  record's current status, when remedial_requirement_id was set at issue. */
  remedial_training?: {
    id: string
    status: string
    due_date: string | null
    completed_date: string | null
  } | null
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
  /** Present only when a company template resolved for this infraction —
   *  see discipline_templates.resolve_template. `rendered_body` is the
   *  template's body rendered over this draft's own field values;
   *  `missing_fields` lists known placeholders that had nothing to fill
   *  them (e.g. no manager on file) so the caller can flag a gap rather
   *  than silently ship a blank clause. */
  template_id?: string
  template_name?: string
  rendered_body?: string
  missing_fields?: string[]
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
  /** Optional remedial training assigned in the same transaction as issuance. */
  remedial_requirement_id?: string
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

/** Closed vocabulary rendered server-side — see
 *  discipline_templates.DISCIPLINE_TEMPLATE_PLACEHOLDERS. An unrecognized
 *  {{token}} survives verbatim in the rendered letter rather than being
 *  silently blanked. */
export const DISCIPLINE_TEMPLATE_PLACEHOLDERS = [
  'employee_name', 'employee_title', 'manager_name', 'company_name', 'issued_date',
  'infraction_type', 'discipline_type', 'occurrence_dates', 'incident_number',
  'policy_citations', 'description', 'expected_improvement', 'review_date',
] as const

export type DisciplineTemplate = {
  id: string
  company_id: string
  name: string
  infraction_type: string | null
  discipline_type: DisciplineLevel | null
  body: string
  is_default: boolean
  is_active: boolean
  created_by: string | null
  created_at: string
  updated_at: string
}

export type DisciplineTemplateUpsertInput = {
  name: string
  infraction_type?: string | null
  discipline_type?: DisciplineLevel | null
  body: string
  is_default?: boolean
  is_active?: boolean
}

export type DisciplineApprover = {
  user_id: string
  email: string
  name: string
  is_hr_approver: boolean
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

  list: (status?: DisciplineStatus, approvalStatus?: DisciplineApprovalStatus) => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (approvalStatus) params.set('approval_status', approvalStatus)
    const qs = params.toString()
    return api.get<DisciplineRecord[]>(`/discipline/records${qs ? `?${qs}` : ''}`)
  },

  pendingApprovals: () => api.get<DisciplineRecord[]>('/discipline/records/pending-approval'),

  /** Records HR sent back for revision (approval_status='changes_requested') —
   *  the sibling queue to pendingApprovals. */
  changesRequested: () => api.get<DisciplineRecord[]>('/discipline/records/changes-requested'),

  approve: (recordId: string) =>
    api.post<DisciplineRecord>(`/discipline/records/${recordId}/approve`),

  /** Throws ApiError 409 if the record isn't awaiting approval.
   *  `disposition='reject'` (default) is terminal — no un-deny. `'revise'`
   *  sends it back to the drafter, editable via `updateDraft` + resubmittable
   *  via `resubmit`. */
  deny: (recordId: string, reason: string, disposition: DenyDisposition = 'reject') =>
    api.post<DisciplineRecord>(`/discipline/records/${recordId}/deny`, { reason, disposition }),

  /** Edit a record's content — only while approval_status='changes_requested'.
   *  Throws ApiError 409 otherwise. Send only the fields being changed. */
  updateDraft: (
    recordId: string,
    fields: Partial<
      Pick<DisciplineRecord, 'description' | 'expected_improvement' | 'discipline_type' | 'severity'>
    >,
  ) => api.patch<DisciplineRecord>(`/discipline/records/${recordId}`, fields),

  /** Send a 'changes_requested' record back to HR for another decision.
   *  Throws ApiError 409 if it isn't awaiting revision. */
  resubmit: (recordId: string) =>
    api.post<DisciplineRecord>(`/discipline/records/${recordId}/resubmit`),

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

  listTemplates: (includeInactive = false) => {
    const qs = includeInactive ? '?include_inactive=true' : ''
    return api.get<DisciplineTemplate[]>(`/discipline/templates${qs}`)
  },

  createTemplate: (body: DisciplineTemplateUpsertInput) =>
    api.post<DisciplineTemplate>('/discipline/templates', body),

  updateTemplate: (templateId: string, body: DisciplineTemplateUpsertInput) =>
    api.put<DisciplineTemplate>(`/discipline/templates/${templateId}`, body),

  deleteTemplate: (templateId: string) =>
    api.delete<{ ok: boolean }>(`/discipline/templates/${templateId}`),

  listApprovers: () => api.get<DisciplineApprover[]>('/discipline/approvers'),

  setApprover: (userId: string, isHrApprover: boolean) =>
    api.put<{ user_id: string; is_hr_approver: boolean }>(`/discipline/approvers/${userId}`, {
      is_hr_approver: isHrApprover,
    }),
}
