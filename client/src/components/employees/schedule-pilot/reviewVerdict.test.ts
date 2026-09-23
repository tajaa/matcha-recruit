import { describe, expect, it } from 'vitest'
import type { AutopilotDemandModel, ScheduleReview, ScheduleReviewAssignment } from '../../../types/employeeSchedule'
import { approvalVerdict, demandCoverage, findingLabel, groupFindings, proposalPreviewShifts } from './reviewVerdict'

const DAY = '2026-10-05'

function assignment(overrides: Partial<ScheduleReviewAssignment> = {}): ScheduleReviewAssignment {
  return {
    shift_id: 'autopilot:2026-10-05:barista:1', role: 'Barista',
    starts_at: `${DAY}T07:00:00+00:00`, ends_at: `${DAY}T15:00:00+00:00`,
    employee_id: 'e-amy', employee_name: 'Amy', op: 'assign', verdict: 'ok', reasons: [],
    ...overrides,
  }
}

function review(overrides: Partial<ScheduleReview> = {}): ScheduleReview {
  return {
    proposal_id: 'run-1', kind: 'week_draft', compliance_status: 'verified',
    assignments: [assignment()], rejected: [], unfilled: [], employees: [], advisories: [], findings: [],
    jurisdiction: { state: 'CA', status: 'curated', message: 'Scheduling law for CA is on file.' },
    ...overrides,
  }
}

const CARD = 'Food Handler Card requires an approved credential document before scheduling.'

function openSeat(index: number, code = 'credential_missing', reason = CARD) {
  return {
    shift_id: `autopilot:${DAY}:lead:${index}`, role: 'Shift Lead',
    starts_at: `${DAY}T13:00:00+00:00`, ends_at: `${DAY}T20:00:00+00:00`,
    reason, reason_code: code, exclusions: {},
  }
}

describe('approvalVerdict', () => {
  it('says ready when nothing is in the way, and the button is plain', () => {
    const verdict = approvalVerdict(review())
    expect(verdict).toMatchObject({ tone: 'ok', headline: 'Ready to approve', approveLabel: 'Approve', issues: [] })
    expect(verdict.facts).toEqual(['1/1 filled'])
  })

  it('groups open seats by their stable code, commonest first, with the server reason', () => {
    const verdict = approvalVerdict(review({
      unfilled: [openSeat(1), openSeat(2), openSeat(3), openSeat(4, 'not_qualified', 'not qualified for the shift job')],
    }))
    expect(verdict.tone).toBe('bad')
    expect(verdict.headline).toBe('4 of 5 shifts would stay open')
    expect(verdict.approveLabel).toBe('Approve with 4 shifts open')
    expect(verdict.issues.map((issue) => [issue.label, issue.detail])).toEqual([
      ['3 shifts left open', CARD],
      ['1 shift left open', 'not qualified for the shift job'],
    ])
    expect(verdict.issues[0].fix).toEqual({ kind: 'ask', text: `3 shifts would stay open (${CARD}). What would it take to fill them?` })
  })

  it('names a week nobody could staff as such', () => {
    const verdict = approvalVerdict(review({ assignments: [], unfilled: [openSeat(1), openSeat(2)] }))
    expect(verdict.headline).toBe('Nothing could be staffed — all 2 shifts would stay open')
  })

  it('falls back to the reason text when an older proposal carries no code', () => {
    const verdict = approvalVerdict(review({ unfilled: [openSeat(1, ''), openSeat(2, '')] }))
    expect(verdict.issues[0].label).toBe('2 shifts left open')
  })

  it('flags hours over a personal cap before the house policy, and only when they grew', () => {
    const verdict = approvalVerdict(review({
      employees: [
        { employee_id: 'e-amy', name: 'Amy', before: { minutes: 1200 }, after: { minutes: 2100 }, warnings: [] },
        { employee_id: 'e-ben', name: 'Ben', before: { minutes: 1800 }, after: { minutes: 2640 }, warnings: [] },
        { employee_id: 'e-cy', name: 'Cy', before: { minutes: 2700 }, after: { minutes: 2700 }, warnings: [] },
        { employee_id: 'e-di', name: 'Di', before: { minutes: 1800 }, after: { minutes: 2640 }, warnings: [] },
      ],
    }), {
      'e-amy': { max_weekly_minutes: 1800, allow_overtime: false },
      'e-di': { max_weekly_minutes: null, allow_overtime: true },
    })
    expect(verdict.tone).toBe('warn')
    expect(verdict.headline).toBe('Ready to approve · 2 things to know')
    expect(verdict.issues.map((issue) => `${issue.label} · ${issue.detail}`)).toEqual([
      'Amy goes to 35h · over their 30h cap',
      'Ben goes to 44h · over the 40h house policy',
    ])
    expect(verdict.issues[0].fix).toEqual({ kind: 'person', employeeId: 'e-amy' })
  })

  it('uses the server sentence for law it could not verify, and treats unavailable as a stop', () => {
    const unmapped = approvalVerdict(review({ compliance_status: 'unmapped', jurisdiction: { state: 'TX', status: 'unmapped', message: 'Legality was NOT verified for TX.' } }))
    expect(unmapped.issues[0]).toMatchObject({ tone: 'warn', detail: 'Legality was NOT verified for TX.' })
    const unavailable = approvalVerdict(review({ compliance_status: 'unavailable' }))
    expect(unavailable.tone).toBe('bad')
    expect(unavailable.headline).toBe('State rules could not be loaded')
    expect(unavailable.approveLabel).toBe('Approve')
  })

  it('lists refusals, advisories and real gaps — never advisory findings', () => {
    const verdict = approvalVerdict(review({
      rejected: [{ ...assignment(), employee_id: null, reasons: [{ code: 'x', message: 'would overlap', policy: false }] }],
      advisories: [{ message: 'past 40h', statute: 'FLSA', employee_name: 'Amy', shift_id: null }],
      findings: [
        { kind: 'coverage_gap', severity: 'gap', detail: 'Nobody 18:00–20:00 Monday.' },
        { kind: 'coverage_gap', severity: 'gap', detail: 'Nobody 18:00–20:00 Tuesday.' },
        { kind: 'break_relief_thin', severity: 'advisory', detail: 'thin' },
      ],
    }))
    expect(verdict.issues.map((issue) => issue.label)).toEqual([
      '1 assignment not staged', '1 statutory advisory to acknowledge', '2 × hours with nobody on',
    ])
  })

  it('shows cost and labor % as facts, or the server note when % is withheld', () => {
    const model = { labor: { forecast_sales_week: 1000, scheduled_cost_after: 250, labor_pct: 25 } } as unknown as AutopilotDemandModel
    const priced = approvalVerdict(review({ cost: { after: 250 } as ScheduleReview['cost'], demand_model: model }))
    expect(priced.facts).toEqual(['1/1 filled', '$250 scheduled', '25% of forecast sales'])
    const withheld = approvalVerdict(review({
      demand_model: { labor: { forecast_sales_week: 1000, scheduled_cost_after: 0, labor_pct: null, note: '2 seats are still open, so labor % isn\'t shown.' } } as unknown as AutopilotDemandModel,
    }))
    expect(withheld.facts).toContain('2 seats are still open, so labor % isn\'t shown.')
  })
})

