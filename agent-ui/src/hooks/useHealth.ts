import { useState, useEffect, useRef } from 'preact/hooks'
import { api } from '../lib/api'
import type { HealthStatus } from '../lib/api'

export function useHealth(enabled: boolean) {
  const [status, setStatus] = useState<HealthStatus | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval>>()

  useEffect(() => {
    if (!enabled) return

    const check = () => {
      api.health().then(setStatus).catch(() => setStatus(null))
    }
    check()
    intervalRef.current = setInterval(check, 30000)
    return () => clearInterval(intervalRef.current)
  }, [enabled])

  return status
}
