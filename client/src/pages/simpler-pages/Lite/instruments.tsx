import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useInView } from 'framer-motion'

import { DISPLAY, GREEN, CARD_BG, CARD_TEXT, CARD_MUTED, CARD_LINE } from './constants'
import { useCountUp, useLoopCycle } from './hooks'

function PulseDot({ size = 8 }: { size?: number }) {
  return (
    <span className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <motion.span
        className="absolute rounded-full"
        style={{ width: size, height: size, backgroundColor: GREEN }}
        animate={{ scale: [1, 2.4, 1], opacity: [0.35, 0, 0.35] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
      />
      <span className="relative block rounded-full" style={{ width: size, height: size, backgroundColor: GREEN }} />
    </span>
  )
}

function InstrumentFrame({ caption, foot, children }: { caption: string; foot: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: CARD_LINE, backgroundColor: CARD_BG }}>
      <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: CARD_LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: CARD_MUTED }}>{caption}</span>
        <span className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: CARD_MUTED }}>
          <PulseDot size={5} />
          Live
        </span>
      </div>
      <div className="px-5 py-6">{children}</div>
      <div className="px-5 py-3 border-t text-[10px] font-mono uppercase tracking-[0.12em]" style={{ borderColor: CARD_LINE, color: CARD_MUTED }}>
        {foot}
      </div>
    </div>
  )
}

// 01 — magic-link intake: a real text arrives, resolves to logged. No pipeline detail.
function IntakeInstrument() {
  const [logged, setLogged] = useState(false)
  useEffect(() => {
    const t = setInterval(() => setLogged((v) => !v), 5200)
    return () => clearInterval(t)
  }, [])
  return (
    <InstrumentFrame caption="Magic link · intake" foot="No login, no app — a defensible record">
      <div className="flex items-center justify-center py-3" style={{ minHeight: 84 }}>
        <AnimatePresence mode="wait">
          {!logged ? (
            <motion.div
              key="text"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.35 }}
              className="max-w-[280px] rounded-2xl rounded-bl-sm px-4 py-3 text-[13px] border"
              style={{ backgroundColor: CARD_TEXT, borderColor: CARD_LINE, color: CARD_BG, lineHeight: 1.4 }}
            >
              "Wet floor by the loading dock, no injury, cleaned up"
            </motion.div>
          ) : (
            <motion.div
              key="logged"
              initial={{ opacity: 0, scale: 0.92 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.92 }}
              transition={{ duration: 0.35 }}
              className="flex items-center gap-2.5"
            >
              <span style={{ color: GREEN, fontSize: '1.1rem' }}>✓</span>
              <span style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.4rem', color: CARD_TEXT }}>
                Logged.
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      <div className="mt-2 pt-5 border-t flex items-center justify-between" style={{ borderColor: CARD_LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>Dallas — Store 3</span>
        <span className="text-[11px] font-mono" style={{ color: CARD_TEXT }}>Reported in seconds</span>
      </div>
    </InstrumentFrame>
  )
}

// 02 — HRIS/CSV roster import, already synced. No import-flow detail.
function RosterInstrument() {
  const sources = ['Gusto', 'Rippling', 'BambooHR', 'ADP', 'CSV']
  const [active, setActive] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setActive((v) => (v + 1) % sources.length), 1400)
    return () => clearInterval(t)
  }, [sources.length])
  return (
    <InstrumentFrame caption="Roster · import" foot="Every report pre-fills the right employee">
      <div className="flex flex-wrap justify-center gap-2 py-2">
        {sources.map((s, i) => (
          <motion.span
            key={s}
            className="px-3 py-1.5 rounded-full text-[11px] font-mono uppercase tracking-wider"
            animate={{
              color: i === active ? CARD_TEXT : CARD_MUTED,
              borderColor: i === active ? GREEN : CARD_LINE,
              fontWeight: i === active ? 600 : 400,
            }}
            transition={{ duration: 0.3 }}
            style={{ border: '1px solid' }}
          >
            {s}
          </motion.span>
        ))}
      </div>
      <div className="mt-5 pt-5 border-t flex items-center justify-between" style={{ borderColor: CARD_LINE }}>
        <span className="flex items-center gap-2">
          <PulseDot size={7} />
          <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>Synced</span>
        </span>
        <span className="text-[11px] font-mono" style={{ color: CARD_TEXT }}>312 employees</span>
      </div>
    </InstrumentFrame>
  )
}

