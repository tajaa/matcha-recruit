import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, TouchSensor, useSensor, useSensors, type DragEndEvent, type DragStartEvent } from '@dnd-kit/core'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, Sparkles } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import { useLocationScope, locationLabel } from '../../hooks/useLocationScope'
import { useScheduleEditor } from '../../hooks/employees/useScheduleEditor'
import { useToast } from '../../components/ui'
import { fetchJobs } from '../../api/employees/employeeSchedule'
import { getScheduleSuggestionStatus, type ScheduleSuggestionStatus } from '../../api/employees/scheduleAssistant'
import LocationPicker from '../../components/shared/LocationPicker'
import { addDays, startOfWeekSunday, toISODate, type ScheduleJob, type Shift } from '../../types/employeeSchedule'
import { resolveScheduleDrop, type ScheduleDragData, type ScheduleDropData } from '../../components/employees/schedule-editor/drag'
import RosterPanel from '../../components/employees/schedule-editor/RosterPanel'
import ScheduleEditorToolbar from '../../components/employees/schedule-editor/ScheduleEditorToolbar'
import ShiftInspector, { type NewShiftDefaults } from '../../components/employees/schedule-editor/ShiftInspector'
import WeekTimeGrid from '../../components/employees/schedule-editor/WeekTimeGrid'
import ScheduleEditorGuide from '../../components/employees/schedule-editor/ScheduleEditorGuide'
import ScheduleHuumePanel from '../../components/employees/schedule-editor/ScheduleHuumePanel'
import ScheduleJobsTab from '../../components/employees/schedule-editor/ScheduleJobsTab'

// Bump when guide content materially changes so existing managers see new
// scheduling safeguards instead of staying pinned to an obsolete walkthrough.
const GUIDE_STORAGE_KEY = 'matcha.schedule-editor.guide.v3'

function hasSeenGuide(): boolean {
  try {
    return window.localStorage.getItem(GUIDE_STORAGE_KEY) === 'seen'
  } catch {
    return false
  }
}

function parseWeek(value: string | null): string {
  if (value && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(new Date(`${value}T00:00:00Z`).getTime())) return value
  return toISODate(startOfWeekSunday(new Date()))
}

