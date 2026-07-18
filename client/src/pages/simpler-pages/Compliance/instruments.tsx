import { useRef } from 'react'
import { motion, useInView } from 'framer-motion'

import { InstrumentFrame } from './InstrumentFrame'
import { PulseDot } from './PulseDot'
import { useLoopCycle } from './useLoopCycle'
import { CARD_LINE, CARD_MUTED, CARD_TEXT, DISPLAY, GREEN } from './theme'

// ---------------------------------------------------------------------------
// Pillars — four full-width editorial rows (≈ two pages of scroll), not a
// compact card grid. Each pillar alternates copy / instrument sides and gets
// its own bespoke grayscale diagram: a jurisdiction stack that resolves to
// the governing rule, a graded handbook, a policy lifecycle, a credential
// countdown. One green mark per instrument — the node it resolves to — and
// an oversized ghost numeral bleeding off the copy side. Grayscale else.
// ---------------------------------------------------------------------------

// 01 — a nested stack that narrows federal → city, resolving to the one
// governing rule (lit).
function JurisdictionInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const rows = [
    { label: 'Federal', w: 100, note: 'Baseline' },
    { label: 'State', w: 78, note: 'Overlay' },
    { label: 'County', w: 56, note: 'Overlay' },
    { label: 'City', w: 38, note: 'Governs', lit: true },
  ]
  return (
    <InstrumentFrame caption="Requirement stack" foot="Resolves to the one rule that governs">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3">
          {rows.map((r, i) => (
            <div key={r.label} className="flex items-center gap-4">
              <div className="w-16 shrink-0 text-[10px] font-mono uppercase tracking-wider text-right" style={{ color: r.lit ? CARD_TEXT : CARD_MUTED, fontWeight: r.lit ? 600 : 400 }}>
                {r.label}
              </div>
              <div className="relative flex-1 h-7">
                <motion.div
                  className="absolute inset-y-0 left-0 rounded-sm flex items-center px-2.5 overflow-hidden"
                  style={{
                    border: `1px solid ${r.lit ? 'transparent' : CARD_LINE}`,
                    backgroundColor: r.lit ? GREEN : 'transparent',
                  }}
                  initial={{ width: 0 }}
                  animate={inView ? { width: `${r.w}%` } : {}}
                  transition={{ duration: 0.6, delay: i * 0.18, ease: [0.16, 1, 0.3, 1] }}
                >
                  <motion.span
                    className="text-[9px] font-mono uppercase tracking-wider whitespace-nowrap"
                    style={{ color: r.lit ? '#1a1408' : CARD_MUTED }}
                    initial={{ opacity: 0 }}
                    animate={inView ? { opacity: 1 } : {}}
                    transition={{ duration: 0.3, delay: i * 0.18 + 0.35 }}
                  >
                    {r.note}
                  </motion.span>
                </motion.div>
                {r.lit && (
                  <motion.span
                    className="absolute top-1/2 -translate-y-1/2"
                    style={{ left: `${r.w}%` }}
                    initial={{ opacity: 0, scale: 0.5 }}
                    animate={inView ? { opacity: 1, scale: 1 } : {}}
                    transition={{ duration: 0.3, delay: i * 0.18 + 0.5 }}
                  >
                    <PulseDot />
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

// 02 — a graded handbook: section rows with grade marks, one flagged.
function HandbookInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const sections = [
    { label: 'At-will & EEO', w: 82, grade: 'ok' },
    { label: 'Meal & rest breaks', w: 64, grade: 'flag' },
    { label: 'Leave policies', w: 74, grade: 'ok' },
    { label: 'Anti-harassment', w: 58, grade: 'weak' },
    { label: 'Pay & overtime', w: 70, grade: 'ok' },
  ]
  const mark: Record<string, { t: string; c: string }> = {
    ok: { t: '✓', c: CARD_MUTED },
    weak: { t: '~', c: CARD_MUTED },
    flag: { t: 'CRITICAL', c: GREEN },
  }
  return (
    <InstrumentFrame caption="Handbook · graded" foot="Every section scored against your state">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3.5">
          {sections.map((s, i) => {
            const m = mark[s.grade]
            const lit = s.grade === 'flag'
            return (
              <motion.div
                key={s.label}
                className="flex items-center gap-3"
                initial={{ opacity: 0, x: -8 }}
                animate={inView ? { opacity: 1, x: 0 } : {}}
                transition={{ duration: 0.4, delay: i * 0.1, ease: 'easeOut' }}
              >
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] mb-1.5" style={{ color: lit ? CARD_TEXT : CARD_MUTED, fontWeight: lit ? 600 : 400 }}>
                    {s.label}
                  </div>
                  <div className="h-1 rounded-full overflow-hidden" style={{ backgroundColor: CARD_LINE }}>
                    <motion.div
                      className="h-full rounded-full"
                      style={{ backgroundColor: lit ? GREEN : CARD_LINE }}
                      initial={{ width: 0 }}
                      animate={inView ? { width: `${s.w}%` } : {}}
                      transition={{ duration: 0.6, delay: i * 0.1 + 0.1, ease: [0.16, 1, 0.3, 1] }}
                    />
                  </div>
                </div>
                {lit ? (
                  <span className="flex items-center gap-1.5 shrink-0">
                    <PulseDot size={6} />
                    <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: m.c }}>{m.t}</span>
                  </span>
                ) : (
                  <span className="text-[11px] font-mono w-14 text-right shrink-0" style={{ color: m.c }}>{m.t}</span>
                )}
              </motion.div>
            )
          })}
        </div>
      </div>
    </InstrumentFrame>
  )
}

// 03 — a policy kept current, with a live review date. No lifecycle detail.
function PolicyInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const words = ['Always current.', 'Never stale.']
  return (
    <InstrumentFrame caption="Policy · lifecycle" foot="Next review tracked — never slips">
      <div ref={ref} className="flex flex-col items-center text-center gap-4 py-3">
        <PulseDot size={10} />
        <p key={cycle} style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.6rem', color: CARD_TEXT, lineHeight: 1.2 }}>
          {words.map((w, i) => (
            <motion.span
              key={w}
              className="inline-block mr-2"
              initial={{ opacity: 0, y: 8 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: 0.15 + i * 0.3, ease: 'easeOut' }}
            >
              {w}
            </motion.span>
          ))}
        </p>
      </div>
      <div className="mt-6 pt-5 border-t flex items-center justify-between" style={{ borderColor: CARD_LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>Next review</span>
        <span className="text-[12px] font-mono" style={{ color: CARD_TEXT }}>Mar 14 · 42 days</span>
      </div>
    </InstrumentFrame>
  )
}

// 04 — a credential countdown, expiry node lit.
function CredentialInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const marks = [
    { label: '90d', note: 'Reminder' },
    { label: '30d', note: 'Nudge' },
    { label: '0d', note: 'Expires', lit: true },
  ]
  return (
    <InstrumentFrame caption="Credential · countdown" foot="Flagged long before it lapses">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-4">
          {marks.map((m, i) => (
            <motion.div
              key={m.label}
              className="flex items-center gap-4"
              initial={{ opacity: 0, y: 6 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.3, ease: 'easeOut' }}
            >
              <div className="w-10 shrink-0 text-[13px] font-mono tabular-nums text-right" style={{ color: m.lit ? CARD_TEXT : CARD_MUTED, fontWeight: m.lit ? 600 : 400 }}>
                {m.label}
              </div>
              <div className="flex items-center gap-2.5 flex-1">
                {m.lit ? <PulseDot size={7} /> : <span className="block rounded-full" style={{ width: 6, height: 6, border: `1px solid ${CARD_LINE}` }} />}
                <div className="flex-1 h-px" style={{ backgroundColor: m.lit ? GREEN : CARD_LINE }} />
                <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: m.lit ? GREEN : CARD_MUTED }}>{m.note}</span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </InstrumentFrame>
  )
}

export const INSTRUMENTS: Record<string, () => React.ReactElement> = {
  jurisdiction: JurisdictionInstrument,
  'handbook-audit': HandbookInstrument,
  'policy-management': PolicyInstrument,
  credentialing: CredentialInstrument,
}
