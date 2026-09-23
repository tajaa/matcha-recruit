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
  it('shows Autopilot demand and keeps the server explanation verbatim', () => {
    renderPane({ review: review({
      demand_model: {
        week_start: '2026-08-23', days: [{
          date: '2026-08-24', weekday: 'Monday', open: '08:00', close: '16:00',
          window_with_buffers: '08:00–16:00', closed: false,
          forecast_sales: 1200, baseline_sales: 1300, sales_index: 0.92,
          weather: { condition: 'RAIN', precip_probability: 65, modifier: 0.9, sensitivity: 'rain_hurts' },
          labor_hours_target: 16, labor_hours_planned: 16, labor_method: 'splh',
          shape_source: 'history', staffing_curve: [], shifts_count: 2,
          notes: ['16.0h from $1,200.00 at $75.00/labor-hour learned from published weeks'],
        }],
        forecast_sales_week: 1200, labor_hours_week: 16, labor_hours_target_week: 16,
        confidence: 'medium', inputs_used: ['sales_history'], inputs_missing: ['hourly_sales'],
        capacity: { employees: 3, weekly_hours: 120 }, policy: {},
        notes: ['rain Monday trimmed demand 10%'],
        sentence: 'Forecast $1,200 from sales; 16 labor hours planned.',
        labor: {
          forecast_sales_week: 1200, scheduled_cost_after: 300, labor_pct: null,
          open_positions: 2, note: "2 seats are still open, so labor % isn't shown.",
        },
      },
    }) })
    // An open week never reads as a percentage — the server's reason instead.
    expect(within(screen.getByLabelText('Autopilot demand model')).getByText(/2 seats are still open, so labor % isn't shown\./)).toBeInTheDocument()
    expect(screen.queryByText(/of forecast sales/)).not.toBeInTheDocument()
    expect(screen.getByLabelText('Autopilot demand model')).toBeInTheDocument()
    expect(screen.getByText('Forecast $1,200 from sales; 16 labor hours planned.')).toBeInTheDocument()
    expect(screen.getByText('rain Monday trimmed demand 10%')).toBeInTheDocument()
    expect(screen.getByText('rain · 65%')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Autopilot day notes')).getByText(
      /16\.0h from \$1,200\.00 at \$75\.00\/labor-hour learned from published weeks/,
    )).toBeInTheDocument()
  })

  it('does not render an Autopilot block for a normal review', () => {
    renderPane()
    expect(screen.queryByLabelText('Autopilot demand model')).not.toBeInTheDocument()
  })

  it('answers "can I approve this?" first, then counts the evidence', () => {
    renderPane({
      review: review({
        assignments: [review().assignments[0], WARNED],
        rejected: [REJECTED],
        unfilled: [UNFILLED],
        advisories: [{ message: 'past 40h incurs weekly overtime', statute: 'FLSA', employee_name: 'Dana Reyes', shift_id: 's2' }],
        compliance_status: 'advisory',
      }),
    })

    const verdict = screen.getByLabelText('Approval verdict')
    expect(within(verdict).getByText('1 of 3 shifts would stay open')).toBeInTheDocument()
    expect(within(verdict).getByText('2/3 filled')).toBeInTheDocument()
    const issues = within(verdict).getByLabelText('Before you approve')
    expect(within(issues).getByText('1 shift left open')).toBeInTheDocument()
    expect(within(issues).getByText('1 assignment not staged')).toBeInTheDocument()
    expect(within(issues).getByText('1 statutory advisory to acknowledge')).toBeInTheDocument()
    // The verdict precedes every evidence block in the document.
    const evidence = screen.getByText('Staged').closest('details') as HTMLElement
    expect(verdict.compareDocumentPosition(evidence) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    const count = (label: string) => (screen.getByText(label).closest('summary') as HTMLElement).textContent
    expect(count('Staged')).toContain('2')
    expect(count('Not staged')).toContain('1')
    expect(count('Unfilled')).toContain('1')
  })

  it('collapses the evidence of a big proposal and keeps a small change open', () => {
    const many = Array.from({ length: 12 }, (_, index) => ({ ...review().assignments[0], shift_id: `s${index}` }))
    const { unmount } = renderPane({ review: review({ assignments: many }) })
    expect((screen.getByText('Staged').closest('details') as HTMLDetailsElement).open).toBe(false)
    unmount()
    renderPane()
    expect((screen.getByText('Staged').closest('details') as HTMLDetailsElement).open).toBe(true)
  })

  it('approves and cancels from the review when the caller can decide', () => {
    const onApprove = vi.fn()
    const onCancel = vi.fn()
    renderPane({ review: review({ unfilled: [UNFILLED] }), onApprove, onCancel })
    // With a gap the button names it, so approval happens with it in view.
    fireEvent.click(screen.getByRole('button', { name: 'Approve with 1 shift open' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onApprove).toHaveBeenCalledOnce()
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('disables the decision while the thread is mid-reply, and offers none without a handler', () => {
    const { unmount } = renderPane({ onApprove: vi.fn(), decisionDisabled: true })
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
    unmount()
    renderPane()
    expect(screen.queryByRole('button', { name: /^Approve/ })).not.toBeInTheDocument()
  })

  it('routes each fix to where it can be fixed', () => {
    const onAskHuume = vi.fn()
    const onSelectPerson = vi.fn()
    renderPane({
      review: review({
        unfilled: [UNFILLED],
        employees: [{ employee_id: 'e-dana', name: 'Dana Reyes', before: { minutes: 1800 }, after: { minutes: 2640 }, warnings: [] }],
      }),
      onAskHuume, onSelectPerson,
    })
    fireEvent.click(within(screen.getByLabelText('Approval verdict')).getByRole('button', { name: /Ask Huume/ }))
    expect(onAskHuume.mock.calls[0][0]).toMatch(/1 shift would stay open \(policy: second shift that day\)/)
    fireEvent.click(screen.getByRole('button', { name: /Show their week/ }))
    expect(onSelectPerson).toHaveBeenCalledWith('e-dana')
  })

  it('offers the board view only for a generated week', () => {
    const onShowWeek = vi.fn()
    const { unmount } = renderPane({ onShowWeek })
    expect(screen.queryByRole('button', { name: /See the week on the board/ })).not.toBeInTheDocument()
    unmount()
    renderPane({ review: review({ kind: 'week_draft' }), onShowWeek })
    fireEvent.click(screen.getByRole('button', { name: /See the week on the board/ }))
    expect(onShowWeek).toHaveBeenCalledOnce()
  })

  it('names each refusal with the server’s own reason', () => {
    renderPane({ review: review({ rejected: [REJECTED] }) })

    const block = screen.getByText('Not staged').closest('details') as HTMLElement
    expect(within(block).getByText(/would overlap the Shift Lead Mon Aug 24 06:00–14:00 shift earlier in this batch/)).toBeInTheDocument()
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

    const block = screen.getByText('Statutory advisories').closest('details') as HTMLElement
    expect(within(block).getByText(/Employee is scheduled 48.0h this week/)).toBeInTheDocument()
    expect(within(block).getByText(/\(FLSA, 29 U.S.C. § 207\(a\)\)/)).toBeInTheDocument()
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

    const findings = screen.getByLabelText('Findings by kind')
    expect(within(findings).getByText('gap')).toBeInTheDocument()
    expect(within(findings).getByText('advisory')).toBeInTheDocument()
    expect(within(findings).getByText(/Amy is already on overlapping shifts/)).toBeInTheDocument()
    // Only the real hole reaches the verdict; the advisory stays evidence.
    const verdict = screen.getByLabelText('Before you approve')
    expect(within(verdict).getByText('1 × someone already double-booked')).toBeInTheDocument()
    expect(within(verdict).queryByText(/carries 6 of 6/)).not.toBeInTheDocument()
  })

  it('folds identical findings into one line with a count', () => {
    renderPane({
      review: review({
        findings: Array.from({ length: 28 }, (_, index) => ({
          kind: 'break_relief_thin', severity: 'advisory', detail: `Shift ${index % 2} has no spare cover.`,
        })),
      }),
    })
    const findings = screen.getByLabelText('Findings by kind')
    expect(within(findings).getAllByRole('listitem').filter((item) => item.parentElement === findings)).toHaveLength(1)
    expect(within(findings).getByText('28')).toBeInTheDocument()
    expect(within(findings).getByText('Shift 0 has no spare cover.')).toBeInTheDocument()
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
