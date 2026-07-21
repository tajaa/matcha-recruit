import { useState, useRef, useCallback, useEffect } from 'react'
import { postSSE } from '../../api/sse'

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

  // Abort any in-flight stream on unmount so navigation away stops the
  // server-side generation instead of draining it into a dead component.
  useEffect(() => () => abortRef.current?.abort(), [])

  const runAnalysis = useCallback(
    (type: IRStreamAnalysisType) => {
      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl

      setState({ streaming: true, messages: [], result: null, error: '', analysisType: type })

      const endpoint = type === 'similar' ? 'similar' : type

      postSSE(
        `/ir/incidents/${incidentId}/analyze/${endpoint}`,
        undefined,
        (data) => {
          const msg = data as { type?: string; message?: string; result?: unknown; data?: unknown }
          if (msg.type === 'phase') {
            setState((s) => ({ ...s, messages: [...s.messages, msg.message ?? ''] }))
          }
          if (msg.type === 'cached' || msg.type === 'complete') {
            setState((s) => ({ ...s, result: (msg.result ?? msg.data) as typeof s.result, streaming: false }))
            return true
          }
          if (msg.type === 'error') {
            setState((s) => ({ ...s, error: msg.message ?? 'Analysis failed', streaming: false }))
            return true
          }
        },
        { signal: ctrl.signal },
      )
        .catch((e) => {
          if (ctrl.signal.aborted) return
          setState((s) => ({
            ...s,
            error: e instanceof Error ? e.message : 'Stream failed',
            streaming: false,
          }))
        })
        .finally(() => {
          if (!ctrl.signal.aborted) setState((s) => ({ ...s, streaming: false }))
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
