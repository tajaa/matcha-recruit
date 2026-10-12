import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/client'
import { useScheduleEditor } from './useScheduleEditor'
import type { Shift, WeekLaborCost, WeekResponse } from '../../types/employeeSchedule'
import { DndContext } from '@dnd-kit/core'
import WeekTimeGrid from '../../components/employees/schedule-editor/WeekTimeGrid'
import WeekRosterGrid from '../../components/employees/schedule-pilot/WeekRosterGrid'
import DayAgenda from '../../components/employees/schedule-pilot/DayAgenda'

const { assignEmployeeMock, fetchWeekMock, fetchScheduleLocationsMock, updateShiftMock, moveAssignmentMock, deleteShiftMock, publishRangeMock, createShiftMock } = vi.hoisted(() => ({
  createShiftMock: vi.fn(),
  deleteShiftMock: vi.fn(),
  publishRangeMock: vi.fn(),
  assignEmployeeMock: vi.fn(),
  fetchWeekMock: vi.fn(),
  fetchScheduleLocationsMock: vi.fn(),
  updateShiftMock: vi.fn(),
  moveAssignmentMock: vi.fn(),
}))

vi.mock('../../api/employees/employeeSchedule', () => ({
  fetchWeek: fetchWeekMock,
  fetchScheduleLocations: fetchScheduleLocationsMock,
  updateShift: updateShiftMock,
  moveAssignment: moveAssignmentMock,
  createShift: createShiftMock,
  deleteShift: deleteShiftMock,
  publishRange: publishRangeMock,
  assignEmployee: assignEmployeeMock,
  unassignEmployee: vi.fn(),
}))

const shift = (id: string, assigned: string[] = [], extra: Partial<Shift> = {}): Shift => ({
  id, starts_at: '2026-08-09T09:00:00Z', ends_at: '2026-08-09T17:00:00Z',
  assignments: assigned.map((employee_id) => ({ employee_id, name: employee_id, job_title: null, status: 'assigned' as const, availability_overridden: false, availability_override_at: null })),
  role: null, department: null, location_id: null, template_id: null, series_id: null,
  break_minutes: 30, required_staff: 1, color: null, notes: null, status: 'draft' as const,
  kind: 'work' as const, training_requirement_id: null, job_id: null, published_at: null, ...extra,
})

