import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../ui'
import AutoSchedulesTab from './AutoSchedulesTab'


const mocks = vi.hoisted(() => ({
  fetchRule: vi.fn(),
  fetchTemplates: vi.fn(),
  runNow: vi.fn(),
  saveRule: vi.fn(),
  hasFeature: vi.fn(),
}))

vi.mock('../../hooks/useMe', () => ({ useMe: () => ({ hasFeature: mocks.hasFeature }) }))

vi.mock('../../api/employees/employeeSchedule', () => ({
  fetchAutoSchedule: mocks.fetchRule,
  fetchWeekTemplates: mocks.fetchTemplates,
  runAutoScheduleNow: mocks.runNow,
  saveAutoSchedule: mocks.saveRule,
}))

const template = {
  id: 'template-1', name: 'Standard Week', location_id: 'loc-1', color: null, notes: null, blocks: [],
}

function automationRule(locationId: string, weeks = 1) {
  return {
    id: `rule-${locationId}`, location_id: locationId, location_name: locationId, timezone: 'UTC',
    enabled: true, cadence: 'weekly', mode: 'autopilot', week_template_id: null,
    week_template_name: null, run_weekday: 4, run_date: null, run_time: '09:00',
    target_weeks_ahead: weeks, target_week_start: null, next_run_at: null,
    last_attempt_at: null, last_completed_at: null, last_status: null,
    last_message: null, last_generation_run_id: null,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

function automationTree(locationId: string) {
  return <MemoryRouter><ToastProvider><AutoSchedulesTab locationId={locationId} /></ToastProvider></MemoryRouter>
}

describe('AutoSchedulesTab', () => {
  beforeEach(() => {
    mocks.hasFeature.mockReturnValue(false)
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

  it.each(['success', 'failure'])('ignores a stale location load %s without ending the current load', async (outcome) => {
    const first = deferred<{ rule: ReturnType<typeof automationRule> }>()
    const current = deferred<{ rule: ReturnType<typeof automationRule> }>()
    mocks.fetchRule.mockReturnValueOnce(first.promise).mockReturnValueOnce(current.promise)
    const view = render(automationTree('loc-1'))
    view.rerender(automationTree('loc-2'))
    await act(async () => { if (outcome === 'success') first.resolve({ rule: automationRule('loc-1', 3) }); else first.reject(new Error('Old location failed')) })
    expect(screen.queryByLabelText('Week to prepare')).not.toBeInTheDocument()
    expect(screen.queryByText('Old location failed')).not.toBeInTheDocument()
    await act(async () => current.resolve({ rule: automationRule('loc-2', 2) }))
    expect(screen.getByLabelText('Week to prepare')).toHaveValue('2')
  })

  it('does not reuse an old load after returning to the same location', async () => {
    const first = deferred<{ rule: ReturnType<typeof automationRule> }>()
    mocks.fetchRule.mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce({ rule: automationRule('loc-2') })
      .mockResolvedValueOnce({ rule: automationRule('loc-1', 2) })
    const view = render(automationTree('loc-1'))
    view.rerender(automationTree('loc-2'))
    await screen.findByLabelText('Week to prepare')
    view.rerender(automationTree('loc-1'))
    expect(await screen.findByLabelText('Week to prepare')).toHaveValue('2')
    await act(async () => first.resolve({ rule: automationRule('loc-1', 4) }))
    expect(screen.getByLabelText('Week to prepare')).toHaveValue('2')
  })

  it.each(['success', 'failure'])('ignores an old save %s after A → B → A while another save is pending', async (outcome) => {
    mocks.hasFeature.mockReturnValue(true)
    mocks.fetchRule.mockImplementation(async (id: string) => ({ rule: automationRule(id) }))
    const first = deferred<ReturnType<typeof automationRule>>()
    const current = deferred<ReturnType<typeof automationRule>>()
    mocks.saveRule.mockReturnValueOnce(first.promise).mockReturnValueOnce(current.promise)
    const view = render(automationTree('loc-1'))
    fireEvent.change(await screen.findByLabelText('Week to prepare'), { target: { value: '4' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save auto schedule' }))
    view.rerender(automationTree('loc-2'))
    await screen.findByLabelText('Week to prepare')
    view.rerender(automationTree('loc-1'))
    fireEvent.change(await screen.findByLabelText('Week to prepare'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save auto schedule' }))
    await act(async () => { if (outcome === 'success') first.resolve(automationRule('loc-1', 4)); else first.reject(new Error('Old save failed')) })
    expect(screen.getByLabelText('Week to prepare')).toHaveValue('2')
    expect(screen.getByRole('button', { name: 'Save auto schedule' })).toBeDisabled()
    expect(screen.queryByText('Old save failed')).not.toBeInTheDocument()
    await act(async () => current.resolve(automationRule('loc-1', 2)))
    expect(screen.getByRole('button', { name: 'Save auto schedule' })).not.toBeDisabled()
  })

  it.each(['success', 'failure'])('ignores an old run %s after A → B → A while another run is pending', async (outcome) => {
    mocks.fetchRule.mockImplementation(async (id: string) => ({ rule: automationRule(id) }))
    mocks.hasFeature.mockReturnValue(true)
    const first = deferred<{ status: string; message: string; week_start: string }>()
    const current = deferred<{ status: string; message: string; week_start: string }>()
    mocks.runNow.mockReturnValueOnce(first.promise).mockReturnValueOnce(current.promise)
    const view = render(automationTree('loc-1'))
    fireEvent.click(await screen.findByRole('button', { name: 'Run now' }))
    view.rerender(automationTree('loc-2'))
    await screen.findByRole('button', { name: 'Run now' })
    view.rerender(automationTree('loc-1'))
    fireEvent.click(await screen.findByRole('button', { name: 'Run now' }))
    await act(async () => { if (outcome === 'success') first.resolve({ status: 'generated', message: 'Old run', week_start: '2026-10-04' }); else first.reject(new Error('Old run failed')) })
    expect(screen.queryByRole('link', { name: /Review the generated week/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run now' })).toBeDisabled()
    expect(screen.queryByText('Old run failed')).not.toBeInTheDocument()
    await act(async () => current.resolve({ status: 'generated', message: 'Current run', week_start: '2026-10-11' }))
    expect(await screen.findByRole('link', { name: /Review the generated week/ })).toHaveAttribute('href', '/ops/schedule/editor?week=2026-10-11&location=loc-1')
  })

  it('lets a revoked Autopilot rule be paused or switched to a template', async () => {
    mocks.fetchRule.mockResolvedValue({ rule: automationRule('loc-1') })
    render(automationTree('loc-1'))
    expect(await screen.findByRole('button', { name: 'Autopilot' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Run now' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Save auto schedule' })).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Enabled' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save auto schedule' }))
    await waitFor(() => expect(mocks.saveRule).toHaveBeenCalledWith('loc-1', expect.objectContaining({ enabled: false, mode: 'autopilot' })))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save auto schedule' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'From template' }))
    fireEvent.change(screen.getByLabelText('Week template'), { target: { value: 'template-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save auto schedule' }))
    await waitFor(() => expect(mocks.saveRule).toHaveBeenLastCalledWith('loc-1', expect.objectContaining({ mode: 'template', week_template_id: 'template-1' })))
  })

  it('saves Autopilot without a week template when the premium flag is enabled', async () => {
    mocks.hasFeature.mockImplementation((flag: string) => flag === 'schedule_autopilot')
    render(<ToastProvider><AutoSchedulesTab locationId="loc-1" /></ToastProvider>)

    fireEvent.click(await screen.findByRole('button', { name: 'Autopilot' }))
    expect(screen.queryByLabelText('Week template')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save auto schedule' }))

    await waitFor(() => expect(mocks.saveRule).toHaveBeenCalledWith('loc-1', expect.objectContaining({
      mode: 'autopilot', week_template_id: null,
    })))
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
      mode: 'template',
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

  describe('one-time rule target week', () => {
    // Only Date is faked, so the component's promises and waitFor still run.
    beforeEach(() => {
      vi.useFakeTimers({ toFake: ['Date'] })
      vi.setSystemTime(new Date('2026-09-27T20:19:00Z'))
    })
    afterEach(() => { vi.useRealTimers() })

    const onceRule = (targetWeekStart: string) => ({
      rule: {
        id: 'rule-1', location_id: 'loc-1', location_name: 'Downtown', timezone: 'America/Los_Angeles',
        enabled: false, cadence: 'once', week_template_id: 'template-1', week_template_name: 'Standard Week',
        run_weekday: null, run_date: '2026-09-05', run_time: '09:00', target_weeks_ahead: null,
        target_week_start: targetWeekStart, next_run_at: null, last_attempt_at: null, last_completed_at: null,
        last_status: null, last_message: null, last_generation_run_id: null,
      },
    })

    it('warns before Run now when the saved week has already passed', async () => {
      // The Po Coffee rule: saved for 2026-09-06, run on 2026-09-27.
      mocks.fetchRule.mockResolvedValue(onceRule('2026-09-06'))
      render(<MemoryRouter><ToastProvider><AutoSchedulesTab locationId="loc-1" /></ToastProvider></MemoryRouter>)

      expect(await screen.findByText(/The week of 2026-09-06 has already passed/)).toBeInTheDocument()
    })

    it('dates the last result so an old refusal does not read as current', async () => {
      // Po Coffee's rule after the 2026-09-28 06:25 UTC refusal.
      mocks.fetchRule.mockResolvedValue({
        rule: {
          ...onceRule('2026-10-04').rule,
          last_status: 'already_present',
          last_attempt_at: '2026-09-28T06:25:12Z',
          last_message: 'A schedule suggestion or approved schedule already exists for that week.',
        },
      })
      render(<MemoryRouter><ToastProvider><AutoSchedulesTab locationId="loc-1" /></ToastProvider></MemoryRouter>)

      const stamp = new Intl.DateTimeFormat(undefined, {
        timeZone: 'America/Los_Angeles', dateStyle: 'medium', timeStyle: 'short',
      }).format(new Date('2026-09-28T06:25:12Z'))
      expect(await screen.findByText(`already present · ${stamp}`)).toBeInTheDocument()
    })

    it('stays quiet for the current or a future week', async () => {
      mocks.fetchRule.mockResolvedValue(onceRule('2026-10-04'))
      render(<MemoryRouter><ToastProvider><AutoSchedulesTab locationId="loc-1" /></ToastProvider></MemoryRouter>)

      await screen.findByRole('button', { name: 'Run now' })
      expect(screen.queryByText(/has already passed/)).not.toBeInTheDocument()
    })

    it("judges the week on the location's clock, not UTC's", async () => {
      // 01:00 UTC Sunday 2026-10-04 is still Saturday evening in Los Angeles,
      // so the week of 2026-09-27 has not ended there.
      vi.setSystemTime(new Date('2026-10-04T01:00:00Z'))
      mocks.fetchRule.mockResolvedValue(onceRule('2026-09-27'))
      render(<MemoryRouter><ToastProvider><AutoSchedulesTab locationId="loc-1" /></ToastProvider></MemoryRouter>)

      await screen.findByRole('button', { name: 'Run now' })
      expect(screen.queryByText(/has already passed/)).not.toBeInTheDocument()
    })

    it('warns a store ahead of UTC once its own week has turned', async () => {
      // 16:00 UTC Saturday 2026-10-03 is already Sunday 01:00 in Tokyo.
      vi.setSystemTime(new Date('2026-10-03T16:00:00Z'))
      mocks.fetchRule.mockResolvedValue({
        rule: { ...onceRule('2026-09-27').rule, timezone: 'Asia/Tokyo' },
      })
      render(<MemoryRouter><ToastProvider><AutoSchedulesTab locationId="loc-1" /></ToastProvider></MemoryRouter>)

      expect(await screen.findByText(/The week of 2026-09-27 has already passed/)).toBeInTheDocument()
    })

    it('follows the saved week Run now builds, not an unsaved edit', async () => {
      mocks.fetchRule.mockResolvedValue(onceRule('2026-09-06'))
      render(<MemoryRouter><ToastProvider><AutoSchedulesTab locationId="loc-1" /></ToastProvider></MemoryRouter>)

      await screen.findByText(/The week of 2026-09-06 has already passed/)
      fireEvent.change(screen.getByLabelText('Week starting'), { target: { value: '2026-10-04' } })

      // Run now would still build 2026-09-06 until the new week is saved.
      expect(screen.getByText(/The week of 2026-09-06 has already passed/)).toBeInTheDocument()
    })

    it('stays quiet when only an unsaved edit points at a past week', async () => {
      mocks.fetchRule.mockResolvedValue(onceRule('2026-10-04'))
      render(<MemoryRouter><ToastProvider><AutoSchedulesTab locationId="loc-1" /></ToastProvider></MemoryRouter>)

      await screen.findByRole('button', { name: 'Run now' })
      fireEvent.change(screen.getByLabelText('Week starting'), { target: { value: '2026-09-06' } })

      expect(screen.queryByText(/has already passed/)).not.toBeInTheDocument()
    })
  })
})
