import { api } from '../client'
import type { LocationScheduleProfile, LocationScheduleProfileUpdate } from '../../types/employeeSchedule'

/** The location's scheduling setup — operating hours, week start, the default
 *  week template, and the leader requirement. Huume writes this from its
 *  interview; the Week Start pane is the hand-editable counterpart. */
export function fetchLocationScheduleProfile(locationId: string) {
  return api.get<LocationScheduleProfile>(`/employee-schedule/locations/${locationId}/profile`)
}

/** True PATCH: only the supplied fields are written. */
export function saveLocationScheduleProfile(locationId: string, payload: LocationScheduleProfileUpdate) {
  return api.put<LocationScheduleProfile>(`/employee-schedule/locations/${locationId}/profile`, payload)
}
