import { api } from '../client'
import type {
  ScheduleStore, ScheduleStorePayload, StoreAssignmentResult, StoreReadiness, UnassignedEmployee,
} from '../../types/employeeSchedule'

/** Stores, managed from the schedule itself. Creating and editing go through
 *  the same location service Company settings uses, so a store is the same row
 *  whichever screen made it — this just asks for what scheduling needs. */
export function createScheduleStore(payload: ScheduleStorePayload) {
  return api.post<ScheduleStore>('/employee-schedule/locations', payload)
}

/** Also the repair path: saving a store that has no jurisdiction links one. */
export function updateScheduleStore(locationId: string, payload: Partial<ScheduleStorePayload>) {
  return api.patch<ScheduleStore>(`/employee-schedule/locations/${locationId}`, payload)
}

export function fetchStoreReadiness(locationId: string) {
  return api.get<StoreReadiness>(`/employee-schedule/locations/${locationId}/readiness`)
}

export function fetchUnassignedEmployees() {
  return api.get<{ employees: UnassignedEmployee[] }>('/employee-schedule/locations/unassigned-employees')
    .then((result) => result.employees)
}

/** Add-only: employees already at another store come back in `skipped`. */
export function assignEmployeesToStore(locationId: string, employeeIds: string[]) {
  return api.post<StoreAssignmentResult>(
    `/employee-schedule/locations/${locationId}/employees`,
    { employee_ids: employeeIds },
  )
}
