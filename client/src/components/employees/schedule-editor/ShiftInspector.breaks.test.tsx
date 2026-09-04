import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ShiftInspector from './ShiftInspector'

const fetchShiftBreakStagger = vi.fn()
const updateAssignmentBreakPlan = vi.fn().mockResolvedValue(undefined)

vi.mock('../../../api/employees/employeeSchedule', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchShiftBreakStagger: (...args: unknown[]) => fetchShiftBreakStagger(...args),
  updateAssignmentBreakPlan: (...args: unknown[]) => updateAssignmentBreakPlan(...args),
  updateAssignmentNote: vi.fn().mockResolvedValue(undefined),
}))

function assignment(overrides: Record<string, unknown> = {}) {
  return {
    employee_id: 'emp-1',
    name: 'Ada Ling',
    job_title: 'Barista',
    status: 'accepted',
    availability_overridden: false,
    availability_override_at: null,
    manager_note: null,
    manager_note_visible_to_employee: true,
    compliance_guidance: {
      status: 'complete',
      summary: 'Mandatory 30-minute unpaid meal break by 2 PM',
      requirements: [],
      advisories: [],
    },
    planned_breaks: null,
    ...overrides,
  }
}

function staggerResult(overrides: Record<string, unknown> = {}) {
  return {
    employee_id: 'emp-1',
    kind: 'meal',
    ordinal: 1,
    status: 'suggested',
    duration_minutes: 30,
    suggested_start: '2026-08-31T12:00:00-07:00',
    suggested_end: '2026-08-31T12:30:00-07:00',
    reason: null,
    ...overrides,
  }
}

function renderWith(assignments: unknown[], plan: Record<string, unknown>, readOnly = false) {
  fetchShiftBreakStagger.mockResolvedValue({
    schema_version: 1, max_concurrent_breaks: 1, results: [], advisories: [], ...plan,
  })
  const onAssignmentUpdated = vi.fn().mockResolvedValue(undefined)
  render(
    <ShiftInspector
      shift={{
        id: 'shift-1', starts_at: '2026-08-31T09:00:00Z', ends_at: '2026-08-31T17:00:00Z',
        role: null, job_id: null, department: null, break_minutes: 30,
        required_staff: 1, notes: null, kind: 'work', training_requirement_id: null,
        assignments,
      } as never}
      defaults={null}
      locationId="loc-1"
      locationName="Downtown"
      roster={[]}
      jobs={[]}
      trainingEnabled={false}
      readOnly={readOnly}
      saving={false}
      onCreate={vi.fn().mockResolvedValue(undefined)}
      onUpdate={vi.fn().mockResolvedValue(undefined)}
      onDelete={vi.fn().mockResolvedValue(undefined)}
      onAssignmentUpdated={onAssignmentUpdated}
      onClose={vi.fn()}
    />,
  )
  return onAssignmentUpdated
}

describe('ShiftInspector break staggering', () => {
  beforeEach(() => {
    fetchShiftBreakStagger.mockReset()
    updateAssignmentBreakPlan.mockClear()
  })

  it('seeds the editable time from the suggestion and saves what the manager keeps', async () => {
    renderWith([assignment()], { results: [staggerResult()] })

    const input = await screen.findByLabelText('30-min meal break start for Ada Ling')
    expect(input).toHaveValue('12:00')

    fireEvent.change(input, { target: { value: '12:45' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save break times' }))

    await waitFor(() => expect(updateAssignmentBreakPlan).toHaveBeenCalled())
    const [shiftId, employeeId, planned] = updateAssignmentBreakPlan.mock.calls[0]
    expect(shiftId).toBe('shift-1')
    expect(employeeId).toBe('emp-1')
    // The clock is replaced in place: the suggestion's date and offset survive.
    expect(planned).toEqual([expect.objectContaining({
      kind: 'meal', ordinal: 1, duration_minutes: 30,
      start_local: '2026-08-31T12:45:00-07:00', source: 'manager',
    })])
  })

  it('prefers an already-saved time over a fresh suggestion', async () => {
    renderWith(
      [assignment({
        planned_breaks: [{
          kind: 'meal', ordinal: 1, start_local: '2026-08-31T13:15:00-07:00',
          duration_minutes: 30, source: 'manager',
        }],
      })],
      { results: [staggerResult()] },
    )

    expect(await screen.findByLabelText('30-min meal break start for Ada Ling')).toHaveValue('13:15')
    expect(screen.getByText('Saved')).toBeInTheDocument()
  })

  it('shows the reason when a break cannot be placed, and keeps the legal line', async () => {
    renderWith([assignment()], {
      results: [staggerResult({
        status: 'insufficient_coverage', suggested_start: null, suggested_end: null,
        reason: 'No 30-minute slot inside its legal window keeps enough staff on the floor.',
      })],
    })

    expect(await screen.findByText(/keeps enough staff on the floor/)).toBeInTheDocument()
    expect(screen.getByText('Mandatory 30-minute unpaid meal break by 2 PM')).toBeInTheDocument()
  })

  it('surfaces an unresolved rule instead of a time', async () => {
    renderWith([assignment()], {
      results: [staggerResult({
        status: 'unresolved', suggested_start: null, suggested_end: null,
        reason: 'Break requirements could not be mapped for this location; verify manually.',
      })],
    })

    expect(await screen.findByText(/could not be mapped/)).toBeInTheDocument()
    expect(screen.getByLabelText('30-min meal break start for Ada Ling')).toHaveValue('')
  })

  it('renders the shift-level coverage shortfall advisory', async () => {
    renderWith([assignment()], {
      results: [staggerResult()],
      advisories: [{
        check: 'break_stagger', code: 'coverage_shortfall', severity: 'advisory',
        message: 'This shift has no spare staffing above its required 1.',
      }],
    })

    expect(await screen.findByText(/no spare staffing above its required 1/)).toBeInTheDocument()
  })

  it('renders no stagger control for a waived requirement', async () => {
    // A waived meal produces no stagger result at all, so there is nothing to time.
    renderWith([assignment({
      compliance_guidance: {
        status: 'complete',
        summary: 'Meal break waiver on file; no mandatory meal break applies to this shift.',
        requirements: [], advisories: [],
      },
    })], { results: [] })

    await waitFor(() => expect(fetchShiftBreakStagger).toHaveBeenCalled())
    expect(screen.queryByText('Suggested break times')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save break times' })).not.toBeInTheDocument()
  })

  it('does not offer a save control on a locked published shift', async () => {
    renderWith([assignment()], { results: [staggerResult()] }, true)

    expect(await screen.findByLabelText('30-min meal break start for Ada Ling')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save break times' })).not.toBeInTheDocument()
  })

  it('does not query suggestions for a shift with nobody on it', async () => {
    renderWith([], { results: [] })

    await waitFor(() => expect(screen.getByText('Nobody yet')).toBeInTheDocument())
    expect(fetchShiftBreakStagger).not.toHaveBeenCalled()
  })
})
