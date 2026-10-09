import { useState } from 'react'
import { useDroppable } from '@dnd-kit/core'
import type { Shift } from '../../../types/employeeSchedule'
import { fmtDayLabel } from '../../../types/employeeSchedule'
import { costLabel } from '../schedule-pilot/reviewShape'
import type { DemandSegment, PreviewShift } from '../schedule-pilot/reviewVerdict'
import type { ShiftMark } from '../schedule-pilot/boardMarks'
import { layoutOverlappingShifts, shiftDurationMinutes, visibleWindow } from './calendarMath'
import PreviewShiftBlock from './PreviewShiftBlock'
import ShiftBlock from './ShiftBlock'

interface WeekTimeGridProps {
  days: string[]
  shifts: Shift[]
  pendingKeys: ReadonlySet<string>
  editPublished: boolean
  selectedEmployeeId: string | null
  huumeSelectedShiftIds: ReadonlySet<string>
  /** Scheduled cost per ISO day. Undefined = the viewer has no `labor_cost`
   *  access, and the column header shows no money at all. */
  costByDay?: Record<string, number>
  /** Days where somebody worked who could not be priced. Those render a dash:
   *  a "$0" beside a fully-staffed day reads as "this day is free". */
  unpricedDays?: ReadonlySet<string>
  /** A proposal's shifts, drawn read-only beside the real ones before
   *  anything is written (a generated week under review). */
  previewShifts?: PreviewShift[]
  /** Per ISO day: demanded vs covered headcount, as a band on the column's
   *  left edge — red where the proposal staffs less than the demand. */
  demand?: Record<string, DemandSegment[]>
  /** What a pending proposal does to shifts already on the board. */
  marks?: ReadonlyMap<string, ShiftMark>
  /** Shifts an applied Huume change just touched. */
  recentShiftIds?: ReadonlySet<string>
  onCreateAt(date: string, minute: number, employeeId?: string): void
  onOpenShift(shift: Shift): void
  onToggleHuumeSelection(shift: Shift): void
  onAssignSelected(shift: Shift): void
  onResizeShift(shift: Shift, endMinute: number): void
}

