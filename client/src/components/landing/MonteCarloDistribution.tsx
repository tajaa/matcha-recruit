import { useRef } from 'react'
import { useInView } from 'framer-motion'
import { SCAN_LINE_BG } from './shared'

/* ── Monte Carlo Distribution (Risk Assessment) ──────────────── */
export function MonteCarloDistribution() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const barCount = 24
  const heights = Array.from({ length: barCount }, (_, i) => {
    const x = (i - barCount / 2) / (barCount / 4)
    return Math.exp(-0.5 * x * x) * 100
  })
  const maxH = Math.max(...heights)

  return (
    <div ref={ref} className="relative h-72 lg:h-80 overflow-hidden flex items-end justify-center gap-[3px] px-8 pb-10 pt-6"
      style={{ backgroundImage: SCAN_LINE_BG }}
    >
      {/* Threshold line */}
      <div
        className="absolute left-0 right-0 border-t border-dashed transition-opacity duration-1000"
        style={{
          top: '28%',
          borderColor: 'rgba(239,68,68,0.4)',
          opacity: inView ? 1 : 0,
          transitionDelay: '1.2s',
        }}
      >
        <span className="absolute right-2 -top-4 text-[8px] text-red-400/60 uppercase">
          Critical Threshold
        </span>
      </div>

      {heights.map((h, i) => {
        const pct = (h / maxH) * 70
        const hue = pct > 55 ? 0 : pct > 35 ? 38 : 160
        return (
          <div
            key={i}
            className="flex-1 max-w-3 transition-all rounded-t-[1px]"
            style={{
              height: inView ? `${pct}%` : '0%',
              background: `hsl(${hue}, 70%, ${45 + (pct / 70) * 15}%)`,
              opacity: inView ? 0.85 : 0,
              transitionDuration: '800ms',
              transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)',
              transitionDelay: `${i * 40 + 200}ms`,
              boxShadow: pct > 55 ? `0 0 8px hsla(${hue}, 70%, 50%, 0.3)` : 'none',
            }}
          />
        )
      })}

      {/* Axis labels */}
      <div className="absolute bottom-2 left-8 right-8 flex justify-between text-[7px] text-zinc-600">
        <span>$0</span>
        <span>ANNUAL LOSS EXPOSURE</span>
        <span>$5M+</span>
      </div>

      {/* Stats overlay */}
      <div
        className="absolute top-3 left-3 flex flex-col gap-1 transition-opacity duration-700"
        style={{ opacity: inView ? 1 : 0, transitionDelay: '1.5s' }}
      >
        <span className="text-[8px] text-emerald-500/70">P50: $142,000</span>
        <span className="text-[8px] text-amber-500/70">P90: $890,000</span>
        <span className="text-[8px] text-red-400/70">P99: $2.4M</span>
      </div>
    </div>
  )
}