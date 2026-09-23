import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { graphPaper, PAPER } from './theme'

/** Shared chrome for an animation: the media box, then a control + caption
 *  row. Used both by the live stage and by its loading fallback, so swapping
 *  one for the other never moves anything on the page. */
export function StageLayout({
  media,
  control,
  caption,
  mediaClassName = '',
  mediaStyle,
  decor,
}: {
  media: ReactNode
  control: ReactNode
  caption?: ReactNode
  mediaClassName?: string
  mediaStyle?: CSSProperties
  decor?: ReactNode
}) {
  return (
    <div>
      <div className={`relative ${mediaClassName}`} style={mediaStyle}>
        {media}
        {decor}
      </div>
      <div className="mt-4 flex items-start gap-4">
        <div className="h-8 w-8 shrink-0">{control}</div>
        <div className="min-w-0 flex-1">{caption}</div>
      </div>
    </div>
  )
}

/** Stand-in while Remotion loads: the same blank graph-paper sheet the
 *  compositions open on, at the composition's scale, so the handoff is
 *  invisible. */
export function Poster({ width, height, cell = 16 }: { width: number; height: number; cell?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setScale(el.offsetWidth / width)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [width])
  return (
    <div
      ref={ref}
      aria-hidden
      style={{
        width: '100%',
        aspectRatio: `${width} / ${height}`,
        backgroundColor: PAPER,
        ...(scale ? graphPaper(cell * scale) : {}),
      }}
    />
  )
}
