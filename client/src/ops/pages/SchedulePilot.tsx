import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, TouchSensor, useSensor, useSensors, type DragEndEvent, type DragStartEvent } from '@dnd-kit/core'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Sparkles, X } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import { useLocationScope, locationLabel } from '../../hooks/useLocationScope'
import { useScheduleEditor } from '../../hooks/employees/useScheduleEditor'
import { useScheduleJobs } from '../../hooks/employees/useScheduleJobs'
import { usePlanningInputs } from '../../hooks/employees/usePlanningInputs'
import { useScheduleScenarios } from '../../hooks/employees/useScheduleScenarios'
import { useScheduleHuumeThread } from '../../hooks/employees/useScheduleHuumeThread'
import { useToast } from '../../components/ui'
import { adoptScheduleProposal, getScheduleSuggestionStatus, type ScheduleSuggestionStatus } from '../../api/employees/scheduleAssistant'
import { fetchLocationScheduleProfile } from '../../api/employees/locationProfile'
import LocationPicker from '../../components/shared/LocationPicker'
import {
  addDays, errorMessage, startOfWeek, toISODate,
  type LocationScheduleProfile, type Shift,
} from '../../types/employeeSchedule'
import { resolveScheduleDrop, type ScheduleDragData, type ScheduleDropData } from '../../components/employees/schedule-editor/drag'
import type { NewShiftDefaults } from '../../components/employees/schedule-editor/ShiftInspector'
import ScheduleEditorGuide from '../../components/employees/schedule-editor/ScheduleEditorGuide'
import ScheduleHuumePanel from '../../components/employees/schedule-editor/ScheduleHuumePanel'
import ScheduleJobsTab from '../../components/employees/schedule-editor/ScheduleJobsTab'
import WeekStartPane from '../../components/employees/schedule-editor/WeekStartPane'
import BoardPane from '../../components/employees/schedule-pilot/BoardPane'
import InputsRail from '../../components/employees/schedule-pilot/InputsRail'
import ReviewPane from '../../components/employees/schedule-pilot/ReviewPane'
import ScenariosStrip, { type StagedChip } from '../../components/employees/schedule-pilot/ScenariosStrip'
import SchedulePilotToolbar, { type CenterView } from '../../components/employees/schedule-pilot/SchedulePilotToolbar'
import { asScheduleReview } from '../../components/employees/schedule-pilot/reviewShape'

// Bump when guide content materially changes so existing managers see the new
// workspace walkthrough instead of staying pinned to the old editor's.
const GUIDE_STORAGE_KEY = 'matcha.schedule-pilot.guide.v1'

function hasSeenGuide(): boolean {
  try {
    return window.localStorage.getItem(GUIDE_STORAGE_KEY) === 'seen'
  } catch {
    return false
  }
}

/** Snaps to the location's own week start: a `?week=` carried over from
 * another store (or from before the manager changed the start day) would
 * otherwise scope the grid to a week the server now refuses. */
export function parseWeek(value: string | null, weekStartWeekday: number): string {
  if (value && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(new Date(`${value}T00:00:00Z`).getTime())) {
    return toISODate(startOfWeek(new Date(`${value}T00:00:00Z`), weekStartWeekday))
  }
  return toISODate(startOfWeek(new Date(), weekStartWeekday))
}

type Drawer = null | 'jobs' | 'weekSetup'
type MobileTab = 'inputs' | 'board' | 'review' | 'huume'
type ReviewSource = { kind: 'staged' } | { kind: 'scenario'; id: string }

/** The Schedule Pilot: the working surface for a week. Inputs on the left
 *  (who is loaded, who is free, the open seats, the house policy next to the
 *  law status), the board or the review in the middle, Huume always mounted
 *  on the right, and a scenarios strip across the top. Same URL and
 *  `?week=&location=` contract as the editor it replaces. */
