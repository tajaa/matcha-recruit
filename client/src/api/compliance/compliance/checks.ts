import { api } from '../../client'
import type {
  CheckLogEntry,
  UpcomingLegislation,
  AssignableUser,
} from '../../../types/compliance'

// ── Compliance Checks ──

/** Per-location compliance re-check. Answers with SSE, not JSON — the stream IS
 *  the work (the server projects as it yields), so callers drive it through
 *  `postSSE` (api/sse.ts) rather than `api.post`, which would choke parsing
 *  `data: {...}`. A path, not an absolute URL — postSSE prepends the base. */
export function getComplianceCheckPath(locationId: string): string {
  return `/compliance/locations/${locationId}/check`
}

export function fetchCheckLog(locationId: string, limit = 20) {
  return api.get<CheckLogEntry[]>(
    `/compliance/locations/${locationId}/check-log?limit=${limit}`
  )
}

// ── Upcoming Legislation ──

export function fetchUpcomingLegislation(locationId: string) {
  return api.get<UpcomingLegislation[]>(
    `/compliance/locations/${locationId}/upcoming-legislation`
  )
}

export function assignLegislation(
  legislationId: string,
  data: { location_id: string; action_owner_id?: string; action_due_date?: string }
) {
  return api.put<{ alert_id: string }>(
    `/compliance/legislation/${legislationId}/assign`,
    data
  )
}

// ── Users ──

export function fetchAssignableUsers() {
  return api.get<AssignableUser[]>('/compliance/assignable-users')
}
