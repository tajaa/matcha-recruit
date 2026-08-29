import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../ui'
import AutoSchedulesTab from './AutoSchedulesTab'


const mocks = vi.hoisted(() => ({
  fetchRule: vi.fn(),
  fetchTemplates: vi.fn(),
  runNow: vi.fn(),
  saveRule: vi.fn(),
}))

vi.mock('../../api/employees/employeeSchedule', () => ({
  fetchAutoSchedule: mocks.fetchRule,
  fetchWeekTemplates: mocks.fetchTemplates,
  runAutoScheduleNow: mocks.runNow,
  saveAutoSchedule: mocks.saveRule,
}))

const template = {
  id: 'template-1', name: 'Standard Week', location_id: 'loc-1', color: null, notes: null, blocks: [],
}

describe('AutoSchedulesTab', () => {
  beforeEach(() => {
    mocks.fetchRule.mockResolvedValue({ rule: null })
    mocks.fetchTemplates.mockResolvedValue({ week_templates: [template] })
    mocks.saveRule.mockImplementation(async (_locationId: string, payload: Record<string, unknown>) => ({
      id: 'rule-1',
      location_id: 'loc-1',
      location_name: 'Downtown',
      timezone: 'America/Los_Angeles',
      week_template_name: 'Standard Week',
      next_run_at: '2026-09-03T16:00:00+00:00',
      last_attempt_at: null,
      last_completed_at: null,
      last_status: null,
      last_message: null,
      last_generation_run_id: null,
      ...payload,
    }))
  })

  it('saves a weekly, location-scoped review cadence', async () => {
    render(<ToastProvider><AutoSchedulesTab locationId="loc-1" /></ToastProvider>)

    const templateSelect = await screen.findByLabelText('Week template')
    fireEvent.change(templateSelect, { target: { value: 'template-1' } })
    fireEvent.change(screen.getByLabelText('Run day'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('Run time'), { target: { value: '08:30' } })
    fireEvent.change(screen.getByLabelText('Week to prepare'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save auto schedule' }))

    await waitFor(() => expect(mocks.saveRule).toHaveBeenCalledWith('loc-1', {
      enabled: true,
      cadence: 'weekly',
      week_template_id: 'template-1',
      run_time: '08:30',
      run_weekday: 2,
      run_date: null,
      target_weeks_ahead: 2,
      target_week_start: null,
    }))
  })

  it('links a generated suggestion to the scoped full shift editor', async () => {
    mocks.fetchRule.mockResolvedValue({
      rule: {
        id: 'rule-1', location_id: 'loc-1', location_name: 'Downtown', timezone: 'America/Los_Angeles',
        enabled: true, cadence: 'once', week_template_id: 'template-1', week_template_name: 'Standard Week',
        run_weekday: null, run_date: '2026-08-29', run_time: '09:00', target_weeks_ahead: null,
        target_week_start: '2026-08-30', next_run_at: null, last_attempt_at: null, last_completed_at: null,
        last_status: null, last_message: null, last_generation_run_id: null,
      },
    })
    mocks.runNow.mockResolvedValue({
      status: 'generated', message: 'Huume prepared a schedule suggestion for manager review.',
      week_start: '2026-08-30', generation_run_id: 'generation-1',
    })

    render(<MemoryRouter><ToastProvider><AutoSchedulesTab locationId="loc-1" /></ToastProvider></MemoryRouter>)

    fireEvent.click(await screen.findByRole('button', { name: 'Run now' }))

    expect(await screen.findByRole('link', { name: /Review the generated week/ })).toHaveAttribute(
      'href', '/ops/schedule/editor?week=2026-08-30&location=loc-1',
    )
  })

  it('discards a generated suggestion when the selected location changes', async () => {
    mocks.fetchRule.mockResolvedValue({
      rule: {
        id: 'rule-1', location_id: 'loc-1', location_name: 'Downtown', timezone: 'America/Los_Angeles',
        enabled: true, cadence: 'once', week_template_id: 'template-1', week_template_name: 'Standard Week',
        run_weekday: null, run_date: '2026-08-29', run_time: '09:00', target_weeks_ahead: null,
        target_week_start: '2026-08-30', next_run_at: null, last_attempt_at: null, last_completed_at: null,
        last_status: null, last_message: null, last_generation_run_id: null,
      },
    })
    let resolveRun: (result: {
      status: string; message: string; week_start: string; generation_run_id: string
    }) => void = () => undefined
    mocks.runNow.mockReturnValue(new Promise((resolve) => { resolveRun = resolve }))

    const view = render(
      <MemoryRouter><ToastProvider><AutoSchedulesTab locationId="loc-1" /></ToastProvider></MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Run now' }))
    view.rerender(
      <MemoryRouter><ToastProvider><AutoSchedulesTab locationId="loc-2" /></ToastProvider></MemoryRouter>,
    )

    await act(async () => resolveRun({
      status: 'generated', message: 'Huume prepared a schedule suggestion for manager review.',
      week_start: '2026-08-30', generation_run_id: 'generation-1',
    }))

    expect(screen.queryByRole('link', { name: /Review the generated week/ })).not.toBeInTheDocument()
  })
})
