import type { CSSProperties } from 'react'
import { DISPLAY, MONO } from './theme'

/** Page container: 1320 max, 16px phone gutter. */
export const WRAP = 'mx-auto w-full max-w-[1320px] px-4 sm:px-8 lg:px-12'

export const mono = (size: string, extra?: CSSProperties): CSSProperties => ({
  fontFamily: MONO,
  fontSize: size,
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  ...extra,
})

export const display: CSSProperties = {
  fontFamily: DISPLAY,
  fontWeight: 800,
  textTransform: 'uppercase',
  lineHeight: 0.88,
  letterSpacing: '-0.005em',
}

/** The Sunday afternoon the week gets built — every section is one step of it,
 *  in order, ending at the 4:12 PM publish the hero animation stamps. */
export const STEPS = [
  { id: 'draft', time: '2:00', label: 'Draft' },
  { id: 'check', time: '3:40', label: 'Check' },
  { id: 'change', time: '3:58', label: 'Change' },
  { id: 'cost', time: '4:05', label: 'Cost' },
  { id: 'publish', time: '4:12', label: 'Publish' },
] as const

export type StepId = (typeof STEPS)[number]['id']
