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

export interface PayEquityReview {
  id: string
  company_id: string
  review_date: string | null
  scope: string | null
  methodology: string | null
  gap_pct: number | null
  remediation: string | null
  cadence_days: number
  next_due_date: string | null
  is_overdue: boolean
  notes: string | null
  created_at: string
}

export type PayEquitySeverity = 'flag' | 'watch' | 'ok'

export interface PayEquityRole {
  title: string
  n: number
  median: number
  min: number
  max: number
  p25: number
  p75: number
  spread_pct: number
  iqr_pct: number
  range_ratio: number | null
  below_band_n: number
  remediation_cost: number
  severity: PayEquitySeverity
}

// Full result of the within-role dispersion engine (pay_equity_analysis.analyze).
export interface PayEquityAnalysisResult {
  employee_count: number
  analyzed_roles: number
  flagged_roles: number
  headline_gap_pct: number
  worst: PayEquityRole | null
  roles: PayEquityRole[]
  total_payroll: number
  median_spread_pct: number
  employees_below_band: number
  flagged_payroll_pct: number
  remediation_estimate: number
  band_floor_pct: number
}

export interface WorkforceSummary {
  ai_audits: { total: number; overdue: number }
  biometric: { active: number; missing_consent: number }
  pay_equity: { total: number; overdue: number }
  pay_transparency: { required_states: number; action_needed: number }
}
