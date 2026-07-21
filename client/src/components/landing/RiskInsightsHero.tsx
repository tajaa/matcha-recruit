import { useEffect, useRef, useState } from 'react'
import { motion, useInView } from 'framer-motion'
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis } from 'recharts'

// Live-feeling Risk Insights mockup for the Matcha Lite landing hero. Dark
// dashboard chrome (intentionally hardcoded zinc palette, independent of the
// ivory marketing tokens) mirroring /app/ir/risk-insights. Mock data — but it
// MOVES continuously: the trend area chart scrolls + breathes a stacked hump,
// and the worker-comp posture numbers count up then live-jitter forever.
// (No risk-matrix table here — that surface was retired with the rest of the
// unused landing panels.)

// ---------------------------------------------------------------------------
// Moving incident-trend area chart — a stacked hump that scrolls and breathes
// ---------------------------------------------------------------------------

const TREND_POINTS = 26
const TREND_LAYERS = [
  { key: 'critical', color: '#b54a3f', amp: 6, spread: 4.5, phase: 0.0, breath: 0.9 },
  { key: 'elevated', color: '#c98a3e', amp: 9, spread: 5.5, phase: 0.6, breath: 1.4 },
  { key: 'baseline', color: '#2f9e74', amp: 7, spread: 7.0, phase: 1.1, breath: 0.6 },
] as const

function gaussian(x: number, center: number, spread: number) {
  const d = x - center
  return Math.exp(-(d * d) / (2 * spread * spread))
}

function buildTrendFrame(t: number) {
  // t (seconds) drifts the hump centers across the x-window; a slower sine
  // breathes each layer's amplitude so the whole surface swells and recedes.
  return Array.from({ length: TREND_POINTS }, (_, x) => {
    const row: Record<string, number> = { x }
    for (const layer of TREND_LAYERS) {
      const drift = (t * 0.085 + layer.phase) % 1
      const c1 = drift * (TREND_POINTS + 8) - 4
      const c2 = c1 - TREND_POINTS * 0.62
      const breathe = 1 + Math.sin(t * layer.breath + layer.phase * 3) * 0.32
      const amp = layer.amp * breathe
      const v = amp * gaussian(x, c1, layer.spread) + amp * 0.5 * gaussian(x, c2, layer.spread * 0.9)
      row[layer.key] = Math.round(v * 10) / 10
    }
    return row
  })
}

