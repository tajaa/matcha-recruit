import { useEffect, useState } from 'react'
import { useReducedMotion } from 'framer-motion'

// Counts a number up from 0 once in view, and again every time `trigger` changes.
export function useCountUp(target: number, active: boolean, duration = 900, trigger = 0) {
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (!active) return
    let raf: number
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      setValue(Math.round(target * eased))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [active, target, duration, trigger])
  return value
}

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
