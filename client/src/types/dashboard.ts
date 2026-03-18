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
  investigating: number
  pending_action: number
}

export interface StalePolicySummary {
  stale_count: number
  oldest_days: number
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
  critical_compliance_alerts: number
  warning_compliance_alerts: number
  er_case_summary: ERCaseSummary | null
  stale_policies: StalePolicySummary | null
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

// ── /auth/me Response ──

export interface MeUser {
  id: string
  email: string
  role: string
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
  name: string
  phone: string | null
  job_title: string | null
  email: string
  created_at: string
}

export interface MeResponse {
  user: MeUser
  profile: MeClientProfile | null
  onboarding_needed: Record<string, boolean>
  visible_features: Record<string, boolean>
}
