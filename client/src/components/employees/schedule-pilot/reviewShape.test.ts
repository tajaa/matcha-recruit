import { describe, expect, it } from 'vitest'
import { asScheduleReview, askAbout, compareReviews, hoursLabel } from './reviewShape'
import type { ScheduleReview } from '../../../types/employeeSchedule'

function review(overrides: Partial<ScheduleReview> = {}): ScheduleReview {
  return {
    proposal_id: 'p1',
    kind: 'edit',
    compliance_status: 'verified',
    assignments: [],
    rejected: [],
    unfilled: [],
    employees: [],
    advisories: [],
    findings: [],
    jurisdiction: { state: 'CA', status: 'curated', message: 'on file' },
    ...overrides,
  }
}

function assignment(shiftId: string, name: string | null, startsAt = '2026-08-24T06:00:00+00:00') {
  return {
    shift_id: shiftId, role: 'Shift Lead', starts_at: startsAt, ends_at: '2026-08-24T14:00:00+00:00',
    employee_id: name ? `e-${name}` : null, employee_name: name, op: 'assign',
    verdict: 'ok' as const, reasons: [],
  }
}

function employee(id: string, name: string, before: number, after: number) {
  return {
    employee_id: id, name,
    before: { minutes: before, shifts: 1, days: 1 },
    after: { minutes: after, shifts: 2, days: 2 },
    warnings: [],
  }
}

describe('asScheduleReview', () => {
  it('tightens the loose staged-action shape, defaulting every absent field', () => {
    const tightened = asScheduleReview({
      kind: 'week_draft',
      assignments: [{ shift_id: 's1', employee_name: 'Dana Reyes' }],
      rejected: [{ shift_id: 's2', reasons: [{ message: 'already on the Opener' }] }],
      unfilled: [{ shift_key: 's3', reason: 'policy: second shift that day' }],
      employees: [{ name: 'Dana Reyes' }],
      advisories: [{ message: 'past 40h' }],
    })

    expect(tightened).not.toBeNull()
    expect(tightened!.kind).toBe('week_draft')
    // Never optimistic: an absent compliance status is "not verified", never "verified".
    expect(tightened!.compliance_status).toBe('unmapped')
    expect(tightened!.assignments[0]).toMatchObject({ role: 'Shift', op: 'assign', verdict: 'ok', reasons: [] })
    expect(tightened!.rejected[0].reasons[0]).toEqual({ code: '', message: 'already on the Opener', policy: false })
    // The planner spells the key `shift_key`; the review contract uses `shift_id`.
    expect(tightened!.unfilled[0]).toMatchObject({ shift_id: 's3', reason: 'policy: second shift that day', exclusions: {} })
    expect(tightened!.employees[0]).toMatchObject({ employee_id: '', name: 'Dana Reyes', warnings: [] })
    expect(tightened!.advisories[0]).toEqual({ message: 'past 40h', statute: null, employee_name: null, shift_id: null })
    expect(tightened!.jurisdiction.message).toBe('Legality was not verified for this location.')
  })

  it('is null for a staged action that carries no review', () => {
    expect(asScheduleReview(null)).toBeNull()
    expect(asScheduleReview(undefined)).toBeNull()
  })

  it('keeps a fully-formed review intact', () => {
    const source = review({ assignments: [assignment('s1', 'Dana Reyes')] })
    expect(asScheduleReview(source)).toEqual(source)
  })
})

