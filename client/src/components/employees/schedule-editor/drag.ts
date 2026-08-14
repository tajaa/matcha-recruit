export type ScheduleDragData =
  | { kind: 'roster-employee'; employeeId: string }
  | { kind: 'shift-assignment'; employeeId: string; fromShiftId: string }
  | { kind: 'shift'; shiftId: string }

export type ScheduleDropData =
  | { kind: 'shift'; shiftId: string }
  | { kind: 'time-slot'; date: string; minute: number }
  | { kind: 'unassign' }

export type ScheduleDropAction =
  | { kind: 'assign'; employeeId: string; toShiftId: string }
  | { kind: 'move-assignment'; employeeId: string; fromShiftId: string; toShiftId: string }
  | { kind: 'unassign'; employeeId: string; fromShiftId: string }
  | { kind: 'move-shift'; shiftId: string; date: string; minute: number }
  | { kind: 'create-with-employee'; employeeId: string; date: string; minute: number }

export function resolveScheduleDrop(
  active: ScheduleDragData,
  over: ScheduleDropData | null,
): ScheduleDropAction | null {
  if (!over) return null
  if (active.kind === 'roster-employee') {
    if (over.kind === 'shift') return { kind: 'assign', employeeId: active.employeeId, toShiftId: over.shiftId }
    if (over.kind === 'time-slot') return { kind: 'create-with-employee', employeeId: active.employeeId, date: over.date, minute: over.minute }
    return null
  }
  if (active.kind === 'shift-assignment') {
    if (over.kind === 'shift') {
      if (over.shiftId === active.fromShiftId) return null
      return { kind: 'move-assignment', employeeId: active.employeeId, fromShiftId: active.fromShiftId, toShiftId: over.shiftId }
    }
    if (over.kind === 'unassign') return { kind: 'unassign', employeeId: active.employeeId, fromShiftId: active.fromShiftId }
    return null
  }
  if (active.kind === 'shift' && over.kind === 'time-slot') {
    return { kind: 'move-shift', shiftId: active.shiftId, date: over.date, minute: over.minute }
  }
  return null
}
