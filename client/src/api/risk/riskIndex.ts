import { api } from '../client'
import type { RiskIndex, SubmissionReadiness, VenueExposure, ExclusionGap } from '../../types/riskIndex'

// Client-facing portal (own company)
export function fetchRiskProfile() {
  return api.get<RiskIndex>('/risk-profile')
}

export function fetchSubmissionReadiness() {
  return api.get<SubmissionReadiness>('/risk-profile/readiness')
}

export function fetchVenueExposure() {
  return api.get<VenueExposure>('/risk-profile/venue')
}

export function fetchExclusionGap() {
  return api.get<ExclusionGap>('/risk-profile/exclusions')
}

export interface RiskNarrative {
  summary: string
  actions: string[]
  available: boolean
}
export function fetchRiskNarrative() {
  return api.post<RiskNarrative>('/risk-profile/narrative', {})
}
