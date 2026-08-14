import { api } from '../client'
import type {
  ScheduleIntelOverview, IncidentCorrelation, FairWorkweek, PretextShield,
  QualifiedCoverage, Unavailable,
  AvailabilityOverrides,
} from '../../types/scheduleIntelligence'

export function fetchOverview() {
  return api.get<ScheduleIntelOverview | Unavailable>('/schedule-intelligence/overview')
}

export function fetchAvailabilityOverrides(days = 90) {
  return api.get<AvailabilityOverrides | Unavailable>(
    `/schedule-intelligence/availability-overrides?days=${days}`,
  )
}

export function fetchIncidentCorrelation(days = 180) {
  return api.get<IncidentCorrelation | Unavailable>(
    `/schedule-intelligence/incident-correlation?days=${days}`,
  )
}

export function fetchFairWorkweek(days = 90) {
  return api.get<FairWorkweek | Unavailable>(`/schedule-intelligence/fair-workweek?days=${days}`)
}

export function fetchPretextShield(months = 6) {
  return api.get<PretextShield | Unavailable>(`/schedule-intelligence/pretext-shield?months=${months}`)
}

export function fetchQualifiedCoverage(days = 14) {
  return api.get<QualifiedCoverage | Unavailable>(
    `/schedule-intelligence/qualified-coverage?days=${days}`,
  )
}
