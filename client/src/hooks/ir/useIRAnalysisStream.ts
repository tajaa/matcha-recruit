import { useState, useRef, useCallback } from 'react'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

export type IRStreamAnalysisType = 'root-cause' | 'recommendations' | 'similar'

type StreamState = {
  streaming: boolean
  messages: string[]
  result: unknown | null
  error: string
  analysisType: IRStreamAnalysisType | null
}

export function useIRAnalysisStream(incidentId: string) {
  const [state, setState] = useState<StreamState>({
    streaming: false,
    messages: [],
    result: null,
    error: '',
    analysisType: null,
  })
  const abortRef = useRef<AbortController | null>(null)

  const runAnalysis = useCallback(
    (type: IRStreamAnalysisType) => {
      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl

      setState({ streaming: true, messages: [], result: null, error: '', analysisType: type })

      const token = localStorage.getItem('matcha_access_token')
      const endpoint = type === 'similar' ? 'similar' : type
      const url = `${BASE}/ir/incidents/${incidentId}/analyze/${endpoint}`

      fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        signal: ctrl.signal,
      })
        .then(async (res) => {
          if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
          const reader = res.body?.getReader()
          if (!reader) throw new Error('No response body')
          const decoder = new TextDecoder()
          let buf = ''

          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buf += decoder.decode(value, { stream: true })
            const lines = buf.split('\n')
            buf = lines.pop() ?? ''

            for (const line of lines) {
              if (!line.startsWith('data: ')) continue
              const raw = line.slice(6).trim()
              if (raw === '[DONE]') {
                setState((s) => ({ ...s, streaming: false }))
                return
              }
              try {
                const msg = JSON.parse(raw)
                if (msg.type === 'phase') {
                  setState((s) => ({ ...s, messages: [...s.messages, msg.message ?? ''] }))
                }
                if (msg.type === 'cached' || msg.type === 'complete') {
                  setState((s) => ({ ...s, result: msg.result ?? msg.data, streaming: false }))
                  return
                }
                if (msg.type === 'error') {
                  setState((s) => ({ ...s, error: msg.message ?? 'Analysis failed', streaming: false }))
                  return
                }
              } catch { /* skip malformed */ }
            }
          }
          setState((s) => ({ ...s, streaming: false }))
        })
        .catch((e) => {
          if (e.name !== 'AbortError') {
            setState((s) => ({
              ...s,
              error: e instanceof Error ? e.message : 'Stream failed',
              streaming: false,
            }))
          }
        })
    },
    [incidentId],
  )

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setState({ streaming: false, messages: [], result: null, error: '', analysisType: null })
  }, [])

  return { ...state, runAnalysis, reset }
}
