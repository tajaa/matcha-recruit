import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { useInView } from './hooks'
import { RED_PEN } from './theme'

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

type Seg = [cmd: 'M' | 'C' | 'S', ...xy: number[]]

// Designed in a 100×40 (circle) / 100×30 (underline) box, then scaled to the
// word's real pixel box — never stretched by preserveAspectRatio, which would
// distort the stroke and break the dash math the draw-on relies on.
const PATHS: Record<'circle' | 'underline', { box: [number, number]; segs: Seg[] }> = {
  // an ellipse that overshoots its own start, like a quick pen loop
  circle: {
    box: [100, 40],
    segs: [
      ['M', 14, 9],
      ['C', 40, -1, 90, 1, 96, 17],
      ['C', 101, 32, 62, 41, 30, 38],
      ['C', 5, 35, -3, 22, 8, 12],
      ['C', 15, 5, 32, 2, 48, 3],
    ],
  },
  // a single confident underline with a little lift at the end
  underline: {
    box: [100, 30],
    segs: [
      ['M', 1, 22],
      ['C', 18, 17, 36, 25, 55, 20],
      ['S', 88, 16, 99, 21],
    ],
  },
}

function scaled(kind: keyof typeof PATHS, w: number, h: number): string {
  const { box, segs } = PATHS[kind]
  const sx = w / box[0]
  const sy = h / box[1]
  return segs
    .map(([cmd, ...xy]) => cmd + ' ' + xy.map((v, i) => (i % 2 === 0 ? v * sx : v * sy).toFixed(1)).join(' '))
    .join(' ')
}

/** A red-pen mark drawn over a word when it first comes into view. */
export function PenMark({
  kind,
  children,
  delay = 250,
}: {
  kind: keyof typeof PATHS
  children: ReactNode
  delay?: number
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const seen = useInView(ref, '0px 0px -20% 0px', 0.6)
  const [size, setSize] = useState<[number, number] | null>(null)
  useLayoutEffect(() => {
    const el = svgRef.current
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      setSize([r.width, r.height])
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  // Explicit width/height: an absolutely positioned <svg> is a replaced
  // element, so left+right alone don't stretch it (it falls back to 300px).
  const box: CSSProperties =
    kind === 'circle'
      ? { left: '-9%', top: '-24%', width: '118%', height: '144%' }
      : { left: '-2%', bottom: '-0.3em', width: '104%', height: '0.34em' }
  return (
    <span ref={ref} className={`pen-mark ${seen ? 'is-in' : ''}`} style={{ position: 'relative', display: 'inline-block', ['--d' as string]: `${delay}ms` }}>
      {children}
      <svg ref={svgRef} aria-hidden viewBox={size ? `0 0 ${size[0]} ${size[1]}` : undefined} className="pointer-events-none absolute overflow-visible" style={box}>
        {size && (
          <path
            d={scaled(kind, size[0], size[1])}
            fill="none"
            stroke={RED_PEN}
            strokeWidth={kind === 'circle' ? 3 : 4}
            strokeLinecap="round"
            strokeLinejoin="round"
            pathLength={1}
          />
        )}
      </svg>
    </span>
  )
}
