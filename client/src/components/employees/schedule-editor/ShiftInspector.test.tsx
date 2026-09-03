import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ShiftInspector from './ShiftInspector'
import { NO_ROLES_MESSAGE, ROLE_REQUIRED_MESSAGE } from './roleSelection'

const jobs = [{
  id: 'job-1', name: 'Barista', location_id: 'loc-1', color: null, notes: null,
  credential_grace_days: null, employee_ids: [], credential_requirements: [],
}]

function renderInspector() {
  const onCreate = vi.fn().mockResolvedValue(undefined)
  render(
    <ShiftInspector
      shift={null}
      defaults={{ date: '2026-08-31', minute: 540 }}
      locationId="loc-1"
      locationName="Downtown"
      roster={[]}
      jobs={jobs}
      trainingEnabled={false}
      readOnly={false}
      saving={false}
      onCreate={onCreate}
      onUpdate={vi.fn().mockResolvedValue(undefined)}
      onDelete={vi.fn().mockResolvedValue(undefined)}
      onAssignmentUpdated={vi.fn().mockResolvedValue(undefined)}
      onClose={vi.fn()}
    />,
  )
  return onCreate
}

function renderEditingInspector() {
  const onUpdate = vi.fn().mockResolvedValue(undefined)
  render(
    <ShiftInspector
      shift={{
        id: 'shift-1', starts_at: '2026-08-31T09:00:00Z', ends_at: '2026-08-31T17:00:00Z',
        role: null, job_id: null, department: null, break_minutes: 0,
        required_staff: 1, notes: null, kind: 'work', training_requirement_id: null,
        assignments: [],
      } as never}
      defaults={null}
      locationId="loc-1"
      locationName="Downtown"
      roster={[]}
      jobs={[]}
      trainingEnabled={false}
      readOnly={false}
      saving={false}
      onCreate={vi.fn().mockResolvedValue(undefined)}
      onUpdate={onUpdate}
      onDelete={vi.fn().mockResolvedValue(undefined)}
      onAssignmentUpdated={vi.fn().mockResolvedValue(undefined)}
      onClose={vi.fn()}
    />,
  )
  return onUpdate
}

