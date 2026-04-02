import { useRef } from 'react'
import { useInView } from 'framer-motion'
import { SCAN_LINE_BG, RADAR_DIMS, RADAR_VALUES } from './shared'

/* ── 9-Dimension Radar (Pre-Termination Intel) ────────────────── */
export function RadarChart() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const cx = 50, cy = 50, r = 35

  const toXY = (angle: number, radius: number) => ({
    x: cx + Math.cos(angle - Math.PI / 2) * radius,
    y: cy + Math.sin(angle - Math.PI / 2) * radius,
  })

  const polygon = RADAR_VALUES.map((v, i) => {
    const angle = (i / RADAR_DIMS.length) * Math.PI * 2
    const p = toXY(angle, r * v)
    return `${p.x},${p.y}`
  }).join(' ')

  return (
    <div ref={ref} className="relative h-72 lg:h-80 flex items-center justify-center overflow-hidden"
      style={{ backgroundImage: SCAN_LINE_BG }}
    >
      <svg viewBox="0 0 100 100" className="w-64 h-64 lg:w-72 lg:h-72">
        {/* Concentric rings */}
        {[0.25, 0.5, 0.75, 1].map(scale => (
          <polygon
            key={scale}
            points={RADAR_DIMS.map((_, i) => {
              const a = (i / RADAR_DIMS.length) * Math.PI * 2
              const p = toXY(a, r * scale)
              return `${p.x},${p.y}`
            }).join(' ')}
            fill="none"
            stroke="#3f3f46"
            strokeWidth="0.3"
          />
        ))}

        {/* Axes */}
        {RADAR_DIMS.map((_, i) => {
          const a = (i / RADAR_DIMS.length) * Math.PI * 2
          const p = toXY(a, r)
          return <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="#3f3f46" strokeWidth="0.2" />
        })}

        {/* Data polygon */}
        <polygon
          points={polygon}
          fill="rgba(245,158,11,0.1)"
          stroke="#f59e0b"
          strokeWidth="0.6"
          strokeLinejoin="round"
          style={{
            opacity: inView ? 1 : 0,
            transition: 'opacity 1.2s ease',
            transitionDelay: '0.3s',
          }}
        >
          <animate attributeName="stroke-opacity" values="1;0.5;1" dur="3s" repeatCount="indefinite" />
        </polygon>

        {/* Data points */}
        {RADAR_VALUES.map((v, i) => {
          const a = (i / RADAR_DIMS.length) * Math.PI * 2
          const p = toXY(a, r * v)
          return (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r="1"
              fill={v > 0.7 ? '#ef4444' : '#f59e0b'}
              style={{
                opacity: inView ? 1 : 0,
                transition: 'opacity 0.5s',
                transitionDelay: `${i * 100 + 800}ms`,
              }}
            >
              {v > 0.7 && <animate attributeName="r" values="1;1.8;1" dur="2s" repeatCount="indefinite" />}
            </circle>
          )
        })}

        {/* Labels */}
        {RADAR_DIMS.map((label, i) => {
          const a = (i / RADAR_DIMS.length) * Math.PI * 2
          const p = toXY(a, r + 8)
          return (
            <text
              key={label}
              x={p.x}
              y={p.y}
              textAnchor="middle"
              dominantBaseline="middle"
              className=""
              style={{
                fontSize: '2.5px',
                fill: RADAR_VALUES[i] > 0.7 ? '#ef4444' : '#71717a',
                opacity: inView ? 1 : 0,
                transition: 'opacity 0.5s',
                transitionDelay: `${i * 100 + 600}ms`,
              }}
            >
              {label}
            </text>
          )
        })}
      </svg>

      {/* Risk score */}
      <div
        className="absolute top-3 right-3 text-right transition-opacity duration-700"
        style={{ opacity: inView ? 1 : 0, transitionDelay: '1.5s' }}
      >
        <div className="text-[8px] text-zinc-500 uppercase">Risk Score</div>
        <div className="text-lg font-[Orbitron] font-bold text-amber-500">72</div>
        <div className="text-[8px] text-red-400/60 uppercase">HIGH</div>
      </div>
    </div>
  )
}