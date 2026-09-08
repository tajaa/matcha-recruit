import { useEffect, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, CalendarClock, Loader2 } from 'lucide-react'
import { PillTabs } from '../../components/ui'
import {
  fetchMySchedule, fetchMyTeamSchedule, fetchMyRequests, fetchMyOffers, fetchMyCoworkers,
} from '../../api/employees/employeeSchedule'
import type { Shift, ScheduleRequest } from '../../types/employeeSchedule'
import { addDays, errorMessage } from '../../types/employeeSchedule'
import { HORIZON_DAYS, todayISO } from './schedule/shared'
import ScheduleTab from './schedule/ScheduleTab'
import AvailabilityTab from './schedule/AvailabilityTab'
import RequestsTab from './schedule/RequestsTab'

type PortalTab = 'schedule' | 'availability' | 'requests'

const TAB_VALUES: PortalTab[] = ['schedule', 'availability', 'requests']

function parseTab(raw: string | null): PortalTab {
  return TAB_VALUES.includes(raw as PortalTab) ? raw as PortalTab : 'schedule'
}

/** Shell for the employee's schedule surface: one fetch of the four-week
 *  horizon, three focused tabs over it. The tab lives in `?tab=` so a refresh
 *  or the browser back button lands where the employee was, rather than
 *  dumping them back at the top of the schedule. */
export default function PortalSchedule() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [shifts, setShifts] = useState<Shift[]>([])
  const [teamShifts, setTeamShifts] = useState<Shift[]>([])
  const [requests, setRequests] = useState<ScheduleRequest[]>([])
  const [offers, setOffers] = useState<ScheduleRequest[]>([])
  const [coworkers, setCoworkers] = useState<{ id: string; name: string }[]>([])
  // Captured when the fetch goes out, not read again at render time: the
  // week sections must partition exactly the horizon that was requested, and
  // a session left open across midnight would otherwise shift one and drop
  // the last day out of every section.
  const [horizonStart, setHorizonStart] = useState(todayISO)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [requestError, setRequestError] = useState<string | null>(null)

  const tab = parseTab(searchParams.get('tab'))

  const load = useCallback(async () => {
    const start = todayISO()
    const end = `${addDays(start, HORIZON_DAYS)}T00:00:00Z`
    const [schedule, teamSchedule, reqs, openOffers, roster] = await Promise.allSettled([
      fetchMySchedule(`${start}T00:00:00Z`, end),
      fetchMyTeamSchedule(`${start}T00:00:00Z`, end),
      fetchMyRequests(),
      fetchMyOffers(),
      fetchMyCoworkers(),
    ])
    if (schedule.status === 'rejected') throw schedule.reason
    setHorizonStart(start)
    setShifts(schedule.value.shifts)
    setLoadError(null)
    const errors: string[] = []
    if (teamSchedule.status === 'fulfilled') setTeamShifts(teamSchedule.value.shifts)
    else errors.push('full schedule')
    if (reqs.status === 'fulfilled') setRequests(reqs.value.requests)
    else errors.push('request history')
    if (openOffers.status === 'fulfilled') setOffers(openOffers.value.offers)
    else errors.push('available offers')
    if (roster.status === 'fulfilled') setCoworkers(roster.value.employees)
    else errors.push('coworkers')
    setRequestError(errors.length ? `Could not load ${errors.join(', ')}. Your published shifts are still available.` : null)
  }, [])

  // Swallowing this would render "no published shifts" — a fake-legitimate empty
  // state — on top of a 403 or a 500.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        await load()
      } catch (err) {
        if (!cancelled) setLoadError(errorMessage(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [load])

  // Push, not replace: the back button should walk back through the tabs the
  // employee opened. `week` rides along so returning to the schedule keeps the
  // dates they were reading.
  const selectTab = useCallback((next: PortalTab) => {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev)
      params.set('tab', next)
      return params
    })
  }, [setSearchParams])

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>

  if (loadError) {
    return (
      <div className="max-w-3xl">
        <div className="flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/5 p-4">
          <AlertTriangle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-medium text-zinc-100">Couldn’t load your schedule</div>
            <div className="text-sm text-zinc-400 mt-0.5">{loadError}</div>
          </div>
        </div>
      </div>
    )
  }

  const tabOptions: { value: PortalTab; label: string }[] = [
    { value: 'schedule', label: 'Schedule' },
    { value: 'availability', label: 'My Availability' },
    { value: 'requests', label: offers.length ? `My Requests (${offers.length})` : 'My Requests' },
  ]

  return (
    <div className="max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <CalendarClock className="h-5 w-5 text-zinc-400" /> My Schedule
        </h1>
        <p className="text-sm text-zinc-500 mt-1">Your published shifts for the next four weeks, a week at a time. Availability and requests have their own tabs.</p>
      </div>

      <div className="overflow-x-auto pb-1">
        <PillTabs options={tabOptions} value={tab} onChange={selectTab} />
      </div>

      {requestError && <p className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-300">{requestError}</p>}

      {tab === 'schedule' && (
        <ScheduleTab horizonStart={horizonStart} shifts={shifts} teamShifts={teamShifts} coworkers={coworkers} onChanged={load} />
      )}
      {tab === 'availability' && (
        <AvailabilityTab teamShifts={teamShifts} onSubmitted={load} />
      )}
      {tab === 'requests' && (
        <RequestsTab requests={requests} offers={offers} shifts={shifts} teamShifts={teamShifts} onChanged={load} />
      )}
    </div>
  )
}
