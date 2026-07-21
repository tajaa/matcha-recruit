import { useEffect, useState, useCallback } from 'react'
import { fetchWeek, publishRange } from '../../../api/employees/employeeSchedule'
import type {
  Shift, RosterEmployee, ScheduleSummary,
} from '../../../types/employeeSchedule'
import {
  toISODate, addDays, startOfWeekSunday,
} from '../../../types/employeeSchedule'

type Tab = 'schedule' | 'templates' | 'requests'

export function useEmployeeSchedule() {
  const [tab, setTab] = useState<Tab>('schedule')
  const [weekStart, setWeekStart] = useState(() => toISODate(startOfWeekSunday(new Date())))
  const [shifts, setShifts] = useState<Shift[]>([])
  const [roster, setRoster] = useState<RosterEmployee[]>([])
  const [summary, setSummary] = useState<ScheduleSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [publishing, setPublishing] = useState(false)

  const reload = useCallback(async () => {
    const w = await fetchWeek(weekStart)
    setShifts(w.shifts)
    setRoster(w.roster)
    setSummary(w.summary)
  }, [weekStart])

  useEffect(() => {
    setLoading(true)
    reload().finally(() => setLoading(false))
  }, [reload])

  function patchShift(updated: Shift) {
    setShifts((prev) => prev.map((s) => (s.id === updated.id ? updated : s)))
  }

  async function publishWeek() {
    setPublishing(true)
    try {
      await publishRange(`${weekStart}T00:00:00Z`, `${addDays(weekStart, 7)}T00:00:00Z`)
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
    summary,
    loading,
    publishing,
    reload,
    patchShift,
    publishWeek,
    days,
  }
}
