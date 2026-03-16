import { CATEGORY_LABELS } from '../generated/complianceCategories'
export { CATEGORY_LABELS }
export type { CategoryGroup } from '../generated/complianceCategories'

export interface JurisdictionOption {
  city: string
  state: string
  county: string | null
  has_local_ordinance: boolean
}

/** @deprecated Use JurisdictionOption */
export type Jurisdiction = JurisdictionOption

export interface LocationCreate {
  name?: string
  address?: string
  city: string
  state: string
  county?: string
  zipcode?: string
}

export interface LocationUpdate {
  name?: string
  address?: string
  city?: string
  state?: string
  county?: string
  zipcode?: string
  is_active?: boolean
}

export interface BusinessLocation {
  id: string
  company_id: string
  name: string | null
  address: string | null
  city: string
  state: string
  county: string | null
  zipcode: string | null
  is_active: boolean
  auto_check_enabled: boolean
  auto_check_interval_days: number
  next_auto_check: string | null
  last_compliance_check: string | null
  requirements_count: number
  unread_alerts_count: number
  employee_count: number
  employee_names: string[]
  data_status: string
  coverage_status: string
  has_local_ordinance: boolean
  source?: 'manual' | 'employee_derived'
  created_at: string
}

export interface ComplianceRequirement {
  id: string
  category: string
  rate_type: string | null
  applicable_industries: string[]
  jurisdiction_level: 'federal' | 'state' | 'county' | 'city'
  jurisdiction_name: string
  title: string
  description: string | null
  current_value: string | null
  numeric_value: number | null
  source_url: string | null
  source_name: string | null
  effective_date: string | null
  previous_value: string | null
  last_changed_at: string | null
  affected_employee_count: number | null
  affected_employee_names: string[]
  min_wage_violation_count: number | null
  is_pinned: boolean
}

export interface VerificationSource {
  url: string
  name: string
  type: 'official' | 'news' | 'blog' | 'other'
  snippet?: string
}

export interface ComplianceAlert {
  id: string
  location_id: string
  requirement_id: string | null
  alert_type: 'change' | 'new_requirement' | 'upcoming_legislation' | 'deadline_approaching' | null
  title: string
  message: string
  severity: 'info' | 'warning' | 'critical'
  status: 'unread' | 'read' | 'dismissed' | 'actioned'
  category: string | null
  action_required: string | null
  source_url: string | null
  source_name: string | null
  deadline: string | null
  confidence_score: number | null
  verification_sources: VerificationSource[] | null
  effective_date: string | null
  metadata: Record<string, unknown> | null
  affected_employee_count: number | null
  created_at: string
  read_at: string | null
}

export interface ComplianceSummary {
  total_locations: number
  total_requirements: number
  unread_alerts: number
  critical_alerts: number
  recent_changes: {
    location: string
    category: string
    title: string
    old_value: string | null
    new_value: string
    changed_at: string
  }[]
  auto_check_locations: number
  upcoming_deadlines: {
    title: string
    effective_date: string
    days_until: number
    status: string
    category: string | null
    location: string
  }[]
}

export interface PinnedRequirement {
  id: string
  category: string
  jurisdiction_level: string
  jurisdiction_name: string
  title: string
  description: string | null
  current_value: string | null
  effective_date: string | null
  source_url: string | null
  is_pinned: boolean
  location_name: string | null
  city: string
  state: string
}

export interface CheckLogEntry {
  id: string
  location_id: string
  company_id: string
  check_type: 'manual' | 'scheduled' | 'proactive'
  status: 'running' | 'completed' | 'failed'
  started_at: string
  completed_at: string | null
  new_count: number
  updated_count: number
  alert_count: number
  error_message: string | null
}

export interface UpcomingLegislation {
  id: string
  location_id: string
  category: string | null
  title: string
  description: string | null
  current_status: 'proposed' | 'passed' | 'signed' | 'effective_soon' | 'effective' | 'dismissed'
  expected_effective_date: string | null
  impact_summary: string | null
  source_url: string | null
  source_name: string | null
  confidence: number | null
  days_until_effective: number | null
  affected_employee_count: number | null
  created_at: string
}

export interface AssignableUser {
  id: string
  name: string
  email: string
  role: 'client' | 'admin'
}

export interface ComplianceActionPlanUpdate {
  action_owner_id?: string | null
  next_action?: string | null
  action_due_date?: string | null
  recommended_playbook?: string | null
  estimated_financial_impact?: string | null
  mark_actioned?: boolean
}

export interface AvailablePoster {
  location_id: string
  location_name: string
  state: string
  template_id: string | null
  poster_type: string
  title: string
  description: string | null
  download_url: string | null
  status: 'available' | 'ordered' | 'not_available'
}

export interface PosterOrder {
  id: string
  location_id: string
  template_ids: string[]
  status: 'pending' | 'processing' | 'shipped' | 'delivered' | 'cancelled'
  created_at: string
}

// SSE event types for compliance check streaming

export interface SSEHeartbeat {
  type: 'heartbeat'
}

export interface SSEProgress {
  type: 'progress'
  message: string
  phase: string
  progress: number
  timestamp: string
}

export interface SSENewRequirement {
  type: 'new_requirement'
  requirement_id: string
  category: string
  title: string
  jurisdiction_level: string
  current_value: string
}

export interface SSEAlertGenerated {
  type: 'alert_generated'
  alert_id: string
  title: string
  severity: string
  message: string
}

export interface SSEError {
  type: 'error'
  message: string
}

export type ComplianceSSEEvent =
  | SSEHeartbeat
  | SSEProgress
  | SSENewRequirement
  | SSEAlertGenerated
  | SSEError

// Requirement categories

export const REQUIREMENT_CATEGORIES = [
  'minimum_wage',
  'overtime',
  'sick_leave',
  'family_leave',
  'anti_discrimination',
  'workplace_safety',
  'workers_comp',
  'tax_withholding',
  'pay_frequency',
  'meal_breaks',
  'rest_breaks',
  'final_pay',
  'posting_requirements',
  'pto',
  'fair_scheduling',
  'ban_the_box',
  'non_compete',
  'harassment_training',
  'data_privacy',
  'whistleblower',
  'accommodations',
  'other',
] as const

export type RequirementCategory = (typeof REQUIREMENT_CATEGORIES)[number]

export const categoryLabel: Record<RequirementCategory, string> = {
  minimum_wage: 'Minimum Wage',
  overtime: 'Overtime',
  sick_leave: 'Sick Leave',
  family_leave: 'Family Leave',
  anti_discrimination: 'Anti-Discrimination',
  workplace_safety: 'Workplace Safety',
  workers_comp: "Workers' Comp",
  tax_withholding: 'Tax Withholding',
  pay_frequency: 'Pay Frequency',
  meal_breaks: 'Meal Breaks',
  rest_breaks: 'Rest Breaks',
  final_pay: 'Final Pay',
  posting_requirements: 'Posting Requirements',
  pto: 'PTO',
  fair_scheduling: 'Fair Scheduling',
  ban_the_box: 'Ban the Box',
  non_compete: 'Non-Compete',
  harassment_training: 'Harassment Training',
  data_privacy: 'Data Privacy',
  whistleblower: 'Whistleblower',
  accommodations: 'Accommodations',
  other: 'Other',
}
