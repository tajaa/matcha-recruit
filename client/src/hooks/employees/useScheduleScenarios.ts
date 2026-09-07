import { useCallback, useEffect, useRef, useState } from 'react'
import { applyFillVacant, cancelFillVacant, previewFillVacant } from '../../api/employees/employeeSchedule'
import type { FillVacantPreviewRequest, ScheduleReview } from '../../types/employeeSchedule'
import { errorMessage } from '../../types/employeeSchedule'
import { ApiError } from '../../api/client'

export type ScenarioStatus = 'ready' | 'applying' | 'applied' | 'staged'

export interface Scenario {
  proposal_id: string
  label: string
  review: ScheduleReview
  pill_text: string
  created_at: number
  status: ScenarioStatus
  /** The apply result's message, once applied. */
  applied_message?: string
}

export type ScenarioRequest = Omit<FillVacantPreviewRequest, 'week_start'>

/** A note from a preview that produced no scenario: nothing fillable, a
 *  clarify, or a refusal — with the seats it could not fill. */
export interface ScenarioNotice {
  status: 'empty' | 'clarify' | 'refused' | 'error'
  message: string
  unfilled: ScheduleReview['unfilled']
}

function autoLabel(request: ScenarioRequest, index: number): string {
  if (request.label?.trim()) return request.label.trim()
  const parts: string[] = []
  if (request.role_hint) parts.push(`${request.role_hint} shifts`)
  else if (request.shift_ids?.length) parts.push(`${request.shift_ids.length} selected shift${request.shift_ids.length === 1 ? '' : 's'}`)
  else parts.push('all open shifts')
  if (request.employee_id) parts.push('one person')
  if (request.exclude_employee_ids?.length) parts.push(`without ${request.exclude_employee_ids.length}`)
  if (request.allow_split_shift) parts.push('splits allowed')
  return `Scenario ${index}: ${parts.join(' · ')}`
}

/** The Schedule Pilot's scenarios strip: each entry is one server-side fill
 *  preview (`POST …/fill-vacant/preview`), a `schedule_chat_proposals` row
 *  that is this manager's handle on the simulation. Nothing is written until
 *  Apply (REST) or Stage → Confirm (in the thread). In-memory only — cleared
 *  when the location or week changes, discarding the rows it leaves behind. */
export function useScheduleScenarios(locationId: string, weekStart: string) {
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [previewing, setPreviewing] = useState(false)
  const [notice, setNotice] = useState<ScenarioNotice | null>(null)
  const scenariosRef = useRef<Scenario[]>([])
  scenariosRef.current = scenarios
  const selectedIdsRef = useRef<string[]>([])
  selectedIdsRef.current = selectedIds
  const counter = useRef(0)

  useEffect(() => () => {
    // Scope changed (or the page closed): the rows that were never applied or
    // staged are discarded so they cannot be applied later by accident.
    for (const scenario of scenariosRef.current) {
      if (scenario.status === 'ready') void cancelFillVacant(scenario.proposal_id).catch(() => undefined)
    }
    scenariosRef.current = []
    counter.current = 0
    setScenarios([])
    setSelectedIds([])
    setNotice(null)
  }, [locationId, weekStart])

  const preview = useCallback(async (request: ScenarioRequest): Promise<Scenario | null> => {
    if (!locationId) return null
    setPreviewing(true)
    setNotice(null)
    try {
      const result = await previewFillVacant(locationId, { ...request, week_start: weekStart })
      if (result.status !== 'ready') {
        setNotice({ status: result.status, message: result.message, unfilled: result.unfilled ?? [] })
        return null
      }
      counter.current += 1
      const scenario: Scenario = {
        proposal_id: result.proposal_id,
        label: result.label?.trim() || autoLabel(request, counter.current),
        review: result.review,
        pill_text: result.pill_text,
        created_at: Date.now(),
        status: 'ready',
      }
      setScenarios((current) => [...current, scenario])
      setSelectedIds([scenario.proposal_id])
      return scenario
    } catch (error) {
      setNotice({ status: 'error', message: errorMessage(error), unfilled: [] })
      return null
    } finally {
      setPreviewing(false)
    }
  }, [locationId, weekStart])

  const apply = useCallback(async (proposalId: string) => {
    setScenarios((current) => current.map((item) => item.proposal_id === proposalId ? { ...item, status: 'applying' } : item))
    try {
      const result = await applyFillVacant(proposalId)
      setScenarios((current) => current.map((item) => item.proposal_id === proposalId
        ? { ...item, status: 'applied', applied_message: result.message }
        : item))
      return result
    } catch (error) {
      // 409 means the row is no longer `proposed` (already applied or
      // discarded server-side): re-offering Apply on it would only 409 again.
      const spent = error instanceof ApiError && error.status === 409
      setScenarios((current) => spent
        ? current.filter((item) => item.proposal_id !== proposalId)
        : current.map((item) => item.proposal_id === proposalId ? { ...item, status: 'ready' } : item))
      if (spent) setSelectedIds((current) => current.filter((id) => id !== proposalId))
      throw error
    }
  }, [])

  const discard = useCallback(async (proposalId: string) => {
    const scenario = scenariosRef.current.find((item) => item.proposal_id === proposalId)
    if (scenario?.status === 'ready') await cancelFillVacant(proposalId).catch(() => undefined)
    setScenarios((current) => current.filter((item) => item.proposal_id !== proposalId))
    setSelectedIds((current) => current.filter((id) => id !== proposalId))
  }, [])

  /** After the thread adopted this scenario as its staged action. The row is
   *  now the thread's to confirm or cancel, so it is no longer discarded here.
   *  The thread holds one staged action, so a scenario staged earlier was
   *  cancelled by the server on adoption — its chip goes with it. */
  const markStaged = useCallback((proposalId: string) => {
    setScenarios((current) => current
      .filter((item) => item.proposal_id === proposalId || item.status !== 'staged')
      .map((item) => item.proposal_id === proposalId ? { ...item, status: 'staged' } : item))
    setSelectedIds((current) => current.filter((id) => id === proposalId
      || scenariosRef.current.find((item) => item.proposal_id === id)?.status !== 'staged'))
  }, [])

  /** Plain click selects one; a compare click keeps the current one and adds
   *  this as the second (at most two). Returns the resulting selection so the
   *  caller can point the review at what is actually selected. */
  const select = useCallback((proposalId: string, options: { compare?: boolean } = {}): string[] => {
    const current = selectedIdsRef.current
    let next: string[]
    if (!options.compare) next = current.length === 1 && current[0] === proposalId ? [] : [proposalId]
    else if (current.includes(proposalId)) next = current.filter((id) => id !== proposalId)
    else next = [...current.slice(-1), proposalId]
    selectedIdsRef.current = next
    setSelectedIds(next)
    return next
  }, [])

  return {
    scenarios, selectedIds, previewing, notice,
    preview, apply, discard, markStaged, select,
    clearSelection: () => setSelectedIds([]),
    dismissNotice: () => setNotice(null),
  }
}
