import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useScheduleScenarios } from './useScheduleScenarios'
import { ApiError } from '../../api/client'
import type { ScheduleReview } from '../../types/employeeSchedule'

const { previewMock, applyMock, cancelMock } = vi.hoisted(() => ({
  previewMock: vi.fn(),
  applyMock: vi.fn(),
  cancelMock: vi.fn(),
}))

vi.mock('../../api/employees/employeeSchedule', () => ({
  previewFillVacant: previewMock,
  applyFillVacant: applyMock,
  cancelFillVacant: cancelMock,
}))

function review(overrides: Partial<ScheduleReview> = {}): ScheduleReview {
  return {
    proposal_id: 'p1', kind: 'edit', compliance_status: 'verified',
    assignments: [], rejected: [], unfilled: [], employees: [], advisories: [], findings: [],
    jurisdiction: { state: 'CA', status: 'curated', message: 'on file' },
    ...overrides,
  }
}

function ready(proposalId: string, label: string | null = null) {
  return { status: 'ready' as const, proposal_id: proposalId, pill_text: 'pill', review: review({ proposal_id: proposalId }), label }
}

function render(locationId = 'loc1', weekStart = '2026-08-23') {
  return renderHook(
    ({ location, week }: { location: string; week: string }) => useScheduleScenarios(location, week),
    { initialProps: { location: locationId, week: weekStart } },
  )
}

beforeEach(() => {
  previewMock.mockReset()
  applyMock.mockReset().mockResolvedValue({ status: 'applied', message: '2 changes are live.', touched_shift_ids: ['s1', 's2'] })
  cancelMock.mockReset().mockResolvedValue(undefined)
})

describe('useScheduleScenarios — previewing', () => {
  it('adds a chip for a ready preview and selects it', async () => {
    previewMock.mockResolvedValue(ready('proposal-1'))
    const { result } = render()

    await act(async () => { await result.current.preview({ role_hint: 'shift lead' }) })

    expect(previewMock).toHaveBeenCalledWith('loc1', { role_hint: 'shift lead', week_start: '2026-08-23' })
    expect(result.current.scenarios).toHaveLength(1)
    expect(result.current.scenarios[0]).toMatchObject({ proposal_id: 'proposal-1', status: 'ready', pill_text: 'pill' })
    expect(result.current.selectedIds).toEqual(['proposal-1'])
    expect(result.current.notice).toBeNull()
  })

  it('names a scenario from its own constraints when the manager gave no label', async () => {
    previewMock.mockResolvedValue(ready('proposal-1'))
    const { result } = render()

    await act(async () => { await result.current.preview({ role_hint: 'shift lead', employee_id: 'e1', allow_split_shift: true }) })

    expect(result.current.scenarios[0].label).toBe('Scenario 1: shift lead shifts · one person · splits allowed')
  })

  it('keeps the manager’s own label when they gave one', async () => {
    previewMock.mockResolvedValue(ready('proposal-1', 'Spread the leads'))
    const { result } = render()

    await act(async () => { await result.current.preview({ label: 'Spread the leads' }) })

    expect(result.current.scenarios[0].label).toBe('Spread the leads')
  })

  it('reports a refusal as a notice and stages no chip', async () => {
    previewMock.mockResolvedValue({
      status: 'empty', message: 'No open shift could be filled under the staffing rules.',
      unfilled: [{ shift_id: 's1', role: 'Shift Lead', starts_at: null, ends_at: null, reason: 'not qualified for the shift job', exclusions: {} }],
    })
    const { result } = render()

    await act(async () => { await result.current.preview({}) })

    expect(result.current.scenarios).toEqual([])
    expect(result.current.notice).toEqual({
      status: 'empty',
      message: 'No open shift could be filled under the staffing rules.',
      unfilled: [{ shift_id: 's1', role: 'Shift Lead', starts_at: null, ends_at: null, reason: 'not qualified for the shift job', exclusions: {} }],
    })
  })

  it('surfaces a failed request rather than swallowing it', async () => {
    previewMock.mockRejectedValue(new Error('Network is down'))
    const { result } = render()

    await act(async () => { await result.current.preview({}) })

    expect(result.current.notice).toMatchObject({ status: 'error', message: 'Network is down' })
    expect(result.current.previewing).toBe(false)
  })

  it('does nothing without a location', async () => {
    const { result } = render('')
    await act(async () => { await result.current.preview({}) })
    expect(previewMock).not.toHaveBeenCalled()
  })
})

/** Applies and returns what it threw. The rejection has to be caught inside
 *  `act`, or the state updates the hook queued while failing are never
 *  flushed and every assertion reads the state from before the apply. */
async function applyExpectingFailure(
  result: { current: ReturnType<typeof useScheduleScenarios> },
  proposalId: string,
): Promise<unknown> {
  let thrown: unknown = null
  await act(async () => { await result.current.apply(proposalId).catch((error: unknown) => { thrown = error }) })
  expect(thrown).not.toBeNull()
  return thrown
}

