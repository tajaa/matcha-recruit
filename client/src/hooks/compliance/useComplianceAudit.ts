import { useCallback, useEffect, useState } from 'react'
import { fetchComplianceAudit } from '../../api/compliance/compliance'
import type { ComplianceAuditOverview } from '../../types/compliance'

// Fetched lazily — this hook only runs when ComplianceAuditTab actually
// mounts (i.e. the Audit tab is selected), not at Compliance page load. The
// endpoint runs a company-wide reconcile plus a per-location visibility
// pipeline; firing it just to badge Requirements rows would be waste.
export function useComplianceAudit(companyId?: string) {
  const [data, setData] = useState<ComplianceAuditOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Separate from `error`: a failed silent refresh must not tear down a tab
  // that is already showing real data (see `refresh` below). `error` stays
  // reserved for the fatal "nothing loaded" case that blanks the tab.
  const [refreshError, setRefreshError] = useState<string | null>(null)

  const load = useCallback(async (silent: boolean) => {
    if (!silent) {
      setLoading(true)
      setError(null)
    }
    setRefreshError(null)
    try {
      setData(await fetchComplianceAudit(companyId))
    } catch {
      if (silent) {
        setRefreshError('Could not refresh — showing the last loaded data.')
      } else {
        setError('Could not load the audit overview.')
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }, [companyId])

  const refetch = useCallback(() => { void load(false) }, [load])
  // Same fetch without the loading flag: an attestation has to move the
  // statute/location rollups, but flipping `loading` would tear down every
  // StatuteCard — including the expanded checklist the user just clicked in.
  // A failure here goes to `refreshError`, not `error`, for the same reason.
  const refresh = useCallback(() => { void load(true) }, [load])

  useEffect(() => { refetch() }, [refetch])

  return { data, loading, error, refreshError, refetch, refresh }
}
