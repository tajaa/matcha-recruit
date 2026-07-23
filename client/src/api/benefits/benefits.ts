import { api } from '../client'

export type PlanType = 'medical' | 'dental' | 'vision' | 'life' | 'disability' | 'other'
export type PlanStatus = 'draft' | 'active' | 'archived'
export type CoverageTier = 'employee_only' | 'employee_spouse' | 'employee_children' | 'family'
export type CostPeriod = 'monthly' | 'per_pay_period'
export type OePeriodStatus = 'draft' | 'open' | 'closed'
export type ElectionStatus = 'draft' | 'submitted' | 'approved' | 'rejected'
export type LifeEventType =
  | 'marriage' | 'divorce' | 'birth_adoption' | 'death_of_dependent'
  | 'loss_of_coverage' | 'gain_of_coverage' | 'dependent_status_change'
  | 'relocation' | 'other'
export type LifeEventStatus = 'pending' | 'approved' | 'denied' | 'expired'
export type DependentRelationship = 'spouse' | 'child' | 'domestic_partner' | 'other'

export type Tier = {
  id: string
  plan_id: string
  coverage_tier: CoverageTier
  employee_cost: number
  employer_cost: number
  cost_period: CostPeriod
}

export type Plan = {
  id: string
  company_id: string
  plan_type: PlanType
  name: string
  carrier_name: string | null
  description: string | null
  status: PlanStatus
  waivable: boolean
  tiers: Tier[]
  created_at: string
  updated_at: string
}

export type TierInput = {
  coverage_tier: CoverageTier
  employee_cost: number
  employer_cost: number
  cost_period: CostPeriod
}

export type PlanCreateInput = {
  plan_type: PlanType
  name: string
  carrier_name?: string | null
  description?: string | null
  waivable?: boolean
  tiers: TierInput[]
}

export type PlanUpdateInput = Partial<{
  name: string
  carrier_name: string | null
  description: string | null
  status: PlanStatus
  waivable: boolean
}>

export type OePeriod = {
  id: string
  company_id: string
  name: string
  starts_on: string
  ends_on: string
  plan_year_start: string | null
  status: OePeriodStatus
  opened_at: string | null
  closed_at: string | null
}

export type Dependent = { name: string; relationship: DependentRelationship; dob?: string | null }

export type Election = {
  id: string
  employee_id: string
  employee_name?: string
  plan_type: PlanType
  plan_id: string | null
  plan_name?: string
  tier_id: string | null
  coverage_tier?: CoverageTier
  waived: boolean
  dependents: Dependent[]
  status: ElectionStatus
  submitted_at: string | null
  decided_at: string | null
  decision_note: string | null
  effective_date: string | null
}

export type LifeEvent = {
  id: string
  employee_id: string
  employee_name?: string
  event_type: LifeEventType
  event_date: string
  description: string | null
  status: LifeEventStatus
  window_days: number
  window_ends_on: string | null
  review_note: string | null
}

export type EligibilityException = {
  id: string
  company_id: string
  employee_name: string | null
  exception_type: string
  reference_date: string
  days_elapsed: number | null
  days_remaining: number | null
  estimated_monthly_leak: number | null
  status: string
  source: string | null
  detected_at: string
}

export type RenewalRiskDimension = {
  dimension_type: string
  dimension_value: string
  risk_band: string
  turnover_pct: number
  turnover_delta_pct: number
  lost_workdays: number
  near_misses: number
  behavioral_incidents: number
  headcount: number
  triggers: string[]
}

export const benefitsApi = {
  // Plans
  listPlans: (status?: PlanStatus) => {
    const qs = status ? `?status=${encodeURIComponent(status)}` : ''
    return api.get<{ plans: Plan[] }>(`/benefits/plans${qs}`)
  },
  createPlan: (input: PlanCreateInput) => api.post<Plan>('/benefits/plans', input),
  getPlan: (planId: string) => api.get<Plan>(`/benefits/plans/${planId}`),
  updatePlan: (planId: string, input: PlanUpdateInput) => api.patch<Plan>(`/benefits/plans/${planId}`, input),
  replaceTiers: (planId: string, tiers: TierInput[]) =>
    api.put<{ tiers: Tier[] }>(`/benefits/plans/${planId}/tiers`, tiers),
  deletePlan: (planId: string) => api.delete<{ result: 'deleted' | 'archived' }>(`/benefits/plans/${planId}`),

  // Enrollment periods
  listPeriods: () => api.get<{ periods: OePeriod[] }>('/benefits/enrollment/periods'),
  createPeriod: (input: { name: string; starts_on: string; ends_on: string; plan_year_start?: string | null }) =>
    api.post<OePeriod>('/benefits/enrollment/periods', input),
  updatePeriod: (periodId: string, input: Partial<{ name: string; starts_on: string; ends_on: string; plan_year_start: string | null }>) =>
    api.patch<OePeriod>(`/benefits/enrollment/periods/${periodId}`, input),
  openPeriod: (periodId: string) => api.post<OePeriod>(`/benefits/enrollment/periods/${periodId}/open`),
  closePeriod: (periodId: string) => api.post<OePeriod>(`/benefits/enrollment/periods/${periodId}/close`),
  reviewPeriodElections: (periodId: string) =>
    api.get<{
      elections: Election[]
      status_counts: Record<string, number>
      not_submitted: { employee_id: string; employee_name: string }[]
    }>(`/benefits/enrollment/periods/${periodId}/elections`),

  // Election decisions
  approveElection: (electionId: string, note?: string) =>
    api.post<Election>(`/benefits/enrollment/elections/${electionId}/approve`, { note }),
  rejectElection: (electionId: string, note?: string) =>
    api.post<Election>(`/benefits/enrollment/elections/${electionId}/reject`, { note }),

  // Life events
  listLifeEvents: (status: LifeEventStatus = 'pending') =>
    api.get<{ life_events: LifeEvent[] }>(`/benefits/enrollment/life-events?status=${status}`),
  approveLifeEvent: (eventId: string, note?: string) =>
    api.post<LifeEvent>(`/benefits/enrollment/life-events/${eventId}/approve`, { note }),
  denyLifeEvent: (eventId: string, note?: string) =>
    api.post<LifeEvent>(`/benefits/enrollment/life-events/${eventId}/deny`, { note }),

  // Eligibility / roster (pre-existing endpoints, first UI)
  eligibilityExceptions: () => api.get<{ exceptions: EligibilityException[] }>('/benefits/eligibility-exceptions'),
  renewalRisk: () => api.get<{ dimensions: RenewalRiskDimension[] }>('/benefits/renewal-risk'),
  runDetection: () => api.post<{ ingested?: number; exceptions_detected?: number; risk?: unknown }>('/benefits/run'),
  uploadRoster: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.upload<{ ingested: number; exceptions_detected: number; risk: unknown }>('/benefits/roster/upload', fd)
  },
  downloadRosterTemplate: () => api.download('/benefits/roster/template', 'benefit_roster_template.csv'),
}
