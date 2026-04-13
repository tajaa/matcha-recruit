import { useEffect, useState } from 'react'
import { Activity } from 'lucide-react'

// Mirrors risk_assessment_service.py (5 weighted dims + Monte Carlo loss distribution).
// Weights match the seeded risk_assessment_weights in database.py.

type Band = 'low' | 'moderate' | 'high' | 'critical'
type Dimension = { key: string; label: string; target: number; weight: number }

const DIMENSIONS: Dimension[] = [
  { key: 'compliance',  label: 'Compliance',  target: 72, weight: 0.30 },
  { key: 'incidents',   label: 'Incidents',   target: 58, weight: 0.25 },
  { key: 'er_cases',    label: 'ER Cases',    target: 62, weight: 0.25 },
  { key: 'workforce',   label: 'Workforce',   target: 81, weight: 0.15 },
  { key: 'legislative', label: 'Legislative', target: 45, weight: 0.05 },
]

function getBand(score: number): Band {
  if (score <= 25) return 'low'
  if (score <= 50) return 'moderate'
  if (score <= 75) return 'high'
  return 'critical'
}

const BAND_COLOR: Record<Band, string> = {
  low: '#86efac', moderate: '#9a8a70', high: '#d7ba7d', critical: '#ce9178',
}
const BAND_LABEL: Record<Band, string> = { low: 'Low', moderate: 'Moderate', high: 'High', critical: 'Critical' }

// Lognormal-ish loss distribution heights for histogram bars
const BAR_COUNT = 22
function lognormalHeight(i: number): number {
  const x = (i + 0.5) / BAR_COUNT
  const mu = Math.log(0.35)
  const sigma = 0.55
  const lnx = Math.log(Math.max(x, 0.001))
  const density = Math.exp(-Math.pow(lnx - mu, 2) / (2 * sigma * sigma)) / (x * sigma * Math.sqrt(2 * Math.PI))
  return density
}
const RAW_HEIGHTS = Array.from({ length: BAR_COUNT }, (_, i) => lognormalHeight(i))
const MAX_HEIGHT = Math.max(...RAW_HEIGHTS)
const HEIGHTS = RAW_HEIGHTS.map((h) => h / MAX_HEIGHT)

const P50_IDX = 6
const P90_IDX = 14
const P99_IDX = 19

const STEP_MS = 850
const RESET_PAUSE_MS = 2600
const MC_TARGET = 10000
const MC_TICKS = 45

