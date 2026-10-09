import { memo, useState } from 'react'
import { CalendarRange, Loader2, Rows3 } from 'lucide-react'
import type { useScheduleEditor } from '../../../hooks/employees/useScheduleEditor'
import type { ScheduleJob, ScheduleReview, Shift } from '../../../types/employeeSchedule'
import ShiftInspector, { type NewShiftDefaults } from '../schedule-editor/ShiftInspector'
import WeekTimeGrid from '../schedule-editor/WeekTimeGrid'
import type { DemandSegment, PreviewShift } from './reviewVerdict'
import type { ShiftMark } from './boardMarks'
import WeekRosterGrid from './WeekRosterGrid'

type BoardView = 'week' | 'timeline'
const VIEW_STORAGE_KEY = 'schedulePilot.boardView'

function readView(): BoardView {
  try {
    return window.localStorage.getItem(VIEW_STORAGE_KEY) === 'timeline' ? 'timeline' : 'week'
  } catch {
    return 'week'
  }
}

export interface BoardPaneProps {
  days: string[]
  editor: ReturnType<typeof useScheduleEditor>
  editPublished: boolean
  selectedEmployeeId: string | null
  huumeSelectedShiftIds: ReadonlySet<string>
  inspectorShift: Shift | null
  newDefaults: NewShiftDefaults | null
  locationId: string
  locationName: string
  jobs: ScheduleJob[]
  trainingEnabled: boolean
  /** Undefined when the viewer has no `labor_cost` access. */
  costByDay?: Record<string, number>
  unpricedDays?: ReadonlySet<string>
  /** A generated week under review, drawn read-only (see `reviewVerdict`). */
  previewShifts?: PreviewShift[]
  demand?: Record<string, DemandSegment[]>
  /** What a pending proposal does to shifts already on the board. */
  marks?: ReadonlyMap<string, ShiftMark>
  /** Shifts an applied Huume change just touched. */
  recentShiftIds?: ReadonlySet<string>
  /** The proposal on show — the Week view draws who it adds or removes. */
  review?: ScheduleReview | null
  onSelectEmployee?(employeeId: string | null): void
  canMutate(shift: Shift | undefined): boolean
  onOpenNew(defaults: NewShiftDefaults): void
  onOpenShift(shift: Shift): void
  onCloseInspector(): void
  onCreated(shiftId: string): void
  onToggleHuumeSelection(shift: Shift): void
}

/** The week grid and the shift inspector — the old editor's body, verbatim in
 *  behaviour. The people list moved to the inputs rail; the DnD context
 *  wraps the whole workspace so drags still land here. */
function BoardPane({
  days, editor, editPublished, selectedEmployeeId, huumeSelectedShiftIds, inspectorShift, newDefaults,
  locationId, locationName, jobs, trainingEnabled, costByDay, unpricedDays, previewShifts, demand, marks, recentShiftIds, review, onSelectEmployee, canMutate, onOpenNew, onOpenShift, onCloseInspector, onCreated,
  onToggleHuumeSelection,
}: BoardPaneProps) {
  const [view, setView] = useState<BoardView>(readView)
  const chooseView = (next: BoardView) => {
    setView(next)
    try { window.localStorage.setItem(VIEW_STORAGE_KEY, next) } catch { /* the choice lasts for this page only */ }
  }
  if (editor.loading) {
    return <div className="flex h-full min-h-[320px] items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-600" /></div>
  }
  const inspectorReadOnly = !!inspectorShift && (inspectorShift.status === 'published' && !editPublished || inspectorShift.status === 'cancelled')
  const viewButton = (value: BoardView, label: string, Icon: typeof Rows3, hint: string) => (
    <button
      type="button"
      role="tab"
      aria-selected={view === value}
      onClick={() => chooseView(value)}
      title={hint}
      className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] ${view === value ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-500 hover:text-zinc-200'}`}
    ><Icon className="h-3.5 w-3.5" />{label}</button>
  )
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <div role="tablist" aria-label="Board view" className="flex shrink-0 items-center gap-1 border-b border-white/[0.06] px-3 py-1.5">
        {viewButton('week', 'Week', Rows3, 'Everyone\'s week at a glance')}
        {viewButton('timeline', 'Timeline', CalendarRange, 'Hours of the day — drag and resize shifts')}
      </div>
    <div className="flex min-h-0 min-w-0 flex-1 flex-col lg:flex-row">
      {view === 'week' ? (
        <WeekRosterGrid
          days={days}
          shifts={editor.shifts}
          roster={editor.roster}
          review={review}
          previewShifts={previewShifts}
          marks={marks}
          recentShiftIds={recentShiftIds}
          selectedEmployeeId={selectedEmployeeId}
          huumeSelectedShiftIds={huumeSelectedShiftIds}
          onOpenShift={onOpenShift}
          onToggleHuumeSelection={onToggleHuumeSelection}
          onSelectEmployee={onSelectEmployee}
          onCreateFor={(date, employeeId) => onOpenNew({ date, minute: 9 * 60, employeeIds: [employeeId] })}
        />
      ) : (
      <WeekTimeGrid
        days={days}
        shifts={editor.shifts}
        pendingKeys={editor.pendingKeys}
        editPublished={editPublished}
        selectedEmployeeId={selectedEmployeeId}
        huumeSelectedShiftIds={huumeSelectedShiftIds}
        costByDay={costByDay}
        unpricedDays={unpricedDays}
        previewShifts={previewShifts}
        demand={demand}
        marks={marks}
        recentShiftIds={recentShiftIds}
        onCreateAt={(date, minute, employeeId) => onOpenNew({ date, minute, employeeIds: employeeId ? [employeeId] : undefined })}
        onOpenShift={onOpenShift}
        onToggleHuumeSelection={onToggleHuumeSelection}
        onAssignSelected={(shift) => { if (selectedEmployeeId && canMutate(shift)) void editor.assignToShift(shift, selectedEmployeeId) }}
        onResizeShift={(shift, endMinute) => { if (canMutate(shift)) void editor.resizeShift(shift, endMinute) }}
      />
      )}
      {(inspectorShift || newDefaults) && (
        <ShiftInspector
          key={inspectorShift?.id ?? `${newDefaults?.date}-${newDefaults?.minute}`}
          shift={inspectorShift}
          defaults={newDefaults}
          locationId={locationId}
          locationName={locationName}
          roster={editor.roster}
          jobs={jobs}
          trainingEnabled={trainingEnabled}
          readOnly={inspectorReadOnly}
          saving={!!(inspectorShift && editor.pendingKeys.has(`shift:${inspectorShift.id}`))}
          onCreate={async (payload) => { const created = await editor.createDraft(payload); if (created) onCreated(created.id) }}
          onUpdate={async (payload) => { if (inspectorShift) await editor.updateShiftDraft(inspectorShift, payload) }}
          onDelete={async () => { if (inspectorShift && await editor.removeShift(inspectorShift)) onCloseInspector() }}
          onAssignmentUpdated={editor.reload}
          onClose={onCloseInspector}
        />
      )}
    </div>
    </div>
  )
}

// Memoized: the page re-renders on every Huume composer keystroke and stream
// event, and this subtree is a droppable/draggable pair per shift.
export default memo(BoardPane)
