// Handbook types — mirrors server/app/core/models/handbook.py

export type HandbookStatus = 'draft' | 'active' | 'archived'
export type HandbookMode = 'single_state' | 'multi_state'
export type HandbookSourceType = 'template' | 'upload'
export type HandbookSectionType = 'core' | 'state' | 'custom' | 'uploaded'
export type HandbookChangeStatus = 'pending' | 'accepted' | 'rejected'

export type WorkbookType =
  | 'clinical_patient_care'
  | 'infection_control'
  | 'hipaa_privacy'
  | 'safety_emergency'
  | 'human_resources'
  | 'administrative_operations'
  | 'compliance_regulatory'
  | 'financial_billing'
  | 'operations'
  | 'safety_compliance'
  | 'it_security'
  | 'finance'
  | 'general'

export const HEALTHCARE_WORKBOOK_TYPES: WorkbookType[] = [
  'clinical_patient_care',
  'infection_control',
  'hipaa_privacy',
  'safety_emergency',
  'human_resources',
  'administrative_operations',
  'compliance_regulatory',
  'financial_billing',
]

export const GENERAL_WORKBOOK_TYPES: WorkbookType[] = [
  'human_resources',
  'operations',
  'safety_compliance',
  'it_security',
  'finance',
  'general',
]

export const WORKBOOK_TYPE_LABELS: Record<WorkbookType, string> = {
  clinical_patient_care: 'Clinical / Patient Care',
  infection_control: 'Infection Control',
  hipaa_privacy: 'HIPAA & Privacy',
  safety_emergency: 'Safety & Emergency',
  human_resources: 'Human Resources',
  administrative_operations: 'Administrative / Operations',
  compliance_regulatory: 'Compliance & Regulatory',
  financial_billing: 'Financial / Billing',
  operations: 'Operations',
  safety_compliance: 'Safety & Compliance',
  it_security: 'IT & Security',
  finance: 'Finance',
  general: 'General',
}

export type HandbookScope = {
  id: string
  state: string
  city: string | null
  zipcode: string | null
  location_id: string | null
}

export type HandbookScopeInput = {
  state: string
  city?: string | null
  zipcode?: string | null
  location_id?: string | null
}

export type HandbookSection = {
  id: string
  section_key: string
  title: string
  content: string
  section_order: number
  section_type: HandbookSectionType
  jurisdiction_scope: Record<string, unknown>
  last_reviewed_at: string | null
}

export type HandbookSectionInput = {
  section_key: string
  title: string
  content: string
  section_order: number
  section_type: HandbookSectionType
  jurisdiction_scope?: Record<string, unknown> | null
}

export type CompanyHandbookProfile = {
  company_id: string
  legal_name: string
  dba: string | null
  ceo_or_president: string
  headcount: number | null
  remote_workers: boolean
  minors: boolean
  tipped_employees: boolean
  union_employees: boolean
  federal_contracts: boolean
  group_health_insurance: boolean
  background_checks: boolean
  hourly_employees: boolean
  salaried_employees: boolean
  commissioned_employees: boolean
  tip_pooling: boolean
  updated_by: string | null
  updated_at: string
}

export type CompanyHandbookProfileInput = {
  legal_name: string
  dba?: string | null
  ceo_or_president: string
  headcount?: number | null
  remote_workers: boolean
  minors: boolean
  tipped_employees: boolean
  union_employees: boolean
  federal_contracts: boolean
  group_health_insurance: boolean
  background_checks: boolean
  hourly_employees: boolean
  salaried_employees: boolean
  commissioned_employees: boolean
  tip_pooling: boolean
}

export type HandbookListItem = {
  id: string
  title: string
  status: HandbookStatus
  mode: HandbookMode
  source_type: HandbookSourceType
  active_version: number
  workbook_type: WorkbookType | null
  scope_states: string[]
  pending_changes_count: number
  updated_at: string
  published_at: string | null
  created_at: string
}

export type HandbookDetail = {
  id: string
  company_id: string
  title: string
  status: HandbookStatus
  mode: HandbookMode
  source_type: HandbookSourceType
  active_version: number
  workbook_type: WorkbookType | null
  file_url: string | null
  file_name: string | null
  scopes: HandbookScope[]
  profile: CompanyHandbookProfile
  sections: HandbookSection[]
  created_at: string
  updated_at: string
  published_at: string | null
  created_by: string | null
}

