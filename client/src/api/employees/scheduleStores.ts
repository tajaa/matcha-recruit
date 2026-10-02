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

/** The most ids one assign request may carry — the server's cap
 *  (`ScheduleStoreAssignEmployees.employee_ids`, max_length 500). */
export const ASSIGN_BATCH_SIZE = 500

/** Some batches landed before one failed. `assigned` is what did go through,
 *  so the caller can say so and refresh instead of reporting a total failure. */
export class PartialAssignmentError extends Error {
  assigned: string[]
  cause: unknown
  constructor(assigned: string[], cause: unknown) {
    super('Some employees were assigned before a later batch failed')
    this.name = 'PartialAssignmentError'
    this.assigned = assigned
    this.cause = cause
  }
}

/** Add-only: employees already at another store come back in `skipped`.
 *
 *  Sent in batches. A roster import can leave more people unassigned than one
 *  request may carry (uploads allow 1,000 rows), and the dialog's default is
 *  "everyone" — a single request then failed validation and assigned nobody. */
export async function assignEmployeesToStore(locationId: string, employeeIds: string[]) {
  const result: StoreAssignmentResult = { assigned: [], skipped: [] }
  for (let start = 0; start < employeeIds.length; start += ASSIGN_BATCH_SIZE) {
    try {
      const batch = await api.post<StoreAssignmentResult>(
        `/employee-schedule/locations/${locationId}/employees`,
        { employee_ids: employeeIds.slice(start, start + ASSIGN_BATCH_SIZE) },
      )
      result.assigned.push(...batch.assigned)
      result.skipped.push(...batch.skipped)
    } catch (caught) {
      if (result.assigned.length === 0) throw caught
      throw new PartialAssignmentError(result.assigned, caught)
    }
  }
  return result
}
