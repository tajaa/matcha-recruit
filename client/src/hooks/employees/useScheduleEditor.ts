import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  assignEmployee, createShift, deleteShift, fetchWeek, moveAssignment,
  publishRange, unassignEmployee, updateShift,
} from '../../api/employees/employeeSchedule'
import { useToast } from '../../components/ui'
import { conflictPrompt, mealBreakConflictMessage } from '../../pages/app/employees/scheduleConflicts'
import { moveShiftWindow, resizeShiftWindow } from '../../components/employees/schedule-editor/calendarMath'
import type {
  AssignmentMoveResponse, RosterEmployee, RosterFlags,
  ScheduleSummary, Shift, ShiftPayload,
} from '../../types/employeeSchedule'
import { addDays, errorMessage } from '../../types/employeeSchedule'

export type ScheduleSaveState = 'idle' | 'saving' | 'saved' | 'error'

type ScheduleEditorOptions = {
  onMealBreakRequired?: (shift: Shift, employeeId: string, message: string) => void
  onShiftRemoved?: () => void
}

/** `locationId` is required to fetch a week's shifts (the server won't serve
 *  one without it) — pass `''` while the caller is still waiting on the user
 *  to pick a location, and the hook fetches nothing but the location list. */
export function useScheduleEditor(weekStart: string, locationId: string, options: ScheduleEditorOptions = {}) {
  const { toast } = useToast()
  const onMealBreakRequired = options.onMealBreakRequired
  const onShiftRemoved = options.onShiftRemoved
  const [shifts, setShifts] = useState<Shift[]>([])
  const [roster, setRoster] = useState<RosterEmployee[]>([])
  const [rosterFlags, setRosterFlags] = useState<RosterFlags | null>(null)
  const [weekSummary, setSummary] = useState<ScheduleSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [saveState, setSaveState] = useState<ScheduleSaveState>('idle')
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null)
  const [pendingKeys, setPendingKeys] = useState<Set<string>>(new Set())
  const requestVersion = useRef(0)
  const mutationQueues = useRef(new Map<string, Promise<unknown>>())
  const pendingCounts = useRef(new Map<string, number>())

  // Huume cancellations retain the row for history. Every board consumer
  // gets the same live shifts, including after reload and publish responses.
  const activeShifts = useMemo(() => shifts.filter((shift) => shift.status !== 'cancelled'), [shifts])
  const summary = useMemo(() => weekSummary ? {
    ...weekSummary,
    total_shifts: activeShifts.length,
    draft: activeShifts.filter((shift) => shift.status === 'draft').length,
    published: activeShifts.filter((shift) => shift.status === 'published').length,
    open_shifts: activeShifts.filter((shift) => shift.assignments.length < shift.required_staff).length,
    assigned: activeShifts.reduce((total, shift) => total + shift.assignments.length, 0),
  } : null, [activeShifts, weekSummary])

  const reload = useCallback(async (showLoading = true) => {
    const version = ++requestVersion.current
    if (!locationId) {
      setShifts([])
      setRoster([])
      setRosterFlags(null)
      setSummary(null)
      setLoading(false)
      return
    }
    if (showLoading) setLoading(true)
    try {
      const week = await fetchWeek(weekStart, locationId)
      if (version !== requestVersion.current) return
      setShifts(week.shifts)
      setRoster(week.roster)
      setRosterFlags(week.roster_flags)
      setSummary(week.summary)
    } finally {
      if (version === requestVersion.current) setLoading(false)
    }
  }, [weekStart, locationId])

  useEffect(() => {
    // Fetch on scope changes; the synchronous updates only reset the loading state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload()
  }, [reload])

  const patchShift = useCallback((updated: Shift) => {
    setShifts((current) => current.map((shift) => shift.id === updated.id ? updated : shift))
  }, [])

  const patchMove = useCallback((result: AssignmentMoveResponse) => {
    setShifts((current) => current.map((shift) => {
      if (shift.id === result.source_shift.id) return result.source_shift
      if (shift.id === result.target_shift.id) return result.target_shift
      return shift
    }))
  }, [])

  const mutate = useCallback(<T,>(
    keys: string | string[],
    operation: (force: boolean) => Promise<T>,
    onSuccess: (result: T) => void,
    handleConflict?: (error: unknown) => boolean,
  ): Promise<T | null> => {
    const mutationKeys = [...new Set(Array.isArray(keys) ? keys : [keys])].sort()
    for (const key of mutationKeys) {
      pendingCounts.current.set(key, (pendingCounts.current.get(key) ?? 0) + 1)
    }
    setPendingKeys((current) => new Set([...current, ...mutationKeys]))

    const execute = async (): Promise<T | null> => {
      setSaveState('saving')
      try {
        let result: T
        try {
          result = await operation(false)
        } catch (error) {
          if (handleConflict?.(error)) {
            setSaveState('idle')
            return null
          }
          const prompt = conflictPrompt(error)
          if (!prompt || !window.confirm(prompt)) {
            if (prompt) setSaveState('idle')
            else throw error
            return null
          }
          result = await operation(true)
        }
        onSuccess(result)
        setSaveState('saved')
        setLastSavedAt(new Date())
        return result
      } catch (error) {
        setSaveState('error')
        toast(errorMessage(error), 'error')
        await reload()
        return null
      } finally {
        for (const key of mutationKeys) {
          const count = pendingCounts.current.get(key) ?? 0
          if (count <= 1) pendingCounts.current.delete(key)
          else pendingCounts.current.set(key, count - 1)
        }
        setPendingKeys((current) => {
          const next = new Set(current)
          for (const key of mutationKeys) {
            if (!pendingCounts.current.has(key)) next.delete(key)
          }
          return next
        })
      }
    }

    const previous = mutationKeys
      .map((key) => mutationQueues.current.get(key))
      .filter((promise): promise is Promise<unknown> => !!promise)
      .map((promise) => promise.catch(() => undefined))
    const run = Promise.all(previous).then(execute)
    const tracked: Promise<T | null> = run.finally(() => {
      for (const key of mutationKeys) {
        if (mutationQueues.current.get(key) === tracked) mutationQueues.current.delete(key)
      }
    })
    for (const key of mutationKeys) mutationQueues.current.set(key, tracked)
    return tracked
  }, [reload, toast])

  const createDraft = useCallback((payload: ShiftPayload) => mutate(
    ['new-shift'],
    (force) => createShift(payload, force),
    (result) => {
      setShifts((current) => [...current, result].sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at)))
    },
  ), [mutate])

  const updateShiftDraft = useCallback((shift: Shift, payload: Partial<ShiftPayload>) => mutate(
    [`shift:${shift.id}`],
    (force) => updateShift(shift.id, payload, force),
    patchShift,
  ), [mutate, patchShift])

  const moveShift = useCallback((shift: Shift, targetDate: string, targetMinute: number) => updateShiftDraft(
    shift,
    moveShiftWindow(shift, targetDate, targetMinute),
  ), [updateShiftDraft])

  const resizeShift = useCallback((shift: Shift, endMinute: number) => updateShiftDraft(
    shift,
    resizeShiftWindow(shift, endMinute),
  ), [updateShiftDraft])

  const handleMealBreakConflict = useCallback((shift: Shift, employeeId: string, error: unknown) => {
    const message = mealBreakConflictMessage(error)
    if (!message || !onMealBreakRequired) return false
    onMealBreakRequired(shift, employeeId, message)
    return true
  }, [onMealBreakRequired])

  const assignToShift = useCallback((shift: Shift, employeeId: string) => mutate(
    [`shift:${shift.id}`],
    (force) => assignEmployee(shift.id, employeeId, force),
    patchShift,
    (error) => handleMealBreakConflict(shift, employeeId, error),
  ), [handleMealBreakConflict, mutate, patchShift])

  const moveEmployee = useCallback((employeeId: string, fromShiftId: string, toShiftId: string) => {
    const targetShift = shifts.find((shift) => shift.id === toShiftId)
    return mutate(
      [`shift:${fromShiftId}`, `shift:${toShiftId}`],
      (force) => moveAssignment({ employee_id: employeeId, from_shift_id: fromShiftId, to_shift_id: toShiftId }, force),
      patchMove,
      (error) => !!targetShift && handleMealBreakConflict(targetShift, employeeId, error),
    )
  }, [handleMealBreakConflict, mutate, patchMove, shifts])

  const unassignFromShift = useCallback((shift: Shift, employeeId: string) => mutate(
    [`shift:${shift.id}`],
    (force) => unassignEmployee(shift.id, employeeId, force),
    patchShift,
  ), [mutate, patchShift])

  const removeShift = useCallback(async (shift: Shift) => {
    const result = await mutate(
      [`shift:${shift.id}`],
      (force) => deleteShift(shift.id, force),
      () => {
        setShifts((current) => current.filter((item) => item.id !== shift.id))
        // Reprice on the server: deleting a shift can change overtime on
        // other days, so subtracting this shift's cost is not sufficient.
        setSummary((current) => current ? { ...current, cost: undefined } : current)
        void reload(false).catch(() => { /* Keep the successful deletion; cost stays unavailable. */ })
        onShiftRemoved?.()
      },
    )
    return result !== null
  }, [mutate, onShiftRemoved, reload])

  const publishWeek = useCallback(async () => {
    setSaveState('saving')
    try {
      const result = await publishRange(`${weekStart}T00:00:00Z`, `${addDays(weekStart, 7)}T00:00:00Z`, locationId)
      setShifts(result.shifts)
      setSummary(result.summary)
      setSaveState('saved')
      setLastSavedAt(new Date())
    } catch (error) {
      setSaveState('error')
      toast(errorMessage(error), 'error')
      throw error
    }
  }, [toast, weekStart, locationId])

  // One object per change, not per render: the Schedule Pilot passes this
  // whole to memoized panes, and the page re-renders on every composer keystroke.
  return useMemo(() => ({
    shifts: activeShifts, roster, rosterFlags, summary, loading, saveState, lastSavedAt, pendingKeys,
    reload, createDraft, updateShiftDraft, moveShift, resizeShift, assignToShift,
    moveEmployee, unassignFromShift, removeShift, publishWeek,
  }), [
    activeShifts, roster, rosterFlags, summary, loading, saveState, lastSavedAt, pendingKeys,
    reload, createDraft, updateShiftDraft, moveShift, resizeShift, assignToShift,
    moveEmployee, unassignFromShift, removeShift, publishWeek,
  ])
}
