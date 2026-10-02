import { useCallback, useEffect, useState } from 'react'
import { fetchStoreReadiness, fetchUnassignedEmployees } from '../../api/employees/scheduleStores'
import type { StoreReadiness, UnassignedEmployee } from '../../types/employeeSchedule'

export type StoreSetupModal = 'add' | 'edit' | 'assign' | null

/** What stands between a store and a published week, for whichever schedule
 *  screen is showing it: is the store itself publishable, and is anyone still
 *  waiting to be placed at a store. Both are answered up front so a manager
 *  learns about them before building a week, not when Publish refuses. */
export function useStoreSetup(locationId: string) {
  const [modal, setModal] = useState<StoreSetupModal>(null)
  const [readiness, setReadiness] = useState<StoreReadiness | null>(null)
  const [unassigned, setUnassigned] = useState<UnassignedEmployee[]>([])
  const [version, setVersion] = useState(0)

  const refresh = useCallback(() => setVersion((current) => current + 1), [])

  useEffect(() => {
    let cancelled = false
    // Advisory only: a failed check must never block the schedule itself.
    fetchUnassignedEmployees()
      .then((employees) => { if (!cancelled) setUnassigned(employees) })
      .catch(() => { if (!cancelled) setUnassigned([]) })
    return () => { cancelled = true }
  }, [version])

  useEffect(() => {
    let cancelled = false
    if (!locationId) {
      void Promise.resolve().then(() => { if (!cancelled) setReadiness(null) })
      return () => { cancelled = true }
    }
    fetchStoreReadiness(locationId)
      .then((result) => { if (!cancelled) setReadiness(result) })
      .catch(() => { if (!cancelled) setReadiness(null) })
    return () => { cancelled = true }
  }, [locationId, version])

  return { modal, setModal, readiness, unassigned, refresh }
}

export type StoreSetup = ReturnType<typeof useStoreSetup>
