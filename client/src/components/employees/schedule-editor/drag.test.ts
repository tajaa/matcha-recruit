import { describe, expect, it } from 'vitest'
import { resolveScheduleDrop } from './drag'

describe('schedule editor drag resolution', () => {
  it('assigns a roster employee to an existing shift', () => {
    expect(resolveScheduleDrop({ kind: 'roster-employee', employeeId: 'e1' }, { kind: 'shift', shiftId: 's1' }))
      .toEqual({ kind: 'assign', employeeId: 'e1', toShiftId: 's1' })
  })
  it('creates an assigned draft on an empty slot', () => {
    expect(resolveScheduleDrop({ kind: 'roster-employee', employeeId: 'e1' }, { kind: 'time-slot', date: '2026-08-09', minute: 540 }))
      .toEqual({ kind: 'create-with-employee', employeeId: 'e1', date: '2026-08-09', minute: 540 })
  })
  it('moves an existing assignment to another shift', () => {
    expect(resolveScheduleDrop({ kind: 'shift-assignment', employeeId: 'e1', fromShiftId: 's1' }, { kind: 'shift', shiftId: 's2' }))
      .toEqual({ kind: 'move-assignment', employeeId: 'e1', fromShiftId: 's1', toShiftId: 's2' })
  })
  it('does not move an assignment onto its source', () => {
    expect(resolveScheduleDrop({ kind: 'shift-assignment', employeeId: 'e1', fromShiftId: 's1' }, { kind: 'shift', shiftId: 's1' })).toBeNull()
  })
  it('supports the unassign zone', () => {
    expect(resolveScheduleDrop({ kind: 'shift-assignment', employeeId: 'e1', fromShiftId: 's1' }, { kind: 'unassign' }))
      .toEqual({ kind: 'unassign', employeeId: 'e1', fromShiftId: 's1' })
  })
  it('returns null for an incompatible drop', () => {
    expect(resolveScheduleDrop({ kind: 'shift', shiftId: 's1' }, { kind: 'shift', shiftId: 's2' })).toBeNull()
  })
})
