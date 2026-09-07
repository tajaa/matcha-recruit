import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ReviewPane from './ReviewPane'
import type { ScheduleReview } from '../../../types/employeeSchedule'

function review(overrides: Partial<ScheduleReview> = {}): ScheduleReview {
  return {
    proposal_id: 'p1',
    kind: 'edit',
    compliance_status: 'verified',
    assignments: [{
      shift_id: 's1', role: 'Shift Lead', starts_at: '2026-08-24T06:00:00+00:00', ends_at: '2026-08-24T14:00:00+00:00',
      employee_id: 'e-dana', employee_name: 'Dana Reyes', op: 'assign', verdict: 'ok', reasons: [],
    }],
    rejected: [],
    unfilled: [],
    employees: [],
    advisories: [],
    findings: [],
    jurisdiction: { state: 'CA', status: 'curated', message: 'Scheduling law for CA is on file (hand-curated).' },
    ...overrides,
  }
}

const WARNED = {
  shift_id: 's2', role: 'Shift Lead', starts_at: '2026-08-24T14:00:00+00:00', ends_at: '2026-08-24T22:00:00+00:00',
  employee_id: 'e-dana', employee_name: 'Dana Reyes', op: 'assign', verdict: 'warn' as const,
  reasons: [{ code: 'rest_gap', message: 'only 0.0h rest next to another shift (policy: 8h minimum)', policy: true }],
}

const REJECTED = {
  shift_id: 's9', role: 'Shift Lead', starts_at: '2026-08-24T10:00:00+00:00', ends_at: '2026-08-24T18:00:00+00:00',
  employee_id: null, employee_name: 'Dana Reyes', op: 'assign',
  reasons: [{ code: 'intra_batch_overlap', message: 'would overlap the Shift Lead Mon Aug 24 06:00–14:00 shift earlier in this batch', policy: false }],
}

const UNFILLED = {
  shift_id: 's3', role: 'Shift Lead', starts_at: '2026-08-25T06:00:00+00:00', ends_at: '2026-08-25T14:00:00+00:00',
  reason: 'policy: second shift that day',
  exclusions: { 'policy: second shift that day': 2, 'not qualified for the shift job': 1 },
}

function renderPane(props: Partial<React.ComponentProps<typeof ReviewPane>> = {}) {
  return render(<ReviewPane review={review()} title="Huume · staged change" {...props} />)
}

describe('ReviewPane — nothing staged', () => {
  it('invites the manager to act instead of showing an empty frame', () => {
    render(<ReviewPane review={null} title="Nothing staged" />)
    expect(screen.getByText(/Nothing is staged/)).toBeInTheDocument()
  })

  it('uses the caller’s own hint when it has a better one', () => {
    render(<ReviewPane review={null} title="Nothing staged" emptyHint="Run a scenario to see one here." />)
    expect(screen.getByText('Run a scenario to see one here.')).toBeInTheDocument()
  })
})

