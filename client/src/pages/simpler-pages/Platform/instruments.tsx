import { useRef } from 'react'
import { motion, useInView } from 'framer-motion'

import { InstrumentFrame } from './InstrumentFrame'
import { PulseDot } from './PulseDot'
import { useCountUp, useLoopCycle } from './hooks'
import { CARD_LINE, CARD_MUTED, CARD_TEXT, DISPLAY, GREEN } from './theme'

// ---------------------------------------------------------------------------
// Pillars — four full-width editorial rows (≈ two pages of scroll). Each
// pillar alternates copy / instrument sides and gets its own bespoke
// grayscale diagram, with one green mark for the node it resolves to and an
// oversized ghost numeral bleeding off the copy side. Grayscale everywhere.
// ---------------------------------------------------------------------------

// 01 — incident intake, resolved to routed. No pipeline detail.
function IntakeInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const words = ['Reported.', 'Scored.', 'Routed.']
  return (
    <InstrumentFrame caption="Incident · intake" foot="Every report categorized, scored, and routed">
      <div ref={ref} className="flex flex-col items-center text-center gap-4 py-3">
        <PulseDot size={10} />
        <p key={cycle} style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.6rem', color: CARD_TEXT, lineHeight: 1.2 }}>
          {words.map((w, i) => (
            <motion.span
              key={w}
              className="inline-block mr-2"
              initial={{ opacity: 0, y: 8 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: 0.15 + i * 0.22, ease: 'easeOut' }}
            >
              {w}
            </motion.span>
          ))}
        </p>
      </div>
      <div className="mt-6 pt-5 border-t flex items-center justify-between" style={{ borderColor: CARD_LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>Atlanta — Store 7</span>
        <span className="text-[11px] font-mono" style={{ color: CARD_TEXT }}>In the right hands</span>
      </div>
    </InstrumentFrame>
  )
}

// 02 — compliance monitor rows, one flagged.
function ComplianceInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const rows = [
    { j: 'A', label: 'Wage & hour rules', status: 'clear' },
    { j: 'B', label: 'Break requirements', status: 'flag' },
    { j: 'C', label: 'Leave policies', status: 'clear' },
    { j: 'D', label: 'Scheduling rules', status: 'clear' },
  ]
  return (
    <InstrumentFrame caption="Compliance · monitor" foot="Deltas flagged before they take effect">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3.5">
          {rows.map((r, i) => {
            const lit = r.status === 'flag'
            return (
              <motion.div
                key={r.label}
                className="flex items-center gap-3"
                initial={{ opacity: 0, x: -8 }}
                animate={inView ? { opacity: 1, x: 0 } : {}}
                transition={{ duration: 0.4, delay: i * 0.12, ease: 'easeOut' }}
              >
                <span className="w-9 shrink-0 text-[9px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>{r.j}</span>
                <span className="flex-1 min-w-0 text-[12px] truncate" style={{ color: lit ? CARD_TEXT : CARD_MUTED, fontWeight: lit ? 600 : 400 }}>{r.label}</span>
                {lit ? (
                  <motion.span
                    className="flex items-center gap-1.5 shrink-0"
                    initial={{ opacity: 0 }}
                    animate={inView ? { opacity: 1 } : {}}
                    transition={{ duration: 0.3, delay: i * 0.12 + 0.35 }}
                  >
                    <PulseDot size={6} />
                    <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: GREEN }}>Flagged</span>
                  </motion.span>
                ) : (
                  <span className="text-[9px] font-mono uppercase tracking-wider shrink-0" style={{ color: CARD_MUTED }}>Clear</span>
                )}
              </motion.div>
            )
          })}
        </div>
      </div>
    </InstrumentFrame>
  )
}

// 03 — case cluster: pattern detection surfaces a repeat.
function CaseInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  // 5×3 scatter; the lit cells trace a repeat cluster, in scan order.
  const litOrder = [2, 7, 12]
  const litRank = new Map(litOrder.map((cell, i) => [cell, i]))
  return (
    <InstrumentFrame caption="Cases · pattern" foot="Repeat behavior surfaced across the record">
      <div ref={ref}>
        <div key={cycle}>
          <div className="grid grid-cols-5 gap-y-4 gap-x-3 place-items-center py-1">
            {Array.from({ length: 15 }).map((_, i) => {
              const rank = litRank.get(i)
              return rank === undefined ? (
                <motion.span
                  key={i}
                  className="block rounded-full"
                  style={{ width: 6, height: 6, backgroundColor: CARD_LINE }}
                  initial={{ opacity: 0 }}
                  animate={inView ? { opacity: 1 } : {}}
                  transition={{ duration: 0.4, delay: 0.02 * i }}
                />
              ) : (
                <motion.span
                  key={i}
                  initial={{ opacity: 0, scale: 0.4 }}
                  animate={inView ? { opacity: 1, scale: 1 } : {}}
                  transition={{ duration: 0.35, delay: 0.5 + rank * 0.3, ease: 'backOut' }}
                >
                  <PulseDot size={8} />
                </motion.span>
              )
            })}
          </div>
          <motion.div
            className="mt-5 pt-5 border-t flex items-center justify-between"
            style={{ borderColor: CARD_LINE }}
            initial={{ opacity: 0 }}
            animate={inView ? { opacity: 1 } : {}}
            transition={{ duration: 0.4, delay: 0.5 + litOrder.length * 0.3 }}
          >
            <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: GREEN }}>Pattern found</span>
            <span className="text-[11px] font-mono" style={{ color: CARD_TEXT }}>A repeat, one location</span>
          </motion.div>
        </div>
      </div>
    </InstrumentFrame>
  )
}

// 04 — domains feeding a single composite risk index.
function ConvergenceInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const riskIndex = useCountUp(72, inView, 1100, cycle)
  const domains = [
    { label: 'EHS', w: 70 },
    { label: 'GRC', w: 54 },
    { label: 'ER', w: 62 },
  ]
  return (
    <InstrumentFrame caption="Risk · composite" foot="Every domain rolled into one live index">
      <div ref={ref}>
        <div key={cycle} className="flex items-center gap-6">
          <div className="flex-1 flex flex-col gap-3">
            {domains.map((d, i) => (
              <div key={d.label} className="flex items-center gap-3">
                <span className="w-9 shrink-0 text-[9px] font-mono uppercase tracking-wider text-right" style={{ color: CARD_MUTED }}>{d.label}</span>
                <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: CARD_LINE }}>
                  <motion.div
                    className="h-full rounded-full"
                    style={{ backgroundColor: CARD_MUTED }}
                    initial={{ width: 0 }}
                    animate={inView ? { width: `${d.w}%` } : {}}
                    transition={{ duration: 0.8, delay: i * 0.15, ease: [0.16, 1, 0.3, 1] }}
                  />
                </div>
              </div>
            ))}
          </div>
          <span className="text-[11px] font-mono" style={{ color: CARD_MUTED }}>→</span>
          <div className="flex flex-col items-center gap-1 shrink-0">
            <div className="flex items-baseline gap-1">
              <span className="tabular-nums leading-none" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '2.75rem', color: GREEN }}>{riskIndex}</span>
            </div>
            <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>Risk index</span>
          </div>
        </div>
      </div>
    </InstrumentFrame>
  )
}

export const INSTRUMENTS: Record<string, () => React.ReactElement> = {
  ehs: IntakeInstrument,
  grc: ComplianceInstrument,
  er: CaseInstrument,
  convergence: ConvergenceInstrument,
}
