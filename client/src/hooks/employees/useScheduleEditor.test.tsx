import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useScheduleEditor } from './useScheduleEditor'

const { fetchWeekMock, updateShiftMock, moveAssignmentMock } = vi.hoisted(() => ({
  fetchWeekMock: vi.fn(),
  updateShiftMock: vi.fn(),
  moveAssignmentMock: vi.fn(),
}))

vi.mock('../../api/employees/employeeSchedule', () => ({
  fetchWeek: fetchWeekMock,
  updateShift: updateShiftMock,
  moveAssignment: moveAssignmentMock,
  createShift: vi.fn(),
  deleteShift: vi.fn(),
  publishRange: vi.fn(),
  assignEmployee: vi.fn(),
  unassignEmployee: vi.fn(),
}))

const shift = (id: string, assigned: string[] = []) => ({
  id, starts_at: '2026-08-09T09:00:00Z', ends_at: '2026-08-09T17:00:00Z',
  assignments: assigned.map((employee_id) => ({ employee_id, name: employee_id, job_title: null, status: 'assigned' as const })),
  role: null, department: null, location_id: null, template_id: null, series_id: null,
  break_minutes: 30, required_staff: 1, color: null, notes: null, status: 'draft' as const,
  kind: 'work' as const, training_requirement_id: null, published_at: null,
})

describe('useScheduleEditor', () => {
  beforeEach(() => {
    fetchWeekMock.mockResolvedValue({
      week_start: '2026-08-09', shifts: [shift('s1', ['e1']), shift('s2')],
      roster: [{ id: 'e1', name: 'Aisha Rivera', job_title: null, department: null }],
      roster_flags: null, locations: [],
      summary: { total_shifts: 2, published: 0, draft: 2, open_shifts: 1, assigned: 1 },
    })
    updateShiftMock.mockResolvedValue(shift('s1', ['e1']))
    moveAssignmentMock.mockResolvedValue({ source_shift: shift('s1'), target_shift: shift('s2', ['e1']) })
  })

  it('loads the week payload', async () => {
    const { result } = renderHook(() => useScheduleEditor('2026-08-09'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.roster[0].name).toBe('Aisha Rivera')
    expect(result.current.shifts).toHaveLength(2)
  })

  it('moves a shift with a preserved duration window', async () => {
    const { result } = renderHook(() => useScheduleEditor('2026-08-09'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { await result.current.moveShift(result.current.shifts[0], '2026-08-10', 600) })
    expect(updateShiftMock).toHaveBeenCalledWith('s1', {
      starts_at: '2026-08-10T10:00:00Z', ends_at: '2026-08-10T18:00:00Z',
    }, false)
  })

  it('patches both shifts after an assignment move', async () => {
    const { result } = renderHook(() => useScheduleEditor('2026-08-09'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { await result.current.moveEmployee('e1', 's1', 's2') })
    expect(moveAssignmentMock).toHaveBeenCalledWith({ employee_id: 'e1', from_shift_id: 's1', to_shift_id: 's2' }, false)
    await waitFor(() => expect(result.current.shifts.find((item) => item.id === 's2')?.assignments[0]?.employee_id).toBe('e1'))
  })
})
