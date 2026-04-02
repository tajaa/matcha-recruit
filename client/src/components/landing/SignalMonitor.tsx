import { useRef, useEffect, useState } from 'react'
import { useInView } from 'framer-motion'
import { SCAN_LINE_BG, SIGNAL_WAVE_1, SIGNAL_WAVE_2, SIGNAL_WAVE_3 } from './shared'

/* ── Signal Monitor (Legislative Tracker) ─────────────────────── */
export function SignalMonitor() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-80px' })
  const [scanX, setScanX] = useState(0)

  useEffect(() => {
    if (!inView) return
    let raf: number
    const animate = () => {
      setScanX(prev => (prev + 0.3) % 100)
      raf = requestAnimationFrame(animate)
    }
    raf = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf)
  }, [inView])

  return (
    <div ref={ref} className="relative h-72 lg:h-80 overflow-hidden" style={{ backgroundImage: SCAN_LINE_BG }}>
      <svg className="absolute inset-0 w-full h-full" viewBox="0 0 100 100" preserveAspectRatio="none">
        {/* Background grid */}
        {[20, 40, 60, 80].map(y => (
          <line key={`h${y}`} x1="0" y1={y} x2="100" y2={y} stroke="#3f3f46" strokeWidth="0.15" />
        ))}
        {[20, 40, 60, 80].map(x => (
          <line key={`v${x}`} x1={x} y1="0" x2={x} y2="100" stroke="#3f3f46" strokeWidth="0.15" />
        ))}

        {/* Waveforms */}
        <polyline
          points={SIGNAL_WAVE_1}
          fill="none"
          stroke="#f59e0b"
          strokeWidth="0.4"
          opacity={inView ? 0.6 : 0}
          style={{ transition: 'opacity 1s' }}
        >
          <animateTransform attributeName="transform" type="translate" from="-2,0" to="2,0" dur="3s" repeatCount="indefinite" />
        </polyline>
        <polyline
          points={SIGNAL_WAVE_2}
          fill="none"
          stroke="#d97706"
          strokeWidth="0.3"
          opacity={inView ? 0.35 : 0}
          style={{ transition: 'opacity 1.2s' }}
        >
          <animateTransform attributeName="transform" type="translate" from="1,0" to="-1,0" dur="4s" repeatCount="indefinite" />
        </polyline>
        <polyline
          points={SIGNAL_WAVE_3}
          fill="none"
          stroke="#fbbf24"
          strokeWidth="0.25"
          opacity={inView ? 0.2 : 0}
          style={{ transition: 'opacity 1.5s' }}
        >
          <animateTransform attributeName="transform" type="translate" from="-1,0" to="1,0" dur="5s" repeatCount="indefinite" />
        </polyline>

        {/* Scanline */}
        <line
          x1={scanX} y1="0" x2={scanX} y2="100"
          stroke="#f59e0b" strokeWidth="0.3" opacity="0.5"
        />
        <circle cx={scanX} cy={50 + Math.sin(scanX * 0.15) * 15} r="1.2" fill="#f59e0b" opacity="0.8">
          <animate attributeName="r" values="1.2;2;1.2" dur="0.8s" repeatCount="indefinite" />
        </circle>

        {/* Alert blips */}
        {[25, 58, 82].map((x, i) => (
          <g key={i}>
            <circle cx={x} cy={50 + Math.sin(x * 0.2 + i) * 12} r="0.8" fill="#f59e0b" opacity="0.9">
              <animate attributeName="opacity" values="0.9;0.3;0.9" dur={`${1.5 + i * 0.3}s`} repeatCount="indefinite" />
            </circle>
            <circle cx={x} cy={50 + Math.sin(x * 0.2 + i) * 12} r="2.5" fill="none" stroke="#f59e0b" strokeWidth="0.2" opacity="0.3">
              <animate attributeName="r" values="2.5;5;2.5" dur={`${1.5 + i * 0.3}s`} repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.3;0;0.3" dur={`${1.5 + i * 0.3}s`} repeatCount="indefinite" />
            </circle>
          </g>
        ))}
      </svg>

      <div className="absolute bottom-3 left-3 text-[8px] text-amber-500/50 uppercase">
        Regulatory Signal // {inView ? 'Monitoring' : 'Standby'}
      </div>
    </div>
  )
}