import { useEffect, useState, useCallback } from 'react'
import { fetchWeek, publishRange } from '../../../api/employees/employeeSchedule'
import type {
  Shift, RosterEmployee, ScheduleSummary, RosterFlags,
} from '../../../types/employeeSchedule'
import {
  toISODate, addDays, startOfWeekSunday,
} from '../../../types/employeeSchedule'

export type EmployeeScheduleTab = 'schedule' | 'templates' | 'auto-schedules' | 'requests' | 'audit' | 'intelligence'

export function useEmployeeSchedule(
  initialDate?: string,
  initialTab: EmployeeScheduleTab = 'schedule',
  locationId = '',
) {
  const [tab, setTab] = useState<EmployeeScheduleTab>(initialTab)
  // `initialDate` (from a ?date= deep link — see systemContent.tsx's
  // shift-link token) opens the week that date falls in, not always "this
  // week": a shift-chat confirmation can land in a future or past week.
  const [weekStart, setWeekStart] = useState(() =>
    toISODate(startOfWeekSunday(initialDate ? new Date(`${initialDate}T00:00:00Z`) : new Date())),
  )
  const [shifts, setShifts] = useState<Shift[]>([])
  const [roster, setRoster] = useState<RosterEmployee[]>([])
  const [rosterFlags, setRosterFlags] = useState<RosterFlags | null>(null)
  const [summary, setSummary] = useState<ScheduleSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [publishing, setPublishing] = useState(false)

  const reload = useCallback(async () => {
    if (!locationId) {
      setShifts([])
      setRoster([])
      setRosterFlags(null)
      setSummary(null)
      return
    }
    const w = await fetchWeek(weekStart, locationId)
    setShifts(w.shifts)
    setRoster(w.roster)
    setRosterFlags(w.roster_flags)
    setSummary(w.summary)
  }, [locationId, weekStart])

  useEffect(() => {
    setLoading(true)
    reload().finally(() => setLoading(false))
  }, [reload])

  function patchShift(updated: Shift) {
    setShifts((prev) => prev.map((s) => (s.id === updated.id ? updated : s)))
  }

  async function publishWeek() {
    if (!locationId) return
    setPublishing(true)
    try {
      await publishRange(`${weekStart}T00:00:00Z`, `${addDays(weekStart, 7)}T00:00:00Z`, locationId)
      await reload()
    } finally {
      setPublishing(false)
    }
  }

  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))

  return {
    tab, setTab,
    weekStart, setWeekStart,
    shifts,
    roster,
    rosterFlags,
    summary,
    loading,
    publishing,
    reload,
    patchShift,
    publishWeek,
    days,
  }
}
