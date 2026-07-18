import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getMatchaXBuildStreamUrl } from '../../api/billing/matchaXOnboarding'
import { ensureFreshToken } from '../../api/client'

/**
 * Consumes the Matcha-X onboarding build SSE stream
 * (POST /matcha-x-onboarding/build/stream) via fetch + ReadableStream so the
 * Authorization header can be attached (EventSource can't). Clone of
 * hooks/useEnrichStream — same envelope, different event vocabulary.
 *
 * The build POSTs a JSON body `{ handbook_url }` (the value Step 2's upload
 * returned) so the server can overlay handbook coverage on the finale.
 */

// One graded requirement from the handbook-coverage overlay (server reuses
// handbook_audit_service._grade_state_coverage).
export type HandbookGrade = {
  requirement_key?: string
  requirement_title?: string
  covered: boolean
  severity?: 'critical' | 'important' | 'recommended'
  citation?: string | null
  what_good_looks_like?: string
  matched_section_title?: string | null
}

export type BuildEvent = {
  type: string
  message?: string
  // locations_scanned
  count?: number
  labels?: string[]
  // location_start / passthrough (tagged per-location)
  location_id?: string
  label?: string
  city?: string | null
  state?: string
  // run_compliance_check_stream passthrough
  jurisdiction_id?: string
  missing_categories?: string[]
  // location_built — note `covered` is a number here but an array on
  // handbook_coverage, hence the union; narrow by `type` at the use site.
  covered?: number | HandbookGrade[]
  codified_new?: number
  researched_live?: boolean
  // roster_scanned / jurisdiction_new / roster-tagged location_built (D3.2) —
  // `source: "roster"` marks an event as coming from the roster union rather
  // than a typed location.
  source?: 'roster'
  locations_total?: number
  locations_new?: number
  roles?: string[]
  // handbook_grading / handbook_coverage
  gaps?: HandbookGrade[]
  covered_count?: number
  gap_count?: number
  reason?: string
  // complete
  locations?: number
  jurisdictions?: number
  requirements?: number
  handbook_states_graded?: number
  handbook_coverage_pct?: number | null
  roster_locations_added?: number
  skipped_no_work_state?: number
}

// Live running totals derived from the event stream — drives the finale header.
export type BuildTotals = {
  locationsBuilt: number
  requirements: number
  codifiedNew: number
  jurisdictions: number
  handbookCovered: number
  handbookGaps: number
}

export function useMatchaXBuildStream() {
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState<BuildEvent[]>([])
  const [done, setDone] = useState<BuildEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const run = useCallback(async (handbookUrl?: string | null) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setRunning(true)
    setEvents([])
    setDone(null)
    setError(null)

    const token = await ensureFreshToken()

    try {
      const res = await fetch(getMatchaXBuildStreamUrl(), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ handbook_url: handbookUrl || null }),
        signal: ctrl.signal,
      })
      if (!res.ok) throw new Error(`Build failed (${res.status})`)
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
            const ev = JSON.parse(data) as BuildEvent
            if (ev.type === 'complete') setDone(ev)
            // Only the orchestrator's own (un-tagged) error is fatal; per-location
            // hiccups are downgraded to warnings server-side and carry a
            // `location_id` — shown in the feed only.
            if (ev.type === 'error' && !ev.location_id) {
              setError(ev.message ?? 'Compliance build failed')
            }
            setEvents((prev) => [...prev, ev])
          } catch {
            /* skip malformed */
          }
        }
      }
      setRunning(false)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setError(e instanceof Error ? e.message : 'Build stream failed')
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

  // Abort an in-flight build if the component unmounts (e.g. the user navigates
  // away mid-stream) — a fully-live, uncapped build would otherwise keep
  // researching jurisdictions and burning tokens with nobody watching.
  useEffect(() => () => abortRef.current?.abort(), [])

  const totals = useMemo<BuildTotals>(() => {
    const t: BuildTotals = {
      locationsBuilt: 0,
      requirements: 0,
      codifiedNew: 0,
      jurisdictions: 0,
      handbookCovered: 0,
      handbookGaps: 0,
    }
    const jurisdictions = new Set<string>()
    for (const ev of events) {
      if (ev.type === 'location_built') {
        t.locationsBuilt += 1
        t.requirements += typeof ev.covered === 'number' ? ev.covered : 0
        t.codifiedNew += ev.codified_new ?? 0
      }
      if (ev.type === 'handbook_coverage') {
        t.handbookCovered += ev.covered_count ?? 0
        t.handbookGaps += ev.gap_count ?? 0
      }
      if (ev.jurisdiction_id) jurisdictions.add(ev.jurisdiction_id)
    }
    t.jurisdictions = jurisdictions.size
    return t
  }, [events])

  return { running, events, done, error, totals, run, reset }
}
