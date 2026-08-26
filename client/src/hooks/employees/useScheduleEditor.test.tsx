import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/client'
import { useScheduleEditor } from './useScheduleEditor'

const { assignEmployeeMock, fetchWeekMock, fetchScheduleLocationsMock, updateShiftMock, moveAssignmentMock } = vi.hoisted(() => ({
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
  createShift: vi.fn(),
  deleteShift: vi.fn(),
  publishRange: vi.fn(),
  assignEmployee: assignEmployeeMock,
  unassignEmployee: vi.fn(),
}))

const shift = (id: string, assigned: string[] = []) => ({
  id, starts_at: '2026-08-09T09:00:00Z', ends_at: '2026-08-09T17:00:00Z',
  assignments: assigned.map((employee_id) => ({ employee_id, name: employee_id, job_title: null, status: 'assigned' as const })),
  role: null, department: null, location_id: null, template_id: null, series_id: null,
  break_minutes: 30, required_staff: 1, color: null, notes: null, status: 'draft' as const,
  kind: 'work' as const, training_requirement_id: null, job_id: null, published_at: null,
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
  })

  it('loads the week payload', async () => {
    const { result } = renderHook(() => useScheduleEditor('2026-08-09', 'loc1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.roster[0].name).toBe('Aisha Rivera')
    expect(result.current.shifts).toHaveLength(2)
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
