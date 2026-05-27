import { useState, useRef, useCallback } from 'react'
import { getEnrichStreamUrl } from '../api/adminOnboarding'

/**
 * Consumes the master-admin gap-analysis enrichment SSE stream
 * (POST /admin/onboarding/enrich/{companyId}/stream) via fetch + ReadableStream
 * so the Authorization header can be attached (EventSource can't). Mirrors
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
}

export function useEnrichStream() {
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState<EnrichEvent[]>([])
  const [done, setDone] = useState<EnrichEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const run = useCallback(async (companyId: string) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setRunning(true)
    setEvents([])
    setDone(null)
    setError(null)

    const token = localStorage.getItem('matcha_access_token')

    try {
      const res = await fetch(getEnrichStreamUrl(companyId), {
        method: 'POST',
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        signal: ctrl.signal,
      })
      if (!res.ok) throw new Error(`Stream failed (${res.status})`)
      const reader = res.body?.getReader()
      if (!reader) throw new Error('No response body')
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done: streamDone, value } = await reader.read()
        if (streamDone) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6).trim()
          if (data === '[DONE]') {
            setRunning(false)
            return
          }
          try {
            const ev = JSON.parse(data) as EnrichEvent
            if (ev.type === 'complete') setDone(ev)
            // Only the orchestrator's own (un-namespaced) error is fatal.
            // Per-jurisdiction research errors are downgraded to warnings
            // server-side and carry a `jurisdiction` — shown in the feed only.
            if (ev.type === 'error' && !ev.jurisdiction) setError(ev.message ?? 'Gap analysis failed')
            setEvents((prev) => [...prev, ev])
          } catch {
            /* skip malformed */
          }
        }
      }
      setRunning(false)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setError(e instanceof Error ? e.message : 'Gap analysis stream failed')
      }
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
