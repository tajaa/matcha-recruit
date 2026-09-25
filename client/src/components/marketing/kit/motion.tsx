import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { useInView, useReducedMotion } from './hooks'

/** Fades + lifts its children in the first time they scroll into view. The
 *  transition itself lives in LandingStyles (`.sr`), so reduced motion is one
 *  media query there rather than a branch here. */
export function Reveal({
  children,
  delay = 0,
  className = '',
  style,
  as: Tag = 'div',
}: {
  children: ReactNode
  delay?: number
  className?: string
  style?: CSSProperties
  as?: 'div' | 'li' | 'section' | 'span'
}) {
  const ref = useRef<HTMLElement>(null)
  const seen = useInView(ref)
  return (
    <Tag
      ref={ref as never}
      className={`sr ${seen ? 'is-in' : ''} ${className}`}
      style={{ ...style, ['--d' as string]: `${delay}ms` }}
    >
      {children}
    </Tag>
  )
}

/** Counts from `from` up to `value` once, the first time it's seen. Screen
 *  readers get the final value; reduced motion shows it straight away. */
export function CountUp({ value, from = 0, format = String }: { value: number; from?: number; format?: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const seen = useInView(ref, '0px 0px -15% 0px', 0.5)
  const reduced = useReducedMotion()
  const [shown, setShown] = useState(from)
  useEffect(() => {
    if (!seen || reduced) return
    let raf = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 1500)
      setShown(from + (value - from) * (1 - Math.pow(1 - t, 3)))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [seen, reduced, value, from])
  return (
    <span ref={ref} aria-label={format(value)} style={{ fontVariantNumeric: 'tabular-nums' }}>
      <span aria-hidden>{format(reduced ? value : Math.round(shown))}</span>
    </span>
  )
}
