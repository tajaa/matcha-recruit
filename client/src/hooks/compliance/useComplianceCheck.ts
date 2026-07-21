import { useState, useRef, useCallback, useEffect } from 'react'
import { getComplianceCheckPath } from '../../api/compliance/compliance'
import { postSSE } from '../../api/sse'

export interface ComplianceCheckMessage {
  type: string
  status?: string
  message?: string
  location?: string
  new?: number
  updated?: number
  alerts?: number
  missing_categories?: string[]
}

export function useComplianceCheck(onComplete: () => void) {
  const [scanning, setScanning] = useState(false)
  const [messages, setMessages] = useState<ComplianceCheckMessage[]>([])
  const abortRef = useRef<AbortController | null>(null)

  // Abort any in-flight stream on unmount so navigation away stops the
  // server-side generation instead of draining it into a dead component.
  useEffect(() => () => abortRef.current?.abort(), [])

  const runCheck = useCallback(async (locationId: string) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setScanning(true)
    setMessages([])

    try {
      await postSSE(
        getComplianceCheckPath(locationId),
        undefined,
        (data) => { setMessages((prev) => [...prev, data as ComplianceCheckMessage]) },
        { signal: ctrl.signal },
      )
      onComplete()
    } catch {
      if (!ctrl.signal.aborted) {
        setMessages((prev) => [...prev, { type: 'error', message: 'Compliance check failed' }])
      }
    } finally {
      setScanning(false)
    }
  }, [onComplete])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setScanning(false)
    setMessages([])
  }, [])

  return { scanning, messages, runCheck, reset }
}
