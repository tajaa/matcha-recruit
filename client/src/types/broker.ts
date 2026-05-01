// --- Portfolio reporting ---

export interface BrokerPortfolioSummary {
  total_linked_companies: number
  active_link_count: number
  pending_setup_count: number
  expired_setup_count: number
  healthy_companies: number
  at_risk_companies: number
  average_policy_compliance_rate: number
  open_action_item_total: number
  total_pre_term_checks?: number
  avg_portfolio_override_rate?: number
}

export interface BrokerCompanyMetric {
  company_id: string
  company_name: string
  link_status: string
  setup_status: string
  policy_compliance_rate: number
  open_action_items: number
  active_employee_count: number
  risk_signal: 'healthy' | 'at_risk' | 'watch'
  pre_term_checks?: number
  avg_separation_risk?: number
  separation_override_rate?: number
}

export interface BrokerPortfolioResponse {
  summary: BrokerPortfolioSummary
  setup_status_counts: Record<string, number>
  companies: BrokerCompanyMetric[]
}

// --- Referred clients ---

export interface BrokerReferredClient {
  company_id: string
  company_name: string
  industry: string
  company_size: string
  company_status: string
  link_status: string
  linked_at: string
  activated_at?: string
  active_employee_count: number
  enabled_feature_count: number
}

export interface BrokerReferredClientsResponse {
  broker_slug: string
  total: number
  clients: BrokerReferredClient[]
}

// --- Handbook coverage ---

export interface BrokerHandbookCoverage {
  handbook_id: string
  handbook_title: string
  company_id: string
  company_name: string
  strength_score: number
  strength_label: 'Strong' | 'Moderate' | 'Weak'
  total_sections: number
  state_count: number
  missing_section_count: number
}

// --- Client setups ---

export interface BrokerClientSetup {
  id: string
  company_name: string
  status: 'draft' | 'invited' | 'activated' | 'expired' | 'cancelled'
  contact_name: string
  contact_email: string
  headcount_hint: number
  invited_at?: string
  activated_at?: string
  created_at: string
  notes?: string
  locations?: { city: string; state: string; type: string }[]
  onboarding_stage?: 'submitted' | 'under_review' | 'configuring' | 'live'
}

export interface BrokerBatchCreateResponse {
  status: string
  count: number
  setups: BrokerClientSetup[]
  errors: { index: number; company_name: string; error: string }[]
}

export interface BrokerClientSetupsResponse {
  setups: BrokerClientSetup[]
  total: number
  expired_count: number
}

// --- Lite referral tokens ---

export interface BrokerLiteReferralToken {
  id: string
  broker_id: string
  token: string
  label: string | null
  created_at: string
  expires_at: string | null
  is_active: boolean
  use_count: number
  last_used_at: string | null
  referral_url: string
}

export interface BrokerLiteReferralTokenListResponse {
  tokens: BrokerLiteReferralToken[]
  total: number
}

// --- Per-client detail ---

export interface BrokerClientCompany {
  id: string
  name: string
  industry: string | null
  size: string | null
  status: string
  link_status: string
  setup_status: string
  onboarding_stage: string | null
  active_employee_count: number
  policy_compliance_rate: number
  open_action_items: number
  risk_signal: 'healthy' | 'watch' | 'at_risk'
}

export interface BrokerClientLocation {
  id: string
  name: string | null
  city: string
  state: string
  total_requirements: number
  categories: Record<string, number>
}

export interface BrokerClientPolicyItem {
  id: string
  title: string
  category: string | null
  status: string
  pending_count: number
  signed_count: number
  total_count: number
  signature_rate: number
}

export interface BrokerClientDetailResponse {
  company: BrokerClientCompany
  compliance: {
    locations: BrokerClientLocation[]
    total_locations: number
    total_requirements: number
  }
  policies: {
    total_active: number
    compliance_rate: number
    items: BrokerClientPolicyItem[]
  }
  ir_summary: {
    total_open: number
    by_severity: Record<string, number>
    recent_30_days: number
  }
  er_summary: {
    total_open: number
    by_status: Record<string, number>
  }
  handbooks: BrokerHandbookCoverage[]
  recent_activity: {
    action: string
    timestamp: string
    source: string
  }[]
}