export type HandbookCreate = {
  title: string
  mode: HandbookMode
  source_type: HandbookSourceType
  industry?: string | null
  scopes: HandbookScopeInput[]
  profile: CompanyHandbookProfileInput
  custom_sections?: HandbookSectionInput[]
  guided_answers?: Record<string, string>
  file_url?: string | null
  file_name?: string | null
  create_from_template?: boolean
  auto_scope_from_employees?: boolean
  workbook_type?: WorkbookType | null
}

export type HandbookUpdate = {
  title?: string | null
  mode?: HandbookMode | null
  scopes?: HandbookScopeInput[] | null
  profile?: CompanyHandbookProfileInput | null
  sections?: HandbookSectionInput[] | null
  file_url?: string | null
  file_name?: string | null
  workbook_type?: WorkbookType | null
}

export type HandbookChangeRequest = {
  id: string
  handbook_id: string
  handbook_version_id: string
  alert_id: string | null
  section_key: string | null
  old_content: string | null
  proposed_content: string
  rationale: string | null
  source_url: string | null
  effective_date: string | null
  status: HandbookChangeStatus
  resolved_by: string | null
  resolved_at: string | null
  created_at: string
}

export type HandbookDistributionResult = {
  handbook_id: string
  handbook_version: number
  assigned_count: number
  skipped_existing_count: number
  distributed_at: string
}

export type HandbookDistributionRecipient = {
  employee_id: string
  name: string
  email: string
  invitation_status: string | null
  already_assigned: boolean
}

export type HandbookAcknowledgementSummary = {
  handbook_id: string
  handbook_version: number
  assigned_count: number
  signed_count: number
  pending_count: number
  expired_count: number
}

export type HandbookFreshnessFinding = {
  section_key: string | null
  finding_type: string
  summary: string
  change_request_id: string | null
  source_url: string | null
  effective_date: string | null
  age_days: number | null
}

export type HandbookFreshnessCheck = {
  check_id: string
  handbook_id: string
  check_type: 'manual' | 'scheduled'
  status: 'running' | 'completed' | 'failed'
  is_outdated: boolean
  impacted_sections: number
  new_change_requests_count: number
  requirements_last_updated_at: string | null
  data_staleness_days: number | null
  current_fingerprint: string | null
  previous_fingerprint: string | null
  checked_at: string
  findings: HandbookFreshnessFinding[]
}

export type HandbookCoverageByState = {
  state: string
  state_name: string
  has_addendum: boolean
  covered_categories: string[]
  missing_categories: string[]
  city_scopes: string[]
}

export type HandbookMissingSection = {
  section_key: string
  title: string
  reason: string
  priority: string
}

export type HandbookCoverage = {
  handbook_id: string
  strength_score: number
  strength_label: string
  total_sections: number
  core_sections: number
  state_sections: number
  custom_sections: number
  uploaded_sections: number
  federal_core_count: number
  state_level_count: number
  city_level_count: number
  state_coverage: HandbookCoverageByState[]
  missing_sections: HandbookMissingSection[]
  industry: string
  industry_label: string
}

export type HandbookGuidedQuestion = {
  id: string
  question: string
  placeholder: string | null
  required: boolean
}

export type HandbookGuidedSectionSuggestion = {
  section_key: string
  title: string
  content: string
  section_order: number
  section_type: HandbookSectionType
  jurisdiction_scope: Record<string, unknown>
}

export type HandbookGuidedDraftRequest = {
  title?: string | null
  mode: HandbookMode
  scopes: HandbookScopeInput[]
  profile: CompanyHandbookProfileInput
  industry?: string | null
  answers: Record<string, string>
  existing_custom_sections?: HandbookGuidedSectionSuggestion[]
}

export type HandbookGuidedDraftResponse = {
  industry: string
  summary: string
  clarification_needed: boolean
  questions: HandbookGuidedQuestion[]
  profile_updates: Record<string, unknown>
  suggested_sections: HandbookGuidedSectionSuggestion[]
}

export type HandbookWizardDraftState = Record<string, unknown>

export type HandbookWizardDraft = {
  id: string
  company_id: string
  user_id: string
  state: HandbookWizardDraftState
  created_at: string
  updated_at: string
}

export type HandbookPublishResponse = {
  id: string
  status: HandbookStatus
  active_version: number
  published_at: string | null
}