describe('ReviewPane — what a change will do', () => {
  it('counts staged, not staged, unfilled, warnings and advisories in the header', () => {
    renderPane({
      review: review({
        assignments: [review().assignments[0], WARNED],
        rejected: [REJECTED],
        unfilled: [UNFILLED],
        advisories: [{ message: 'past 40h incurs weekly overtime', statute: 'FLSA', employee_name: 'Dana Reyes', shift_id: 's2' }],
        compliance_status: 'advisory',
      }),
    })

    const line = (text: string) => screen.getByText((_content, element) => element?.textContent === text)
    expect(line('2 staged')).toBeInTheDocument()
    expect(line('1 not staged')).toBeInTheDocument()
    expect(line('1 unfilled')).toBeInTheDocument()
    expect(line('1 with warnings')).toBeInTheDocument()
    expect(line('1 advisories')).toBeInTheDocument()
  })

  it('names each refusal with the server’s own reason', () => {
    renderPane({ review: review({ rejected: [REJECTED] }) })

    expect(screen.getByText('Not staged')).toBeInTheDocument()
    expect(screen.getByText(/would overlap the Shift Lead Mon Aug 24 06:00–14:00 shift earlier in this batch/)).toBeInTheDocument()
  })

  it('marks a policy warning as policy so it is never mistaken for law', () => {
    renderPane({ review: review({ assignments: [WARNED] }) })
    expect(screen.getByText(/only 0.0h rest next to another shift \(policy: 8h minimum\) \(policy\)/)).toBeInTheDocument()
  })

  it('spells out an open seat’s reason and the full exclusion breakdown', () => {
    renderPane({ review: review({ unfilled: [UNFILLED] }) })

    // The headline reason, then every refusal counted — not just the commonest.
    const reason = screen.getByText((_content, element) => element?.textContent
      === 'policy: second shift that day · 2 policy: second shift that day, 1 not qualified for the shift job')
    expect(reason).toBeInTheDocument()
    expect(within(reason).getByText('· 2 policy: second shift that day, 1 not qualified for the shift job')).toBeInTheDocument()
  })

  it('quotes a statutory advisory with its statute', () => {
    renderPane({
      review: review({
        compliance_status: 'advisory',
        advisories: [{ message: 'Employee is scheduled 48.0h this week', statute: 'FLSA, 29 U.S.C. § 207(a)', employee_name: 'Dana Reyes', shift_id: 's1' }],
      }),
    })

    expect(screen.getByText(/Employee is scheduled 48.0h this week/)).toBeInTheDocument()
    expect(screen.getByText(/\(FLSA, 29 U.S.C. § 207\(a\)\)/)).toBeInTheDocument()
  })

  it('separates a real hole from something worth a look in the findings', () => {
    renderPane({
      review: review({
        findings: [
          { kind: 'existing_double_booking', severity: 'gap', detail: 'Amy is already on overlapping shifts' },
          { kind: 'staffing_concentration', severity: 'advisory', detail: 'Dana Reyes carries 6 of 6 proposed positions' },
        ],
      }),
    })

    expect(screen.getByText('gap')).toBeInTheDocument()
    expect(screen.getByText('advisory')).toBeInTheDocument()
    expect(screen.getByText(/Amy is already on overlapping shifts/)).toBeInTheDocument()
  })

  it('shows each person’s hours before and after with their warnings', () => {
    renderPane({
      review: review({
        employees: [{
          employee_id: 'e-dana', name: 'Dana Reyes',
          before: { minutes: 480, shifts: 1, days: 1 },
          after: { minutes: 960, shifts: 2, days: 2 },
          warnings: ['only 0.0h rest next to another shift (policy: 8h minimum)'],
        }],
      }),
    })

    expect(screen.getByText('Load')).toBeInTheDocument()
    expect(screen.getByText('1→2 shifts · 1→2 days')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Dana Reyes: 8h now, 16h after this change' })).toBeInTheDocument()
    expect(screen.getByText('only 0.0h rest next to another shift (policy: 8h minimum)')).toBeInTheDocument()
  })

  it('leaves a blocked assignment out of the staged list', () => {
    renderPane({
      review: review({
        assignments: [{ ...review().assignments[0], verdict: 'blocked' as const }],
      }),
    })
    expect(screen.queryByText('Staged')).not.toBeInTheDocument()
  })
})

describe('ReviewPane — compliance banner', () => {
  it('repeats the server’s sentence for a state whose law is on file', () => {
    renderPane()
    expect(screen.getByRole('status')).toHaveTextContent('Law on file · no statutory advisories.')
    expect(screen.getByRole('status')).toHaveTextContent('Scheduling law for CA is on file (hand-curated).')
  })

  it('says plainly when legality was not verified, in the server’s words', () => {
    renderPane({
      review: review({
        compliance_status: 'unmapped',
        jurisdiction: { state: 'TX', status: 'unmapped', message: 'Legality was NOT verified for TX — Matcha has no researched scheduling thresholds for it.' },
      }),
    })

    const banner = screen.getByRole('status')
    expect(banner).toHaveTextContent('Legality NOT verified.')
    expect(banner).toHaveTextContent('Legality was NOT verified for TX')
  })

  it('distinguishes rules that could not be loaded from rules that do not exist', () => {
    renderPane({
      review: review({
        compliance_status: 'unavailable',
        jurisdiction: { state: 'TX', status: 'unavailable', message: 'Could not load TX’s scheduling-law thresholds just now — this is temporary, not an all-clear.' },
      }),
    })
    expect(screen.getByRole('status')).toHaveTextContent('State rules could not be loaded.')
  })
})

describe('ReviewPane — acting on a row', () => {
  it('shows a staged shift on the board', () => {
    const onShowShift = vi.fn()
    renderPane({ onShowShift })

    fireEvent.click(screen.getAllByRole('button', { name: 'Show this shift on the board' })[0])
    expect(onShowShift).toHaveBeenCalledWith('s1')
  })

  it('hands a refusal to Huume as a question with its reason', () => {
    const onAskHuume = vi.fn()
    renderPane({ review: review({ assignments: [], rejected: [REJECTED] }), onAskHuume })

    fireEvent.click(screen.getAllByRole('button', { name: 'Ask Huume about this' })[0])
    expect(onAskHuume).toHaveBeenCalledWith(expect.stringContaining("wasn't staged"))
    expect(onAskHuume).toHaveBeenCalledWith(expect.stringContaining('would overlap'))
  })

  it('offers no row actions when the caller cannot act on them', () => {
    renderPane()
    expect(screen.queryByRole('button', { name: 'Show this shift on the board' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ask Huume about this' })).not.toBeInTheDocument()
  })
})

describe('ReviewPane — comparing two scenarios', () => {
  const left = review({
    assignments: [review().assignments[0]],
    employees: [{ employee_id: 'e-dana', name: 'Dana Reyes', before: { minutes: 0 }, after: { minutes: 960 }, warnings: [] }],
  })
  const right = review({
    assignments: [{ ...review().assignments[0], employee_id: 'e-ben', employee_name: 'Ben Ortiz' }],
    employees: [{ employee_id: 'e-ben', name: 'Ben Ortiz', before: { minutes: 0 }, after: { minutes: 480 }, warnings: [] }],
  })

  it('shows what the second scenario does differently, and drops the per-block lists', () => {
    renderPane({ review: left, compare: { label: 'Without Dana', review: right } })

    expect(screen.getByText('Compared with')).toBeInTheDocument()
    expect(screen.getByText('Without Dana')).toBeInTheDocument()
    // Each name shows twice: once in the changed-shift row, once in the hours list.
    expect(screen.getAllByText('Dana Reyes')).toHaveLength(2)
    expect(screen.getAllByText('Ben Ortiz')).toHaveLength(2)
    expect(screen.getByText('1/0 vs 1/0 staged/unfilled')).toBeInTheDocument()
    expect(screen.getByText('Hours after each')).toBeInTheDocument()
    // The single-scenario blocks give way to the diff.
    expect(screen.queryByText('Staged')).not.toBeInTheDocument()
  })

  it('says so when two scenarios staff the week identically', () => {
    renderPane({ review: left, compare: { label: 'Same again', review: left } })
    expect(screen.getByText('Both scenarios staff every shift the same way.')).toBeInTheDocument()
  })
})
