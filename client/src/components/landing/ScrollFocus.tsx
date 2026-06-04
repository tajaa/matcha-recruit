import { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'

// Scroll "focus mode" for marketing pages: as you scroll, the section nearest
// the viewport's upper third is the only one held fully lit — the rest dim,
// blur and shrink back. Once you reach the bottom of the page the lock releases
// and every section presents at once. Shared by Landing.tsx and MatchaLitePage.

export function useScrollFocus() {
  const els = useRef<(HTMLElement | null)[]>([])
  const [active, setActive] = useState(0)
  const [released, setReleased] = useState(false)
  const register = useCallback((idx: number, el: HTMLElement | null) => { els.current[idx] = el }, [])

  useEffect(() => {
    let ticking = false
    const compute = () => {
      ticking = false
      const vh = window.innerHeight
      const focusLine = vh * 0.42
      let best = 0
      let bestDist = Infinity
      els.current.forEach((el, i) => {
        if (!el) return
        const r = el.getBoundingClientRect()
        const mid = r.top + r.height / 2
        const dist = Math.abs(mid - focusLine)
        if (dist < bestDist) { bestDist = dist; best = i }
      })
      setActive(best)
      const doc = document.documentElement
      setReleased(window.scrollY + vh >= doc.scrollHeight - 120)
    }
    const onScroll = () => { if (!ticking) { ticking = true; requestAnimationFrame(compute) } }
    compute()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => { window.removeEventListener('scroll', onScroll); window.removeEventListener('resize', onScroll) }
  }, [])

  return { active, released, register }
}

export type Focus = ReturnType<typeof useScrollFocus>

export function FocusSection({ idx, focus, children }: { idx: number; focus: Focus; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    focus.register(idx, ref.current)
    return () => focus.register(idx, null)
  }, [idx, focus])
  const lit = focus.released || focus.active === idx
  return (
    <motion.div
      ref={ref}
      animate={{ opacity: lit ? 1 : 0.2, filter: lit ? 'blur(0px)' : 'blur(3px)', scale: lit ? 1 : 0.985 }}
      transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      style={{ transformOrigin: 'center top', willChange: 'opacity, filter, transform' }}
    >
      {children}
    </motion.div>
  )
}
