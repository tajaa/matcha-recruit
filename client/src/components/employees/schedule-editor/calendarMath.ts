import type { Shift, ShiftPayload } from '../../../types/employeeSchedule'

export const SLOT_MINUTES = 15
export const MIN_SHIFT_MINUTES = 15
export const MAX_SHIFT_MINUTES = 24 * 60

function dateAtMinute(date: string, minute: number): Date {
  const day = new Date(`${date}T00:00:00Z`)
  day.setUTCMinutes(minute)
  return day
}

function isoMinute(value: Date): string {
  return value.toISOString().replace(/\.000Z$/, 'Z')
}

export function snapMinute(minute: number, interval = SLOT_MINUTES): number {
  const safeInterval = Math.max(1, interval)
  return Math.max(0, Math.min(1440, Math.round(minute / safeInterval) * safeInterval))
}

export function shiftDurationMinutes(shift: Pick<Shift, 'starts_at' | 'ends_at'>): number {
  return Math.max(
    MIN_SHIFT_MINUTES,
    Math.round((Date.parse(shift.ends_at) - Date.parse(shift.starts_at)) / 60000),
  )
}

export function moveShiftWindow(
  shift: Pick<Shift, 'starts_at' | 'ends_at'>,
  targetDate: string,
  targetMinute: number,
): Pick<ShiftPayload, 'starts_at' | 'ends_at'> {
  const start = dateAtMinute(targetDate, snapMinute(targetMinute))
  const end = new Date(start.getTime() + shiftDurationMinutes(shift) * 60000)
  return { starts_at: isoMinute(start), ends_at: isoMinute(end) }
}

export function resizeShiftWindow(
  shift: Pick<Shift, 'starts_at' | 'ends_at'>,
  endMinute: number,
): Pick<ShiftPayload, 'ends_at'> {
  const start = new Date(shift.starts_at)
  const snappedEndMinute = Math.max(0, Math.round(endMinute / SLOT_MINUTES) * SLOT_MINUTES)
  let end = dateAtMinute(start.toISOString().slice(0, 10), snappedEndMinute)
  const originallyOvernight = new Date(shift.ends_at).toISOString().slice(0, 10) !== start.toISOString().slice(0, 10)
  if (end <= start && originallyOvernight) end = new Date(end.getTime() + 24 * 60 * 60000)
  if (end.getTime() - start.getTime() < MIN_SHIFT_MINUTES * 60000) {
    end = new Date(start.getTime() + MIN_SHIFT_MINUTES * 60000)
  }
  return { ends_at: isoMinute(end) }
}

export function shiftPosition(
  shift: Pick<Shift, 'starts_at' | 'ends_at'>,
): { topPercent: number; heightPercent: number; continuesNextDay: boolean } {
  const start = new Date(shift.starts_at)
  const startMinute = start.getUTCHours() * 60 + start.getUTCMinutes()
  const duration = shiftDurationMinutes(shift)
  const visibleDuration = Math.min(duration, 1440 - startMinute)
  return {
    topPercent: (startMinute / 1440) * 100,
    heightPercent: Math.max((visibleDuration / 1440) * 100, (MIN_SHIFT_MINUTES / 1440) * 100),
    continuesNextDay: duration > visibleDuration,
  }
}

/** Lanes for anything with a window — real shifts, and the read-only
 *  proposal blocks the board overlays on them, which must share the lanes. */
export function layoutOverlappingShifts<T extends Pick<Shift, 'starts_at' | 'ends_at'>>(shifts: T[]): Array<{
  shift: T
  lane: number
  laneCount: number
}> {
  const sorted = [...shifts].sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at))
  const lanes: number[] = []
  const placed = sorted.map((shift) => {
    const start = Date.parse(shift.starts_at)
    const end = Date.parse(shift.ends_at)
    let lane = lanes.findIndex((laneEnd) => laneEnd <= start)
    if (lane < 0) lane = lanes.length
    lanes[lane] = end
    return { shift, lane }
  })
  return placed.map((item) => ({ ...item, laneCount: lanes.length || 1 }))
}

/** The default board window for a week with nothing on it yet. */
export const DEFAULT_VISIBLE_WINDOW = { start: 6 * 60, end: 22 * 60 }
const MIN_VISIBLE_MINUTES = 8 * 60
const VISIBLE_PADDING_MINUTES = 60

/** The slice of the day the board draws: every shift (and proposal, and
 *  demand run) with an hour either side, on whole hours, at least eight hours
 *  tall — so a 6:30a–10p store doesn't open on seven empty overnight hours.
 *  A shift that runs past midnight keeps the window open to the end of the day. */
export function visibleWindow(
  items: Array<Pick<Shift, 'starts_at' | 'ends_at'>>,
  extraRanges: Array<{ start: number; end: number }> = [],
): { start: number; end: number } {
  const ranges = [
    ...items.map((item) => {
      const start = new Date(item.starts_at)
      const startMinute = start.getUTCHours() * 60 + start.getUTCMinutes()
      return { start: startMinute, end: Math.min(1440, startMinute + shiftDurationMinutes(item)) }
    }),
    ...extraRanges,
  ]
  if (!ranges.length) return { ...DEFAULT_VISIBLE_WINDOW }
  let start = Math.max(0, Math.floor((Math.min(...ranges.map((range) => range.start)) - VISIBLE_PADDING_MINUTES) / 60) * 60)
  let end = Math.min(1440, Math.ceil((Math.max(...ranges.map((range) => range.end)) + VISIBLE_PADDING_MINUTES) / 60) * 60)
  if (end - start < MIN_VISIBLE_MINUTES) {
    end = Math.min(1440, start + MIN_VISIBLE_MINUTES)
    start = Math.max(0, end - MIN_VISIBLE_MINUTES)
  }
  return { start, end }
}
