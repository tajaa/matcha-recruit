import { useEffect, useRef, useState } from 'react'
import { AMBER, ASH, BONE, LEAF, LINE_D } from '../../home/theme'
import { InstrumentFrame, curvePath, useCyclingIndex, useReducedMotion, VBH, VBW } from '../../home/instruments/shared'
import { BAND_COLOR, BOOK_MONEY, RADAR_ROWS, STATUS_LABEL, TOTAL_ACCOUNTS } from './data'

// ---------------------------------------------------------------------------
// Hero instrument for /matcha-brokers, on the same shared InstrumentFrame as
// Compliance/Platform/Lite's hero instruments. A legible miniature of the
// real /broker/risk-curve chart: X = annual loss in dollars, Y = likelihood,
// with the two reference lines (Expected, PML 99%) the real chart draws —
// the first version dropped both plus the axis, which is why it read as an
// unlabelled hump. Curve idea (curvePath helper) is the one thing worth
// keeping from the old skeuomorphic "Book Risk Console", now deleted.
//
// Status words come from `row.band` via STATUS_LABEL, matching the real
// Accounts table vocabulary (Healthy/Watch/At Risk) — NOT from the cycling
// index. The first version derived the label from `lit` and the dot color
// from `row.band` independently, so a red dot could read "Stable". Cycling
// here only changes emphasis (weight/glow), never which word is shown.
//
// Shows THAT the book is ranked and priced, never HOW — no loss-ratio
// constant, no mod-sensitivity rule, no factor weights. See Brokers.tsx.
// ---------------------------------------------------------------------------

const ROWS = RADAR_ROWS.slice(0, 3)

// Reference-line x-positions as a fraction of the curve width — the hump
// (Expected) and a point out in the tail (PML 99%), matching where the real
// chart's dashed lines fall relative to the distribution.
const EXPECTED_X_FRAC = 0.24
const PML_X_FRAC = 0.72

const AXIS_LABELS = ['$250K', '$500K', '$1M', '$2.5M', '$5M']

function BookCurve() {
  const reduceMotion = useReducedMotion()
  const [phase, setPhase] = useState(0)
  const rafRef = useRef(0)
  const lastRef = useRef(0)

  // Gate the rAF loop on both in-view and tab-visibility, same fix
  // ProductCarousel.tsx applies (IntersectionObserver + visibilitychange) —
  // without it this re-renders ~8x/sec forever, including scrolled past and
  // with the tab backgrounded.
  const wrapRef = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)
  const [hidden, setHidden] = useState(
    typeof document !== 'undefined' && document.visibilityState === 'hidden',
  )

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const io = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.1 })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    const onVis = () => setHidden(document.visibilityState === 'hidden')
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [])

  useEffect(() => {
    if (reduceMotion || !visible || hidden) return
    const FPS = 8
    const step = (now: number) => {
      if (now - lastRef.current > 1000 / FPS) {
        lastRef.current = now
        setPhase((p) => p + 0.045)
      }
      rafRef.current = requestAnimationFrame(step)
    }
    rafRef.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(rafRef.current)
  }, [reduceMotion, visible, hidden])

  const { line, area } = curvePath(phase)
  const expectedX = VBW * EXPECTED_X_FRAC
  const pmlX = VBW * PML_X_FRAC

  return (
    <div ref={wrapRef} className="relative">
      <svg viewBox={`0 0 ${VBW} ${VBH}`} preserveAspectRatio="none" className="w-full h-[86px]">
        <defs>
          <linearGradient id="brokerCurveFill" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={LEAF} />
            <stop offset="55%" stopColor={AMBER} />
            <stop offset="100%" stopColor={BAND_COLOR.critical} />
          </linearGradient>
          <linearGradient id="brokerCurveArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={LEAF} stopOpacity={0.35} />
            <stop offset="100%" stopColor={LEAF} stopOpacity={0} />
          </linearGradient>
        </defs>

        <path d={area} fill="url(#brokerCurveArea)" />
        <path d={line} fill="none" stroke="url(#brokerCurveFill)" strokeWidth={1.5} />

        <line x1={expectedX} x2={expectedX} y1={4} y2={VBH} stroke={LEAF} strokeWidth={1} strokeDasharray="2,2" opacity={0.8} />
        <line x1={pmlX} x2={pmlX} y1={4} y2={VBH} stroke={BAND_COLOR.critical} strokeWidth={1} strokeDasharray="2,2" opacity={0.8} />
      </svg>

      <div className="absolute inset-x-0 top-0 flex text-[8px] font-mono uppercase tracking-wider" style={{ color: ASH }}>
        <span style={{ position: 'absolute', left: `${EXPECTED_X_FRAC * 100}%`, transform: 'translateX(-50%)', color: LEAF }}>
          Expected
        </span>
        <span style={{ position: 'absolute', left: `${PML_X_FRAC * 100}%`, transform: 'translateX(-50%)', color: BAND_COLOR.critical }}>
          PML 99%
        </span>
      </div>

      <div className="mt-1.5 flex items-center justify-between">
        {AXIS_LABELS.map((l) => (
          <span key={l} className="text-[8px] font-mono tabular-nums" style={{ color: ASH, opacity: 0.7 }}>
            {l}
          </span>
        ))}
      </div>
      <div className="mt-1 text-right text-[8.5px] font-mono" style={{ color: ASH }}>
        X = annual loss · Y = likelihood
      </div>
    </div>
  )
}