describe('groupFindings', () => {
  it('puts gaps first, then the biggest groups, de-duplicating details', () => {
    const groups = groupFindings([
      { kind: 'break_relief_thin', severity: 'advisory', detail: 'a' },
      { kind: 'break_relief_thin', severity: 'advisory', detail: 'a' },
      { kind: 'break_relief_thin', severity: 'advisory', detail: 'b' },
      { kind: 'open_buffer_uncovered', severity: 'gap', detail: 'c' },
    ])
    expect(groups.map((group) => [group.kind, group.count, group.details])).toEqual([
      ['open_buffer_uncovered', 1, ['c']],
      ['break_relief_thin', 3, ['a', 'b']],
    ])
  })

  it('labels unknown kinds from the kind itself', () => {
    expect(findingLabel('coverage_gap')).toBe('hours with nobody on')
    expect(findingLabel('some_new_kind')).toBe('some new kind')
  })
})

describe('proposalPreviewShifts', () => {
  it('draws only a generated week — other reviews name shifts already on the board', () => {
    expect(proposalPreviewShifts(review({ kind: 'edit' }))).toEqual([])
    expect(proposalPreviewShifts(null)).toEqual([])
  })

  it('groups seats per shift with names, open seats, warnings and reasons', () => {
    const shifts = proposalPreviewShifts(review({
      assignments: [
        assignment({ shift_id: 'k1', employee_name: 'Amy' }),
        assignment({ shift_id: 'k1', employee_name: 'Ben', verdict: 'warn', reasons: [{ code: 'rest_gap', message: 'short rest', policy: true }] }),
        assignment({ shift_id: 'k2', employee_name: 'Cy', verdict: 'blocked' }),
        assignment({ shift_id: 'k3', starts_at: null }),
      ],
      unfilled: [{ ...openSeat(1), shift_id: 'k1' }, openSeat(9)],
    }))
    expect(shifts.map((shift) => [shift.id, shift.names, shift.open, shift.warn])).toEqual([
      ['k1', ['Amy', 'Ben'], 1, true],
      [`autopilot:${DAY}:lead:9`, [], 1, false],
    ])
    expect(shifts[0].reasons).toEqual(['short rest', CARD])
  })
})

describe('demandCoverage', () => {
  it('marks the slots the proposal staffs below demand, merged into runs', () => {
    const coverage = demandCoverage(review({
      assignments: [
        assignment({ starts_at: `${DAY}T07:00:00+00:00`, ends_at: `${DAY}T15:00:00+00:00` }),
        assignment({ employee_id: 'e-ben', starts_at: `${DAY}T08:00:00+00:00`, ends_at: `${DAY}T12:00:00+00:00` }),
        assignment({ employee_id: null, starts_at: `${DAY}T07:00:00+00:00`, ends_at: `${DAY}T15:00:00+00:00` }),
      ],
      demand_model: {
        days: [
          { date: DAY, closed: false, staffing_curve: [{ start: '07:00', end: '09:00', headcount: 2 }] },
          { date: '2026-10-06', closed: true, staffing_curve: [{ start: '07:00', end: '09:00', headcount: 2 }] },
        ],
      } as unknown as AutopilotDemandModel,
    }))
    expect(coverage).toEqual({
      [DAY]: [
        { start: 420, end: 480, demand: 2, covered: 1 },
        { start: 480, end: 540, demand: 2, covered: 2 },
      ],
    })
  })

  it('is empty without a demand model', () => {
    expect(demandCoverage(review())).toEqual({})
    expect(demandCoverage(null)).toEqual({})
  })
})
