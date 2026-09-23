import { useEffect, useState, type RefObject } from 'react'

export function useMedia(query: string): boolean {
  const [matches, setMatches] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  useEffect(() => {
    const mql = window.matchMedia(query)
    const onChange = () => setMatches(mql.matches)
    onChange()
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])
  return matches
}

export const useReducedMotion = () => useMedia('(prefers-reduced-motion: reduce)')
export const useNarrow = () => useMedia('(max-width: 640px)')

/** True once the element has come within `rootMargin` of the viewport. One-shot:
 *  reveals and lazy loads never need to undo themselves. */
export function useInView(ref: RefObject<Element | null>, rootMargin = '0px 0px -12% 0px', threshold = 0.15): boolean {
  // No IntersectionObserver (very old browser) → treat everything as seen.
  const [seen, setSeen] = useState(() => typeof IntersectionObserver === 'undefined')
  useEffect(() => {
    const el = ref.current
    if (!el || seen) return
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSeen(true)
          io.disconnect()
        }
      },
      { rootMargin, threshold },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [ref, rootMargin, threshold, seen])
  return seen
}

/** Resolves after the browser is idle (or a short timeout), so non-critical
 *  work starts after first paint without waiting for a scroll. */
export function useIdle(enabled: boolean): boolean {
  const [idle, setIdle] = useState(false)
  useEffect(() => {
    if (!enabled || idle) return
    const w = window as Window & {
      requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number
      cancelIdleCallback?: (id: number) => void
    }
    if (w.requestIdleCallback) {
      const id = w.requestIdleCallback(() => setIdle(true), { timeout: 1200 })
      return () => w.cancelIdleCallback?.(id)
    }
    const id = window.setTimeout(() => setIdle(true), 200)
    return () => window.clearTimeout(id)
  }, [enabled, idle])
  return idle
}
