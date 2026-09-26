import type { CSSProperties } from 'react'
import { BODY, INK, MONO, hexA } from './theme'

/** Frosted glass (Change chat, Check report, Publish): translucent white with
 *  a white inner rim over the section's glows. `glassChip` is the brighter
 *  pane that sits on top of a `glassPane`. */
export const GLASS_RIM = 'rgba(255, 255, 255, 0.85)'
export const glassPane: CSSProperties = {
  backgroundColor: 'rgba(255, 255, 255, 0.5)',
  backdropFilter: 'blur(28px) saturate(1.5)',
  WebkitBackdropFilter: 'blur(28px) saturate(1.5)',
  boxShadow: `inset 0 0 0 1px ${GLASS_RIM}, 0 0 0 1px ${hexA(INK, 0.05)}, 0 40px 80px -48px ${hexA(INK, 0.3)}`,
}
export const glassChip: CSSProperties = {
  backgroundColor: 'rgba(255, 255, 255, 0.7)',
  boxShadow: `inset 0 0 0 1px ${GLASS_RIM}, 0 0 0 1px ${hexA(INK, 0.04)}`,
}

/** Page container: 1320 max, 16px phone gutter. */
export const WRAP = 'mx-auto w-full max-w-[1320px] px-4 sm:px-8 lg:px-12'

export const mono = (size: string, extra?: CSSProperties): CSSProperties => ({
  fontFamily: MONO,
  fontSize: size,
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  ...extra,
})

/** Headline type: a tight, medium-weight grotesk. */
export const display: CSSProperties = {
  fontFamily: BODY,
  fontWeight: 500,
  lineHeight: 1,
  letterSpacing: '-0.04em',
}
