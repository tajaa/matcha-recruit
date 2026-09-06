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

vi.mock('./TemplateForm', () => ({ TemplateForm: () => null }))

const profile = {
  location_id: 'loc-1',
  operating_hours: { '1': { open: '08:00', close: '17:00' } },
  default_week_template_id: null,
  leader_job_id: null,
  leader_job_name: null,
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