function fmtClock(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`
}

function TimeSlot({ date, minute, top, onCreate }: { date: string; minute: number; top: number; onCreate(): void }) {
  const { setNodeRef, isOver } = useDroppable({ id: `slot-${date}-${minute}`, data: { kind: 'time-slot', date, minute } })
  return <button ref={setNodeRef} onClick={onCreate} className={`absolute left-0 right-0 border-t border-zinc-900/80 text-left ${isOver ? 'bg-emerald-500/10' : 'hover:bg-white/[0.02]'}`} style={{ top, height: 15 }} aria-label={`Create shift on ${date} at ${minute} minutes`} />
}

/** Where an item sits inside the visible window, in pixels (1px = 1 minute).
 *  Anything running past the window's end is clipped to it. */
function placement(item: { starts_at: string; ends_at: string }, windowStart: number, windowEnd: number) {
  const start = new Date(item.starts_at)
  const startMinute = start.getUTCHours() * 60 + start.getUTCMinutes()
  const end = Math.min(startMinute + shiftDurationMinutes(item), windowEnd)
  return { top: startMinute - windowStart, height: Math.max(end - startMinute, 15) }
}

type GridItem = { starts_at: string; ends_at: string; real?: Shift; preview?: PreviewShift }

export default function WeekTimeGrid({ days, shifts, pendingKeys, editPublished, selectedEmployeeId, huumeSelectedShiftIds, costByDay, unpricedDays, previewShifts, demand, marks, recentShiftIds, onCreateAt, onOpenShift, onToggleHuumeSelection, onAssignSelected, onResizeShift }: WeekTimeGridProps) {
  const [fullDay, setFullDay] = useState(false)
  // Fit the board to the hours that matter (shifts, proposals, demand) unless
  // the manager asks for the whole day — the only way to reach a slot outside it.
  const inWeek = (item: { starts_at: string }) => days.includes(item.starts_at.slice(0, 10))
  const fitted = visibleWindow(
    [...shifts.filter(inWeek), ...(previewShifts ?? []).filter(inWeek)],
    days.flatMap((day) => demand?.[day] ?? []),
  )
  const { start: windowStart, end: windowEnd } = fullDay ? { start: 0, end: 1440 } : fitted
  const windowHeight = windowEnd - windowStart
  const hours = Array.from({ length: windowHeight / 60 + 1 }, (_, i) => windowStart / 60 + i).filter((hour) => hour < 24)
  const slots = Array.from({ length: windowHeight / 15 }, (_, index) => windowStart + index * 15)
  const layouts = days.map((day) => {
    // Previews share the lanes with real shifts so neither covers the other.
    const dayItems: GridItem[] = [
      ...shifts.filter((shift) => shift.starts_at.slice(0, 10) === day)
        .map((shift) => ({ starts_at: shift.starts_at, ends_at: shift.ends_at, real: shift })),
      ...(previewShifts ?? []).filter((shift) => shift.starts_at.slice(0, 10) === day)
        .map((shift) => ({ starts_at: shift.starts_at, ends_at: shift.ends_at, preview: shift })),
    ]
    const positioned = layoutOverlappingShifts(dayItems)
    const laneCount = Math.max(1, ...positioned.map((item) => item.laneCount))
    return { day, positioned, width: Math.max(220, laneCount * 180) }
  })
  const gridTemplateColumns = `48px ${layouts.map((layout) => `${layout.width}px`).join(' ')}`
  const gridMinWidth = 48 + layouts.reduce((total, layout) => total + layout.width, 0)
  return (
    <div className="min-h-0 min-w-0 flex-1 overflow-auto bg-zinc-950 p-3 md:p-5">
      <div style={{ minWidth: gridMinWidth }}>
        <div className="grid border-b border-zinc-800" style={{ gridTemplateColumns }}>
          <div className="flex items-end justify-end pb-2 pr-1">
            <button
              type="button"
              onClick={() => setFullDay((value) => !value)}
              aria-pressed={fullDay}
              title={fullDay ? 'Fit to the hours in use' : 'Show the whole day'}
              className="rounded border border-zinc-800 px-1 font-mono text-[9px] text-zinc-500 hover:border-zinc-600 hover:text-zinc-200"
            >{fullDay ? 'fit' : '24h'}</button>
          </div>
          {layouts.map(({ day, width }) => (
            <div key={day} style={{ width }} className="flex items-baseline gap-2 border-l border-zinc-900 px-2 pb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-zinc-400">{fmtDayLabel(day)}</span>
              {costByDay && (
                <span
                  className="font-mono text-[10px] tabular-nums text-zinc-600"
                  title={unpricedDays?.has(day)
                    ? 'Someone on this day has no pay rate on file — not priced'
                    : 'Scheduled labor cost this day'}
                >
                  {unpricedDays?.has(day)
                    // Partly priced: show what IS known, marked as a floor.
                    // An unmarked "$540" on a day whose fourth person has no
                    // rate reads as the day's total and makes it look cheap.
                    ? (costByDay[day] ? `\u2265${costLabel(costByDay[day])}` : costLabel(null))
                    : costLabel(costByDay[day])}
                </span>
              )}
            </div>
          ))}
        </div>
        <div className="grid" style={{ gridTemplateColumns }}>
          <div className="relative text-[10px] text-zinc-700" style={{ height: windowHeight }}>
            {hours.map((hour) => <span key={hour} className="absolute right-2" style={{ top: Math.max(hour * 60 - windowStart - 6, 0) }}>{String(hour).padStart(2, '0')}:00</span>)}
          </div>
          {layouts.map(({ day, positioned, width }) => {
            return (
              <div key={day} style={{ width, height: windowHeight }} className="relative border-l border-zinc-900 bg-[linear-gradient(to_bottom,rgba(63,63,70,.35)_1px,transparent_1px)] bg-[length:100%_60px]">
                {slots.map((minute) => <TimeSlot key={minute} date={day} minute={minute} top={minute - windowStart} onCreate={() => onCreateAt(day, minute, selectedEmployeeId ?? undefined)} />)}
                {demand?.[day]?.map((segment) => {
                  const short = segment.covered < segment.demand
                  return (
                    <span
                      key={`demand-${segment.start}`}
                      role="img"
                      aria-label={`${fmtClock(segment.start)}–${fmtClock(segment.end)}: demand ${segment.demand}, covered ${segment.covered}`}
                      title={`Demand ${segment.demand} · covered ${segment.covered}`}
                      className={`absolute left-0 z-20 w-1 ${short ? 'bg-red-400/80' : 'bg-emerald-400/50'}`}
                      style={{ top: segment.start - windowStart, height: segment.end - segment.start }}
                    />
                  )
                })}
                {positioned.map(({ shift: item, lane, laneCount }) => {
                  const position = placement(item, windowStart, windowEnd)
                  const laneWidth = width / laneCount
                  const box = { top: position.top, height: position.height, left: lane * laneWidth + 2, width: Math.max(laneWidth - 4, 120) }
                  if (item.preview) return <PreviewShiftBlock key={`preview-${item.preview.id}`} shift={item.preview} style={box} />
                  const shift = item.real as Shift
                  // With a person selected, shifts that neither include them nor
                  // have an open seat for them fade back — their week and the
                  // places they could still go are what is left bright.
                  const dimmed = !!selectedEmployeeId
                    && !shift.assignments.some((assignment) => assignment.employee_id === selectedEmployeeId)
                    && shift.assignments.length >= shift.required_staff
                  return <ShiftBlock key={shift.id} shift={shift} pending={pendingKeys.has(`shift:${shift.id}`)} editable={shift.status !== 'cancelled' && (shift.status === 'draft' || editPublished)} selectedEmployeeId={selectedEmployeeId} huumeSelected={huumeSelectedShiftIds.has(shift.id)} dimmed={dimmed} mark={marks?.get(shift.id)} recent={recentShiftIds?.has(shift.id) ?? false} style={box} onOpen={() => onOpenShift(shift)} onToggleHuumeSelection={() => onToggleHuumeSelection(shift)} onAssignSelected={() => onAssignSelected(shift)} onResize={(endMinute) => onResizeShift(shift, endMinute)} />
                })}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
