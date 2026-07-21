import { useState, useRef, useCallback, useEffect } from 'react'
import { getResearchGapsPath } from '../../api/admin/adminOnboarding'
import { postSSE } from '../../api/sse'
import type { EnrichEvent } from './useEnrichStream'

/**
 * Streams the SELECTIVE gap-fill endpoint
 * (POST /admin/onboarding/research-gaps/{companyId}/stream). Researches only the
 * chosen (jurisdiction, category) items, so runs stay short. fetch + ReadableStream
 * (POST + JSON body), same SSE framing as useEnrichStream.
 */
export type ResearchGapItem = {
  category_slug: string
  scope_level?: string | null
  state?: string | null
  county?: string | null
  city?: string | null
}

export function useResearchGaps() {
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState<EnrichEvent[]>([])
  const [done, setDone] = useState<EnrichEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Abort any in-flight stream on unmount so navigation away stops the
  // server-side generation instead of draining it into a dead component.
  useEffect(() => () => abortRef.current?.abort(), [])

  const run = useCallback(async (companyId: string, items: ResearchGapItem[]) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setRunning(true)
    setEvents([])
    setDone(null)
    setError(null)

    try {
      await postSSE(
        getResearchGapsPath(companyId),
        { items },
        (data) => {
          const ev = data as EnrichEvent
          if (ev.type === 'complete') setDone(ev)
          if (ev.type === 'error' && !ev.jurisdiction) setError(ev.message ?? 'Research failed')
          setEvents((prev) => [...prev, ev])
        },
        { signal: ctrl.signal },
      )
    } catch (e) {
      if (!ctrl.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Research stream failed')
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
