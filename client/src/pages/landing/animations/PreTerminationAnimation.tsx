import { useEffect, useState } from 'react'
import { ShieldAlert } from 'lucide-react'

// Pre-termination risk SCREENING radar — 9 dimensions, 3 overlaid case polygons.
// Mirrors pre_termination_service.py: 9 risk dimensions, 0-100 score, bands
// low/moderate/high/critical. Higher value on an axis = MORE risk on that factor.
// This is decision SUPPORT — it screens and surfaces risk for a human reviewer;
// high/critical screens require acknowledgment. It does not decide terminations.

type Dimension = { key: string; label: string; short: string }

// The 9 real dimensions from pre_termination_service.py
const DIMENSIONS: Dimension[] = [
  { key: 'er_cases',          label: 'ER cases',          short: 'ER'     },
  { key: 'ir_involvement',    label: 'IR involvement',    short: 'IR'     },
  { key: 'leave_status',      label: 'Leave status',      short: 'LEAVE'  },
  { key: 'protected_activity',label: 'Protected activity',short: 'PROT'   },
  { key: 'documentation',     label: 'Documentation',     short: 'DOCS'   },
  { key: 'tenure_timing',     label: 'Tenure / timing',   short: 'TENURE' },
  { key: 'consistency',       label: 'Consistency',       short: 'CONS'   },
  { key: 'manager_profile',   label: 'Manager profile',   short: 'MGR'    },
  { key: 'retaliation_risk',  label: 'Retaliation risk',  short: 'RETAL'  },
]

type Band = 'low' | 'moderate' | 'high' | 'critical'

type Case = {
  name: string
  color: string
  values: number[] // 0..1 risk per dimension (order matches DIMENSIONS); higher = riskier
  band: Band
}

// Values are RISK magnitudes (higher = more risk). Critical case spikes on
// retaliation / protected activity / open ER cases.
const CASES: Case[] = [
  { name: 'Case #A247', color: '#86efac', values: [0.10, 0.05, 0.00, 0.05, 0.15, 0.20, 0.10, 0.10, 0.08], band: 'low'      },
  { name: 'Case #B183', color: '#d7ba7d', values: [0.45, 0.30, 0.55, 0.40, 0.60, 0.35, 0.50, 0.45, 0.42], band: 'high'     },
  { name: 'Case #C391', color: '#ce9178', values: [0.85, 0.70, 0.65, 0.92, 0.55, 0.40, 0.60, 0.50, 0.95], band: 'critical' },
]

const BAND_LABEL: Record<Band, string> = {
  low: 'Low', moderate: 'Moderate', high: 'High', critical: 'Critical',
}

const SIZE = 200
const CENTER = SIZE / 2
const R_MAX = 75
const N = DIMENSIONS.length

function toXY(angleRad: number, radius: number): { x: number; y: number } {
  return {
    x: CENTER + Math.sin(angleRad) * radius,
    y: CENTER - Math.cos(angleRad) * radius,
  }
}

