import { useEffect, useRef, useState, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  rootMargin?: string
  minHeight?: number
}

export function LazyMount({ children, fallback, rootMargin = '400px', minHeight }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [shouldMount, setShouldMount] = useState(false)
  const [shown, setShown] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      setShouldMount(true)
      return
    }
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShouldMount(true)
          obs.disconnect()
        }
      },
      { rootMargin },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [rootMargin])

  useEffect(() => {
    if (!shouldMount) return
    const t = window.setTimeout(() => setShown(true), 30)
    return () => window.clearTimeout(t)
  }, [shouldMount])

  return (
    <div
      ref={ref}
      className={minHeight ? 'w-full' : 'w-full h-full'}
      style={{
        minHeight,
        opacity: shown ? 1 : 0,
        transform: shown ? 'translateY(0)' : 'translateY(8px)',
        transition: 'opacity 600ms ease, transform 600ms ease',
      }}
    >
      {shouldMount ? children : fallback}
    </div>
  )
}
