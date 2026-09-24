import type { CSSProperties, ReactNode } from 'react'
import { PAPER } from './theme'

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

/** Stand-in while Remotion loads: the same blank surface the composition
 *  opens on (plain paper unless `surface` says otherwise), so the handoff is
 *  invisible. */
export function Poster({ width, height, surface }: { width: number; height: number; surface?: CSSProperties }) {
  return <div aria-hidden style={{ width: '100%', aspectRatio: `${width} / ${height}`, ...(surface ?? { backgroundColor: PAPER }) }} />
}
