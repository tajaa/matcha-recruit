import { useState, useCallback, useEffect, useRef } from 'react'
import { fetchRequirements, fetchUpcomingLegislation, fetchCheckLog } from '../../api/compliance'
import type { ComplianceRequirement, UpcomingLegislation, CheckLogEntry } from '../../types/compliance'

// `lite` = Matcha-X read-only taste: skips the Pro-only check-log fetch
// (`/check-log` stays compliance-gated; History tab is locked for lite anyway).
export function useLocationDetail(locationId: string | null, lite = false) {
  const [requirements, setRequirements] = useState<ComplianceRequirement[]>([])
  const [upcomingLegislation, setUpcomingLegislation] = useState<UpcomingLegislation[]>([])
  const [checkLog, setCheckLog] = useState<CheckLogEntry[]>([])
  const [loading, setLoading] = useState(false)

  // Per-loader request ids drop stale responses when locationId switches while
  // an older fetch is still in flight (they run concurrently via refetch).
  const reqReq = useRef(0)
  const upReq = useRef(0)
  const logReq = useRef(0)

  const loadRequirements = useCallback(async () => {
    if (!locationId) { setRequirements([]); return }
    const id = ++reqReq.current
    try { const d = await fetchRequirements(locationId); if (id === reqReq.current) setRequirements(d) } catch { if (id === reqReq.current) setRequirements([]) }
  }, [locationId])

  const loadUpcoming = useCallback(async () => {
    if (!locationId) { setUpcomingLegislation([]); return }
    const id = ++upReq.current
    try { const d = await fetchUpcomingLegislation(locationId); if (id === upReq.current) setUpcomingLegislation(d) } catch { if (id === upReq.current) setUpcomingLegislation([]) }
  }, [locationId])

  const loadCheckLog = useCallback(async () => {
    if (!locationId) { setCheckLog([]); return }
    const id = ++logReq.current
    try { const d = await fetchCheckLog(locationId); if (id === logReq.current) setCheckLog(d) } catch { if (id === logReq.current) setCheckLog([]) }
  }, [locationId])

  const refetch = useCallback(async () => {
    if (!locationId) return
    setLoading(true)
    await Promise.all([loadRequirements(), loadUpcoming(), ...(lite ? [] : [loadCheckLog()])])
    setLoading(false)
  }, [locationId, lite, loadRequirements, loadUpcoming, loadCheckLog])

  useEffect(() => {
    if (locationId) { refetch() }
    else { setRequirements([]); setUpcomingLegislation([]); setCheckLog([]) }
  }, [locationId, refetch])

  return { requirements, upcomingLegislation, checkLog, loading, refetch, loadRequirements }
}
