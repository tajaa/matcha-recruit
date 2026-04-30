// ── Dashboard Stats (from /dashboard/stats) ──

export interface PendingIncident {
  id: string
  incident_number: string
  title: string
  severity: string
}

export interface ActivityItem {
  action: string
  timestamp: string
  type: 'success' | 'warning' | 'neutral'
}

export interface IncidentSummary {
  total_open: number
  critical: number
  high: number
  medium: number
  low: number
  recent_7_days: number
}

export interface WageAlertSummary {
  hourly_violations: number
  salary_violations: number
  locations_affected: number
}

export interface ERCaseSummary {
  open_cases: number
  open: number
  in_review: number
  pending_determination: number
  investigating: number
  pending_action: number
}

export interface StalePolicySummary {
  stale_count: number
  oldest_days: number
}

export type FlightRiskTier = 'high' | 'medium' | 'low' | 'none'

export interface EmployeeWageGapDetail {
  employee_id: string
  name: string
  job_title: string | null
  soc_code: string
  soc_label: string
  work_city: string | null
  work_state: string | null
  pay_rate: number
  market_p50: number
  market_p25: number | null
  market_p75: number | null
  delta_dollars_per_hour: number
  delta_percent: number
  annual_cost_to_reach_p50: number
  annual_cost_to_reach_p25: number
  benchmark_tier: 'metro' | 'state' | 'national'
  benchmark_area: string
  flight_risk_tier: FlightRiskTier
}

export interface RoleRollupItem {
  soc_code: string
  soc_label: string
  headcount: number
  below_market_count: number
  median_delta_percent: number
  total_annual_cost_to_lift_to_p50: number
}

export interface WageGapDetailsResponse {
  employees: EmployeeWageGapDetail[]
  role_rollups: RoleRollupItem[]
}

export interface WageGapSummary {
  hourly_employees_count: number
  employees_evaluated: number
  employees_below_market: number
  employees_at_or_above_market: number
  employees_unclassified: number
  median_delta_percent: number | null
  dollars_per_hour_to_close_gap: number
  annual_cost_to_lift: number
  max_replacement_cost_exposure: number
}

// ── Flight-Risk (§3.3, QSR_RETENTION_PLAN.md) ──

export type FlightRiskLevel = 'low' | 'elevated' | 'high' | 'critical'

export interface ManagerHotspot {
  manager_id: string
  manager_name: string
  flagged_count: number
}

export interface FlightRiskWidgetSummary {
  employees_evaluated: number
  critical_count: number
  high_count: number
  elevated_count: number
  low_count: number
  expected_loss_at_replacement: number
  top_driver: string | null
  top_driver_count: number
  early_tenure_count: number
  manager_hotspots: ManagerHotspot[]
}

export interface FlightRiskFactor {
  name: string
  contribution: number
  color: 'green' | 'yellow' | 'red'
  narrative: string
  value: number | null
}

export interface EmployeeFlightRisk {
  employee_id: string
  name: string
  score: number
  tier: FlightRiskLevel
  top_factor: string
  factors: FlightRiskFactor[]
  expected_replacement_cost: number
}

export interface EmployeeFlightRiskList {
  employees: EmployeeFlightRisk[]
}

export interface DashboardStats {
  active_policies: number
  pending_signatures: number
  total_employees: number
  compliance_rate: number
  pending_incidents: PendingIncident[]
  recent_activity: ActivityItem[]
  incident_summary: IncidentSummary | null
  wage_alerts: WageAlertSummary | null
  wage_gap_summary: WageGapSummary | null
  flight_risk_summary: FlightRiskWidgetSummary | null
  critical_compliance_alerts: number
  warning_compliance_alerts: number
  er_case_summary: ERCaseSummary | null
  stale_policies: StalePolicySummary | null
  escalated_queries_open: number
  escalated_queries_high: number
}

// ── Credential Expirations (from /dashboard/credential-expirations) ──

export interface CredentialExpiration {
  employee_id: string
  employee_name: string
  job_title: string | null
  credential_type: string
  credential_label: string
  expiry_date: string
  severity: 'expired' | 'critical' | 'warning'
}

