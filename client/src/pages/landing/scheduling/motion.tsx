import { useRef, type CSSProperties, type ReactNode } from 'react'
import { useInView } from './hooks'

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
