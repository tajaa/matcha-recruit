import { describe, expect, it } from 'vitest'
import { layoutOverlappingShifts, moveShiftWindow, resizeShiftWindow, shiftPosition, snapMinute } from './calendarMath'
import type { Shift } from '../../../types/employeeSchedule'

const shift = (id: string, starts_at: string, ends_at: string): Shift => ({
  id, starts_at, ends_at, assignments: [], role: null, department: null, location_id: null,
  template_id: null, series_id: null, break_minutes: 0, required_staff: 1, color: null,
  notes: null, status: 'draft', kind: 'work', training_requirement_id: null, published_at: null,
})

describe('schedule editor calendar math', () => {
  it('snaps to fifteen-minute slots', () => expect(snapMinute(23)).toBe(30))
  it('moves a shift while preserving duration', () => {
    expect(moveShiftWindow(shift('a', '2026-08-09T09:00:00Z', '2026-08-09T17:00:00Z'), '2026-08-10', 615)).toEqual({
      starts_at: '2026-08-10T10:15:00Z', ends_at: '2026-08-10T18:15:00Z',
    })
  })
  it('preserves overnight windows', () => {
    expect(moveShiftWindow(shift('a', '2026-08-09T22:00:00Z', '2026-08-10T06:00:00Z'), '2026-08-11', 1320)).toEqual({
      starts_at: '2026-08-11T22:00:00Z', ends_at: '2026-08-12T06:00:00Z',
    })
  })
  it('enforces a minimum resize duration', () => {
    expect(resizeShiftWindow(shift('a', '2026-08-09T09:00:00Z', '2026-08-09T17:00:00Z'), 540).ends_at).toBe('2026-08-09T09:15:00Z')
  })
  it('marks overnight blocks and gives overlapping shifts lanes', () => {
    expect(shiftPosition(shift('a', '2026-08-09T22:00:00Z', '2026-08-10T06:00:00Z')).continuesNextDay).toBe(true)
    const placed = layoutOverlappingShifts([
      shift('a', '2026-08-09T09:00:00Z', '2026-08-09T12:00:00Z'),
      shift('b', '2026-08-09T10:00:00Z', '2026-08-09T13:00:00Z'),
    ])
    expect(placed.map((item) => item.lane)).toEqual([0, 1])
    expect(placed.every((item) => item.laneCount === 2)).toBe(true)
  })
})