export default function ScheduleEditor() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const weekStart = parseWeek(searchParams.get('week'))
  const {
    locationId: requestedLocationId,
    setLocationId,
    locations,
    loading: locationsLoading,
  } = useLocationScope()
  const locationId = locations.some((location) => location.id === requestedLocationId) ? requestedLocationId : ''
  const { me, hasFeature } = useMe()
  const { toast } = useToast()
  const trainingEnabled = hasFeature('training')
  const credentialTemplatesEnabled = hasFeature('credential_templates')
  const [editPublished, setEditPublished] = useState(false)
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string | null>(null)
  const [inspectorShiftId, setInspectorShiftId] = useState<string | null>(null)
  const [newDefaults, setNewDefaults] = useState<NewShiftDefaults | null>(null)
  const [activeDrag, setActiveDrag] = useState<ScheduleDragData | null>(null)
  const [publishing, setPublishing] = useState(false)
  const [guideOpen, setGuideOpen] = useState(() => !hasSeenGuide())
  const [jobsOpen, setJobsOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [automaticSuggestion, setAutomaticSuggestion] = useState<ScheduleSuggestionStatus | null>(null)
  const [huumeSelectedShiftIds, setHuumeSelectedShiftIds] = useState<Set<string>>(() => new Set())
  const [jobs, setJobs] = useState<ScheduleJob[]>([])
  const openBreakPlanner = useCallback((shift: Shift, _employeeId: string, message: string) => {
    setNewDefaults(null)
    setInspectorShiftId(shift.id)
    toast(`Add planned break minutes, save the shift, then assign again. ${message}`, 'info')
  }, [toast])
  const editor = useScheduleEditor(weekStart, locationId, { onMealBreakRequired: openBreakPlanner })
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 180, tolerance: 8 } }),
    useSensor(KeyboardSensor),
  )
  const days = Array.from({ length: 7 }, (_, index) => addDays(weekStart, index))
  const inspectorShift = inspectorShiftId ? editor.shifts.find((shift) => shift.id === inspectorShiftId) ?? null : null
  const inspectorReadOnly = !!inspectorShift && (inspectorShift.status === 'published' && !editPublished || inspectorShift.status === 'cancelled')
  const currentLocation = locations.find((l) => l.id === locationId)
  const currentLocationName = currentLocation ? locationLabel(currentLocation) : ''
  const firstName = me?.profile?.name.trim().split(/\s+/)[0] || 'there'
  const huumeSelectedShifts = editor.shifts.filter((shift) => huumeSelectedShiftIds.has(shift.id))

  useEffect(() => {
    setHuumeSelectedShiftIds(new Set())
  }, [locationId, weekStart])

  useEffect(() => {
    if (!locationsLoading && requestedLocationId && !locationId) setLocationId('')
  }, [locationId, locationsLoading, requestedLocationId, setLocationId])

  useEffect(() => {
    let cancelled = false
    setAutomaticSuggestion(null)
    if (!locationId) return () => { cancelled = true }
    void getScheduleSuggestionStatus(locationId, weekStart)
      .then((result) => {
        if (!cancelled) setAutomaticSuggestion(result.available ? result : null)
      })
      .catch(() => {
        if (!cancelled) setAutomaticSuggestion(null)
      })
    return () => { cancelled = true }
  }, [locationId, weekStart])

  const reloadJobs = useCallback(async () => {
    if (!locationId) {
      setJobs([])
      return
    }
    try {
      const response = await fetchJobs(locationId)
      setJobs(response.jobs)
    } catch {
      setJobs([])
    }
  }, [locationId])

  useEffect(() => {
    void reloadJobs()
  }, [reloadJobs])

  const setWeek = useCallback((next: string) => {
    setSearchParams((current) => {
      const params = new URLSearchParams(current)
      params.set('week', next)
      return params
    }, { replace: true })
  }, [setSearchParams])

  function openNew(defaults: NewShiftDefaults) {
    setInspectorShiftId(null)
    setNewDefaults(defaults)
  }

  function openShift(shift: Shift) {
    setNewDefaults(null)
    setInspectorShiftId(shift.id)
  }

  function canMutate(shift: Shift | undefined): boolean {
    if (!shift || shift.status === 'cancelled') return false
    return shift.status === 'draft' || editPublished
  }

  function closeGuide() {
    try { window.localStorage.setItem(GUIDE_STORAGE_KEY, 'seen') } catch { /* best effort */ }
    setGuideOpen(false)
  }

  async function handleDragEnd(event: DragEndEvent) {
    setActiveDrag(null)
    const active = event.active.data.current as ScheduleDragData | undefined
    const over = event.over?.data.current as ScheduleDropData | undefined
    const action = active ? resolveScheduleDrop(active, over ?? null) : null
    if (!action) return

    if (action.kind === 'assign') {
      const target = editor.shifts.find((shift) => shift.id === action.toShiftId)
      if (canMutate(target)) await editor.assignToShift(target!, action.employeeId)
      else toast('This shift is locked. Enable Edit published to change it.', 'info')
    } else if (action.kind === 'move-assignment') {
      const target = editor.shifts.find((shift) => shift.id === action.toShiftId)
      if (canMutate(target) && canMutate(editor.shifts.find((shift) => shift.id === action.fromShiftId))) {
        await editor.moveEmployee(action.employeeId, action.fromShiftId, action.toShiftId)
      } else toast('Both shifts must be editable before moving an assignment.', 'info')
    } else if (action.kind === 'unassign') {
      const source = editor.shifts.find((shift) => shift.id === action.fromShiftId)
      if (canMutate(source)) await editor.unassignFromShift(source!, action.employeeId)
      else toast('This shift is locked. Enable Edit published to unassign someone.', 'info')
    } else if (action.kind === 'move-shift') {
      const shift = editor.shifts.find((item) => item.id === action.shiftId)
      if (canMutate(shift)) await editor.moveShift(shift!, action.date, action.minute)
      else toast('This shift is locked. Enable Edit published to move it.', 'info')
    } else if (action.kind === 'create-with-employee') {
      openNew({ date: action.date, minute: action.minute, employeeIds: [action.employeeId] })
    }
  }

  function handleDragStart(event: DragStartEvent) {
    setActiveDrag(event.active.data.current as ScheduleDragData)
  }

  async function handlePublish() {
    setPublishing(true)
    try {
      await editor.publishWeek()
      toast('Week published', 'success')
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not publish week', 'error')
    } finally {
      setPublishing(false)
    }
  }

  return (
    <DndContext sensors={sensors} onDragStart={handleDragStart} onDragCancel={() => setActiveDrag(null)} onDragEnd={handleDragEnd}>
      <div className="flex h-full min-h-0 min-w-0 flex-col bg-zinc-950 text-zinc-100">
        <ScheduleEditorToolbar
          weekStart={weekStart}
          summary={editor.summary}
          saveState={editor.saveState}
          lastSavedAt={editor.lastSavedAt}
          editPublished={editPublished}
          publishing={publishing}
          locations={locations}
          locationId={locationId}
          onChangeLocation={setLocationId}
          onPreviousWeek={() => setWeek(addDays(weekStart, -7))}
          onNextWeek={() => setWeek(addDays(weekStart, 7))}
          onThisWeek={() => setWeek(toISODate(startOfWeekSunday(new Date())))}
          onTogglePublishedEditing={setEditPublished}
          onPublish={handlePublish}
          onExit={() => navigate(`/ops/schedule?week=${weekStart}${locationId ? `&location=${locationId}` : ''}`)}
          onHelp={() => setGuideOpen(true)}
          jobsOpen={jobsOpen}
          jobsDisabled={!locationId}
          credentialsEnabled={credentialTemplatesEnabled}
          onToggleJobs={() => { setJobsOpen((value) => !value); setChatOpen(false) }}
          chatOpen={chatOpen}
          huumeSelectionCount={huumeSelectedShifts.length}
          onToggleChat={() => { setChatOpen((value) => !value); setJobsOpen(false) }}
        />
        {automaticSuggestion && !chatOpen && locationId && (
          <div className="flex items-center gap-3 border-b border-emerald-500/20 bg-emerald-500/[0.07] px-4 py-2 text-xs text-emerald-100 md:px-6">
            <Sparkles className="h-4 w-4 shrink-0 text-emerald-300" />
            <span>Huume prepared a suggested schedule for the week of {automaticSuggestion.week_start}.</span>
            <button
              type="button"
              onClick={() => {
                if (automaticSuggestion.week_start && automaticSuggestion.week_start !== weekStart) {
                  setWeek(automaticSuggestion.week_start)
                }
                setChatOpen(true)
                setJobsOpen(false)
              }}
              className="ml-auto rounded-lg border border-emerald-400/40 px-2.5 py-1 text-[11px] font-medium text-emerald-200 hover:bg-emerald-400/10"
            >
              Review suggestion
            </button>
          </div>
        )}
        {!locationId ? (
          <div className="flex min-h-[500px] flex-col items-center justify-center gap-3 text-center">
            <p className="text-sm text-zinc-400">Pick a location to see its schedule.</p>
            {locations.length > 0 ? (
              <LocationPicker locations={locations} value="" onChange={setLocationId} />
            ) : (
              <p className="text-xs text-zinc-600">No locations set up yet — add one under Company.</p>
            )}
          </div>
        ) : jobsOpen ? (
          <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
            <ScheduleJobsTab key={locationId} locationId={locationId} credentialTemplatesEnabled={credentialTemplatesEnabled} onJobsChanged={reloadJobs} />
          </div>
        ) : editor.loading ? (
          <div className="flex min-h-[500px] items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-zinc-600" /></div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
            <RosterPanel roster={editor.roster} rosterFlags={editor.rosterFlags} selectedEmployeeId={selectedEmployeeId} onSelectEmployee={setSelectedEmployeeId} requiredJobId={inspectorShift?.job_id} requiredJobDate={inspectorShift?.starts_at.slice(0, 10)} />
            <WeekTimeGrid days={days} shifts={editor.shifts} pendingKeys={editor.pendingKeys} editPublished={editPublished} selectedEmployeeId={selectedEmployeeId} huumeSelectedShiftIds={huumeSelectedShiftIds} onCreateAt={(date, minute, employeeId) => openNew({ date, minute, employeeIds: employeeId ? [employeeId] : undefined })} onOpenShift={openShift} onToggleHuumeSelection={(shift) => setHuumeSelectedShiftIds((current) => { const next = new Set(current); if (next.has(shift.id)) next.delete(shift.id); else next.add(shift.id); return next })} onAssignSelected={(shift) => { if (selectedEmployeeId && canMutate(shift)) void editor.assignToShift(shift, selectedEmployeeId) }} onResizeShift={(shift, endMinute) => { if (canMutate(shift)) void editor.resizeShift(shift, endMinute) }} />
            {(inspectorShift || newDefaults) && (
              <ShiftInspector
                key={inspectorShift?.id ?? `${newDefaults?.date}-${newDefaults?.minute}`}
                shift={inspectorShift}
                defaults={newDefaults}
                locationId={locationId}
                locationName={currentLocationName}
                roster={editor.roster}
                jobs={jobs}
                trainingEnabled={trainingEnabled}
                readOnly={inspectorReadOnly}
                saving={!!(inspectorShift && editor.pendingKeys.has(`shift:${inspectorShift.id}`))}
                onCreate={async (payload) => { const created = await editor.createDraft(payload); if (created) { setNewDefaults(null); setInspectorShiftId(created.id) } }}
                onUpdate={async (payload) => { if (inspectorShift) await editor.updateShiftDraft(inspectorShift, payload) }}
                onDelete={async () => { if (inspectorShift && await editor.removeShift(inspectorShift)) { setInspectorShiftId(null); setNewDefaults(null) } }}
                onAssignmentUpdated={editor.reload}
                onClose={() => { setInspectorShiftId(null); setNewDefaults(null) }}
              />
            )}
            {chatOpen && (
              <ScheduleHuumePanel
                key={`${weekStart}:${locationId}`}
                firstName={firstName}
                weekStart={weekStart}
                locationId={locationId || null}
                locationName={currentLocationName}
                selectedShifts={huumeSelectedShifts}
                onClearSelectedShifts={() => setHuumeSelectedShiftIds(new Set())}
                onApplied={() => { setAutomaticSuggestion(null); void editor.reload() }}
                onAutomaticActionSettled={() => setAutomaticSuggestion(null)}
                onClose={() => setChatOpen(false)}
              />
            )}
          </div>
        )}
      </div>
      <DragOverlay>{activeDrag ? <div className="rounded-lg border border-emerald-500/50 bg-zinc-900 px-3 py-2 text-xs text-zinc-200 shadow-xl">{activeDrag.kind === 'shift' ? 'Moving shift' : activeDrag.kind === 'shift-assignment' ? 'Moving assignment' : 'Scheduling employee'}</div> : null}</DragOverlay>
      <ScheduleEditorGuide open={guideOpen} onClose={closeGuide} />
    </DndContext>
  )
}