export function RiskAssessmentAnimation() {
  const [scanned, setScanned] = useState(-1)
  const [scores, setScores] = useState<number[]>(() => DIMENSIONS.map(() => 0))
  const [iteration, setIteration] = useState(0)
  const [histProgress, setHistProgress] = useState(0) // 0..1
  const [scanX, setScanX] = useState(-10)

  useEffect(() => {
    let cancelled = false
    let timers: number[] = []
    const clear = () => { timers.forEach((t) => window.clearTimeout(t)); timers = [] }

    const tickScore = (idx: number, target: number, durationMs: number) => {
      const start = performance.now()
      const loop = () => {
        if (cancelled) return
        const elapsed = performance.now() - start
        const t = Math.min(1, elapsed / durationMs)
        const eased = 1 - Math.pow(1 - t, 2)
        setScores((prev) => { const n = [...prev]; n[idx] = Math.round(eased * target); return n })
        if (t < 1) timers.push(window.setTimeout(loop, 16))
      }
      loop()
    }

    const tickHistogram = (durationMs: number) => {
      const start = performance.now()
      const loop = () => {
        if (cancelled) return
        const elapsed = performance.now() - start
        const t = Math.min(1, elapsed / durationMs)
        const eased = 1 - Math.pow(1 - t, 3)
        setHistProgress(eased)
        if (t < 1) timers.push(window.setTimeout(loop, 16))
      }
      loop()
    }

    const scanSweep = () => {
      if (cancelled) return
      setScanX(-10)
      const start = performance.now()
      const dur = 1400
      const loop = () => {
        if (cancelled) return
        const elapsed = performance.now() - start
        const t = Math.min(1, elapsed / dur)
        setScanX(-10 + t * 120)
        if (t < 1) timers.push(window.setTimeout(loop, 16))
      }
      loop()
    }

    const run = () => {
      if (cancelled) return
      setScanned(-1); setScores(DIMENSIONS.map(() => 0)); setIteration(0); setHistProgress(0)

      DIMENSIONS.forEach((d, idx) => {
        timers.push(window.setTimeout(() => {
          if (cancelled) return
          setScanned(idx)
          tickScore(idx, d.target, 550)
        }, idx * STEP_MS + 350))
      })

      const totalDuration = DIMENSIONS.length * STEP_MS + 500
      timers.push(window.setTimeout(() => tickHistogram(totalDuration - 400), 300))

      const iterStart = 350
      const iterEnd = totalDuration
      for (let i = 0; i <= MC_TICKS; i++) {
        const at = iterStart + ((iterEnd - iterStart) * i) / MC_TICKS
        timers.push(window.setTimeout(() => {
          if (cancelled) return
          setIteration(Math.round((MC_TARGET * i) / MC_TICKS))
        }, at))
      }

      // Scan sweeps periodically during the run
      timers.push(window.setTimeout(scanSweep, 1200))
      timers.push(window.setTimeout(scanSweep, 2800))

      timers.push(window.setTimeout(() => {
        if (cancelled) return
        setScanned(DIMENSIONS.length)
      }, DIMENSIONS.length * STEP_MS + 700))

      const totalMs = DIMENSIONS.length * STEP_MS + 700 + RESET_PAUSE_MS
      timers.push(window.setTimeout(run, totalMs))
    }

    run()
    return () => { cancelled = true; clear() }
  }, [])

  const overallScore = Math.round(DIMENSIONS.reduce((acc, d, i) => acc + scores[i] * d.weight, 0))
  const complete = scanned >= DIMENSIONS.length
  const band = getBand(overallScore)
  const bandColor = BAND_COLOR[band]

  return (
    <div className="w-full h-full flex flex-col relative" style={{ backgroundColor: '#0e0d0b', color: '#d4d4d4' }}>
      {/* Grid background */}
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
          <Activity className="w-3.5 h-3.5" style={{ color: '#9a8a70' }} />
          <span className="text-[11px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
            Risk Assessment Engine
          </span>
          <span className="text-[8.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono" style={{ color: '#d7ba7d', border: '1px solid rgba(215,186,125,0.4)' }}>
            Live
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[9.5px]">
          <span style={{ color: '#6a737d' }}>MC iter</span>
          <span className="tabular-nums" style={{ color: '#d7ba7d' }}>{iteration.toLocaleString()}</span>
          <span style={{ color: '#3f3f46' }}>/</span>
          <span className="tabular-nums" style={{ color: '#6a737d' }}>{MC_TARGET.toLocaleString()}</span>
        </div>
      </div>

      {/* Body: left (dims + score) | right (MC histogram) */}
      <div className="relative flex-1 grid grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] min-h-0">
        {/* LEFT: 5-dim + overall */}
        <div className="flex flex-col p-3 border-r min-h-0" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
          {/* Overall score header */}
          <div className="flex items-baseline justify-between mb-2">
            <div className="flex items-baseline gap-1.5">
              <span className="text-[8px] uppercase tracking-wider font-mono" style={{ color: '#6a737d' }}>Overall</span>
              <span className="font-light font-mono leading-none tabular-nums transition-colors duration-500" style={{ color: complete ? bandColor : '#e4ded2', fontSize: '28px' }}>
                {overallScore || '—'}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full transition-colors duration-500" style={{ backgroundColor: bandColor }} />
              <span className="text-[8.5px] uppercase tracking-wider font-mono" style={{ color: bandColor }}>
                {complete ? BAND_LABEL[band] : 'Scanning'}
              </span>
            </div>
          </div>

          {/* Weighted score bar */}
          <div className="h-[2px] rounded-full mb-3" style={{ backgroundColor: 'rgba(255,255,255,0.06)' }}>
            <div className="h-full rounded-full transition-all duration-500" style={{ width: `${overallScore}%`, backgroundColor: bandColor, boxShadow: `0 0 6px ${bandColor}80` }} />
          </div>

          {/* Dimension rows */}
          <div className="flex-1 flex flex-col justify-around gap-[3px] min-h-0">
            {DIMENSIONS.map((d, idx) => {
              const s = scores[idx]
              const active = scanned === idx && !complete
              const started = s > 0 || active
              const dColor = s > 0 ? BAND_COLOR[getBand(s)] : '#3f3f46'
              return (
                <div key={d.key} className="flex items-center gap-2">
                  <span className="w-[58px] text-[8.5px] font-mono shrink-0 truncate uppercase tracking-wide" style={{ color: active ? '#e4ded2' : started ? '#9a8a70' : '#6a737d' }}>
                    {d.label}
                  </span>
                  <div className="flex-1 h-[3px] rounded-full" style={{ backgroundColor: 'rgba(255,255,255,0.06)' }}>
                    <div className="h-full rounded-full transition-all duration-200" style={{ width: `${s}%`, backgroundColor: dColor }} />
                  </div>
                  <span className="text-[8.5px] tabular-nums font-mono w-5 text-right shrink-0" style={{ color: started ? '#d4d4d4' : '#3f3f46' }}>
                    {s > 0 ? s : '—'}
                  </span>
                  <span className="text-[7px] tabular-nums font-mono w-6 text-right shrink-0" style={{ color: '#52525b' }}>
                    ×{d.weight.toFixed(2)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        {/* RIGHT: Monte Carlo histogram */}
        <div className="flex flex-col p-3 relative overflow-hidden min-h-0">
          {/* Chart header */}
          <div className="flex items-center justify-between mb-2">
            <span className="text-[8px] uppercase tracking-wider font-mono" style={{ color: '#6a737d' }}>
              Loss Distribution
            </span>
            <div className="flex gap-2 font-mono text-[8px]">
              <span style={{ color: '#86efac' }}>P50</span>
              <span style={{ color: '#d7ba7d' }}>P90</span>
              <span style={{ color: '#ce9178' }}>P99</span>
            </div>
          </div>

          {/* Histogram area */}
          <div className="flex-1 relative min-h-0">
            {/* Y-axis tick lines */}
            {[0.25, 0.5, 0.75, 1].map((y) => (
              <div key={y} className="absolute left-0 right-0 border-t" style={{ bottom: `${y * 100}%`, borderColor: 'rgba(255,255,255,0.04)', borderStyle: y === 1 ? 'solid' : 'dashed' }} />
            ))}

            {/* Bars */}
            <div className="absolute inset-0 flex items-end gap-[2px]">
              {HEIGHTS.map((h, i) => {
                const visible = histProgress * BAR_COUNT >= i
                const isTail = i >= P99_IDX
                const isWarn = i >= P90_IDX && i < P99_IDX
                const color = isTail ? '#ce9178' : isWarn ? '#d7ba7d' : '#52525b'
                const barH = visible ? h * 100 : 0
                return (
                  <div key={i} className="flex-1 relative">
                    <div
                      className="absolute bottom-0 left-0 right-0 transition-all duration-300"
                      style={{
                        height: `${barH}%`,
                        backgroundColor: color,
                        opacity: isTail ? 0.9 : isWarn ? 0.75 : 0.55,
                        boxShadow: isTail && visible ? `0 0 8px ${color}` : 'none',
                      }}
                    />
                  </div>
                )
              })}
            </div>

            {/* Reference lines: P50, P90, P99 */}
            {[
              { idx: P50_IDX, color: '#86efac', label: 'P50' },
              { idx: P90_IDX, color: '#d7ba7d', label: 'P90' },
              { idx: P99_IDX, color: '#ce9178', label: 'P99' },
            ].map((ref) => {
              const xPct = ((ref.idx + 0.5) / BAR_COUNT) * 100
              const show = histProgress * BAR_COUNT >= ref.idx
              return (
                <div
                  key={ref.label}
                  className="absolute top-0 bottom-0 border-l transition-opacity duration-500"
                  style={{
                    left: `${xPct}%`,
                    borderColor: ref.color,
                    borderStyle: 'dashed',
                    borderLeftWidth: '1px',
                    opacity: show ? 0.7 : 0,
                  }}
                >
                  <span className="absolute -top-[2px] left-1 text-[7px] font-mono tabular-nums" style={{ color: ref.color }}>
                    {ref.label}
                  </span>
                </div>
              )
            })}

            {/* Scan line */}
            <div
              className="absolute top-0 bottom-0 w-[1.5px] pointer-events-none transition-opacity"
              style={{
                left: `${scanX}%`,
                backgroundColor: '#d7ba7d',
                boxShadow: '0 0 8px #d7ba7d, 0 0 16px #d7ba7d',
                opacity: scanX > 0 && scanX < 100 ? 0.7 : 0,
              }}
            />
          </div>

          {/* X-axis label */}
          <div className="flex justify-between mt-1 text-[7px] font-mono uppercase tracking-wider" style={{ color: '#52525b' }}>
            <span>$0</span>
            <span>ANNUAL LOSS EXPOSURE →</span>
            <span>$12M</span>
          </div>
        </div>
      </div>

      {/* Footer: VaR/CVaR stats */}
      <div className="relative px-4 py-2 border-t flex items-center justify-between shrink-0 font-mono text-[8.5px]" style={{ borderColor: 'rgba(255,255,255,0.08)', backgroundColor: 'rgba(255,255,255,0.015)' }}>
        <div className="flex items-center gap-4">
          <span style={{ color: '#6a737d' }}>VaR 95%</span>
          <span className="tabular-nums" style={{ color: '#d7ba7d' }}>$2.4M</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#6a737d' }}>CVaR 99%</span>
          <span className="tabular-nums" style={{ color: '#ce9178' }}>$4.1M</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#6a737d' }}>σ</span>
          <span className="tabular-nums" style={{ color: '#9a8a70' }}>0.042</span>
        </div>
        <span style={{ color: '#9a8a70' }}>
          {complete ? 'Converged' : '5-dim · NAICS peers'}
        </span>
      </div>
    </div>
  )
}