function polygonPoints(values: number[]): string {
  return values
    .map((v, i) => {
      const a = (i / N) * Math.PI * 2
      const { x, y } = toXY(a, R_MAX * v)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

const STEP_MS = 1000
const RESET_PAUSE_MS = 2500

export function PreTerminationAnimation() {
  const [revealed, setRevealed] = useState(-1)
  const [sweepAngle, setSweepAngle] = useState(0)

  useEffect(() => {
    let cancelled = false
    let timers: number[] = []
    const clear = () => { timers.forEach((t) => window.clearTimeout(t)); timers = [] }

    const run = () => {
      if (cancelled) return
      setRevealed(-1)

      CASES.forEach((_, idx) => {
        timers.push(window.setTimeout(() => {
          if (cancelled) return
          setRevealed(idx)
        }, idx * STEP_MS + 500))
      })

      timers.push(window.setTimeout(() => {
        if (cancelled) return
        setRevealed(CASES.length)
      }, CASES.length * STEP_MS + 500))

      const totalMs = CASES.length * STEP_MS + 500 + RESET_PAUSE_MS
      timers.push(window.setTimeout(run, totalMs))
    }

    const sweepStart = performance.now()
    const sweepLoop = () => {
      if (cancelled) return
      const elapsed = performance.now() - sweepStart
      setSweepAngle((elapsed / 4000) * Math.PI * 2)
      timers.push(window.setTimeout(sweepLoop, 32))
    }
    sweepLoop()

    run()
    return () => { cancelled = true; clear() }
  }, [])

  return (
    <div className="w-full h-full flex flex-col relative" style={{ backgroundColor: '#0e0d0b', color: '#d4d4d4' }}>
      {/* Grid bg */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.08]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
        }}
      />

      {/* Header */}
      <div className="relative flex items-center justify-between px-4 py-2.5 border-b shrink-0" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-3.5 h-3.5" style={{ color: '#9a8a70' }} />
          <span className="text-[11px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
            Pre-Termination Screening
          </span>
          <span className="text-[8.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono" style={{ color: '#d7ba7d', border: '1px solid rgba(215,186,125,0.4)' }}>
            Decision support
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[9.5px]">
          <span style={{ color: '#6a737d' }}>{N} dimensions</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#86efac' }}>For human review</span>
        </div>
      </div>

      {/* Body: radar (left) + legend (right) */}
      <div className="relative flex-1 grid grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] min-h-0">
        {/* RADAR */}
        <div className="relative flex items-center justify-center p-2 min-h-0 overflow-hidden">
          <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} className="max-w-full max-h-full">
            <defs>
              <radialGradient id="sweepGrad" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#d7ba7d" stopOpacity="0.3" />
                <stop offset="100%" stopColor="#d7ba7d" stopOpacity="0" />
              </radialGradient>
            </defs>

            {/* Concentric rings */}
            {[0.25, 0.5, 0.75, 1].map((scale, si) => (
              <polygon
                key={si}
                points={DIMENSIONS.map((_, i) => {
                  const a = (i / N) * Math.PI * 2
                  const { x, y } = toXY(a, R_MAX * scale)
                  return `${x},${y}`
                }).join(' ')}
                fill="none"
                stroke={si === 3 ? 'rgba(215,186,125,0.45)' : 'rgba(255,255,255,0.08)'}
                strokeDasharray={si === 3 ? '' : '2 2'}
                strokeWidth={si === 3 ? 1 : 0.5}
              />
            ))}

            {/* Spokes */}
            {DIMENSIONS.map((_, i) => {
              const a = (i / N) * Math.PI * 2
              const { x, y } = toXY(a, R_MAX)
              return (
                <line
                  key={i}
                  x1={CENTER}
                  y1={CENTER}
                  x2={x}
                  y2={y}
                  stroke="rgba(255,255,255,0.06)"
                  strokeWidth={0.5}
                  strokeDasharray="1 2"
                />
              )
            })}

            {/* Rotating sweep */}
            <g transform={`rotate(${(sweepAngle * 180) / Math.PI} ${CENTER} ${CENTER})`}>
              <path
                d={`M ${CENTER} ${CENTER} L ${CENTER} ${CENTER - R_MAX} A ${R_MAX} ${R_MAX} 0 0 1 ${CENTER + R_MAX * Math.sin(Math.PI / 3)} ${CENTER - R_MAX * Math.cos(Math.PI / 3)} Z`}
                fill="url(#sweepGrad)"
                opacity={0.6}
              />
            </g>

            {/* Case polygons */}
            {CASES.map((c, idx) => {
              const isRevealed = revealed >= idx
              return (
                <g key={idx} style={{ opacity: isRevealed ? 1 : 0, transition: 'opacity 600ms' }}>
                  <polygon
                    points={polygonPoints(c.values)}
                    fill={c.color}
                    fillOpacity={0.1}
                    stroke={c.color}
                    strokeWidth={1.2}
                    strokeLinejoin="round"
                    style={{ filter: isRevealed ? `drop-shadow(0 0 4px ${c.color}80)` : 'none' }}
                  />
                  {c.values.map((v, i) => {
                    const a = (i / N) * Math.PI * 2
                    const { x, y } = toXY(a, R_MAX * v)
                    return (
                      <circle
                        key={i}
                        cx={x}
                        cy={y}
                        r={1.6}
                        fill={c.color}
                        stroke="#0e0d0b"
                        strokeWidth={0.5}
                      />
                    )
                  })}
                </g>
              )
            })}

            {/* Dimension labels */}
            {DIMENSIONS.map((dim, i) => {
              const a = (i / N) * Math.PI * 2
              const { x, y } = toXY(a, R_MAX + 14)
              return (
                <text
                  key={i}
                  x={x}
                  y={y}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize={7}
                  fontFamily="ui-monospace, monospace"
                  fill="#9a8a70"
                  style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}
                >
                  {dim.short}
                </text>
              )
            })}

            <circle cx={CENTER} cy={CENTER} r={1} fill="#52525b" />
          </svg>
        </div>

        {/* LEGEND */}
        <div className="flex flex-col p-3 border-l min-h-0" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
          <div className="text-[8px] uppercase tracking-wider font-mono mb-2" style={{ color: '#6a737d' }}>
            Reviews
          </div>

          <div className="flex-1 flex flex-col justify-around min-h-0 gap-1.5">
            {CASES.map((c, idx) => {
              const isRevealed = revealed >= idx
              const avgScore = Math.round((c.values.reduce((a, b) => a + b, 0) / c.values.length) * 100)
              return (
                <div
                  key={idx}
                  className="transition-all duration-500"
                  style={{ opacity: isRevealed ? 1 : 0.25 }}
                >
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span
                      className="w-2 h-2 rounded-sm shrink-0"
                      style={{
                        backgroundColor: c.color,
                        boxShadow: isRevealed ? `0 0 4px ${c.color}` : 'none',
                      }}
                    />
                    <span className="text-[9px] font-mono truncate flex-1" style={{ color: isRevealed ? '#e4ded2' : '#52525b' }}>
                      {c.name}
                    </span>
                    <span className="text-[9px] tabular-nums font-mono" style={{ color: isRevealed ? c.color : '#52525b' }}>
                      {isRevealed ? avgScore : '--'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1 ml-3.5">
                    <div className="flex-1 h-[2px] rounded-full" style={{ backgroundColor: 'rgba(255,255,255,0.06)' }}>
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{
                          width: isRevealed ? `${avgScore}%` : '0%',
                          backgroundColor: c.color,
                        }}
                      />
                    </div>
                    <span
                      className="text-[7px] font-mono uppercase tracking-wider shrink-0 px-1 py-[1px] rounded"
                      style={{
                        color: c.color,
                        border: `1px solid ${c.color}40`,
                        opacity: isRevealed ? 1 : 0,
                      }}
                    >
                      {BAND_LABEL[c.band]}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="relative px-4 py-2 border-t flex items-center justify-between shrink-0 font-mono text-[8.5px]" style={{ borderColor: 'rgba(255,255,255,0.08)', backgroundColor: 'rgba(255,255,255,0.015)' }}>
        <div className="flex items-center gap-3">
          <span style={{ color: '#6a737d' }}>Dimensions</span>
          <span className="tabular-nums" style={{ color: '#86efac' }}>{N} screened</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#9a8a70' }}>Screening — not legal advice</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#6a737d' }}>Critical</span>
          <span className="tabular-nums" style={{ color: '#ce9178' }}>1 → ack required</span>
        </div>
      </div>
    </div>
  )
}
