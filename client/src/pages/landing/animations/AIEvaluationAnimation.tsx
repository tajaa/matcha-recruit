import { useEffect, useState } from 'react'
import { Cpu } from 'lucide-react'

// Multi-dimensional AI tool evaluation radar — 6 dimensions, 3 overlaid candidate polygons.
// Mirrors the density of RadarChart.tsx from the old landing.

type Dimension = { key: string; label: string; short: string }

const DIMENSIONS: Dimension[] = [
  { key: 'accuracy',   label: 'Accuracy',    short: 'ACC' },
  { key: 'bias',       label: 'Bias risk',   short: 'BIAS' },
  { key: 'compliance', label: 'Compliance',  short: 'CMP' },
  { key: 'cost',       label: 'Cost',        short: 'COST' },
  { key: 'latency',    label: 'Latency',     short: 'LAT' },
  { key: 'privacy',    label: 'Privacy',     short: 'PRIV' },
]

type Tool = {
  name: string
  color: string
  values: number[] // 0..1 for each dimension (order must match DIMENSIONS)
  verdict: 'recommended' | 'review' | 'reject'
}

const TOOLS: Tool[] = [
  { name: 'Aurora Copilot', color: '#86efac', values: [0.88, 0.82, 0.92, 0.62, 0.76, 0.90], verdict: 'recommended' },
  { name: 'Nexus Agents',   color: '#d7ba7d', values: [0.72, 0.55, 0.70, 0.85, 0.80, 0.60], verdict: 'review' },
  { name: 'Stratify Flow',  color: '#ce9178', values: [0.45, 0.40, 0.38, 0.78, 0.52, 0.42], verdict: 'reject' },
]

const VERDICT_LABEL = {
  recommended: 'Recommended',
  review: 'Review',
  reject: 'Reject',
}

const SIZE = 200
const CENTER = SIZE / 2
const R_MAX = 75
const N = DIMENSIONS.length

// Polar to cartesian; 0 deg = top of the chart
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

export function AIEvaluationAnimation() {
  const [revealed, setRevealed] = useState(-1) // -1 = none shown, N = all done
  const [sweepAngle, setSweepAngle] = useState(0)

  useEffect(() => {
    let cancelled = false
    let timers: number[] = []
    const clear = () => { timers.forEach((t) => window.clearTimeout(t)); timers = [] }

    const run = () => {
      if (cancelled) return
      setRevealed(-1)

      TOOLS.forEach((_, idx) => {
        timers.push(window.setTimeout(() => {
          if (cancelled) return
          setRevealed(idx)
        }, idx * STEP_MS + 500))
      })

      timers.push(window.setTimeout(() => {
        if (cancelled) return
        setRevealed(TOOLS.length)
      }, TOOLS.length * STEP_MS + 500))

      const totalMs = TOOLS.length * STEP_MS + 500 + RESET_PAUSE_MS
      timers.push(window.setTimeout(run, totalMs))
    }

    // Radar sweep — rotates continuously
    const sweepStart = performance.now()
    const sweepLoop = () => {
      if (cancelled) return
      const elapsed = performance.now() - sweepStart
      setSweepAngle((elapsed / 4000) * Math.PI * 2) // one rotation per 4s
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
          <Cpu className="w-3.5 h-3.5" style={{ color: '#9a8a70' }} />
          <span className="text-[11px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
            AI Tool Evaluation
          </span>
          <span className="text-[8.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono" style={{ color: '#d7ba7d', border: '1px solid rgba(215,186,125,0.4)' }}>
            n=3
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[9.5px]">
          <span style={{ color: '#6a737d' }}>{N} dimensions</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#86efac' }}>Pareto frontier</span>
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

            {/* Tool polygons */}
            {TOOLS.map((tool, idx) => {
              const isRevealed = revealed >= idx
              return (
                <g key={idx} style={{ opacity: isRevealed ? 1 : 0, transition: 'opacity 600ms' }}>
                  <polygon
                    points={polygonPoints(tool.values)}
                    fill={tool.color}
                    fillOpacity={0.1}
                    stroke={tool.color}
                    strokeWidth={1.2}
                    strokeLinejoin="round"
                    style={{ filter: isRevealed ? `drop-shadow(0 0 4px ${tool.color}80)` : 'none' }}
                  />
                  {/* Vertices */}
                  {tool.values.map((v, i) => {
                    const a = (i / N) * Math.PI * 2
                    const { x, y } = toXY(a, R_MAX * v)
                    return (
                      <circle
                        key={i}
                        cx={x}
                        cy={y}
                        r={1.6}
                        fill={tool.color}
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

            {/* Center dot */}
            <circle cx={CENTER} cy={CENTER} r={1} fill="#52525b" />
          </svg>
        </div>

        {/* LEGEND */}
        <div className="flex flex-col p-3 border-l min-h-0" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
          <div className="text-[8px] uppercase tracking-wider font-mono mb-2" style={{ color: '#6a737d' }}>
            Candidates
          </div>

          <div className="flex-1 flex flex-col justify-around min-h-0 gap-1.5">
            {TOOLS.map((tool, idx) => {
              const isRevealed = revealed >= idx
              const avgScore = Math.round((tool.values.reduce((a, b) => a + b, 0) / tool.values.length) * 100)
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
                        backgroundColor: tool.color,
                        boxShadow: isRevealed ? `0 0 4px ${tool.color}` : 'none',
                      }}
                    />
                    <span className="text-[9px] font-mono truncate flex-1" style={{ color: isRevealed ? '#e4ded2' : '#52525b' }}>
                      {tool.name}
                    </span>
                    <span className="text-[9px] tabular-nums font-mono" style={{ color: isRevealed ? tool.color : '#52525b' }}>
                      {isRevealed ? avgScore : '--'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1 ml-3.5">
                    <div className="flex-1 h-[2px] rounded-full" style={{ backgroundColor: 'rgba(255,255,255,0.06)' }}>
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{
                          width: isRevealed ? `${avgScore}%` : '0%',
                          backgroundColor: tool.color,
                        }}
                      />
                    </div>
                    <span
                      className="text-[7px] font-mono uppercase tracking-wider shrink-0 px-1 py-[1px] rounded"
                      style={{
                        color: tool.color,
                        border: `1px solid ${tool.color}40`,
                        opacity: isRevealed ? 1 : 0,
                      }}
                    >
                      {VERDICT_LABEL[tool.verdict]}
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
          <span style={{ color: '#6a737d' }}>Benchmark</span>
          <span className="tabular-nums" style={{ color: '#86efac' }}>1,200 tasks</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#6a737d' }}>Bias test</span>
          <span className="tabular-nums" style={{ color: '#d7ba7d' }}>StereoSet</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#6a737d' }}>Audit</span>
          <span className="tabular-nums" style={{ color: '#9a8a70' }}>SOC2 · HIPAA</span>
        </div>
      </div>
    </div>
  )
}
