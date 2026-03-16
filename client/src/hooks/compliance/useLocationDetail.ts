import { useState, useCallback, useEffect } from 'react'
import { fetchRequirements, fetchUpcomingLegislation, fetchCheckLog } from '../../api/compliance'
import type { ComplianceRequirement, UpcomingLegislation, CheckLogEntry } from '../../types/compliance'

export function useLocationDetail(locationId: string | null) {
  const [requirements, setRequirements] = useState<ComplianceRequirement[]>([])
  const [upcomingLegislation, setUpcomingLegislation] = useState<UpcomingLegislation[]>([])
  const [checkLog, setCheckLog] = useState<CheckLogEntry[]>([])
  const [loading, setLoading] = useState(false)

  const loadRequirements = useCallback(async () => {
    if (!locationId) { setRequirements([]); return }
    try { setRequirements(await fetchRequirements(locationId)) } catch { setRequirements([]) }
  }, [locationId])

  const loadUpcoming = useCallback(async () => {
    if (!locationId) { setUpcomingLegislation([]); return }
    try { setUpcomingLegislation(await fetchUpcomingLegislation(locationId)) } catch { setUpcomingLegislation([]) }
  }, [locationId])

  const loadCheckLog = useCallback(async () => {
    if (!locationId) { setCheckLog([]); return }
    try { setCheckLog(await fetchCheckLog(locationId)) } catch { setCheckLog([]) }
  }, [locationId])

  const refetch = useCallback(async () => {
    if (!locationId) return
    setLoading(true)
    await Promise.all([loadRequirements(), loadUpcoming(), loadCheckLog()])
    setLoading(false)
  }, [locationId, loadRequirements, loadUpcoming, loadCheckLog])

  useEffect(() => {
    if (locationId) { refetch() }
    else { setRequirements([]); setUpcomingLegislation([]); setCheckLog([]) }
  }, [locationId, refetch])

  return { requirements, upcomingLegislation, checkLog, loading, refetch, loadRequirements }
}
