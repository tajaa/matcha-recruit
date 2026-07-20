import { useState, useRef, useCallback, useEffect } from 'react'
import { getEnrichStreamPath } from '../../api/admin/adminOnboarding'
import { postSSE } from '../../api/sse'

/**
 * Consumes the master-admin gap-analysis enrichment SSE stream
 * (POST /admin/onboarding/enrich/{companyId}/stream) via postSSE (api/sse.ts) so the
 * Authorization header can be attached (EventSource can't). Mirrors
 * hooks/compliance/useComplianceCheck.
 */
export type EnrichEvent = {
  type: string
  message?: string
  // roster_scanned
  locations_total?: number
  locations_new?: number
  roles?: string[]
  // jurisdiction_new / jurisdiction_tracking / researching / passthrough
  city?: string | null
  state?: string
  jurisdiction?: string
  // run_compliance_check_stream passthrough
  new?: number
  updated?: number
  alerts?: number
  missing_categories?: string[]
  // scoped
  covered?: number
  missing?: number
  scope_rows_written?: number
  credentials?: { name: string; applies_to_role?: string | null }[]
  // complete
  session_id?: string
  company_id?: string
  new_jurisdictions?: { city?: string | null; state: string }[]
  existing_scope_count?: number
  suggestions?: number
  // research-gaps stream
  categories?: string[]
  jurisdictions_filled?: number
}

export function useEnrichStream() {
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState<EnrichEvent[]>([])
  const [done, setDone] = useState<EnrichEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Abort any in-flight stream on unmount so navigation away stops the
  // server-side generation instead of draining it into a dead component.
  useEffect(() => () => abortRef.current?.abort(), [])

  const run = useCallback(async (companyId: string) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setRunning(true)
    setEvents([])
    setDone(null)
    setError(null)

    try {
      await postSSE(
        getEnrichStreamPath(companyId),
        undefined,
        (data) => {
          const ev = data as EnrichEvent
          if (ev.type === 'complete') setDone(ev)
          // Only the orchestrator's own (un-namespaced) error is fatal.
          // Per-jurisdiction research errors are downgraded to warnings
          // server-side and carry a `jurisdiction` — shown in the feed only.
          if (ev.type === 'error' && !ev.jurisdiction) setError(ev.message ?? 'Gap analysis failed')
          setEvents((prev) => [...prev, ev])
        },
        { signal: ctrl.signal },
      )
    } catch (e) {
      if (!ctrl.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Gap analysis stream failed')
      }
    } finally {
      setRunning(false)
    }
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setRunning(false)
    setEvents([])
    setDone(null)
    setError(null)
  }, [])

  return { running, events, done, error, run, reset }
}
