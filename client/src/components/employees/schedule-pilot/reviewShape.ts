import type { HuumeScheduleReview } from '../../../work/types'
import type { ScheduleReview, ScheduleReviewAssignment, ScheduleReviewEmployee } from '../../../types/employeeSchedule'

/** The staged action carries the review in the loose `work/` shape (that
 *  tree must not import the Matcha types). Tighten it here, once, so the
 *  review pane renders a Huume-staged change, a scenario and a week draft
 *  with one component and no optional chaining in the JSX. */
export function asScheduleReview(loose: HuumeScheduleReview | ScheduleReview | null | undefined): ScheduleReview | null {
  if (!loose || typeof loose !== 'object') return null
  const jurisdiction = loose.jurisdiction ?? {}
  return {
    proposal_id: loose.proposal_id ?? null,
    kind: loose.kind ?? 'edit',
    compliance_status: loose.compliance_status ?? 'unmapped',
    assignments: (loose.assignments ?? []).map((item) => ({
      shift_id: item.shift_id ?? null,
      role: item.role ?? 'Shift',
      starts_at: item.starts_at ?? null,
      ends_at: item.ends_at ?? null,
      employee_id: item.employee_id ?? null,
      employee_name: item.employee_name ?? null,
      op: item.op ?? 'assign',
      verdict: item.verdict ?? 'ok',
      reasons: (item.reasons ?? []).map((reason) => ({
        code: reason.code ?? '', message: reason.message ?? '', policy: !!reason.policy,
      })),
    })),
    rejected: (loose.rejected ?? []).map((item) => ({
      shift_id: item.shift_id ?? null,
      role: item.role ?? 'Shift',
      starts_at: item.starts_at ?? null,
      ends_at: item.ends_at ?? null,
      employee_id: null,
      employee_name: item.employee_name ?? null,
      op: item.op ?? 'assign',
      reasons: (item.reasons ?? []).map((reason) => ({
        code: reason.code ?? '', message: reason.message ?? '', policy: !!reason.policy,
      })),
    })),
    unfilled: (loose.unfilled ?? []).map((item) => {
      const record = item as Record<string, unknown>
      return {
        shift_id: String(record.shift_id ?? record.shift_key ?? ''),
        role: (record.role as string | null) ?? null,
        starts_at: (record.starts_at as string | null) ?? null,
        ends_at: (record.ends_at as string | null) ?? null,
        reason: String(record.reason ?? 'no eligible employees'),
        exclusions: (record.exclusions as Record<string, number> | undefined) ?? {},
      }
    }),
    employees: (loose.employees ?? []).map((item) => ({
      employee_id: item.employee_id ?? '',
      name: item.name ?? 'Employee',
      before: item.before ?? {},
      after: item.after ?? {},
      warnings: item.warnings ?? [],
    })),
    advisories: (loose.advisories ?? []).map((item) => ({
      message: item.message ?? '', statute: item.statute ?? null,
      employee_name: item.employee_name ?? null, shift_id: item.shift_id ?? null,
    })),
    findings: loose.findings ?? [],
    jurisdiction: {
      state: jurisdiction.state ?? null,
      status: jurisdiction.status ?? 'unmapped',
      message: jurisdiction.message ?? 'Legality was not verified for this location.',
    },
  }
}

export interface ReviewComparison {
  /** Shifts the two scenarios staff differently (or only one staffs). */
  assignments: Array<{
    shift_id: string
    role: string
    starts_at: string | null
    left: string | null
    right: string | null
  }>
  /** Hours after each scenario, per person who appears in either. */
  employees: Array<{ employee_id: string; name: string; left: number; right: number }>
  /** Compact totals for the chip line. */
  totals: { left: { staged: number; unfilled: number }; right: { staged: number; unfilled: number } }
}

function namesByShift(review: ScheduleReview): Map<string, { role: string; starts_at: string | null; names: string[] }> {
  const map = new Map<string, { role: string; starts_at: string | null; names: string[] }>()
  for (const item of review.assignments) {
    if (!item.shift_id) continue
    const entry = map.get(item.shift_id) ?? { role: item.role, starts_at: item.starts_at, names: [] }
    if (item.employee_name) entry.names.push(item.employee_name)
    map.set(item.shift_id, entry)
  }
  return map
}

