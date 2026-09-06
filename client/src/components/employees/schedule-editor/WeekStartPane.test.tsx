import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../../ui'
import WeekStartPane from './WeekStartPane'


const mocks = vi.hoisted(() => ({
  fetchProfile: vi.fn(),
  saveProfile: vi.fn(),
  fetchTemplates: vi.fn(),
}))

vi.mock('../../../api/employees/locationProfile', () => ({
  fetchLocationScheduleProfile: mocks.fetchProfile,
  saveLocationScheduleProfile: mocks.saveProfile,
}))

vi.mock('../../../api/employees/employeeSchedule', () => ({
  fetchWeekTemplates: mocks.fetchTemplates,
}))

// Stands in for the real form so a save can be driven from a test: it hands
// back a template id the way TemplateForm does after a successful write.
vi.mock('./TemplateForm', () => ({
  TemplateForm: ({ submitLabel, onDone }: {
    submitLabel: string
    onDone: (saved: { id: string }) => void | Promise<void>
  }) => (
    <button type="button" onClick={() => { void onDone({ id: 'tpl-1' }) }}>{submitLabel}</button>
  ),
}))

const profile = {
  location_id: 'loc-1',
  profile_exists: true,
  week_rules: { established: false, missing: ['operating_hours', 'staffing_pattern', 'leader_rule'] },
  operating_hours: { '1': { open: '08:00', close: '17:00' } },
  default_week_template_id: null,
  leader_job_id: null,
  leader_job_name: null,
  leader_required: null,
  notes: null,
  week_start_weekday: 0,
  open_buffer_minutes: 30,
  close_buffer_minutes: 20,
  template: null,
}

function renderPane() {
  return render(
    <ToastProvider>
      <WeekStartPane locationId="loc-1" jobs={[]} />
    </ToastProvider>,
  )
}

describe('WeekStartPane — prep and close buffers', () => {
  beforeEach(() => {
    mocks.fetchProfile.mockResolvedValue(profile)
    mocks.saveProfile.mockResolvedValue(profile)
    mocks.fetchTemplates.mockResolvedValue({ week_templates: [] })
  })

  it('seeds the saved buffers so Huume’s answers are visible and editable', async () => {
    renderPane()

    const openInput = await screen.findByLabelText('Minutes of prep before open')
    expect((openInput as HTMLInputElement).value).toBe('30')
    expect(
      (screen.getByLabelText('Minutes of cleanup after close') as HTMLInputElement).value,
    ).toBe('20')
  })

  it('saves the buffers alongside the hours in one write', async () => {
    renderPane()

    const openInput = await screen.findByLabelText('Minutes of prep before open')
    fireEvent.change(openInput, { target: { value: '45' } })
    fireEvent.change(screen.getByLabelText('Minutes of cleanup after close'), {
      target: { value: '0' },
    })
    fireEvent.click(screen.getByText('Save week setup'))

    await waitFor(() => expect(mocks.saveProfile).toHaveBeenCalled())
    const payload = mocks.saveProfile.mock.calls[0][1]
    expect(payload.open_buffer_minutes).toBe(45)
    // 0 is a real answer, not an omission — it has to reach the server as one.
    expect(payload.close_buffer_minutes).toBe(0)
    expect(payload.operating_hours).toEqual({ '1': { open: '08:00', close: '17:00' } })
  })

  it('clamps a nonsense buffer rather than failing the whole save', async () => {
    renderPane()

    const openInput = await screen.findByLabelText('Minutes of prep before open')
    fireEvent.change(openInput, { target: { value: '9000' } })
    fireEvent.click(screen.getByText('Save week setup'))

    await waitFor(() => expect(mocks.saveProfile).toHaveBeenCalled())
    expect(mocks.saveProfile.mock.calls[0][1].open_buffer_minutes).toBe(240)
  })
})

