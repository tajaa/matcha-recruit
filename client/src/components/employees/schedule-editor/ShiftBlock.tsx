import { AlertTriangle, Check, GripVertical, Lock, Sparkles, Users } from 'lucide-react'
import { useDraggable, useDroppable } from '@dnd-kit/core'
import type { Shift } from '../../../types/employeeSchedule'
import { fmtTime } from '../../../types/employeeSchedule'
import { shiftDurationMinutes } from './calendarMath'

interface ShiftBlockProps {
  shift: Shift
  pending: boolean
  editable: boolean
  selectedEmployeeId: string | null
  huumeSelected: boolean
  style: React.CSSProperties
  onOpen(): void
  onToggleHuumeSelection(): void
  onAssignSelected(): void
  onResize(endMinute: number): void
}

function AssignmentChip({ employeeId, name, shiftId, editable, availabilityOverridden }: {
  employeeId: string
  name: string
  shiftId: string
  editable: boolean
  availabilityOverridden: boolean
}) {
  const { attributes, listeners, setNodeRef } = useDraggable({
    id: `assignment-${shiftId}-${employeeId}`,
    data: { kind: 'shift-assignment', employeeId, fromShiftId: shiftId },
    disabled: !editable,
  })
  return <button ref={setNodeRef} {...listeners} {...attributes} className="flex w-full items-center gap-1 truncate rounded bg-zinc-800 px-1.5 py-0.5 text-left text-[10px] text-zinc-300 hover:bg-zinc-700"><Users className="h-2.5 w-2.5 shrink-0 text-zinc-500" /><span className="truncate">{name}</span>{availabilityOverridden && <span className="ml-auto shrink-0 text-orange-400" title="Availability override">!</span>}</button>
}

export default function ShiftBlock({ shift, pending, editable, selectedEmployeeId, huumeSelected, style, onOpen, onToggleHuumeSelection, onAssignSelected, onResize }: ShiftBlockProps) {
  const { setNodeRef: setDropRef, isOver } = useDroppable({ id: `shift-drop-${shift.id}`, data: { kind: 'shift', shiftId: shift.id } })
  const { attributes, listeners, setNodeRef: setDragRef, isDragging } = useDraggable({
    id: `shift-${shift.id}`,
    data: { kind: 'shift', shiftId: shift.id },
    disabled: !editable,
  })
  const assigned = shift.assignments.length
  const open = Math.max(shift.required_staff - assigned, 0)
  function beginResize(event: React.PointerEvent<HTMLButtonElement>) {
    event.preventDefault()
    event.stopPropagation()
    const startY = event.clientY
    const start = new Date(shift.starts_at)
    const startMinute = start.getUTCHours() * 60 + start.getUTCMinutes()
    const startingEndMinute = startMinute + shiftDurationMinutes(shift)
    let nextEndMinute = startingEndMinute
    const move = (moveEvent: PointerEvent) => {
      nextEndMinute = startingEndMinute + Math.round((moveEvent.clientY - startY) / 15) * 15
    }
    const finish = () => {
      onResize(nextEndMinute)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', finish)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', finish, { once: true })
  }
  return (
    <div
      ref={setDropRef}
      style={style}
      className={`absolute z-10 min-w-0 overflow-hidden rounded-md border p-1.5 shadow-lg transition-colors ${shift.status === 'cancelled' ? 'border-red-500/30 bg-red-950/80 opacity-60' : huumeSelected ? 'border-emerald-400 bg-emerald-950/70 ring-1 ring-emerald-400/30' : isOver ? 'border-emerald-400 bg-emerald-950/90' : 'border-zinc-700 bg-zinc-900/95'} ${pending ? 'animate-pulse' : ''} ${isDragging ? 'opacity-30' : ''}`}
    >
      <div className="flex items-start gap-1">
        {editable ? <button ref={setDragRef} {...listeners} {...attributes} className="mt-0.5 shrink-0 cursor-grab text-zinc-600 hover:text-zinc-200" aria-label={`Move ${shift.role || 'shift'}`}><GripVertical className="h-3 w-3" /></button> : <Lock className="mt-0.5 h-3 w-3 shrink-0 text-zinc-700" />}
        <button onClick={onOpen} className="min-w-0 flex-1 text-left">
          <span className="block truncate text-[11px] font-medium text-zinc-100">{shift.role || (open > 0 ? 'Open shift' : 'Shift')}</span>
          <span className="block truncate text-[10px] text-zinc-500">{fmtTime(shift.starts_at)}–{fmtTime(shift.ends_at)}</span>
        </button>
        <button
          type="button"
          onClick={onToggleHuumeSelection}
          aria-pressed={huumeSelected}
          aria-label={`${huumeSelected ? 'Remove' : 'Select'} ${shift.role || 'shift'} for Huume`}
          title={huumeSelected ? 'Remove from Huume context' : 'Select for Huume'}
          className={`mt-0.5 shrink-0 rounded p-0.5 ${huumeSelected ? 'bg-emerald-400 text-zinc-950' : 'text-zinc-600 hover:bg-emerald-500/15 hover:text-emerald-300'}`}
        >
          {huumeSelected ? <Check className="h-3 w-3" /> : <Sparkles className="h-3 w-3" />}
        </button>
      </div>
      <div className="mt-1 space-y-0.5">
        {shift.assignments.map((assignment) => <AssignmentChip key={assignment.employee_id} employeeId={assignment.employee_id} name={assignment.name} shiftId={shift.id} editable={editable} availabilityOverridden={assignment.availability_overridden} />)}
      </div>
      <div className="mt-1 flex items-center justify-between gap-1 text-[9px]">
        <span className={open ? 'text-amber-400' : 'text-emerald-400'}>{assigned}/{shift.required_staff}</span>
        {selectedEmployeeId && editable && <button onClick={onAssignSelected} className="truncate text-emerald-400 hover:text-emerald-200">+ assign selected</button>}
        {shift.kind === 'training' && <AlertTriangle className="h-3 w-3 text-sky-400" />}
      </div>
      {editable && <button onPointerDown={beginResize} className="absolute bottom-0 left-1/2 h-1 w-8 -translate-x-1/2 cursor-ns-resize rounded-full bg-zinc-600 hover:bg-emerald-400" title="Resize shift" aria-label="Resize shift" />}
    </div>
  )
}
