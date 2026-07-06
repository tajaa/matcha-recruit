import { useState, useRef, useCallback, useEffect } from 'react'
import { getComplianceCheckUrl } from '../../api/compliance'
import { ensureFreshToken } from '../../api/client'

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

    const token = await ensureFreshToken()
    const url = getComplianceCheckUrl(locationId)

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        signal: ctrl.signal,
      })
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
          const data = line.slice(6).trim()
          if (data === '[DONE]') {
            setScanning(false)
            onComplete()
            return
          }
          try {
            const ev = JSON.parse(data)
            setMessages((prev) => [...prev, ev])
          } catch { /* skip malformed */ }
        }
      }
      setScanning(false)
      onComplete()
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setMessages((prev) => [...prev, { type: 'error', message: 'Compliance check failed' }])
      }
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
