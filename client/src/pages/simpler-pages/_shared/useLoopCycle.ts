import { useEffect, useState } from 'react'
import { useReducedMotion } from 'framer-motion'

// Ticks up once every `intervalMs` while `active` (the instrument is in
// view), so a `key={cycle}` on the animated content replays its entrance.
export const CARD_LOOP_MS = 4000
export function useLoopCycle(active: boolean, intervalMs = CARD_LOOP_MS) {
  const reduce = useReducedMotion()
  const [cycle, setCycle] = useState(0)
  useEffect(() => {
    if (!active || reduce) return
    const id = setInterval(() => setCycle((c) => c + 1), intervalMs)
    return () => clearInterval(id)
  }, [active, reduce, intervalMs])
  return cycle
}
