import { Loader2 } from 'lucide-react'
import type { useScheduleEditor } from '../../../hooks/employees/useScheduleEditor'
import type { ScheduleJob, Shift } from '../../../types/employeeSchedule'
import ShiftInspector, { type NewShiftDefaults } from '../schedule-editor/ShiftInspector'
import WeekTimeGrid from '../schedule-editor/WeekTimeGrid'

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
export default function BoardPane({
  days, editor, editPublished, selectedEmployeeId, huumeSelectedShiftIds, inspectorShift, newDefaults,
  locationId, locationName, jobs, trainingEnabled, canMutate, onOpenNew, onOpenShift, onCloseInspector, onCreated,
  onToggleHuumeSelection,
}: BoardPaneProps) {
  if (editor.loading) {
    return <div className="flex h-full min-h-[320px] items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-600" /></div>
  }
  const inspectorReadOnly = !!inspectorShift && (inspectorShift.status === 'published' && !editPublished || inspectorShift.status === 'cancelled')
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col lg:flex-row">
      <WeekTimeGrid
        days={days}
        shifts={editor.shifts}
        pendingKeys={editor.pendingKeys}
        editPublished={editPublished}
        selectedEmployeeId={selectedEmployeeId}
        huumeSelectedShiftIds={huumeSelectedShiftIds}
        onCreateAt={(date, minute, employeeId) => onOpenNew({ date, minute, employeeIds: employeeId ? [employeeId] : undefined })}
        onOpenShift={onOpenShift}
        onToggleHuumeSelection={onToggleHuumeSelection}
        onAssignSelected={(shift) => { if (selectedEmployeeId && canMutate(shift)) void editor.assignToShift(shift, selectedEmployeeId) }}
        onResizeShift={(shift, endMinute) => { if (canMutate(shift)) void editor.resizeShift(shift, endMinute) }}
      />
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
  )
}