describe('WeekStartPane — the leader answer', () => {
  const jobs = [
    { id: 'job-1', name: 'Shift Lead', location_id: 'loc-1', is_active: true },
  ] as never[]

  beforeEach(() => {
    mocks.fetchProfile.mockResolvedValue(profile)
    mocks.saveProfile.mockResolvedValue(profile)
    mocks.fetchTemplates.mockResolvedValue({ week_templates: [] })
  })

  function renderWithJobs() {
    return render(
      <ToastProvider>
        <WeekStartPane locationId="loc-1" jobs={jobs} />
      </ToastProvider>,
    )
  }

  it('saves “No leader required” as an answer, not an empty field', async () => {
    // The week builder counts an unanswered leader question as missing setup,
    // so a store that needs no lead has to be able to say so.
    renderWithJobs()

    // `Select` is a button + dropdown, not a native <select>.
    fireEvent.click(await screen.findByRole('button', { name: /Not answered yet/ }))
    fireEvent.click(screen.getByRole('button', { name: 'No leader required' }))
    fireEvent.click(screen.getByText('Save week setup'))

    await waitFor(() => expect(mocks.saveProfile).toHaveBeenCalled())
    const payload = mocks.saveProfile.mock.calls[0][1]
    expect(payload.leader_required).toBe(false)
    expect(payload.leader_job_id).toBeNull()
  })

  it('leaves the answer null while nobody has picked one', async () => {
    renderWithJobs()

    await screen.findByRole('button', { name: /Not answered yet/ })
    fireEvent.click(screen.getByText('Save week setup'))

    await waitFor(() => expect(mocks.saveProfile).toHaveBeenCalled())
    expect(mocks.saveProfile.mock.calls[0][1].leader_required).toBeNull()
  })

  it('names a leader job as the yes answer', async () => {
    renderWithJobs()

    fireEvent.click(await screen.findByRole('button', { name: /Not answered yet/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Shift Lead' }))
    fireEvent.click(screen.getByText('Save week setup'))

    await waitFor(() => expect(mocks.saveProfile).toHaveBeenCalled())
    const payload = mocks.saveProfile.mock.calls[0][1]
    expect(payload.leader_required).toBe(true)
    expect(payload.leader_job_id).toBe('job-1')
  })

  it('says what is still missing so the manager knows why Huume refuses', async () => {
    renderWithJobs()

    expect(await screen.findByText(/Still missing: hours, a staffing pattern, the leader rule/))
      .toBeInTheDocument()
  })
})


describe('WeekStartPane — saving the staffing pattern', () => {
  const onSaved = vi.fn()

  beforeEach(() => {
    onSaved.mockClear()
    mocks.fetchTemplates.mockResolvedValue({ week_templates: [] })
  })

  function renderWithOnSaved() {
    return render(
      <ToastProvider>
        <WeekStartPane locationId="loc-1" jobs={[]} onSaved={onSaved} />
      </ToastProvider>,
    )
  }

  it('re-reads the setup when the pattern is already this location’s default', async () => {
    // Nothing is written to the profile row on this path, but the pattern's
    // first block is what clears `staffing_pattern` from week_rules.missing —
    // this pane's banner and the editor's both kept claiming it was missing
    // until something else reloaded.
    const alreadyDefault = { ...profile, default_week_template_id: 'tpl-1' }
    mocks.fetchProfile.mockResolvedValue(alreadyDefault)
    mocks.saveProfile.mockResolvedValue(alreadyDefault)

    renderWithOnSaved()
    fireEvent.click(await screen.findByText('Save staffing pattern'))

    await waitFor(() => expect(mocks.fetchProfile).toHaveBeenCalledTimes(2))
    expect(mocks.saveProfile).not.toHaveBeenCalled()
    expect(onSaved).toHaveBeenCalled()
  })

  it('points the profile at a brand-new pattern', async () => {
    mocks.fetchProfile.mockResolvedValue(profile)
    mocks.saveProfile.mockResolvedValue({ ...profile, default_week_template_id: 'tpl-1' })

    renderWithOnSaved()
    fireEvent.click(await screen.findByText('Save staffing pattern'))

    await waitFor(() => expect(mocks.saveProfile).toHaveBeenCalled())
    expect(mocks.saveProfile.mock.calls[0][1]).toEqual({ default_week_template_id: 'tpl-1' })
    expect(onSaved).toHaveBeenCalled()
  })
})
