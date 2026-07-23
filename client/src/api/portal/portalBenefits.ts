import { api } from '../client'
import type {
  Dependent, Election, LifeEvent, LifeEventType, PlanType, Tier,
} from '../benefits/benefits'

export type MyPlan = {
  id: string
  plan_type: PlanType
  name: string
  carrier_name: string | null
  description: string | null
  waivable: boolean
  tiers: Tier[]
}

export type MyBenefitsWindow = {
  kind: 'oe' | 'life_event'
  id: string
  ends_on: string | null
} | null

export type MyBenefits = {
  window: MyBenefitsWindow
  plans: MyPlan[]
  my_elections: Election[]
  current_coverage: Election[]
}

export type ElectionUpsertInput = {
  plan_type: PlanType
  plan_id?: string | null
  tier_id?: string | null
  waived: boolean
  dependents: Dependent[]
}

// NB: the employee-portal router is mounted at /v1/portal (routes/__init__.py),
// not /portal — same prefix portalAskHr.ts / portalDocuments.ts use.
export const portalBenefitsApi = {
  getMyBenefits: () => api.get<MyBenefits>('/v1/portal/me/benefits'),
  upsertElection: (input: ElectionUpsertInput) => api.put<Election>('/v1/portal/me/benefits/elections', input),
  submitElections: () => api.post<{ submitted: Election[] }>('/v1/portal/me/benefits/elections/submit'),
  deleteElection: (electionId: string) => api.delete<{ result: 'deleted' }>(`/v1/portal/me/benefits/elections/${electionId}`),
  listLifeEvents: () => api.get<{ life_events: LifeEvent[] }>('/v1/portal/me/benefits/life-events'),
  reportLifeEvent: (input: { event_type: LifeEventType; event_date: string; description?: string | null }) =>
    api.post<LifeEvent>('/v1/portal/me/benefits/life-events', input),
}
