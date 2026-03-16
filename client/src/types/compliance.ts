export interface Jurisdiction {
  city: string | null
  state: string
  county: string | null
  has_local_ordinance: boolean
}

export interface BusinessLocation {
  id: string
  name: string | null
  address: string | null
  city: string
  state: string
  county: string | null
  zipcode: string | null
  requirements_count: number
  unread_alerts_count: number
  employee_count: number
  employee_names: string[]
  data_status: string
  coverage_status: string
  has_local_ordinance: boolean
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

export interface ComplianceAlert {
  id: string
  alert_type: 'change' | 'new_requirement' | 'upcoming_legislation' | 'deadline_approaching'
  title: string
  message: string
  severity: 'info' | 'warning' | 'critical'
  status: 'unread' | 'read' | 'dismissed' | 'actioned'
  verification_sources: string[]
  confidence_score: number | null
  affected_employee_count: number | null
  created_at: string
}

export interface ComplianceSummary {
  total_locations: number
  total_requirements: number
  unread_alerts: number
  critical_alerts: number
  recent_changes: any[]
  auto_check_locations: number
  upcoming_deadlines: any[]
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
