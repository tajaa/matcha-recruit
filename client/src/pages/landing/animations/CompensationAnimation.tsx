import { useEffect, useState } from 'react'
import { Users } from 'lucide-react'

// Compensation distribution histogram with market band (p25-p75), median line,
// and individual role markers. Mirrors the visual density of LossDistributionPanel.

const BAR_COUNT = 18
// Roughly normal-ish comp distribution across buckets
function bellHeight(i: number): number {
  const x = (i - (BAR_COUNT - 1) / 2) / (BAR_COUNT / 2.5)
  return Math.exp(-x * x)
}
const RAW = Array.from({ length: BAR_COUNT }, (_, i) => bellHeight(i))
const MAX = Math.max(...RAW)
const HEIGHTS = RAW.map((h) => h / MAX)

const P25_IDX = 5
const P50_IDX = 8
const P75_IDX = 11

type Role = {
  label: string
  barIdx: number // where the marker falls on the x-axis
  verdict: 'below' | 'at' | 'above'
  pay: string
}

const ROLES: Role[] = [
  { label: 'Director of People',  barIdx: 3,  verdict: 'below', pay: '$142k' },
  { label: 'Staff Product',       barIdx: 4,  verdict: 'below', pay: '$168k' },
  { label: 'HR Business Partner', barIdx: 8,  verdict: 'at',    pay: '$135k' },
  { label: 'Senior Engineer',     barIdx: 9,  verdict: 'at',    pay: '$215k' },
  { label: 'Senior Ops Manager',  barIdx: 14, verdict: 'above', pay: '$188k' },
]

const STEP_MS = 550
const FILL_DURATION = 900
const SETTLE_PAUSE = 800
const RESET_PAUSE = 2500

const VERDICT_COLOR = {
  below: '#ce9178',
  at: '#86efac',
  above: '#d7ba7d',
}