function MovingTrend({ inView }: { inView: boolean }) {
  const [data, setData] = useState(() => buildTrendFrame(0))
  const rafRef = useRef(0)
  const lastRef = useRef(0)
  const startRef = useRef(0)

  useEffect(() => {
    if (!inView) return
    const loop = (now: number) => {
      if (!startRef.current) startRef.current = now
      // ~24fps state pushes — snappy scroll without thrashing recharts
      if (now - lastRef.current > 42) {
        lastRef.current = now
        setData(buildTrendFrame((now - startRef.current) / 1000))
      }
      rafRef.current = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(rafRef.current)
  }, [inView])

  return (
    <div className="px-5 pt-4 pb-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[8px] uppercase tracking-widest font-bold flex items-center gap-2" style={{ color: '#52525b' }}>
          Incident Trend
          <span className="font-mono normal-case tracking-normal" style={{ color: '#ce5a4f' }}>↗ +429% recent vs prior half</span>
        </span>
        <div className="flex gap-1">
          {['BY SEVERITY', '90D'].map((l, i) => (
            <span key={l} className="px-1.5 py-0.5 rounded text-[7px] font-bold tracking-wider"
              style={{ backgroundColor: i === 0 ? '#27272a' : '#18181b', color: i === 0 ? '#e4e4e7' : '#52525b', border: '1px solid #27272a' }}>
              {l}
            </span>
          ))}
        </div>
      </div>
      <div style={{ height: 170 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 6, right: 0, bottom: 0, left: -28 }}>
            <defs>
              {TREND_LAYERS.map(l => (
                <linearGradient key={l.key} id={`rih-${l.key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={l.color} stopOpacity={0.85} />
                  <stop offset="100%" stopColor={l.color} stopOpacity={0.25} />
                </linearGradient>
              ))}
            </defs>
            <XAxis dataKey="x" hide />
            <YAxis hide domain={[0, 34]} />
            {TREND_LAYERS.map(l => (
              <Area
                key={l.key}
                type="monotone"
                dataKey={l.key}
                stackId="1"
                stroke={l.color}
                strokeWidth={1.25}
                fill={`url(#rih-${l.key})`}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="flex justify-between mt-1 text-[7px] font-mono" style={{ color: '#3f3f46' }}>
        {['Mar 15', 'Apr 5', 'Apr 26', 'May 10', 'May 24'].map(d => <span key={d}>{d}</span>)}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Worker-comp posture cards — count up, then live-jitter forever + sparkline
// ---------------------------------------------------------------------------

function useLiveMetric(
  target: number,
  run: boolean,
  { decimals = 0, jitter = 0, freq = 0.5, duration = 1400 }: { decimals?: number; jitter?: number; freq?: number; duration?: number },
) {
  const [val, setVal] = useState(0)
  const raf = useRef(0)
  const start = useRef(0)
  const last = useRef(0)
  useEffect(() => {
    if (!run) return
    const tick = (now: number) => {
      if (!start.current) start.current = now
      const elapsed = (now - start.current) / 1000
      const t = Math.min(1, (now - start.current) / duration)
      let v: number
      if (t < 1) {
        v = (1 - Math.pow(1 - t, 3)) * target
      } else {
        // continuous wander: two incommensurate sines so it never repeats obviously
        v = target + Math.sin(elapsed * freq * 2 * Math.PI) * jitter + Math.sin(elapsed * freq * 3.3) * jitter * 0.45
      }
      if (now - last.current > 50) { last.current = now; setVal(v) }
      raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [run, target, decimals, jitter, freq, duration])
  return Math.max(0, val).toFixed(decimals)
}

function Sparkline({ run, color, freq }: { run: boolean; color: string; freq: number }) {
  const [pts, setPts] = useState<number[]>(() => Array(20).fill(0.5))
  const raf = useRef(0)
  const start = useRef(0)
  const last = useRef(0)
  useEffect(() => {
    if (!run) return
    const tick = (now: number) => {
      if (!start.current) start.current = now
      if (now - last.current > 90) {
        last.current = now
        const t = (now - start.current) / 1000
        setPts(Array.from({ length: 20 }, (_, i) => {
          const v = 0.5 + Math.sin((i * 0.5) + t * freq) * 0.32 + Math.sin((i * 0.9) - t * freq * 1.7) * 0.14
          return Math.max(0.05, Math.min(0.95, v))
        }))
      }
      raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [run, freq])
  const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${(i / (pts.length - 1)) * 100},${(1 - p) * 24}`).join(' ')
  return (
    <svg viewBox="0 0 100 24" preserveAspectRatio="none" className="w-full h-5 mt-2" style={{ opacity: 0.7 }}>
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function WcCard({ icon, label, value, sub, subColor, accent, freq, inView }: {
  icon: string; label: string; value: string; sub: string; subColor: string; accent: string; freq: number; inView: boolean
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.4 }}
      className="px-4 py-3.5 flex-1 min-w-0"
    >
      <div className="text-[7px] uppercase tracking-widest flex items-center gap-1 mb-2" style={{ color: '#52525b' }}>
        <span>{icon}</span>{label}
      </div>
      <div className="leading-none font-bold tabular-nums" style={{ fontSize: '1.5rem', color: '#ce5a4f', letterSpacing: '-0.02em' }}>
        {value}
      </div>
      <div className="text-[7px] mt-2 uppercase tracking-wider" style={{ color: subColor }}>{sub}</div>
      <Sparkline run={inView} color={accent} freq={freq} />
    </motion.div>
  )
}

function WcPosture({ inView }: { inView: boolean }) {
  const trir = useLiveMetric(66, inView, { decimals: 2, jitter: 1.4, freq: 0.45 })
  const dart = useLiveMetric(36, inView, { decimals: 2, jitter: 1.0, freq: 0.6 })
  const lost = useLiveMetric(326, inView, { decimals: 0, jitter: 4, freq: 0.3 })
  const streak = useLiveMetric(112, inView, { decimals: 0, jitter: 0, freq: 0.4, duration: 1700 })
  return (
    <div className="border-t" style={{ borderColor: 'rgba(39,39,42,0.5)' }}>
      <div className="px-5 pt-3 pb-1 text-[8px] uppercase tracking-widest" style={{ color: '#52525b' }}>
        ♡ Workers Comp Posture · Trailing 12 mo
      </div>
      <div className="flex divide-x" style={{ borderColor: 'rgba(39,39,42,0.5)' }}>
        <WcCard icon="∿" label="TRIR" value={trir} sub="1733% above median" subColor="#b54a3f" accent="#ce5a4f" freq={0.9} inView={inView} />
        <WcCard icon="∿" label="DART" value={dart} sub="1700% above median" subColor="#b54a3f" accent="#c98a3e" freq={1.2} inView={inView} />
        <WcCard icon="▦" label="Lost Days" value={lost} sub="+10 restricted" subColor="#52525b" accent="#71717a" freq={0.6} inView={inView} />
        <WcCard icon="♡" label="Claims-free" value={streak} sub="days" subColor="#52525b" accent="#2f9e74" freq={0.8} inView={inView} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Composed panel
// ---------------------------------------------------------------------------

export function RiskInsightsHero() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-60px' })

  return (
    <div ref={ref} className="rounded-xl overflow-x-auto border font-sans" style={{ borderColor: 'rgba(63,63,70,0.5)', backgroundColor: '#0d0d10' }}>
      <div className="min-w-[480px]">
        <div className="flex items-center justify-between px-5 py-3.5 border-b" style={{ borderColor: 'rgba(39,39,42,0.5)' }}>
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold" style={{ color: '#f4f4f5' }}>Risk Insights</span>
            <motion.span
              className="px-1.5 py-0.5 rounded text-[8px] font-medium"
              style={{ backgroundColor: 'rgba(16,185,129,0.15)', color: '#6ee7b7', border: '1px solid rgba(16,185,129,0.25)' }}
              animate={inView ? { opacity: [1, 0.45, 1] } : {}}
              transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
            >
              LIVE
            </motion.span>
          </div>
          <div className="flex items-center gap-1.5">
            {(['All locations', 'Last 90 days'] as const).map(label => (
              <div key={label} className="flex items-center gap-1 px-2 py-1 rounded" style={{ backgroundColor: '#18181b', border: '1px solid #27272a', color: '#71717a', fontSize: 8 }}>
                {label} <span style={{ fontSize: 7 }}>▾</span>
              </div>
            ))}
          </div>
        </div>
        <MovingTrend inView={inView} />
        <WcPosture inView={inView} />
      </div>
    </div>
  )
}