describe('useScheduleScenarios — acting on one', () => {
  async function withScenario() {
    previewMock.mockResolvedValue(ready('proposal-1'))
    const view = render()
    await act(async () => { await view.result.current.preview({}) })
    return view
  }

  it('applies a scenario and records the server’s message', async () => {
    const { result } = await withScenario()

    await act(async () => { await result.current.apply('proposal-1') })

    expect(applyMock).toHaveBeenCalledWith('proposal-1')
    expect(result.current.scenarios[0]).toMatchObject({ status: 'applied', applied_message: '2 changes are live.' })
  })

  it('puts a failed apply back within reach instead of leaving it stuck', async () => {
    const { result } = await withScenario()
    applyMock.mockRejectedValue(new Error('The planner is unreachable'))

    // Caught inside act(): a rejection that escapes it leaves the updates the
    // hook queued unflushed, and the assertion reads the pre-apply state.
    const failure = await applyExpectingFailure(result, 'proposal-1')

    expect(failure).toHaveProperty('message', 'The planner is unreachable')
    expect(result.current.scenarios[0].status).toBe('ready')
  })

  it('retires a scenario the server has already spent', async () => {
    const { result } = await withScenario()
    act(() => result.current.select('proposal-1'))
    applyMock.mockRejectedValue(new ApiError('That fill preview was already applied or discarded', 409, null))

    const failure = await applyExpectingFailure(result, 'proposal-1')

    // A 409 means the row is gone server-side: re-offering Apply on it would
    // only 409 again.
    expect(failure).toBeInstanceOf(ApiError)
    expect(result.current.scenarios).toEqual([])
    expect(result.current.selectedIds).toEqual([])
  })

  it('discards a scenario, cancelling the row it left on the server', async () => {
    const { result } = await withScenario()

    await act(async () => { await result.current.discard('proposal-1') })

    expect(cancelMock).toHaveBeenCalledWith('proposal-1')
    expect(result.current.scenarios).toEqual([])
    expect(result.current.selectedIds).toEqual([])
  })

  it('drops the chip the server cancelled when a second scenario is staged', async () => {
    previewMock.mockResolvedValueOnce(ready('proposal-1')).mockResolvedValueOnce(ready('proposal-2'))
    const { result } = render()
    await act(async () => { await result.current.preview({}) })
    await act(async () => { await result.current.preview({}) })

    act(() => result.current.markStaged('proposal-1'))
    act(() => result.current.select('proposal-1'))
    // The thread holds one staged action, so adopting the second cancelled the
    // first server-side — its chip goes with it.
    act(() => result.current.markStaged('proposal-2'))

    expect(result.current.scenarios.map((item) => item.proposal_id)).toEqual(['proposal-2'])
    expect(result.current.scenarios[0].status).toBe('staged')
    expect(result.current.selectedIds).toEqual([])
  })

  it('leaves a staged scenario’s row alone — the thread owns it now', async () => {
    const { result } = await withScenario()
    act(() => result.current.markStaged('proposal-1'))
    expect(result.current.scenarios[0].status).toBe('staged')

    await act(async () => { await result.current.discard('proposal-1') })

    expect(cancelMock).not.toHaveBeenCalled()
    expect(result.current.scenarios).toEqual([])
  })
})

describe('useScheduleScenarios — selection', () => {
  async function withTwo() {
    previewMock.mockResolvedValueOnce(ready('proposal-1')).mockResolvedValueOnce(ready('proposal-2'))
    const view = render()
    await act(async () => { await view.result.current.preview({}) })
    await act(async () => { await view.result.current.preview({}) })
    return view
  }

  it('selects one at a time, and clicking the selected one clears it', async () => {
    const { result } = await withTwo()

    act(() => result.current.select('proposal-1'))
    expect(result.current.selectedIds).toEqual(['proposal-1'])

    act(() => result.current.select('proposal-1'))
    expect(result.current.selectedIds).toEqual([])
  })

  it('hands back the resulting selection, so the caller can follow it', async () => {
    const { result } = await withTwo()

    let next: string[] = []
    act(() => { next = result.current.select('proposal-1') })
    expect(next).toEqual(['proposal-1'])

    act(() => { next = result.current.select('proposal-2', { compare: true }) })
    expect(next).toEqual(['proposal-1', 'proposal-2'])

    // A compare click on the selected chip drops it; the caller needs to know
    // what is left, not what was clicked.
    act(() => { next = result.current.select('proposal-2', { compare: true }) })
    expect(next).toEqual(['proposal-1'])
  })

  it('holds at most two for a comparison', async () => {
    const { result } = await withTwo()

    act(() => result.current.select('proposal-1'))
    act(() => result.current.select('proposal-2', { compare: true }))
    expect(result.current.selectedIds).toEqual(['proposal-1', 'proposal-2'])

    // A third pushes the oldest out rather than growing without bound.
    previewMock.mockResolvedValue(ready('proposal-3'))
    await act(async () => { await result.current.preview({}) })
    act(() => result.current.select('proposal-1'))
    act(() => result.current.select('proposal-3', { compare: true }))
    expect(result.current.selectedIds).toEqual(['proposal-1', 'proposal-3'])
  })

  it('drops one out of a comparison when it is clicked again', async () => {
    const { result } = await withTwo()

    act(() => result.current.select('proposal-1'))
    act(() => result.current.select('proposal-2', { compare: true }))
    act(() => result.current.select('proposal-2', { compare: true }))

    expect(result.current.selectedIds).toEqual(['proposal-1'])
  })
})

describe('useScheduleScenarios — leaving the week', () => {
  it('discards the simulations nobody applied, and keeps their rows from lingering', async () => {
    previewMock.mockResolvedValueOnce(ready('proposal-1')).mockResolvedValueOnce(ready('proposal-2'))
    const { result, rerender } = render()
    await act(async () => { await result.current.preview({}) })
    await act(async () => { await result.current.preview({}) })
    act(() => result.current.markStaged('proposal-2'))

    rerender({ location: 'loc1', week: '2026-08-30' })

    // The staged one belongs to the thread now; only the untouched one is cancelled.
    await waitFor(() => expect(cancelMock).toHaveBeenCalledWith('proposal-1'))
    expect(cancelMock).not.toHaveBeenCalledWith('proposal-2')
    expect(result.current.scenarios).toEqual([])
    expect(result.current.selectedIds).toEqual([])
  })
})