describe('compareReviews', () => {
  it('lists only the shifts the two scenarios staff differently', () => {
    const left = review({
      assignments: [assignment('s1', 'Dana Reyes'), assignment('s2', 'Ben Ortiz', '2026-08-25T06:00:00+00:00')],
    })
    const right = review({
      assignments: [assignment('s1', 'Dana Reyes'), assignment('s2', 'Ana Kim', '2026-08-25T06:00:00+00:00')],
    })

    const diff = compareReviews(left, right)

    // s1 is staffed the same in both and never appears.
    expect(diff.assignments).toEqual([{
      shift_id: 's2', role: 'Shift Lead', starts_at: '2026-08-25T06:00:00+00:00',
      left: 'Ben Ortiz', right: 'Ana Kim',
    }])
  })

  it('reports a shift only one scenario staffs as open on the other side', () => {
    const left = review({ assignments: [assignment('s1', 'Dana Reyes')] })
    const right = review({ assignments: [] })

    const diff = compareReviews(left, right)

    expect(diff.assignments).toEqual([{
      shift_id: 's1', role: 'Shift Lead', starts_at: '2026-08-24T06:00:00+00:00',
      left: 'Dana Reyes', right: null,
    }])
  })

  it('orders differences by time so the diff reads like the week', () => {
    const left = review({
      assignments: [
        assignment('late', 'Dana Reyes', '2026-08-27T06:00:00+00:00'),
        assignment('early', 'Dana Reyes', '2026-08-24T06:00:00+00:00'),
      ],
    })
    const diff = compareReviews(left, review())
    expect(diff.assignments.map((row) => row.shift_id)).toEqual(['early', 'late'])
  })

  it('puts the biggest hours swing first, and keeps a person present in only one side', () => {
    const left = review({ employees: [employee('e1', 'Dana Reyes', 480, 960), employee('e2', 'Ben Ortiz', 480, 600)] })
    const right = review({ employees: [employee('e1', 'Dana Reyes', 480, 540)] })

    const diff = compareReviews(left, right)

    expect(diff.employees[0]).toEqual({ employee_id: 'e1', name: 'Dana Reyes', left: 960, right: 540 })
    // Ben is only in the left scenario; his right-hand number is what he already had.
    expect(diff.employees[1]).toEqual({ employee_id: 'e2', name: 'Ben Ortiz', left: 600, right: 480 })
  })

  it('keeps a scenario that empties someone’s week at zero', () => {
    // Presence, not a zero, decides the backfill: a scenario that leaves Dana
    // with no hours is a real outcome, not a person the scenario never touched.
    const left = review({ employees: [employee('e1', 'Dana Reyes', 480, 0)] })
    const right = review({ employees: [employee('e1', 'Dana Reyes', 480, 540)] })

    expect(compareReviews(left, right).employees[0]).toEqual({
      employee_id: 'e1', name: 'Dana Reyes', left: 0, right: 540,
    })
  })

  it('carries each side’s staged and unfilled totals for the chip line', () => {
    const left = review({ assignments: [assignment('s1', 'Dana Reyes')], unfilled: [] })
    const right = review({
      assignments: [],
      unfilled: [{ shift_id: 's1', role: 'Shift Lead', starts_at: null, ends_at: null, reason: 'no eligible employees', exclusions: {} }],
    })

    expect(compareReviews(left, right).totals).toEqual({
      left: { staged: 1, unfilled: 0 },
      right: { staged: 0, unfilled: 1 },
    })
  })
})

describe('askAbout', () => {
  it('asks a question the manager would actually type', () => {
    expect(askAbout('assignment', { name: 'Dana Reyes', role: 'Shift Lead', when: 'Mon 8/24 6a' }))
      .toBe('Why Dana Reyes for the Shift Lead Mon 8/24 6a shift? Who else could take it?')
    expect(askAbout('rejected', { name: 'Dana Reyes', role: 'Shift Lead', when: 'Mon 8/24 6a', reason: 'already on the Opener' }))
      .toContain('already on the Opener')
    expect(askAbout('unfilled', { role: 'Shift Lead', when: 'Mon 8/24 6a', reason: 'policy: second shift that day' }))
      .toContain('What would it take to fill it?')
    expect(askAbout('employee', { name: 'Dana Reyes' })).toContain("Dana Reyes's week")
  })
})

describe('hoursLabel', () => {
  it('keeps whole hours whole and shows one decimal otherwise', () => {
    expect(hoursLabel(480)).toBe('8h')
    expect(hoursLabel(510)).toBe('8.5h')
    expect(hoursLabel(0)).toBe('0h')
    expect(hoursLabel(null)).toBe('0h')
  })
})