describe('useScheduleEditor', () => {
  beforeEach(() => {
    fetchWeekMock.mockResolvedValue({
      week_start: '2026-08-09', location_id: 'loc1', shifts: [shift('s1', ['e1']), shift('s2')],
      roster: [{ id: 'e1', name: 'Aisha Rivera', job_title: null, department: null, job_ids: [] }],
      roster_flags: null,
      summary: { total_shifts: 2, published: 0, draft: 2, open_shifts: 1, assigned: 1 },
    })
    fetchScheduleLocationsMock.mockResolvedValue({ locations: [] })
    updateShiftMock.mockResolvedValue(shift('s1', ['e1']))
    moveAssignmentMock.mockResolvedValue({ source_shift: shift('s1'), target_shift: shift('s2', ['e1']) })
    assignEmployeeMock.mockReset()
    deleteShiftMock.mockResolvedValue({ ok: true, id: 's1' })
  })

  it('loads the week payload', async () => {
    const { result } = renderHook(() => useScheduleEditor('2026-08-09', 'loc1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.roster[0].name).toBe('Aisha Rivera')
    expect(result.current.shifts).toHaveLength(2)
  })

  it('excludes retained cancellations from the board and all shift counts after loading and publishing', async () => {
    const week = cancelledWeek()
    fetchWeekMock.mockResolvedValue(week)
    publishRangeMock.mockResolvedValue({ ...week, shifts: week.shifts.map((item) => (
      item.status === 'draft' ? { ...item, status: 'published' } : item
    )) })
    const { result } = renderHook(() => useScheduleEditor('2026-08-09', 'loc1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.shifts).toEqual(week.shifts.slice(1))
    expect(result.current.summary).toMatchObject({ total_shifts: 2, draft: 1, published: 1, assigned: 2, open_shifts: 0 })

    await act(async () => { await result.current.publishWeek() })
    expect(result.current.shifts.map((item) => item.id)).toEqual(['s1', 's2'])
    expect(result.current.summary).toMatchObject({ total_shifts: 2, draft: 0, published: 2, assigned: 2, open_shifts: 0 })
  })

  it('removes a cancellation returned by an update from the board and counts', async () => {
    updateShiftMock.mockResolvedValue(shift('s1', ['e1'], { status: 'cancelled' }))
    const { result } = renderHook(() => useScheduleEditor('2026-08-09', 'loc1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { await result.current.updateShiftDraft(result.current.shifts[0], { status: 'cancelled' }) })
    expect(result.current.shifts.map((item) => item.id)).toEqual(['s2'])
    expect(result.current.summary).toMatchObject({ total_shifts: 1, draft: 1, published: 0, assigned: 0, open_shifts: 1 })
  })

  it('removes a deleted shift immediately and replaces stale cost with a server repricing without hiding the board', async () => {
    const week = cancelledWeek()
    const repriced = { ...week, shifts: [week.shifts[2]], summary: { ...week.summary, cost: cost(150) } }
    let finishRefresh!: (value: WeekResponse) => void
    fetchWeekMock.mockResolvedValueOnce(week).mockImplementationOnce(() => new Promise<WeekResponse>((resolve) => { finishRefresh = resolve }))
    const onShiftRemoved = vi.fn()
    const { result } = renderHook(() => useScheduleEditor('2026-08-09', 'loc1', { onShiftRemoved }))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.summary?.cost?.total).toBe(400)

    await act(async () => { expect(await result.current.removeShift(result.current.shifts[0])).toBe(true) })
    expect(deleteShiftMock).toHaveBeenCalledWith('s1', false)
    expect(result.current.shifts.map((item) => item.id)).toEqual(['s2'])
    expect(result.current.summary).toMatchObject({ total_shifts: 1, draft: 0, published: 1, assigned: 1 })
    expect(result.current.summary?.cost).toBeUndefined()
    expect(result.current.loading).toBe(false)
    expect(onShiftRemoved).toHaveBeenCalledTimes(1)

    await act(async () => { finishRefresh(repriced) })
    expect(result.current.summary?.cost?.total).toBe(150)
    expect(result.current.summary?.cost?.by_day['2026-08-09']).toBe(150)
    expect(result.current.shifts.map((item) => item.id)).toEqual(['s2'])
  })

  it('does not let an older week fetch restore a successfully deleted shift', async () => {
    const week = cancelledWeek()
    let finishStaleRead!: (value: WeekResponse) => void
    fetchWeekMock.mockResolvedValueOnce(week)
      .mockImplementationOnce(() => new Promise<WeekResponse>((resolve) => { finishStaleRead = resolve }))
      .mockResolvedValueOnce({ ...week, shifts: [week.shifts[2]] })
    const { result } = renderHook(() => useScheduleEditor('2026-08-09', 'loc1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    let staleRead!: Promise<void>
    act(() => { staleRead = result.current.reload() })
    await act(async () => { await result.current.removeShift(result.current.shifts[0]) })
    await act(async () => { finishStaleRead(week); await staleRead })
    expect(result.current.shifts.map((item) => item.id)).toEqual(['s2'])
    expect(result.current.summary?.total_shifts).toBe(1)
  })

  it('counts a newly created draft from the visible shifts', async () => {
    createShiftMock.mockResolvedValue(shift('s3'))
    const { result } = renderHook(() => useScheduleEditor('2026-08-09', 'loc1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { await result.current.createDraft({ starts_at: '2026-08-09T09:00:00Z', ends_at: '2026-08-09T17:00:00Z' }) })
    expect(result.current.summary).toMatchObject({ total_shifts: 3, draft: 3, published: 0, open_shifts: 2, assigned: 1 })
  })

  it('keeps a successful deletion when repricing fails and never restores the old cost', async () => {
    fetchWeekMock.mockResolvedValueOnce(cancelledWeek()).mockRejectedValueOnce(new Error('Network error'))
    const { result } = renderHook(() => useScheduleEditor('2026-08-09', 'loc1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { expect(await result.current.removeShift(result.current.shifts[0])).toBe(true) })
    expect(result.current.shifts.map((item) => item.id)).toEqual(['s2'])
    expect(result.current.summary?.cost).toBeUndefined()
    expect(result.current.saveState).toBe('saved')
  })

  it('retains the shift and totals when deletion fails', async () => {
    fetchWeekMock.mockResolvedValue(cancelledWeek())
    deleteShiftMock.mockRejectedValue(new Error('Delete failed'))
    const onShiftRemoved = vi.fn()
    const { result } = renderHook(() => useScheduleEditor('2026-08-09', 'loc1', { onShiftRemoved }))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { expect(await result.current.removeShift(result.current.shifts[0])).toBe(false) })
    expect(result.current.shifts.map((item) => item.id)).toEqual(['s1', 's2'])
    expect(result.current.summary?.total_shifts).toBe(2)
    expect(result.current.summary?.cost?.total).toBe(400)
    expect(onShiftRemoved).not.toHaveBeenCalled()
  })

  it.each(['roster', 'timeline', 'agenda'] as const)('removes cancelled and deleted shifts from the %s view and preserves the remaining shift', async (view) => {
    fetchWeekMock.mockResolvedValueOnce(cancelledWeek()).mockImplementationOnce(() => new Promise(() => {}))
    render(<EditorBoard view={view} />)
    await waitFor(() => expect(screen.getByLabelText('Shift count')).toHaveTextContent('2 shifts'))
    expect(screen.queryByText(/Cancelled shift/)).not.toBeInTheDocument()
    expect(screen.getByText(/Remove me/)).toBeInTheDocument()
    expect(screen.getByText(/Kept shift/)).toBeInTheDocument()
    if (view === 'roster') expect(screen.getByRole('rowheader', { name: /Aisha Rivera15h/ })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Delete first shift' }))
    await waitFor(() => expect(screen.queryByText(/Remove me/)).not.toBeInTheDocument())
    expect(screen.getByLabelText('Shift count')).toHaveTextContent('1 shifts')
    expect(screen.getByText(/Kept shift/)).toBeInTheDocument()
    if (view === 'roster') expect(screen.getByRole('rowheader', { name: /Aisha Rivera7.5h/ })).toBeInTheDocument()
    if (view === 'agenda') expect(screen.getByRole('tab', { name: /Sunday, Aug 9, 1 shift/ })).toBeInTheDocument()
  })

  it('moves a shift with a preserved duration window', async () => {
    const { result } = renderHook(() => useScheduleEditor('2026-08-09', 'loc1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { await result.current.moveShift(result.current.shifts[0], '2026-08-10', 600) })
    expect(updateShiftMock).toHaveBeenCalledWith('s1', {
      starts_at: '2026-08-10T10:00:00Z', ends_at: '2026-08-10T18:00:00Z',
    }, false)
  })

  it('patches both shifts after an assignment move', async () => {
    const { result } = renderHook(() => useScheduleEditor('2026-08-09', 'loc1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { await result.current.moveEmployee('e1', 's1', 's2') })
    expect(moveAssignmentMock).toHaveBeenCalledWith({ employee_id: 'e1', from_shift_id: 's1', to_shift_id: 's2' }, false)
    await waitFor(() => expect(result.current.shifts.find((item) => item.id === 's2')?.assignments[0]?.employee_id).toBe('e1'))
  })

  it('opens break planning instead of offering a compliance override', async () => {
    const onMealBreakRequired = vi.fn()
    const confirm = vi.spyOn(window, 'confirm')
    assignEmployeeMock.mockRejectedValue(new ApiError('compliance', 409, {
      detail: {
        code: 'schedule_compliance',
        violations: [{ check: 'meal_break', severity: 'advisory', message: 'A 30-minute break is required' }],
      },
    }))
    const { result } = renderHook(() => useScheduleEditor(
      '2026-08-09', 'loc1', { onMealBreakRequired },
    ))
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => { await result.current.assignToShift(result.current.shifts[1], 'e1') })

    expect(onMealBreakRequired).toHaveBeenCalledWith(
      expect.objectContaining({ id: 's2' }), 'e1', 'A 30-minute break is required',
    )
    expect(assignEmployeeMock).toHaveBeenCalledTimes(1)
    expect(confirm).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('opens the target shift break planner when moving an assignment', async () => {
    const onMealBreakRequired = vi.fn()
    moveAssignmentMock.mockRejectedValue(new ApiError('compliance', 409, {
      detail: {
        code: 'schedule_compliance',
        violations: [{ check: 'meal_break', severity: 'advisory', message: 'A 30-minute break is required' }],
      },
    }))
    const { result } = renderHook(() => useScheduleEditor(
      '2026-08-09', 'loc1', { onMealBreakRequired },
    ))
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => { await result.current.moveEmployee('e1', 's1', 's2') })

    expect(onMealBreakRequired).toHaveBeenCalledWith(
      expect.objectContaining({ id: 's2' }), 'e1', 'A 30-minute break is required',
    )
    expect(moveAssignmentMock).toHaveBeenCalledTimes(1)
  })

  it('serializes mutations that affect the same shift', async () => {
    let releaseFirst: (value: ReturnType<typeof shift>) => void = () => undefined
    const firstResponse = new Promise<ReturnType<typeof shift>>((resolve) => {
      releaseFirst = resolve
    })
    updateShiftMock.mockImplementationOnce(() => firstResponse)

    const { result } = renderHook(() => useScheduleEditor('2026-08-09', 'loc1'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    let firstMutation: Promise<unknown> = Promise.resolve()
    let secondMutation: Promise<unknown> = Promise.resolve()
    act(() => {
      firstMutation = result.current.updateShiftDraft(result.current.shifts[0], { role: 'First' })
      secondMutation = result.current.updateShiftDraft(result.current.shifts[0], { role: 'Second' })
    })
    await waitFor(() => expect(updateShiftMock).toHaveBeenCalledTimes(1))

    releaseFirst(shift('s1', ['e1']))
    await act(async () => { await Promise.all([firstMutation, secondMutation]) })

    expect(updateShiftMock).toHaveBeenCalledTimes(2)
    expect(updateShiftMock.mock.calls[1][1]).toEqual({ role: 'Second' })
  })
})

function cost(total: number): WeekLaborCost {
  return {
    week_start: '2026-08-09', total, hourly_total: total, salaried_total: 0, open_seat_total: 0,
    ot_premium: 0, ot_minutes: 0, by_day: { '2026-08-09': total }, employees: [],
    unpriced_employee_ids: [], unpriced_employee_count: 0, unpriced_open_seats: 0,
    unpriced_days: [], truncated: false,
    basis: { daily_ot_hours: 8, daily_doubletime_hours: 12, weekly_ot_hours: 40, ot_multiplier: 1.5, doubletime_multiplier: 2, overtime_citation: null, as_scheduled: true },
  }
}

function cancelledWeek(): WeekResponse {
  return {
    week_start: '2026-08-09', location_id: 'loc1',
    shifts: [
      shift('cancelled', ['e1'], { status: 'cancelled', role: 'Cancelled shift' }),
      shift('s1', ['e1'], { role: 'Remove me' }),
      shift('s2', ['e1'], { status: 'published', role: 'Kept shift' }),
    ],
    roster: [{ id: 'e1', name: 'Aisha Rivera', job_title: null, department: null, job_ids: [] }],
    roster_flags: null,
    // The server includes cancelled rows in these two counts, but its cost
    // query already excludes them.
    summary: { total_shifts: 3, published: 1, draft: 1, assigned: 3, open_shifts: 0, cost: cost(400) },
  }
}

function EditorBoard({ view }: { view: 'roster' | 'timeline' | 'agenda' }) {
  const editor = useScheduleEditor('2026-08-09', 'loc1')
  const common = {
    days: ['2026-08-09'], shifts: editor.shifts, huumeSelectedShiftIds: new Set<string>(),
    onOpenShift: () => {}, onToggleHuumeSelection: () => {},
  }
  return <DndContext>
    <button onClick={() => { void editor.removeShift(editor.shifts[0]) }}>Delete first shift</button>
    <output aria-label="Shift count">{editor.summary?.total_shifts} shifts</output>
    {view === 'roster'
      ? <WeekRosterGrid {...common} roster={editor.roster} selectedEmployeeId={null} onCreateFor={() => {}} />
      : view === 'timeline'
        ? <WeekTimeGrid {...common} pendingKeys={editor.pendingKeys} editPublished={true} selectedEmployeeId={null} onCreateAt={() => {}} onAssignSelected={() => {}} onResizeShift={() => {}} />
        : <DayAgenda {...common} />}
  </DndContext>
}
