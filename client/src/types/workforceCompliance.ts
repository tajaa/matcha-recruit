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
  // A measured protected-class pay gap, or null when none was measured. Distinct
  // from dispersion_pct (within-role spread, which seniority can explain) — the two
  // used to share this field, so a "40% gap" was often 40% of roles showing spread.
  gap_pct: number | null
  dispersion_pct: number | null
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

export type PayEquityPostureBand = 'equitable' | 'watch' | 'action' | 'insufficient'

export interface PayEquityPosture {
  band: PayEquityPostureBand
  label: string
}

// One ranked "fix first" item — the actionable layer over the per-role table.
export interface PayEquityPriorityAction {
  title: string
  severity: PayEquitySeverity
  below_band_n: number
  remediation_cost: number
  spread_pct: number
  action: string
}

// One role's protected-class comparison. Only classes with n ≥ min_class_cell appear;
// smaller cells are counted in suppressed_n and never named.
export interface PayEquityClassGap {
  title: string
  gap_pct: number
  reference: string
  lowest: string
  n: number
  classes: { class: string; n: number; median: number }[]
  suppressed_n: number
}

// Full result of the pay-equity engine (pay_equity_analysis.analyze).
export interface PayEquityAnalysisResult {
  employee_count: number
  analyzed_roles: number
  flagged_roles: number
  headline_gap_pct: number
  // null = not measured (no/insufficient HRIS demographics), never 0 — "we didn't
  // look" and "we looked and found parity" must stay distinguishable.
  class_gap_pct: number | null
  class_gaps: PayEquityClassGap[]
  demographics_coverage_pct: number
  class_gap_measurable: boolean
  min_class_cell: number
  worst: PayEquityRole | null
  roles: PayEquityRole[]
  total_payroll: number
  median_spread_pct: number
  employees_below_band: number
  flagged_payroll_pct: number
  remediation_estimate: number
  band_floor_pct: number
  posture: PayEquityPosture
  priority_actions: PayEquityPriorityAction[]
}

export interface WorkforceSummary {
  ai_audits: { total: number; overdue: number }
  biometric: { active: number; missing_consent: number }
  pay_equity: { total: number; overdue: number }
  pay_transparency: { required_states: number; action_needed: number }
}
