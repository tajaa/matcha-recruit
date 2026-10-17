export type Overview = {
  company: {
    id: string; name: string; industry: string | null; healthcare_specialties: string[]
    size: string | null; status: string; headquarters_state: string | null
    created_at: string | null; enabled_features: Record<string, boolean>; active_employee_count: number
  }
  employees: { id: string; email: string; name: string; department: string | null; job_title: string | null; employment_type: string | null; work_state: string | null; start_date: string | null; active: boolean }[]
  risk: { overall_score: number; overall_band: string; computed_at: string | null } | null
  ir_summary: { total_open: number; critical: number; high: number; medium: number; low: number; recent_30_days: number }
  er_summary: { total_open: number; open: number; in_review: number; pending_determination: number }
  compliance: { total_locations: number; total_requirements: number; critical_alerts: number; warning_alerts: number }
  policies: { total_active: number; stale_count: number }
  recent_incidents: { id: string; incident_number: string; title: string; severity: string; status: string; created_at: string | null }[]
  recent_er_cases: { id: string; case_number: string; title: string; status: string; category: string | null; created_at: string | null }[]
}

export type Registration = {
  id: string
  owner_user_id: string | null
  signup_source: string | null
  is_personal: boolean
  is_test: boolean
  is_suspended: boolean
  deleted_at: string | null
  subscription: {
    pack_id: string
    status: string
    amount_cents: number
    stripe_subscription_id: string
    stripe_customer_id: string
    current_period_end: string | null
    canceled_at: string | null
  } | null
}

export type Tab = 'employees' | 'risk' | 'compliance' | 'tokens' | 'actions'

export type TokenBudget = {
  free_tokens_used: number; free_token_limit: number; free_tokens_remaining: number
  subscription_tokens_used: number; subscription_token_limit: number; subscription_tokens_remaining: number
  total_tokens_remaining: number; has_active_subscription: boolean
}
export type UsageEvent = {
  id: string; model: string | null; total_tokens: number | null; operation: string | null; created_at: string
}
export type TokenDetail = { budget: TokenBudget; recent_usage: UsageEvent[] }

export type Charge = {
  id: string
  amount: number
  amount_refunded: number
  currency: string
  created: number
  status: string
  description: string | null
}
