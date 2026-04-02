import { useRef } from 'react'
import { useInView } from 'framer-motion'
import { SCAN_LINE_BG, PATTERN_INCIDENTS } from './shared'

/* ── Pattern Grid (Incident Reports) ──────────────────────────── */
export function PatternGrid() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const rows = 7
  const cols = 10
  const epicenter = 33

  return (
    <div ref={ref} className="relative h-72 lg:h-80 flex items-center justify-center overflow-hidden"
      style={{ backgroundImage: SCAN_LINE_BG }}
    >
      <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
        {Array.from({ length: rows * cols }, (_, i) => {
          const row = Math.floor(i / cols)
          const col = i % cols
          const epicRow = Math.floor(epicenter / cols)
          const epicCol = epicenter % cols
          const dist = Math.sqrt((row - epicRow) ** 2 + (col - epicCol) ** 2)
          const isIncident = PATTERN_INCIDENTS.has(i)

          return (
            <div
              key={i}
              className="relative h-3 w-3 rounded-full transition-all"
              style={{
                backgroundColor: isIncident
                  ? inView ? '#f59e0b' : '#27272a'
                  : inView ? '#3f3f46' : '#27272a',
                opacity: inView ? 1 : 0,
                transform: inView ? 'scale(1)' : 'scale(0)',
                transitionDuration: '500ms',
                transitionDelay: `${dist * 80 + 200}ms`,
                boxShadow: isIncident && inView ? '0 0 8px rgba(245,158,11,0.4)' : 'none',
                animation: isIncident && inView ? `pulse 2.5s ${dist * 0.15}s infinite` : 'none',
              }}
            />
          )
        })}
      </div>

      {/* Ripple rings from epicenter */}
      {inView && [1, 2, 3].map(ring => (
        <div
          key={ring}
          className="absolute rounded-full border border-amber-500/20 pointer-events-none"
          style={{
            width: `${ring * 80}px`,
            height: `${ring * 80}px`,
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
            animation: `ripple-expand 3s ${ring * 0.6}s infinite`,
          }}
        />
      ))}

      <div className="absolute bottom-3 right-3 text-[8px] text-amber-500/50 uppercase">
        {PATTERN_INCIDENTS.size} Incidents // Pattern Detected
      </div>
    </div>
  )
}