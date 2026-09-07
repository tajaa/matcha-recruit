import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScenariosStrip from './ScenariosStrip'
import type { Scenario } from '../../../hooks/employees/useScheduleScenarios'
import type { ScheduleReview } from '../../../types/employeeSchedule'

function review(overrides: Partial<ScheduleReview> = {}): ScheduleReview {
  return {
    proposal_id: 'p1', kind: 'edit', compliance_status: 'verified',
    assignments: [], rejected: [], unfilled: [], employees: [], advisories: [], findings: [],
    jurisdiction: { state: 'CA', status: 'curated', message: 'on file' },
    ...overrides,
  }
}

function assignment(shiftId: string, verdict: 'ok' | 'warn' | 'blocked' = 'ok') {
  return {
    shift_id: shiftId, role: 'Shift Lead', starts_at: '2026-08-24T06:00:00+00:00', ends_at: '2026-08-24T14:00:00+00:00',
    employee_id: 'e1', employee_name: 'Dana Reyes', op: 'assign', verdict, reasons: [],
  }
}

function scenario(overrides: Partial<Scenario> = {}): Scenario {
  return {
    proposal_id: 'proposal-1',
    label: 'Spread the leads',
    review: review({ assignments: [assignment('s1'), assignment('s2')] }),
    pill_text: 'pill',
    created_at: 0,
    status: 'ready',
    ...overrides,
  }
}

const PROPS = {
  scenarios: [] as Scenario[],
  selectedIds: [] as string[],
  onSelect: vi.fn(),
  staged: null,
  stagedSelected: false,
  onSelectStaged: vi.fn(),
  previewing: false,
  notice: null,
  onDismissNotice: vi.fn(),
  onPreview: vi.fn(),
  jobs: [{ id: 'job-1', name: 'Shift Lead' }, { id: 'job-2', name: 'Barista' }],
  people: [{ id: 'e1', name: 'Dana Reyes' }, { id: 'e2', name: 'Ben Ortiz' }],
  selectedShiftIds: [] as string[],
  onApply: vi.fn(),
  onStage: vi.fn(),
  onDiscard: vi.fn(),
  canStage: true,
}

function renderStrip(overrides: Partial<React.ComponentProps<typeof ScenariosStrip>> = {}) {
  const props = { ...PROPS, ...overrides }
  render(<ScenariosStrip {...props} />)
  return props
}

beforeEach(() => {
  for (const value of Object.values(PROPS)) if (typeof value === 'function') (value as ReturnType<typeof vi.fn>).mockReset()
})