describe('ShiftInspector validation', () => {
  it('requires a company role before creating a shift', async () => {
    const onCreate = renderInspector()

    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(ROLE_REQUIRED_MESSAGE)
    expect(screen.getByLabelText(/Role/)).toHaveAttribute('aria-invalid', 'true')
    expect(onCreate).not.toHaveBeenCalled()
  })

  it('leaves a new shift break blank so the server generates it', async () => {
    const onCreate = renderInspector()

    fireEvent.change(screen.getByLabelText(/Role/), { target: { value: 'job-1' } })
    expect(screen.getByLabelText('Planned break (minutes)')).toHaveValue(null)
    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }))

    await waitFor(() => expect(onCreate).toHaveBeenCalled())
    expect(onCreate.mock.calls[0][0]).not.toHaveProperty('break_minutes')
    expect(onCreate.mock.calls[0][0]).toHaveProperty('break_mode', 'auto')
    expect(onCreate.mock.calls[0][0]).toEqual(expect.objectContaining({
      job_id: 'job-1', role: 'Barista',
    }))
  })

  it('shows required-field errors without creating malformed shifts', async () => {
    const onCreate = renderInspector()

    fireEvent.change(screen.getByLabelText('Start'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Start and end times are required')
    expect(onCreate).not.toHaveBeenCalled()
  })

  it('enforces the API count limits and submits their valid boundaries unchanged', async () => {
    const onCreate = renderInspector()
    fireEvent.change(screen.getByLabelText(/Role/), { target: { value: 'job-1' } })
    const staffInput = screen.getByLabelText('Staff needed')
    const breakInput = screen.getByLabelText('Planned break (minutes)')

    expect(staffInput).toHaveAttribute('max', '99')
    expect(breakInput).toHaveAttribute('max', '1440')

    fireEvent.change(staffInput, { target: { value: '100' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Staff needed must be a whole number from 1 to 99')
    expect(onCreate).not.toHaveBeenCalled()

    fireEvent.change(staffInput, { target: { value: '99' } })
    fireEvent.change(breakInput, { target: { value: '1441' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Planned break must be a whole number from 0 to 1440 minutes')
    expect(onCreate).not.toHaveBeenCalled()

    fireEvent.change(breakInput, { target: { value: '1440' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }))
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({
      required_staff: 99,
      break_minutes: 1440,
      break_mode: 'manual',
    })))
  })

  it('clears the stale label when a job is cleared on an existing shift', async () => {
    // Choosing "No assigned role (legacy)" used to keep the old role string,
    // saving a shift labelled "Barista" that the UI just said has no role.
    const onUpdate = vi.fn().mockResolvedValue(undefined)
    render(
      <ShiftInspector
        shift={{
          id: 'shift-1', starts_at: '2026-08-31T09:00:00Z', ends_at: '2026-08-31T17:00:00Z',
          role: 'Barista', job_id: 'job-1', department: null, break_minutes: 0,
          required_staff: 1, notes: null, kind: 'work', training_requirement_id: null,
          assignments: [],
        } as never}
        defaults={null}
        locationId="loc-1"
        locationName="Downtown"
        roster={[]}
        jobs={jobs}
        trainingEnabled={false}
        readOnly={false}
        saving={false}
        onCreate={vi.fn().mockResolvedValue(undefined)}
        onUpdate={onUpdate}
        onDelete={vi.fn().mockResolvedValue(undefined)}
        onAssignmentUpdated={vi.fn().mockResolvedValue(undefined)}
        onClose={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByLabelText(/Role/), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(onUpdate).toHaveBeenCalled())
    expect(onUpdate.mock.calls[0][0]).toEqual(expect.objectContaining({
      job_id: null, role: null,
    }))
  })

  it('cannot create a draft at a location with no roles', async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined)
    render(
      <ShiftInspector
        shift={null}
        defaults={{ date: '2026-08-31', minute: 540 }}
        locationId="loc-1"
        locationName="Downtown"
        roster={[]}
        jobs={[]}
        trainingEnabled={false}
        readOnly={false}
        saving={false}
        onCreate={onCreate}
        onUpdate={vi.fn().mockResolvedValue(undefined)}
        onDelete={vi.fn().mockResolvedValue(undefined)}
        onAssignmentUpdated={vi.fn().mockResolvedValue(undefined)}
        onClose={vi.fn()}
      />,
    )

    // The empty dropdown said nothing at all here before — the only feedback
    // was an error after the click.
    expect(screen.getByText(NO_ROLES_MESSAGE)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create draft' })).toBeDisabled()
    expect(onCreate).not.toHaveBeenCalled()
  })

  it('uses Auto for an untouched edit and Manual after the manager changes the break', async () => {
    const onUpdate = renderEditingInspector()

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(onUpdate).toHaveBeenCalled())
    expect(onUpdate.mock.calls[0][0]).toHaveProperty('break_mode', 'auto')
    expect(onUpdate.mock.calls[0][0]).not.toHaveProperty('break_minutes')

    fireEvent.change(screen.getByLabelText('Planned break (minutes)'), { target: { value: '30' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(2))
    expect(onUpdate.mock.calls[1][0]).toEqual(expect.objectContaining({
      break_mode: 'manual',
      break_minutes: 30,
    }))
  })

  it('shows the generated break returned after an Auto save', () => {
    const baseShift = {
      id: 'shift-1', starts_at: '2026-08-31T09:00:00Z', ends_at: '2026-08-31T17:00:00Z',
      role: null, job_id: null, department: null, break_minutes: 0,
      required_staff: 1, notes: null, kind: 'work', training_requirement_id: null,
      assignments: [],
    }
    const props = {
      defaults: null, locationId: 'loc-1', locationName: 'Downtown', roster: [], jobs: [],
      trainingEnabled: false, readOnly: false, saving: false,
      onCreate: vi.fn().mockResolvedValue(undefined),
      onUpdate: vi.fn().mockResolvedValue(undefined),
      onDelete: vi.fn().mockResolvedValue(undefined),
      onAssignmentUpdated: vi.fn().mockResolvedValue(undefined), onClose: vi.fn(),
    }
    const view = render(<ShiftInspector {...props} shift={baseShift as never} />)
    expect(screen.getByLabelText('Planned break (minutes)')).toHaveValue(0)

    view.rerender(
      <ShiftInspector {...props} shift={{ ...baseShift, break_minutes: 30 } as never} />,
    )

    expect(screen.getByLabelText('Planned break (minutes)')).toHaveValue(30)
  })
})