export function CompensationAnimation() {
  const [histProgress, setHistProgress] = useState(0)
  const [revealed, setRevealed] = useState(-1)
  const [gapPct, setGapPct] = useState(0)
  const [adjustment, setAdjustment] = useState(0)
  const [complete, setComplete] = useState(false)

  useEffect(() => {
    let cancelled = false
    let timers: number[] = []
    const clear = () => { timers.forEach((t) => window.clearTimeout(t)); timers = [] }

    const tickValue = (from: number, to: number, durationMs: number, setter: (v: number) => void) => {
      const start = performance.now()
      const loop = () => {
        if (cancelled) return
        const elapsed = performance.now() - start
        const t = Math.min(1, elapsed / durationMs)
        const eased = 1 - Math.pow(1 - t, 2)
        setter(from + (to - from) * eased)
        if (t < 1) timers.push(window.setTimeout(loop, 16))
      }
      loop()
    }

    const tickHist = (durationMs: number) => {
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

    const run = () => {
      if (cancelled) return
      setHistProgress(0); setRevealed(-1); setGapPct(0); setAdjustment(0); setComplete(false)

      timers.push(window.setTimeout(() => tickHist(FILL_DURATION), 250))

      ROLES.forEach((_, idx) => {
        timers.push(window.setTimeout(() => {
          if (cancelled) return
          setRevealed(idx)
        }, FILL_DURATION + 300 + idx * STEP_MS))
      })

      timers.push(window.setTimeout(() => {
        if (cancelled) return
        tickValue(0, 7.2, 700, (v) => setGapPct(Math.round(v * 10) / 10))
        tickValue(0, 340000, 700, (v) => setAdjustment(Math.round(v / 1000) * 1000))
      }, FILL_DURATION + 300 + ROLES.length * STEP_MS))

      timers.push(window.setTimeout(() => {
        if (cancelled) return
        setComplete(true)
      }, FILL_DURATION + 300 + ROLES.length * STEP_MS + 900))

      const totalMs = FILL_DURATION + 300 + ROLES.length * STEP_MS + 900 + SETTLE_PAUSE + RESET_PAUSE
      timers.push(window.setTimeout(run, totalMs))
    }

    run()
    return () => { cancelled = true; clear() }
  }, [])

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
          <Users className="w-3.5 h-3.5" style={{ color: '#9a8a70' }} />
          <span className="text-[11px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
            Pay Equity Engine
          </span>
          <span className="text-[8.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono" style={{ color: '#d7ba7d', border: '1px solid rgba(215,186,125,0.4)' }}>
            n=47
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[9.5px]">
          <span style={{ color: '#6a737d' }}>Median</span>
          <span className="tabular-nums" style={{ color: '#86efac' }}>$135k</span>
          <span style={{ color: '#3f3f46' }}>|</span>
          <span style={{ color: '#6a737d' }}>IQR</span>
          <span className="tabular-nums" style={{ color: '#9a8a70' }}>$48k</span>
        </div>
      </div>

      {/* Body: sidebar stats + histogram */}
      <div className="relative flex-1 grid grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] min-h-0">
        {/* LEFT: role list */}
        <div className="flex flex-col p-3 border-r min-h-0" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
          <div className="text-[8px] uppercase tracking-wider font-mono mb-2" style={{ color: '#6a737d' }}>
            Flagged roles
          </div>
          <div className="flex-1 flex flex-col justify-around gap-1 min-h-0">
            {ROLES.map((role, idx) => {
              const visible = revealed >= idx
              const color = VERDICT_COLOR[role.verdict]
              return (
                <div
                  key={idx}
                  className="flex items-center justify-between transition-all duration-300"
                  style={{ opacity: visible ? 1 : 0.2 }}
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span
                      className="w-1 h-1 rounded-full shrink-0"
                      style={{
                        backgroundColor: color,
                        boxShadow: visible ? `0 0 4px ${color}` : 'none',
                      }}
                    />
                    <span className="text-[9px] font-mono truncate" style={{ color: visible ? '#d4d4d4' : '#52525b' }}>
                      {role.label}
                    </span>
                  </div>
                  <span className="text-[8.5px] tabular-nums font-mono shrink-0 ml-2" style={{ color: visible ? color : '#52525b' }}>
                    {role.pay}
                  </span>
                </div>
              )
            })}
          </div>

          {/* Footer stats */}
          <div className="mt-3 pt-2 border-t space-y-1" style={{ borderColor: 'rgba(255,255,255,0.05)' }}>
            <div className="flex items-center justify-between">
              <span className="text-[8px] uppercase tracking-wider font-mono" style={{ color: '#6a737d' }}>
                Pay gap
              </span>
              <span className="text-[11px] tabular-nums font-mono" style={{ color: gapPct > 5 ? '#ce9178' : '#d7ba7d' }}>
                {gapPct.toFixed(1)}%
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[8px] uppercase tracking-wider font-mono" style={{ color: '#6a737d' }}>
                Adjustment
              </span>
              <span className="text-[11px] tabular-nums font-mono" style={{ color: '#e4ded2' }}>
                ${Math.round(adjustment / 1000)}k
              </span>
            </div>
          </div>
        </div>

        {/* RIGHT: distribution histogram */}
        <div className="flex flex-col p-3 relative overflow-hidden min-h-0">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[8px] uppercase tracking-wider font-mono" style={{ color: '#6a737d' }}>
              Comp distribution
            </span>
            <div className="flex gap-2 font-mono text-[8px]">
              <span style={{ color: '#86efac' }}>P50</span>
              <span style={{ color: '#d7ba7d' }}>P25—P75</span>
            </div>
          </div>

          <div className="flex-1 relative min-h-0">
            {/* Y-axis reference lines */}
            {[0.25, 0.5, 0.75, 1].map((y) => (
              <div key={y} className="absolute left-0 right-0 border-t" style={{ bottom: `${y * 100}%`, borderColor: 'rgba(255,255,255,0.04)', borderStyle: y === 1 ? 'solid' : 'dashed' }} />
            ))}

            {/* Market band (p25-p75) */}
            <div
              className="absolute top-0 bottom-0 transition-opacity duration-700"
              style={{
                left: `${(P25_IDX / BAR_COUNT) * 100}%`,
                right: `${100 - ((P75_IDX + 1) / BAR_COUNT) * 100}%`,
                backgroundColor: 'rgba(134,239,172,0.06)',
                borderLeft: '1px dashed rgba(134,239,172,0.35)',
                borderRight: '1px dashed rgba(134,239,172,0.35)',
                opacity: histProgress > 0.5 ? 1 : 0,
              }}
            />

            {/* Bars */}
            <div className="absolute inset-0 flex items-end gap-[2px]">
              {HEIGHTS.map((h, i) => {
                const visible = histProgress * BAR_COUNT >= i
                const inBand = i >= P25_IDX && i <= P75_IDX
                const color = inBand ? '#86efac' : '#52525b'
                return (
                  <div key={i} className="flex-1 relative">
                    <div
                      className="absolute bottom-0 left-0 right-0 transition-all duration-300"
                      style={{
                        height: `${visible ? h * 100 : 0}%`,
                        backgroundColor: color,
                        opacity: inBand ? 0.6 : 0.4,
                      }}
                    />
                  </div>
                )
              })}
            </div>

            {/* P50 (median) line */}
            <div
              className="absolute top-0 bottom-0 transition-opacity duration-500"
              style={{
                left: `${((P50_IDX + 0.5) / BAR_COUNT) * 100}%`,
                borderLeft: '1px solid #86efac',
                boxShadow: '0 0 6px #86efac',
                opacity: histProgress > 0.6 ? 0.9 : 0,
              }}
            >
              <span className="absolute -top-[2px] left-1 text-[7px] font-mono" style={{ color: '#86efac' }}>
                P50
              </span>
            </div>

            {/* Role markers (dots positioned on the distribution) */}
            {ROLES.map((role, idx) => {
              const visible = revealed >= idx
              const color = VERDICT_COLOR[role.verdict]
              const xPct = ((role.barIdx + 0.5) / BAR_COUNT) * 100
              const yPct = HEIGHTS[role.barIdx] * 70 + 10
              return (
                <div
                  key={idx}
                  className="absolute w-2 h-2 rounded-full transition-all duration-500 -translate-x-1/2 translate-y-1/2"
                  style={{
                    left: `${xPct}%`,
                    bottom: `${yPct}%`,
                    backgroundColor: color,
                    boxShadow: visible ? `0 0 0 2px rgba(14,13,11,0.9), 0 0 8px ${color}` : 'none',
                    opacity: visible ? 1 : 0,
                  }}
                />
              )
            })}
          </div>

          <div className="flex justify-between mt-1 text-[7px] font-mono uppercase tracking-wider" style={{ color: '#52525b' }}>
            <span>$80k</span>
            <span>BASE COMPENSATION →</span>
            <span>$260k</span>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="relative px-4 py-2 border-t flex items-center justify-between shrink-0 font-mono text-[8.5px]" style={{ borderColor: 'rgba(255,255,255,0.08)', backgroundColor: 'rgba(255,255,255,0.015)' }}>
        <div className="flex items-center gap-3">
          <span style={{ color: '#6a737d' }}>Scanning 47 roles · 4 departments</span>
        </div>
        <span style={{ color: '#9a8a70' }}>
          {complete ? 'Report ready' : 'Running scan…'}
        </span>
      </div>
    </div>
  )
}
