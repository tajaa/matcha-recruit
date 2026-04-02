import { useEffect, useRef } from 'react'
import { api } from '../api/client'

const INTERVAL_MS = 30_000

export function usePresenceHeartbeat() {
  const active = useRef(true)

  useEffect(() => {
    active.current = true

    function beat() {
      if (!active.current) return
      api.post('/matcha-work/presence/heartbeat').catch(() => {})
    }

    beat()
    const id = setInterval(beat, INTERVAL_MS)
    return () => {
      active.current = false
      clearInterval(id)
    }
  }, [])
}
