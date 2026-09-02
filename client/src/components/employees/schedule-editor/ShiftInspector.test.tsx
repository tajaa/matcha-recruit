import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ShiftInspector from './ShiftInspector'

function renderInspector() {
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
  return onCreate
}

describe('ShiftInspector validation', () => {
  it('leaves a new shift break blank so the server generates it', async () => {
    const onCreate = renderInspector()

    expect(screen.getByLabelText('Planned break (minutes)')).toHaveValue(null)
    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }))

    await waitFor(() => expect(onCreate).toHaveBeenCalled())
    expect(onCreate.mock.calls[0][0]).not.toHaveProperty('break_minutes')
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
    })))
  })
})
