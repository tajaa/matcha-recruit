import { useDroppable } from '@dnd-kit/core'
import type { Shift } from '../../../types/employeeSchedule'
import { fmtDayLabel } from '../../../types/employeeSchedule'
import { layoutOverlappingShifts, shiftPosition } from './calendarMath'
import ShiftBlock from './ShiftBlock'

interface WeekTimeGridProps {
  days: string[]
  shifts: Shift[]
  pendingKeys: ReadonlySet<string>
  editPublished: boolean
  selectedEmployeeId: string | null
  onCreateAt(date: string, minute: number, employeeId?: string): void
  onOpenShift(shift: Shift): void
  onAssignSelected(shift: Shift): void
  onResizeShift(shift: Shift, endMinute: number): void
}

function TimeSlot({ date, minute, onCreate }: { date: string; minute: number; onCreate(): void }) {
  const { setNodeRef, isOver } = useDroppable({ id: `slot-${date}-${minute}`, data: { kind: 'time-slot', date, minute } })
  return <button ref={setNodeRef} onClick={onCreate} className={`absolute left-0 right-0 border-t border-zinc-900/80 text-left ${isOver ? 'bg-emerald-500/10' : 'hover:bg-white/[0.02]'}`} style={{ top: minute, height: 15 }} aria-label={`Create shift on ${date} at ${minute} minutes`} />
}

export default function WeekTimeGrid({ days, shifts, pendingKeys, editPublished, selectedEmployeeId, onCreateAt, onOpenShift, onAssignSelected, onResizeShift }: WeekTimeGridProps) {
  const hours = Array.from({ length: 24 }, (_, i) => i)
  const layouts = days.map((day) => {
    const dayShifts = shifts.filter((shift) => shift.starts_at.slice(0, 10) === day)
    const positioned = layoutOverlappingShifts(dayShifts)
    const laneCount = Math.max(1, ...positioned.map((item) => item.laneCount))
    return { day, positioned, width: Math.max(220, laneCount * 180) }
  })
  const gridTemplateColumns = `48px ${layouts.map((layout) => `${layout.width}px`).join(' ')}`
  const gridMinWidth = 48 + layouts.reduce((total, layout) => total + layout.width, 0)
  return (
    <div className="min-h-0 min-w-0 flex-1 overflow-auto bg-zinc-950 p-3 md:p-5">
      <div style={{ minWidth: gridMinWidth }}>
        <div className="grid border-b border-zinc-800" style={{ gridTemplateColumns }}>
          <div />
          {layouts.map(({ day, width }) => <div key={day} style={{ width }} className="border-l border-zinc-900 px-2 pb-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">{fmtDayLabel(day)}</div>)}
        </div>
        <div className="grid" style={{ gridTemplateColumns }}>
          <div className="relative h-[1440px] text-[10px] text-zinc-700">
            {hours.map((hour) => <span key={hour} className="absolute right-2" style={{ top: hour * 60 - 6 }}>{String(hour).padStart(2, '0')}:00</span>)}
          </div>
          {layouts.map(({ day, positioned, width }) => {
            return (
              <div key={day} style={{ width }} className="relative h-[1440px] border-l border-zinc-900 bg-[linear-gradient(to_bottom,rgba(63,63,70,.35)_1px,transparent_1px)] bg-[length:100%_60px]">
                {Array.from({ length: 96 }, (_, index) => <TimeSlot key={index} date={day} minute={index * 15} onCreate={() => onCreateAt(day, index * 15, selectedEmployeeId ?? undefined)} />)}
                {positioned.map(({ shift, lane, laneCount }) => {
                  const position = shiftPosition(shift)
                  const laneWidth = width / laneCount
                  return <ShiftBlock key={shift.id} shift={shift} pending={pendingKeys.has(`shift:${shift.id}`)} editable={shift.status !== 'cancelled' && (shift.status === 'draft' || editPublished)} selectedEmployeeId={selectedEmployeeId} style={{ top: `${position.topPercent}%`, height: `${position.heightPercent}%`, left: lane * laneWidth + 2, width: Math.max(laneWidth - 4, 120) }} onOpen={() => onOpenShift(shift)} onAssignSelected={() => onAssignSelected(shift)} onResize={(endMinute) => onResizeShift(shift, endMinute)} />
                })}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