// 03 — recent incidents with severity, one High flagged + a pattern note.
function AnalysisInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const rows = [
    { loc: 'Atlanta — Store 7', type: 'Customer escalation', sev: 'High', lit: true },
    { loc: 'Phoenix — Warehouse', type: 'Slip / fall', sev: 'Med' },
    { loc: 'Dallas — Store 3', type: 'Near-miss', sev: 'Low' },
  ]
  return (
    <InstrumentFrame caption="Incidents · analysis" foot="Auto-categorized — your team confirms">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3">
          {rows.map((r, i) => (
            <motion.div
              key={r.loc}
              className="flex items-center gap-3"
              initial={{ opacity: 0, x: -8 }}
              animate={inView ? { opacity: 1, x: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.14, ease: 'easeOut' }}
            >
              <span className="shrink-0">
                {r.lit ? <PulseDot size={6} /> : <span className="block rounded-full" style={{ width: 6, height: 6, backgroundColor: CARD_LINE }} />}
              </span>
              <span className="flex-1 min-w-0 text-[12px] truncate" style={{ color: r.lit ? CARD_TEXT : CARD_MUTED, fontWeight: r.lit ? 600 : 400 }}>{r.loc}</span>
              <span className="text-[10px] font-mono truncate hidden sm:inline shrink-0" style={{ color: CARD_MUTED }}>{r.type}</span>
              <span className="text-[9px] font-mono uppercase tracking-wider shrink-0 w-10 text-right" style={{ color: r.lit ? GREEN : CARD_MUTED }}>{r.sev}</span>
            </motion.div>
          ))}
        </div>
        <motion.div
          className="mt-5 pt-5 border-t flex items-center justify-between"
          style={{ borderColor: CARD_LINE }}
          initial={{ opacity: 0 }}
          animate={inView ? { opacity: 1 } : {}}
          transition={{ duration: 0.4, delay: rows.length * 0.14 + 0.2 }}
        >
          <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: GREEN }}>Pattern detected</span>
          <span className="text-[11px] font-mono" style={{ color: CARD_TEXT }}>A repeat, surfaced early</span>
        </motion.div>
      </div>
    </InstrumentFrame>
  )
}

// 04 — OSHA 300A tally tiles.
function OshaInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const tiles = [
    { label: 'Recordables', target: 7, lit: true },
    { label: 'Lost days', target: 18 },
    { label: 'Cases', target: 5 },
  ]
  return (
    <InstrumentFrame caption="OSHA 300A · summary" foot="Tallies auto-populate — export any time">
      <div ref={ref}>
        <div key={cycle} className="grid grid-cols-3 rounded-lg overflow-hidden border" style={{ borderColor: CARD_LINE }}>
          {tiles.map((t, i) => (
            <OshaTile key={t.label} label={t.label} target={t.target} lit={t.lit} active={inView} last={i === tiles.length - 1} />
          ))}
        </div>
        <div className="mt-4 flex items-center gap-2">
          <PulseDot size={5} />
          <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>Export-ready, any time</span>
        </div>
      </div>
    </InstrumentFrame>
  )
}

function OshaTile({ label, target, lit, active, last }: { label: string; target: number; lit?: boolean; active: boolean; last: boolean }) {
  const value = useCountUp(target, active, 900)
  return (
    <div className="px-3 py-4" style={{ borderRight: last ? undefined : `1px solid ${CARD_LINE}` }}>
      <div className="text-[8px] font-mono uppercase tracking-widest mb-1.5" style={{ color: CARD_MUTED }}>{label}</div>
      <div className="tabular-nums leading-none" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.75rem', color: lit ? GREEN : CARD_TEXT }}>{value}</div>
    </div>
  )
}

export const INSTRUMENTS: Record<string, () => React.ReactElement> = {
  incidents: IntakeInstrument,
  hris: RosterInstrument,
  ir_analysis: AnalysisInstrument,
  osha: OshaInstrument,
}