export function BookInstrument() {
  const reduce = useReducedMotion()
  const litIndex = useCyclingIndex(ROWS.length, 2600, reduce)

  return (
    <InstrumentFrame label="Book risk curve · live" accent={AMBER}>
      <div className="px-5 pt-5 flex items-center justify-between">
        <div>
          <div className="text-[20px] tabular-nums" style={{ color: BONE, fontWeight: 300 }}>
            {BOOK_MONEY.expectedLoss}
          </div>
          <div className="text-[9px] font-mono uppercase tracking-[0.14em]" style={{ color: ASH }}>
            Expected annual loss
          </div>
        </div>
        <div className="text-right">
          <div className="text-[20px] tabular-nums" style={{ color: AMBER, fontWeight: 300 }}>
            {BOOK_MONEY.pml99}
          </div>
          <div className="text-[9px] font-mono uppercase tracking-[0.14em]" style={{ color: ASH }}>
            PML · 99th pct
          </div>
        </div>
      </div>

      <div className="px-5 pt-4">
        <BookCurve />
      </div>

      <div className="px-5 pt-4 pb-4 flex flex-col gap-3">
        {ROWS.map((row, i) => {
          const lit = i === litIndex
          const color = BAND_COLOR[row.band]
          return (
            <div key={row.client} className="flex items-center gap-3">
              <span
                className="shrink-0 block rounded-full transition-all duration-500"
                style={{
                  width: lit ? 8 : 6,
                  height: lit ? 8 : 6,
                  backgroundColor: color,
                  boxShadow: lit ? `0 0 8px ${color}` : 'none',
                }}
              />
              <span
                className="flex-1 min-w-0 text-[12px] truncate transition-colors duration-500"
                style={{ color: lit ? BONE : ASH, fontWeight: lit ? 600 : 400 }}
              >
                {row.client}
              </span>
              <span className="text-[10px] font-mono tabular-nums shrink-0" style={{ color: ASH }}>
                TRIR {row.trir}
              </span>
              <span
                className="text-[9px] font-mono uppercase tracking-wider shrink-0 w-[52px] text-right"
                style={{ color }}
              >
                {STATUS_LABEL[row.band]}
              </span>
            </div>
          )
        })}
      </div>

      <div className="px-5 pb-4 pt-3 border-t" style={{ borderColor: LINE_D }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.12em]" style={{ color: ASH }}>
          Modeled from live client intake, {TOTAL_ACCOUNTS} accounts · directional, not a quote
        </span>
      </div>
    </InstrumentFrame>
  )
}