export interface CredentialExpirationSummary {
  expired: number
  critical: number
  warning: number
}

export interface CredentialExpirationsResponse {
  summary: CredentialExpirationSummary
  expirations: CredentialExpiration[]
}

// ── Upcoming Deadlines (from /dashboard/upcoming) ──

export interface UpcomingItem {
  category: string
  title: string
  subtitle: string | null
  date: string
  days_until: number
  severity: 'critical' | 'warning' | 'info'
  link: string
}

export interface UpcomingResponse {
  items: UpcomingItem[]
  total: number
}

// ── Escalated Queries (from /dashboard/escalated-queries) ──

export interface EscalatedQuery {
  id: string
  status: 'open' | 'in_review' | 'resolved' | 'dismissed'
  severity: 'high' | 'medium' | 'low'
  title: string
  user_query: string
  ai_reply: string | null
  ai_mode: string | null
  ai_confidence: number | null
  missing_fields: string[] | null
  resolution_note: string | null
  resolved_by: string | null
  resolved_at: string | null
  thread_id: string
  created_at: string
  updated_at: string
}

export interface EscalatedQueryDetail extends EscalatedQuery {
  thread_title: string | null
  context_messages: { id: string; role: string; content: string; created_at: string }[]
}

export interface EscalatedQueryListResponse {
  items: EscalatedQuery[]
  total: number
}

// ── Compliance Dashboard (from /compliance/dashboard) ──

export interface ComplianceDashboardKPIs {
  total_locations: number
  unread_alerts: number
  critical_alerts: number
  employees_at_risk: number
  overdue_actions: number
  assigned_actions: number
  unassigned_actions: number
}

export interface ComplianceDashboardItem {
  legislation_id: string
  title: string
  description: string | null
  category: string | null
  severity: 'critical' | 'warning' | 'info'
  status: string
  effective_date: string | null
  days_until: number | null
  location_id: string
  location_name: string
  location_state: string
  alert_id: string | null
  action_status: string
  next_action: string | null
  action_owner_id: string | null
  action_owner_name: string | null
  action_due_date: string | null
  is_overdue: boolean
  sla_state: string
  recommended_playbook: string | null
  estimated_financial_impact: string | null
  affected_employee_count: number
  affected_employee_sample: string[]
  impact_basis: string
  source_url: string | null
}

export interface ComplianceDashboard {
  kpis: ComplianceDashboardKPIs
  coming_up: ComplianceDashboardItem[]
}

// ── Dashboard Flags (from /dashboard/flags) ──

export interface DashboardFlag {
  priority: number
  category: string
  location_subject: string
  description: string
  recommendation: string
  severity: string
  source_type: string
  source_id: string | null
  link: string | null
}

export interface HeatMapCell {
  location: string
  category: string
  count: number
  worst_severity: string
  group: string // Locations, Departments, Company-wide
}

export interface BusinessLocation {
  id: string
  name: string
  city: string
  state: string
}

export interface DashboardFlagsResponse {
  total_flags: number
  critical_count: number
  flags: DashboardFlag[]
  heat_map: HeatMapCell[]
  locations: BusinessLocation[]
  analyzed_at: string | null
}

// ── /auth/me Response ──

export interface MeUser {
  id: string
  email: string
  role: string
  avatar_url?: string | null
  work_onboarded?: boolean
  beta_features?: Record<string, boolean>
}

export interface MeClientProfile {
  id: string
  user_id: string
  company_id: string
  company_name: string
  company_status: string
  rejection_reason: string | null
  industry: string | null
  healthcare_specialties: string[]
  enabled_features: Record<string, boolean>
  is_personal: boolean
  signup_source?: string | null
  ir_onboarding_completed_at?: string | null
  name: string
  phone: string | null
  job_title: string | null
  email: string
  created_at: string
  headcount?: number
}

export interface MeResponse {
  user: MeUser
  profile: MeClientProfile | null
  onboarding_needed: Record<string, boolean>
  visible_features: Record<string, boolean>
}
