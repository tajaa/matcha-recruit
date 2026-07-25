import { useCallback, useEffect, useState } from 'react'
import { fetchComplianceAudit } from '../../api/compliance/compliance'
import type { ComplianceAuditOverview } from '../../types/compliance'

// Fetched lazily — this hook only runs when ComplianceAuditTab actually
// mounts (i.e. the Audit tab is selected), not at Compliance page load. The
// endpoint runs a company-wide reconcile plus a per-location visibility
// pipeline; firing it just to badge Requirements rows would be waste.
export function useComplianceAudit() {
  const [data, setData] = useState<ComplianceAuditOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (silent: boolean) => {
    if (!silent) setLoading(true)
    setError(null)
    try {
      setData(await fetchComplianceAudit())
    } catch {
      setError('Could not load the audit overview.')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  const refetch = useCallback(() => { void load(false) }, [load])
  // Same fetch without the loading flag: an attestation has to move the
  // statute/location rollups, but flipping `loading` would tear down every
  // StatuteCard — including the expanded checklist the user just clicked in.
  const refresh = useCallback(() => { void load(true) }, [load])

  useEffect(() => { refetch() }, [refetch])

  return { data, loading, error, refetch, refresh }
}