export default function SchedulePilot() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const {
    locationId: requestedLocationId,
    setLocationId,
    locations,
    loading: locationsLoading,
    reloadLocations,
  } = useLocationScope()
  const locationId = locations.some((location) => location.id === requestedLocationId) ? requestedLocationId : ''
  const weekStartWeekday = locations.find((l) => l.id === locationId)?.week_start_weekday ?? 0
  const weekStart = parseWeek(searchParams.get('week'), weekStartWeekday)
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
  const [centerView, setCenterView] = useState<CenterView>('board')
  const [drawer, setDrawer] = useState<Drawer>(null)
  const [railOpen, setRailOpen] = useState(true)
  const [threadOpen, setThreadOpen] = useState(true)
  const [mobileTab, setMobileTab] = useState<MobileTab>('board')
  const [reviewSource, setReviewSource] = useState<ReviewSource>({ kind: 'staged' })
  const [automaticSuggestion, setAutomaticSuggestion] = useState<ScheduleSuggestionStatus | null>(null)
  const [weekRules, setWeekRules] = useState<LocationScheduleProfile['week_rules'] | null>(null)
  const [huumeSelectedShiftIds, setHuumeSelectedShiftIds] = useState<Set<string>>(() => new Set())
  const { jobs, reloadJobs } = useScheduleJobs(locationId)
  const openBreakPlanner = useCallback((shift: Shift, _employeeId: string, message: string) => {
    setNewDefaults(null)
    setInspectorShiftId(shift.id)
    setCenterView('board')
    setMobileTab('board')
    toast(`Add planned break minutes, save the shift, then assign again. ${message}`, 'info')
  }, [toast])
  const editor = useScheduleEditor(weekStart, locationId, { onMealBreakRequired: openBreakPlanner })
  const planning = usePlanningInputs(locationId, weekStart)
  const scenarios = useScheduleScenarios(locationId, weekStart)
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 180, tolerance: 8 } }),
    useSensor(KeyboardSensor),
  )
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart])
  const inspectorShift = inspectorShiftId ? editor.shifts.find((shift) => shift.id === inspectorShiftId) ?? null : null
  const currentLocation = locations.find((l) => l.id === locationId)
  const currentLocationName = currentLocation ? locationLabel(currentLocation) : ''
  const firstName = me?.profile?.name.trim().split(/\s+/)[0] || 'there'
  const huumeSelectedShifts = editor.shifts.filter((shift) => huumeSelectedShiftIds.has(shift.id))

  /** Last-request-wins, not a per-effect `cancelled` flag: this is also called
   *  imperatively after a save, so two reads can be in flight against
   *  different locations at once and the slower one must not paint. */
  const weekRulesRequest = useRef(0)
  const reloadWeekRules = useCallback(() => {
    const token = ++weekRulesRequest.current
    if (!locationId) {
      setWeekRules(null)
      return
    }
    void fetchLocationScheduleProfile(locationId)
      .then((profile) => { if (token === weekRulesRequest.current) setWeekRules(profile.week_rules) })
      .catch(() => { if (token === weekRulesRequest.current) setWeekRules(null) })
  }, [locationId])

  useEffect(() => { reloadWeekRules() }, [reloadWeekRules])

  const afterApplied = useCallback(() => {
    setAutomaticSuggestion(null)
    reloadWeekRules()
    void editor.reload()
    planning.reload()
  }, [editor, planning, reloadWeekRules])
  const afterAppliedRef = useRef(afterApplied)
  afterAppliedRef.current = afterApplied

  const thread = useScheduleHuumeThread({
    locationId: locationId || null,
    weekStart,
    selectedShifts: huumeSelectedShifts,
    // A confirmed setup save lands here too, so the banner clears the moment
    // the interview finishes.
    onApplied: () => afterAppliedRef.current(),
    onAutomaticActionSettled: () => setAutomaticSuggestion(null),
  })

  useEffect(() => {
    setHuumeSelectedShiftIds(new Set())
    setReviewSource({ kind: 'staged' })
    setDrawer(null)
    setInspectorShiftId(null)
    setNewDefaults(null)
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

  // ── what the review pane shows ──────────────────────────────────────────
  const stagedAction = thread.action
  const stagedReview = useMemo(() => {
    if (!stagedAction || stagedAction.status !== 'proposed') return null
    if (stagedAction.type !== 'schedule_change' && stagedAction.type !== 'schedule_week_draft') return null
    return asScheduleReview(stagedAction.review)
  }, [stagedAction])

  // A newly staged action opens the review once per confirm_id; the manager
  // can flip back to the board without it re-opening on every render.
  const autoOpenedRef = useRef<string | null>(null)
  useEffect(() => {
    if (!stagedReview || !stagedAction || stagedAction.status !== 'proposed') return
    const key = 'confirm_id' in stagedAction ? stagedAction.confirm_id : null
    if (!key || autoOpenedRef.current === key) return
    autoOpenedRef.current = key
    setReviewSource({ kind: 'staged' })
    setCenterView('review')
  }, [stagedAction, stagedReview])

  const selectedScenarios = scenarios.selectedIds
    .map((id) => scenarios.scenarios.find((item) => item.proposal_id === id))
    .filter((item): item is NonNullable<typeof item> => !!item)
  const reviewScenario = reviewSource.kind === 'scenario'
    ? scenarios.scenarios.find((item) => item.proposal_id === reviewSource.id) ?? null
    : null
  const review = reviewSource.kind === 'staged' ? stagedReview : reviewScenario?.review ?? null
  const compareScenario = reviewSource.kind === 'scenario' && selectedScenarios.length === 2
    ? selectedScenarios.find((item) => item.proposal_id !== reviewSource.id) ?? null
    : null
  const stagedChip: StagedChip | null = stagedReview && stagedAction ? {
    label: stagedAction.type === 'schedule_week_draft' ? 'Huume · generated week' : ('label' in stagedAction && stagedAction.label ? `Staged · ${stagedAction.label}` : 'Huume · staged change'),
    staged: stagedReview.assignments.filter((item) => item.verdict !== 'blocked').length,
    unfilled: stagedReview.unfilled.length,
    rejected: stagedReview.rejected.length,
    compliance: stagedReview.compliance_status,
  } : null
  const reviewTitle = reviewSource.kind === 'staged'
    ? (stagedChip?.label ?? 'Nothing staged')
    : (reviewScenario?.label ?? 'Scenario')
  const reviewSubtitle = reviewSource.kind === 'staged'
    ? (stagedReview ? 'Confirm or cancel it in the Huume thread.' : null)
    : reviewScenario?.status === 'applied'
      ? reviewScenario.applied_message ?? 'Applied.'
      : 'A simulation — nothing is written until you apply it or stage it in the thread.'
  const caps = useMemo(() => Object.fromEntries((planning.inputs?.roster ?? []).map((person) => [person.employee_id, {
    max_weekly_minutes: person.caps.max_weekly_minutes, allow_overtime: person.caps.allow_overtime,
  }])), [planning.inputs])

  const setWeek = useCallback((next: string) => {
    setSearchParams((current) => {
      const params = new URLSearchParams(current)
      params.set('week', next)
      return params
    }, { replace: true })
  }, [setSearchParams])

  // Stable handlers: BoardPane and InputsRail are memoized so the composer's
  // keystrokes and stream events do not re-render the grid and the rail.
  const openNew = useCallback((defaults: NewShiftDefaults) => {
    setInspectorShiftId(null)
    setNewDefaults(defaults)
  }, [])

  const openShift = useCallback((shift: Shift) => {
    setNewDefaults(null)
    setInspectorShiftId(shift.id)
  }, [])

  const canMutate = useCallback((shift: Shift | undefined): boolean => {
    if (!shift || shift.status === 'cancelled') return false
    return shift.status === 'draft' || editPublished
  }, [editPublished])

  const closeInspector = useCallback(() => { setInspectorShiftId(null); setNewDefaults(null) }, [])
  const onCreated = useCallback((id: string) => { setNewDefaults(null); setInspectorShiftId(id) }, [])
  const toggleHuumeSelection = useCallback((shift: Shift) => setHuumeSelectedShiftIds((current) => {
    const next = new Set(current)
    if (next.has(shift.id)) next.delete(shift.id); else next.add(shift.id)
    return next
  }), [])
  const openWeekSetup = useCallback(() => setDrawer('weekSetup'), [])
  const openJobs = useCallback(() => setDrawer('jobs'), [])

  function closeGuide() {
    try { window.localStorage.setItem(GUIDE_STORAGE_KEY, 'seen') } catch { /* best effort */ }
    setGuideOpen(false)
  }

  // Navigation only: it must not touch the Huume context selection, which is
  // appended to every turn as authoritative — that stays the ✨ toggle's job.
  const showShift = useCallback((shiftId: string) => {
    const shift = editor.shifts.find((item) => item.id === shiftId)
    setCenterView('board')
    setMobileTab('board')
    if (shift) openShift(shift)
  }, [editor.shifts, openShift])

  const setThreadInput = thread.setInput
  const askHuume = useCallback((text: string) => {
    setThreadInput(text)
    setThreadOpen(true)
    setMobileTab('huume')
    window.setTimeout(() => document.getElementById('schedule-huume-input')?.focus(), 0)
  }, [setThreadInput])

  function selectScenario(id: string, options?: { compare?: boolean }) {
    // A compare click on an already-selected chip drops it, so the pane must
    // follow what is still selected — otherwise Apply acts on a scenario the
    // manager is not looking at.
    const next = scenarios.select(id, options)
    const focus = next.includes(id) ? id : next[0]
    setReviewSource(focus ? { kind: 'scenario', id: focus } : { kind: 'staged' })
    setCenterView('review')
    setMobileTab('review')
  }

  async function stageScenario(id: string) {
    if (!thread.sessionId) {
      toast('Open the Huume thread first — staging puts the scenario there to confirm.', 'info')
      return
    }
    const displaced = thread.action?.status === 'proposed'
    try {
      const result = await adoptScheduleProposal(thread.sessionId, id)
      thread.setCurrentState(result.current_state)
      scenarios.markStaged(id)
      setReviewSource({ kind: 'staged' })
      setCenterView('review')
      setThreadOpen(true)
      toast(displaced
        ? 'Staged in the thread, replacing the change that was staged before — reply confirm there to apply it.'
        : 'Staged in the thread — reply confirm there to apply it.', 'success')
    } catch (error) {
      toast(errorMessage(error), 'error')
    }
  }

  async function applyScenario(id: string) {
    try {
      const result = await scenarios.apply(id)
      toast(result.message, 'success')
      afterApplied()
    } catch (error) {
      toast(errorMessage(error), 'error')
    }
  }

  async function handleDragEnd(event: DragEndEvent) {
    setActiveDrag(null)
    const active = event.active.data.current as ScheduleDragData | undefined
    const over = event.over?.data.current as ScheduleDropData | undefined
    const action = active ? resolveScheduleDrop(active, over ?? null) : null
    if (!action) return

    // Only a drop that wrote something changes the planning inputs.
    let wrote = false
    if (action.kind === 'assign') {
      const target = editor.shifts.find((shift) => shift.id === action.toShiftId)
      if (canMutate(target)) { await editor.assignToShift(target!, action.employeeId); wrote = true }
      else toast('This shift is locked. Enable Edit published to change it.', 'info')
    } else if (action.kind === 'move-assignment') {
      const target = editor.shifts.find((shift) => shift.id === action.toShiftId)
      if (canMutate(target) && canMutate(editor.shifts.find((shift) => shift.id === action.fromShiftId))) {
        await editor.moveEmployee(action.employeeId, action.fromShiftId, action.toShiftId)
        wrote = true
      } else toast('Both shifts must be editable before moving an assignment.', 'info')
    } else if (action.kind === 'unassign') {
      const source = editor.shifts.find((shift) => shift.id === action.fromShiftId)
      if (canMutate(source)) { await editor.unassignFromShift(source!, action.employeeId); wrote = true }
      else toast('This shift is locked. Enable Edit published to unassign someone.', 'info')
    } else if (action.kind === 'move-shift') {
      const shift = editor.shifts.find((item) => item.id === action.shiftId)
      if (canMutate(shift)) { await editor.moveShift(shift!, action.date, action.minute); wrote = true }
      else toast('This shift is locked. Enable Edit published to move it.', 'info')
    } else if (action.kind === 'create-with-employee') {
      openNew({ date: action.date, minute: action.minute, employeeIds: [action.employeeId] })
    }
    if (wrote) planning.reload()
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

  const mobileTabs: Array<[MobileTab, string]> = [['inputs', 'Inputs'], ['board', 'Board'], ['review', 'Review'], ['huume', 'Huume']]
  const showRail = railOpen
  const showThread = threadOpen

  const centerContent = centerView === 'review' ? (
    <ReviewPane
      review={review}
      title={reviewTitle}
      subtitle={reviewSubtitle}
      caps={caps}
      policyMinutes={planning.inputs?.policy.default_weekly_cap_minutes}
      compare={compareScenario ? { label: compareScenario.label, review: compareScenario.review } : null}
      onShowShift={showShift}
      onAskHuume={askHuume}
      emptyHint={reviewSource.kind === 'staged'
        ? 'Nothing is staged in the thread. Ask Huume for a change, run a scenario from the strip, and what it would do appears here before anything is written.'
        : undefined}
    />
  ) : (
    <BoardPane
      days={days}
      editor={editor}
      editPublished={editPublished}
      selectedEmployeeId={selectedEmployeeId}
      huumeSelectedShiftIds={huumeSelectedShiftIds}
      inspectorShift={inspectorShift}
      newDefaults={newDefaults}
      locationId={locationId}
      locationName={currentLocationName}
      jobs={jobs}
      trainingEnabled={trainingEnabled}
      canMutate={canMutate}
      onOpenNew={openNew}
      onOpenShift={openShift}
      onCloseInspector={closeInspector}
      onCreated={onCreated}
      onToggleHuumeSelection={toggleHuumeSelection}
    />
  )

  const railContent = (
    <InputsRail
      inputs={planning.inputs}
      loading={planning.loading}
      roster={editor.roster}
      rosterFlags={editor.rosterFlags}
      selectedEmployeeId={selectedEmployeeId}
      onSelectEmployee={setSelectedEmployeeId}
      requiredJobId={inspectorShift?.job_id}
      requiredJobDate={inspectorShift?.starts_at.slice(0, 10)}
      weekRules={weekRules}
      locationName={currentLocationName}
      credentialsEnabled={credentialTemplatesEnabled}
      onOpenWeekSetup={openWeekSetup}
      onOpenJobs={openJobs}
      onAskHuume={askHuume}
      onShowShift={showShift}
    />
  )

  const threadContent = (
    <ScheduleHuumePanel
      embedded
      thread={thread}
      firstName={firstName}
      weekStart={weekStart}
      locationId={locationId || null}
      locationName={currentLocationName}
      selectedShifts={huumeSelectedShifts}
      weekRulesEstablished={weekRules?.established ?? true}
      onClearSelectedShifts={() => setHuumeSelectedShiftIds(new Set())}
      onOpenReview={() => { setReviewSource({ kind: 'staged' }); setCenterView('review'); setMobileTab('review') }}
    />
  )

  return (
    <DndContext sensors={sensors} onDragStart={handleDragStart} onDragCancel={() => setActiveDrag(null)} onDragEnd={handleDragEnd}>
      <div className="flex h-full min-h-0 min-w-0 flex-col bg-zinc-950 text-zinc-100">
        <SchedulePilotToolbar
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
          onThisWeek={() => setWeek(toISODate(startOfWeek(new Date(), weekStartWeekday)))}
          onTogglePublishedEditing={setEditPublished}
          onPublish={handlePublish}
          onExit={() => navigate(`/ops/schedule?week=${weekStart}${locationId ? `&location=${locationId}` : ''}`)}
          onHelp={() => setGuideOpen(true)}
          centerView={centerView}
          onSetCenterView={(view) => { setCenterView(view); setMobileTab(view) }}
          reviewReady={!!review}
          railOpen={railOpen}
          onToggleRail={() => setRailOpen((open) => !open)}
          threadOpen={threadOpen}
          onToggleThread={() => setThreadOpen((open) => !open)}
          huumeSelectionCount={huumeSelectedShifts.length}
        />
        {automaticSuggestion && locationId && (
          <div className="flex items-center gap-3 border-b border-emerald-500/20 bg-emerald-500/[0.07] px-4 py-2 text-xs text-emerald-100 md:px-6">
            <Sparkles className="h-4 w-4 shrink-0 text-emerald-300" />
            <span>Huume prepared a suggested schedule for the week of {automaticSuggestion.week_start}.</span>
            <button
              type="button"
              onClick={() => {
                if (automaticSuggestion.week_start && automaticSuggestion.week_start !== weekStart) {
                  setWeek(automaticSuggestion.week_start)
                }
                setThreadOpen(true)
                setMobileTab('huume')
                setReviewSource({ kind: 'staged' })
                setCenterView('review')
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
        ) : (
          <>
            <ScenariosStrip
              scenarios={scenarios.scenarios}
              selectedIds={scenarios.selectedIds}
              onSelect={selectScenario}
              staged={stagedChip}
              stagedSelected={reviewSource.kind === 'staged' && centerView === 'review'}
              onSelectStaged={() => { setReviewSource({ kind: 'staged' }); setCenterView('review'); setMobileTab('review') }}
              previewing={scenarios.previewing}
              notice={scenarios.notice}
              onDismissNotice={scenarios.dismissNotice}
              onPreview={(request) => { void scenarios.preview(request).then((created) => { if (created) { setReviewSource({ kind: 'scenario', id: created.proposal_id }); setCenterView('review'); setMobileTab('review') } }) }}
              jobs={jobs.map((job) => ({ id: job.id, name: job.name }))}
              people={editor.roster.map((person) => ({ id: person.id, name: person.name }))}
              selectedShiftIds={[...huumeSelectedShiftIds]}
              onApply={(id) => { void applyScenario(id) }}
              onStage={(id) => { void stageScenario(id) }}
              onDiscard={(id) => { void scenarios.discard(id).then(() => { if (reviewSource.kind === 'scenario' && reviewSource.id === id) setReviewSource({ kind: 'staged' }) }) }}
              canStage={!!thread.sessionId && !thread.busy}
              disabled={editor.loading}
            />
            {/* Mobile: one pane at a time. */}
            <div className="flex shrink-0 gap-1 border-b border-white/[0.06] px-3 py-1.5 lg:hidden" role="tablist" aria-label="Workspace panes">
              {mobileTabs.map(([tab, label]) => (
                <button key={tab} role="tab" aria-selected={mobileTab === tab} onClick={() => { setMobileTab(tab); if (tab === 'board' || tab === 'review') setCenterView(tab) }} className={`rounded px-2 py-1 font-mono text-[10px] uppercase tracking-[0.15em] ${mobileTab === tab ? 'bg-white/[0.06] text-zinc-100' : 'text-zinc-500'}`}>{label}</button>
              ))}
            </div>
            <div className="relative flex min-h-0 flex-1">
              <div className={`min-h-0 w-full shrink-0 border-r border-white/[0.06] lg:w-72 ${mobileTab === 'inputs' ? 'block' : 'hidden'} ${showRail ? 'lg:block' : 'lg:hidden'}`}>
                {railContent}
              </div>
              <div className={`relative min-h-0 min-w-0 flex-1 ${mobileTab === 'board' || mobileTab === 'review' ? 'block' : 'hidden'} lg:block`}>
                {centerContent}
                {drawer && (
                  <div className="absolute inset-0 z-20 flex flex-col overflow-y-auto bg-zinc-950/98 backdrop-blur" role="dialog" aria-label={drawer === 'jobs' ? 'Jobs' : 'Week setup'}>
                    <div className="flex shrink-0 items-center justify-between border-b border-white/[0.06] px-4 py-2">
                      <span className="text-xs font-medium text-zinc-200">{drawer === 'jobs' ? (credentialTemplatesEnabled ? 'Jobs & credentials' : 'Jobs') : 'Week setup'}</span>
                      <button type="button" onClick={() => setDrawer(null)} className="rounded p-1 text-zinc-500 hover:text-zinc-100" aria-label="Close"><X className="h-4 w-4" /></button>
                    </div>
                    <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
                      {drawer === 'jobs'
                        ? <ScheduleJobsTab key={locationId} locationId={locationId} credentialTemplatesEnabled={credentialTemplatesEnabled} onJobsChanged={reloadJobs} />
                        : <WeekStartPane key={locationId} locationId={locationId} jobs={jobs} onSaved={() => { void reloadLocations(); reloadWeekRules(); planning.reload() }} />}
                    </div>
                  </div>
                )}
              </div>
              <div className={`min-h-0 w-full shrink-0 border-l border-white/[0.06] lg:w-[380px] ${mobileTab === 'huume' ? 'block' : 'hidden'} ${showThread ? 'lg:block' : 'lg:hidden'}`}>
                {threadContent}
              </div>
            </div>
          </>
        )}
      </div>
      <DragOverlay>{activeDrag ? <div className="rounded-lg border border-emerald-500/50 bg-zinc-900 px-3 py-2 text-xs text-zinc-200 shadow-xl">{activeDrag.kind === 'shift' ? 'Moving shift' : activeDrag.kind === 'shift-assignment' ? 'Moving assignment' : 'Scheduling employee'}</div> : null}</DragOverlay>
      <ScheduleEditorGuide open={guideOpen} onClose={closeGuide} />
    </DndContext>
  )
}
