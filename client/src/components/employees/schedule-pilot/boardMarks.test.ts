import { describe, expect, it } from 'vitest'
import type { ScheduleReview, Shift } from '../../../types/employeeSchedule'
import { changedShiftIds, proposalMarks, shiftSignature } from './boardMarks'

function review(overrides: Partial<ScheduleReview> = {}): ScheduleReview {
  return {
    proposal_id: 'p1', kind: 'edit', compliance_status: 'verified',
    assignments: [], rejected: [], unfilled: [], employees: [], advisories: [], findings: [],
    jurisdiction: { state: 'CA', status: 'curated', message: 'On file.' },
    ...overrides,
  }
}

const item = (shiftId: string, op: string, name: string | null, extra: Record<string, unknown> = {}) => ({
  shift_id: shiftId, role: 'Barista', starts_at: '2026-09-14T09:00:00Z', ends_at: '2026-09-14T17:00:00Z',
  employee_id: 'e1', employee_name: name, op, verdict: 'ok' as const, reasons: [], ...extra,
})

describe('proposalMarks', () => {
  const board = new Set(['s1', 's2', 's3'])

  it('says what each op does to the shift it touches', () => {
    const marks = proposalMarks(review({
      assignments: [
        item('s1', 'assign', 'Sam Ferreira'),
        item('s1', 'unassign', 'Dana Lee'),
        item('s2', 'retime', null),
        item('s3', 'cancel', null),
        item('s3', 'swap', 'Jonah Brooks'),
      ],
    }), board)
    expect(marks.get('s1')?.chips.map((chip) => chip.label)).toEqual(['+ Sam', '− Dana'])
    expect(marks.get('s2')?.chips[0].label).toMatch(/^↻ /)
    expect(marks.get('s3')?.chips.map((chip) => chip.tone)).toEqual(['cancel', 'move'])
  })

  it('flags warnings, shows refused and still-open seats, and skips blocked rows', () => {
    const marks = proposalMarks(review({
      assignments: [
        item('s1', 'assign', 'Sam', { verdict: 'warn', reasons: [{ code: 'rest_gap', message: 'Less than 8h rest', policy: true }] }),
        item('s2', 'assign', 'Ellie', { verdict: 'blocked' }),
      ],
      rejected: [{ ...item('s2', 'assign', 'Maria'), reasons: [{ code: 'existing_overlap', message: 'Overlaps', policy: false }] }],
      unfilled: [{ shift_id: 's3', role: 'Barista', starts_at: null, ends_at: null, reason: 'Nobody qualified', exclusions: {} }],
    }), board)
    expect(marks.get('s1')).toMatchObject({ warn: true, chips: [{ label: '+ Sam', title: 'Less than 8h rest' }] })
    expect(marks.get('s2')?.chips).toEqual([{ tone: 'blocked', label: '✕ Maria not staged', title: 'Overlaps' }])
    expect(marks.get('s3')?.chips).toEqual([{ tone: 'open', label: 'stays open', title: 'Nobody qualified' }])
  })

  it('marks nothing for a generated week, a missing review, or a shift not on the board', () => {
    expect(proposalMarks(review({ kind: 'week_draft', assignments: [item('s1', 'assign', 'Sam')] }), board).size).toBe(0)
    expect(proposalMarks(null, board).size).toBe(0)
    expect(proposalMarks(review({ assignments: [item('new-1', 'create', 'Sam'), item(null as unknown as string, 'assign', 'X')] }), board).size).toBe(0)
  })

  it('names someone unnamed as "someone"', () => {
    expect(proposalMarks(review({ assignments: [item('s1', 'assign', '  ')] }), board).get('s1')?.chips[0].label).toBe('+ someone')
  })
})

describe('changedShiftIds', () => {
  const shift = (id: string, extra: Partial<Shift> = {}) => ({
    id, starts_at: '2026-09-14T09:00:00Z', ends_at: '2026-09-14T17:00:00Z', status: 'draft', role: 'Barista',
    required_staff: 1, assignments: [{ employee_id: 'e1', name: 'Sam' }], ...extra,
  } as unknown as Shift)

  it('finds new shifts and shifts whose time, people or status changed', () => {
    const before = new Map([shift('a'), shift('b'), shift('c')].map((s) => [s.id, shiftSignature(s)]))
    const after = [
      shift('a'),
      shift('b', { assignments: [{ employee_id: 'e2', name: 'Dana' }] as Shift['assignments'] }),
      shift('c', { ends_at: '2026-09-14T18:00:00Z' }),
      shift('d'),
    ]
    expect([...changedShiftIds(before, after)].sort()).toEqual(['b', 'c', 'd'])
  })
})