describe('ScenariosStrip — chips', () => {
  it('summarises each scenario without the manager opening it', () => {
    renderStrip({
      scenarios: [scenario({
        review: review({
          assignments: [assignment('s1'), assignment('s2')],
          unfilled: [{ shift_id: 's3', role: 'Shift Lead', starts_at: null, ends_at: null, reason: 'policy: second shift that day', exclusions: {} }],
        }),
      })],
    })

    expect(screen.getByText('Spread the leads')).toBeInTheDocument()
    expect(screen.getByText('2 staged · 1 open')).toBeInTheDocument()
  })

  it('shows the thread’s staged action alongside the simulations', () => {
    const props = renderStrip({
      staged: { label: 'Huume · staged change', staged: 4, unfilled: 2, rejected: 5, compliance: 'unmapped' },
    })

    expect(screen.getByText('Huume · staged change')).toBeInTheDocument()
    expect(screen.getByText('4 staged · 5 refused · 2 open')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Huume · staged change'))
    expect(props.onSelectStaged).toHaveBeenCalled()
  })

  it('selects one chip on a click and compares on a shift-click', () => {
    const props = renderStrip({ scenarios: [scenario()] })

    fireEvent.click(screen.getByText('Spread the leads'))
    expect(props.onSelect).toHaveBeenCalledWith('proposal-1')

    fireEvent.click(screen.getByText('Spread the leads'), { shiftKey: true })
    expect(props.onSelect).toHaveBeenLastCalledWith('proposal-1', { compare: true })
  })

  it('counts only the rows the chip would actually stage', () => {
    // A blocked row is not staged anywhere else either — the chip must not
    // promise a seat the apply would refuse.
    renderStrip({
      scenarios: [scenario({ review: review({ assignments: [assignment('s1'), assignment('s2', 'blocked')] }) })],
    })

    expect(screen.getByText('1 staged')).toBeInTheDocument()
  })

  it('marks a scenario that has already been applied or staged', () => {
    const { unmount } = render(<ScenariosStrip {...PROPS} scenarios={[scenario({ status: 'applied' })]} />)
    expect(screen.getByText('applied')).toBeInTheDocument()
    unmount()

    render(<ScenariosStrip {...PROPS} scenarios={[scenario({ status: 'staged' })]} />)
    expect(screen.getByText('staged')).toBeInTheDocument()
  })
})

describe('ScenariosStrip — acting on the selected scenario', () => {
  it('offers stage, apply and discard, wired to the proposal', () => {
    const props = renderStrip({ scenarios: [scenario()], selectedIds: ['proposal-1'] })

    fireEvent.click(screen.getByRole('button', { name: /Stage in thread/ }))
    expect(props.onStage).toHaveBeenCalledWith('proposal-1')

    fireEvent.click(screen.getByRole('button', { name: /Apply now/ }))
    expect(props.onApply).toHaveBeenCalledWith('proposal-1')

    fireEvent.click(screen.getByRole('button', { name: 'Discard Spread the leads' }))
    expect(props.onDiscard).toHaveBeenCalledWith('proposal-1')
  })

  it('cannot stage into a thread that is not open', () => {
    renderStrip({ scenarios: [scenario()], selectedIds: ['proposal-1'], canStage: false })
    expect(screen.getByRole('button', { name: /Stage in thread/ })).toBeDisabled()
  })

  it('sends a staged scenario back to its thread to be cancelled', () => {
    // The thread owns the staged action; discarding here would leave the
    // thread pointing at a row that no longer exists.
    renderStrip({ scenarios: [scenario({ status: 'staged' })], selectedIds: ['proposal-1'] })

    const discard = screen.getByRole('button', { name: 'Discard Spread the leads' })
    expect(discard).toBeDisabled()
    expect(discard).toHaveAttribute('title', 'Staged in the Huume thread — cancel it there')
  })

  it('offers nothing to act on once the scenario is applied', () => {
    renderStrip({ scenarios: [scenario({ status: 'applied' })], selectedIds: ['proposal-1'] })

    expect(screen.queryByRole('button', { name: /Apply now/ })).not.toBeInTheDocument()
    expect(screen.getByText('Applied')).toBeInTheDocument()
  })

  it('offers nothing while two are being compared — the actions would be ambiguous', () => {
    renderStrip({
      scenarios: [scenario(), scenario({ proposal_id: 'proposal-2', label: 'Without Dana' })],
      selectedIds: ['proposal-1', 'proposal-2'],
    })
    expect(screen.queryByRole('button', { name: /Apply now/ })).not.toBeInTheDocument()
  })
})

describe('ScenariosStrip — new scenario form', () => {
  function openForm(overrides: Partial<React.ComponentProps<typeof ScenariosStrip>> = {}) {
    const props = renderStrip(overrides)
    fireEvent.click(screen.getByRole('button', { name: /New scenario/ }))
    return props
  }

  it('previews every open shift by default', () => {
    const props = openForm()

    fireEvent.click(screen.getByRole('button', { name: /Preview/ }))

    expect(props.onPreview).toHaveBeenCalledWith({
      label: null, job_id: null, shift_ids: null, employee_id: null,
      exclude_employee_ids: null, allow_split_shift: false,
    })
  })

  it('narrows to one job, one person, and allows splits when asked', () => {
    const props = openForm()

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Leads only' } })
    fireEvent.click(screen.getByRole('button', { name: 'One job' }))
    fireEvent.change(screen.getByLabelText('Job'), { target: { value: 'job-1' } })
    fireEvent.change(screen.getByLabelText('Only this person'), { target: { value: 'e1' } })
    fireEvent.click(screen.getByLabelText('Allow split shifts'))
    fireEvent.click(screen.getByRole('button', { name: /Preview/ }))

    expect(props.onPreview).toHaveBeenCalledWith({
      label: 'Leads only', job_id: 'job-1', shift_ids: null, employee_id: 'e1',
      exclude_employee_ids: null, allow_split_shift: true,
    })
  })

  it('will not preview a job scenario until a job is chosen', () => {
    openForm()
    fireEvent.click(screen.getByRole('button', { name: 'One job' }))
    expect(screen.getByRole('button', { name: /Preview/ })).toBeDisabled()
  })

  it('scopes to the shifts picked on the board, and says how many', () => {
    const props = openForm({ selectedShiftIds: ['s1', 's2'] })

    fireEvent.click(screen.getByRole('button', { name: 'Selected (2)' }))
    fireEvent.click(screen.getByRole('button', { name: /Preview/ }))

    expect(props.onPreview).toHaveBeenCalledWith(expect.objectContaining({ shift_ids: ['s1', 's2'] }))
  })

  it('cannot scope to selected shifts when none are picked', () => {
    openForm()
    expect(screen.getByRole('button', { name: 'Selected (0)' })).toBeDisabled()
  })

  it('leaves people out and lets them back in', () => {
    const props = openForm()

    fireEvent.change(screen.getByLabelText('Leave someone out'), { target: { value: 'e2' } })
    expect(screen.getByRole('button', { name: 'Include Ben Ortiz again' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Preview/ }))
    expect(props.onPreview).toHaveBeenCalledWith(expect.objectContaining({ exclude_employee_ids: ['e2'] }))
  })
})

describe('ScenariosStrip — notices', () => {
  it('says why nothing could be filled, with the seats it could not staff', () => {
    const props = renderStrip({
      notice: {
        status: 'empty',
        message: 'No open shift could be filled under the staffing rules.',
        unfilled: [
          { shift_id: 's1', role: 'Shift Lead', starts_at: null, ends_at: null, reason: 'policy: second shift that day', exclusions: {} },
          { shift_id: 's2', role: 'Barista', starts_at: null, ends_at: null, reason: 'not qualified for the shift job', exclusions: {} },
        ],
      },
    })

    const notice = screen.getByRole('status')
    expect(notice).toHaveTextContent('No open shift could be filled under the staffing rules.')
    expect(notice).toHaveTextContent('Shift Lead: policy: second shift that day; Barista: not qualified for the shift job')

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(props.onDismissNotice).toHaveBeenCalled()
  })
})
