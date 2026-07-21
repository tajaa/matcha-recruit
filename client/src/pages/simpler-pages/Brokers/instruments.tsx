import { useRef } from 'react'
import { motion, useInView } from 'framer-motion'
import { InstrumentFrame } from './InstrumentFrame'
import { PulseDot } from './PulseDot'
import { useLoopCycle } from '../_shared/useLoopCycle'
import { CARD_LINE, CARD_MUTED, CARD_TEXT, GREEN } from './theme'

// ── Pillars — alternating rows with bespoke grayscale+green instruments ────

// 01 — risk-band ladder, resolving to the exposed account.
function RiskCurveInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const bands = [
    { label: 'Strong', w: 30 },
    { label: 'Adequate', w: 52 },
    { label: 'Developing', w: 74 },
    { label: 'Exposed', w: 96, lit: true },
  ]
  return (
    <InstrumentFrame caption="Book · risk curve" foot="The account deteriorating before its re-rate">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3">
          {bands.map((b, i) => (
            <div key={b.label} className="flex items-center gap-4">
              <div className="w-20 shrink-0 text-[10px] font-mono uppercase tracking-wider text-right" style={{ color: b.lit ? CARD_TEXT : CARD_MUTED, fontWeight: b.lit ? 600 : 400 }}>
                {b.label}
              </div>
              <div className="relative flex-1 h-2">
                <motion.div
                  className="absolute inset-y-0 left-0 rounded-full"
                  style={{ backgroundColor: b.lit ? GREEN : CARD_LINE }}
                  initial={{ width: 0 }}
                  animate={inView ? { width: `${b.w}%` } : {}}
                  transition={{ duration: 0.6, delay: i * 0.15, ease: [0.16, 1, 0.3, 1] }}
                />
                {b.lit && (
                  <motion.span
                    className="absolute top-1/2 -translate-y-1/2"
                    style={{ left: `${b.w}%` }}
                    initial={{ opacity: 0, scale: 0.5 }}
                    animate={inView ? { opacity: 1, scale: 1 } : {}}
                    transition={{ duration: 0.3, delay: i * 0.15 + 0.5 }}
                  >
                    <PulseDot size={7} />
                  </motion.span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </InstrumentFrame>
  )
}

// 02 — WC portfolio rows, worst-first, top row flagged.
function WcInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const rows = [
    { client: 'Northgate Logistics', lit: true },
    { client: 'Cedar Valley Mfg' },
    { client: 'Harbor Foods Co' },
    { client: 'Summit Builders' },
  ]
  return (
    <InstrumentFrame caption="The book · ranked" foot="The account that needs you, first">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3.5">
          {rows.map((r, i) => (
            <motion.div
              key={r.client}
              className="flex items-center gap-3"
              initial={{ opacity: 0, x: -8 }}
              animate={inView ? { opacity: 1, x: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.12, ease: 'easeOut' }}
            >
              <span className="flex-1 min-w-0 text-[12px] truncate" style={{ color: r.lit ? CARD_TEXT : CARD_MUTED, fontWeight: r.lit ? 600 : 400 }}>{r.client}</span>
              {r.lit ? (
                <span className="flex items-center gap-1.5 shrink-0 w-24 justify-end">
                  <PulseDot size={6} />
                  <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: GREEN }}>Needs a call</span>
                </span>
              ) : (
                <span className="text-[9px] font-mono uppercase tracking-wider shrink-0 w-24 text-right" style={{ color: CARD_MUTED }}>Stable</span>
              )}
            </motion.div>
          ))}
        </div>
      </div>
    </InstrumentFrame>
  )
}

// 03 — action queue, top alert urgent.
function CommandInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const alerts = [
    { client: 'Northgate Logistics', issue: 'Safety trend deteriorating', lit: true },
    { client: 'Cedar Valley Mfg', issue: 'Running above the book' },
    { client: 'Atlas Care Group', issue: 'Rising incident volume' },
  ]
  return (
    <InstrumentFrame caption="Command center · queue" foot="Each flagged trend, an outreach already drafted">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3.5">
          {alerts.map((a, i) => (
            <motion.div
              key={a.client}
              className="flex items-start gap-3"
              initial={{ opacity: 0, y: 6 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.15, ease: 'easeOut' }}
            >
              <span className="mt-1 shrink-0">
                {a.lit ? <PulseDot size={6} /> : <span className="block rounded-full" style={{ width: 6, height: 6, border: `1px solid ${CARD_LINE}` }} />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[12px]" style={{ color: a.lit ? CARD_TEXT : CARD_MUTED, fontWeight: a.lit ? 600 : 400 }}>{a.client}</div>
                <div className="text-[10.5px] mt-0.5" style={{ color: CARD_MUTED }}>{a.issue}</div>
              </div>
              <span className="text-[9px] font-mono uppercase tracking-wider shrink-0" style={{ color: a.lit ? GREEN : CARD_MUTED }}>
                {a.lit ? 'Urgent' : 'Advisory'}
              </span>
            </motion.div>
          ))}
        </div>
      </div>
    </InstrumentFrame>
  )
}

export const INSTRUMENTS: Record<string, () => React.ReactElement> = {
  'risk-curve': RiskCurveInstrument,
  wc: WcInstrument,
  command: CommandInstrument,
}
