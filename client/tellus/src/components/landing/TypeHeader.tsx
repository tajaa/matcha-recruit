import { useEffect, useRef, useState } from 'react'
import { useInView, useReducedMotion } from 'framer-motion'

function Caret({ show }: { show: boolean }) {
  if (!show) return null
  return <span className="ml-0.5 inline-block h-[0.85em] w-[3px] translate-y-[0.1em] animate-pulse bg-tu-accent align-middle" aria-hidden />
}

// Types out a single string once the element scrolls into view. Used for
// section H2s — the hero's H1 needs multi-segment support, see TypedHeadline.
export function TypeHeader({ text, className = '', speed = 22, as: Tag = 'h2' }: { text: string; className?: string; speed?: number; as?: 'h2' | 'h3' }) {
  const ref = useRef<HTMLHeadingElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const reduce = useReducedMotion()
  const [n, setN] = useState(reduce ? text.length : 0)

  useEffect(() => {
    if (!inView || reduce) return
    let i = 0
    const id = setInterval(() => {
      i += 1
      setN(i)
      if (i >= text.length) clearInterval(id)
    }, speed)
    return () => clearInterval(id)
  }, [inView, reduce, text, speed])

  return (
    <Tag ref={ref} className={className}>
      <span aria-hidden>{text.slice(0, n)}<Caret show={n < text.length} /></span>
      <span className="sr-only">{text}</span>
    </Tag>
  )
}

interface Segment {
  text: string
  accent?: boolean
  newLine?: boolean
}

// Multi-segment typewriter for the hero H1 — two lines, second partly
// accent-colored, typed as one continuous stream so the caret only ever
// appears at the true end of the sentence.
export function TypedHeadline({ segments, className = '' }: { segments: Segment[]; className?: string }) {
  const ref = useRef<HTMLHeadingElement>(null)
  const inView = useInView(ref, { once: true, margin: '0px' })
  const reduce = useReducedMotion()
  const total = segments.reduce((s, seg) => s + seg.text.length, 0)
  const [n, setN] = useState(reduce ? total : 0)

  useEffect(() => {
    if (!inView || reduce) return
    let i = 0
    const id = setInterval(() => {
      i += 1
      setN(i)
      if (i >= total) clearInterval(id)
    }, 18)
    return () => clearInterval(id)
  }, [inView, reduce, total])

  let consumed = 0
  return (
    <h1 ref={ref} className={className}>
      <span aria-hidden>
        {segments.map((seg, i) => {
          const start = consumed
          consumed += seg.text.length
          const shown = Math.max(0, Math.min(seg.text.length, n - start))
          return (
            <span key={i}>
              {seg.newLine && <br />}
              <span className={seg.accent ? 'text-tu-accent' : undefined}>{seg.text.slice(0, shown)}</span>
            </span>
          )
        })}
        <Caret show={n < total} />
      </span>
      <span className="sr-only">{segments.map((s) => s.text).join(' ')}</span>
    </h1>
  )
}
