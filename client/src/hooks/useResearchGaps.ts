import { useState, useRef, useCallback } from 'react'
import { getResearchGapsUrl } from '../api/adminOnboarding'
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

  const run = useCallback(async (companyId: string, items: ResearchGapItem[]) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setRunning(true)
    setEvents([])
    setDone(null)
    setError(null)

    const token = localStorage.getItem('matcha_access_token')

    try {
      const res = await fetch(getResearchGapsUrl(companyId), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ items }),
        signal: ctrl.signal,
      })
      if (!res.ok) throw new Error(`Research failed (${res.status})`)
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
            if (ev.type === 'error' && !ev.jurisdiction) setError(ev.message ?? 'Research failed')
            setEvents((prev) => [...prev, ev])
          } catch {
            /* skip malformed */
          }
        }
      }
      setRunning(false)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setError(e instanceof Error ? e.message : 'Research stream failed')
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
