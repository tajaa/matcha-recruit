// Workforce Compliance — business-first EPL risk trackers.

export interface AiAudit {
  id: string
  company_id: string
  tool_name: string
  vendor: string | null
  purpose: string | null
  last_audit_date: string | null
  cadence_days: number
  next_due_date: string | null
  is_overdue: boolean
  notes: string | null
  created_at: string
}

export type CollectionType = 'fingerprint' | 'face' | 'iris' | 'voice' | 'hand_geometry' | 'other'
export type ConsentMethod = 'written' | 'digital' | 'verbal' | 'other'

export interface BiometricPoint {
  id: string
  company_id: string
  location_id: string | null
  collection_type: CollectionType
  purpose: string | null
  consent_obtained: boolean
  consent_obtained_date: string | null
  consent_method: ConsentMethod | null
  retention_policy: string | null
  is_active: boolean
  notes: string | null
  created_at: string
}

export type PayTransparencyStatus = 'compliant' | 'action_needed' | 'na'

export interface PayTransparencyRow {
  state: string
  required: boolean
  status: PayTransparencyStatus
  postings_include_ranges: boolean
  note: string | null
  updated_at: string | null
}

export interface WorkforceSummary {
  ai_audits: { total: number; overdue: number }
  biometric: { active: number; missing_consent: number }
  pay_transparency: { required_states: number; action_needed: number }
}
