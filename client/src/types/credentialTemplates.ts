export type CredentialType = {
  id: string
  key: string
  label: string
  category: string
  description: string | null
  has_expiration: boolean
  has_number: boolean
  has_state: boolean
  is_system: boolean
}

export type RoleCategory = {
  id: string
  key: string
  label: string
  is_clinical: boolean
  sort_order: number
}

export type CredentialRequirementTemplate = {
  id: string
  company_id: string | null
  state: string
  city: string | null
  role_category_id: string
  credential_type_id: string
  is_required: boolean
  due_days: number
  priority: string
  notes: string | null
  source: string
  ai_confidence: number | null
  review_status: string
  reviewed_by: string | null
  reviewed_at: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  // Joined fields
  ct_key?: string
  ct_label?: string
  ct_category?: string
  role_key?: string
  role_label?: string
}

export type CredentialResearchLog = {
  id: string
  company_id: string | null
  state: string
  city: string | null
  role_category_id: string | null
  status: string
  template_count: number
  ai_model: string | null
  error_message: string | null
  started_at: string
  completed_at: string | null
  role_label?: string
}

export type EmployeeCredentialRequirement = {
  id: string
  employee_id: string
  credential_type_id: string
  template_id: string | null
  status: 'pending' | 'submitted' | 'verified' | 'expired' | 'waived' | 'not_applicable'
  is_required: boolean
  priority: string
  due_date: string | null
  onboarding_task_id: string | null
  credential_document_id: string | null
  verified_at: string | null
  waived_at: string | null
  waiver_reason: string | null
  notes: string | null
  created_at: string
  // Joined fields
  credential_type_key: string
  credential_type_label: string
  credential_type_category: string
  has_expiration: boolean
  has_number: boolean
  has_state: boolean
}

export type PreviewResult = {
  role_category: RoleCategory | null
  state: string
  city: string | null
  job_title: string
  requirements: {
    credential_type_key: string
    credential_type_label: string
    is_required: boolean
    due_days: number
    priority: string
    notes: string | null
    source: string
  }[]
}

export const PRIORITY_COLORS: Record<string, string> = {
  blocking: 'text-red-400',
  standard: 'text-amber-400',
  optional: 'text-zinc-500',
}

export const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-amber-500/20 text-amber-400',
  approved: 'bg-emerald-500/20 text-emerald-400',
  auto_approved: 'bg-emerald-500/20 text-emerald-400',
  rejected: 'bg-red-500/20 text-red-400',
}

export const REQUIREMENT_STATUS_COLORS: Record<string, string> = {
  pending: 'bg-amber-500/20 text-amber-400',
  submitted: 'bg-blue-500/20 text-blue-400',
  verified: 'bg-emerald-500/20 text-emerald-400',
  expired: 'bg-red-500/20 text-red-400',
  waived: 'bg-zinc-500/20 text-zinc-400',
  not_applicable: 'bg-zinc-500/20 text-zinc-500',
}