function afterMinutes(employee: ScheduleReviewEmployee): number {
  return employee.after.minutes ?? 0
}

/** What two scenarios do differently — the whole reason to run a second one. */
export function compareReviews(left: ScheduleReview, right: ScheduleReview): ReviewComparison {
  const leftShifts = namesByShift(left)
  const rightShifts = namesByShift(right)
  const shiftIds = new Set([...leftShifts.keys(), ...rightShifts.keys()])
  const assignments: ReviewComparison['assignments'] = []
  for (const shiftId of shiftIds) {
    const a = leftShifts.get(shiftId)
    const b = rightShifts.get(shiftId)
    const leftNames = a?.names.slice().sort().join(', ') ?? null
    const rightNames = b?.names.slice().sort().join(', ') ?? null
    if (leftNames === rightNames) continue
    assignments.push({
      shift_id: shiftId,
      role: (a ?? b)?.role ?? 'Shift',
      starts_at: (a ?? b)?.starts_at ?? null,
      left: leftNames || null,
      right: rightNames || null,
    })
  }
  assignments.sort((x, y) => (x.starts_at ?? '').localeCompare(y.starts_at ?? '') || x.shift_id.localeCompare(y.shift_id))

  const people = new Map<string, { employee_id: string; name: string; left: number; right: number }>()
  for (const employee of left.employees) {
    people.set(employee.employee_id, { employee_id: employee.employee_id, name: employee.name, left: afterMinutes(employee), right: 0 })
  }
  for (const employee of right.employees) {
    const entry = people.get(employee.employee_id)
    if (entry) entry.right = afterMinutes(employee)
    else people.set(employee.employee_id, { employee_id: employee.employee_id, name: employee.name, left: 0, right: afterMinutes(employee) })
  }
  // Someone in only one scenario still has their pre-existing hours in the
  // other — the review's `before`. Presence, not a zero, is the test: a
  // scenario that leaves a person at 0h after is a real outcome to show.
  const inLeft = new Set(left.employees.map((e) => e.employee_id))
  const inRight = new Set(right.employees.map((e) => e.employee_id))
  for (const [id, entry] of people) {
    if (!inLeft.has(id)) entry.left = right.employees.find((e) => e.employee_id === id)?.before.minutes ?? 0
    if (!inRight.has(id)) entry.right = left.employees.find((e) => e.employee_id === id)?.before.minutes ?? 0
  }
  const employees = [...people.values()].sort((x, y) => Math.abs(y.left - y.right) - Math.abs(x.left - x.right) || x.name.localeCompare(y.name))
  return {
    assignments,
    employees,
    totals: {
      left: { staged: left.assignments.length, unfilled: left.unfilled.length },
      right: { staged: right.assignments.length, unfilled: right.unfilled.length },
    },
  }
}

/** One sentence the composer can be seeded with about a review row. */
export function askAbout(kind: 'assignment' | 'rejected' | 'unfilled' | 'employee', item: { name?: string | null; role?: string | null; when?: string | null; reason?: string | null }): string {
  const who = item.name ? `${item.name}` : 'this person'
  const what = [item.role, item.when].filter(Boolean).join(' ')
  switch (kind) {
    case 'assignment': return `Why ${who} for the ${what} shift? Who else could take it?`
    case 'rejected': return `The ${what} shift for ${who} wasn't staged (${item.reason ?? 'refused'}). Who else could take it?`
    case 'unfilled': return `The ${what} shift is still open (${item.reason ?? 'no eligible employees'}). What would it take to fill it?`
    case 'employee': return `Tell me about ${who}'s week — hours, shifts, and anything I should watch.`
  }
}

export function hoursLabel(minutes: number | undefined | null): string {
  const value = (minutes ?? 0) / 60
  return `${Number.isInteger(value) ? value : value.toFixed(1)}h`
}

export type { ScheduleReviewAssignment }
