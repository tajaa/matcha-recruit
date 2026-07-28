import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

import { ASH, BONE, LINE_D } from '../../home/theme'
import { InstrumentFrame, useCyclingIndex, useReducedMotion } from '../../home/instruments/shared'

// ---------------------------------------------------------------------------
// Three pillar instruments (pillar 04 renders home's OshaLogInstrument
// instead — see PillarsGrid.tsx; the old OshaInstrument here printed negative
// tallies for a frame on mount, the same unclamped useCountUp bug removed
// from Platform/hooks.ts, and is superseded rather than fixed).
//
// Every element here PAINTS COMPLETE AT REST — ambient cycling only changes
// which item is highlighted, never whether something exists at all.
// ---------------------------------------------------------------------------

const INCIDENTS_ACCENT = '#86efac'
const HRIS_ACCENT = '#7FB2C9'
const ANALYSIS_ACCENT = '#F2C14E'

// 01 — magic-link intake: a text arrives, resolves to logged. Already safe at
// rest (AnimatePresence always renders exactly one of the two branches).
function IntakeInstrument() {
  const [logged, setLogged] = useState(false)
  useEffect(() => {
    const t = setInterval(() => setLogged((v) => !v), 5200)
    return () => clearInterval(t)
  }, [])
  return (
    <InstrumentFrame label="Magic link · intake" accent={INCIDENTS_ACCENT}>
      <div className="flex items-center justify-center py-6 px-5" style={{ minHeight: 96 }}>
        <AnimatePresence mode="wait">
          {!logged ? (
            <motion.div
              key="text"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.35 }}
              className="max-w-[280px] rounded-2xl rounded-bl-sm px-4 py-3 text-[13px] border"
              style={{ backgroundColor: BONE, borderColor: LINE_D, color: '#14210B', lineHeight: 1.4 }}
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
              <span style={{ color: INCIDENTS_ACCENT, fontSize: '1.1rem' }}>✓</span>
              <span style={{ fontFamily: "var(--font-lite)", fontWeight: 400, fontSize: '1.4rem', color: BONE }}>
                Logged.
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      <div className="px-5 pb-4 pt-3 border-t flex items-center justify-between" style={{ borderColor: LINE_D }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: ASH }}>Dallas — Store 3</span>
        <span className="text-[11px] font-mono" style={{ color: BONE }}>Reported in seconds</span>
      </div>
    </InstrumentFrame>
  )
}

// 02 — HRIS/CSV roster sources, always rendered; cycling moves which source
// is highlighted as "connected".
function RosterInstrument() {
  const reduce = useReducedMotion()
  const sources = ['Gusto', 'Rippling', 'BambooHR', 'ADP', 'CSV']
  const active = useCyclingIndex(sources.length, 1400, reduce)
  return (
    <InstrumentFrame label="Roster · import" accent={HRIS_ACCENT}>
      <div className="flex flex-wrap justify-center gap-2 px-5 pt-6 pb-2">
        {sources.map((s, i) => (
          <span
            key={s}
            className="px-3 py-1.5 rounded-full text-[11px] font-mono uppercase tracking-wider border transition-colors duration-300"
            style={{
              color: i === active ? BONE : ASH,
              borderColor: i === active ? HRIS_ACCENT : LINE_D,
              fontWeight: i === active ? 600 : 400,
            }}
          >
            {s}
          </span>
        ))}
      </div>
      <div className="px-5 pb-4 pt-4 border-t flex items-center justify-between" style={{ borderColor: LINE_D }}>
        <span className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full home-pulse" style={{ backgroundColor: HRIS_ACCENT }} />
          <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: ASH }}>Synced</span>
        </span>
        <span className="text-[11px] font-mono" style={{ color: BONE }}>312 employees</span>
      </div>
    </InstrumentFrame>
  )
}

// 03 — recent incidents; always rendered, cycling moves which row is flagged.
const ANALYSIS_ROWS = [
  { loc: 'Atlanta — Store 7', type: 'Customer escalation', sev: 'High' },
  { loc: 'Phoenix — Warehouse', type: 'Slip / fall', sev: 'Med' },
  { loc: 'Dallas — Store 3', type: 'Near-miss', sev: 'Low' },
]

function AnalysisInstrument() {
  const reduce = useReducedMotion()
  const litIndex = useCyclingIndex(ANALYSIS_ROWS.length, 2400, reduce)
  return (
    <InstrumentFrame label="Incidents · analysis" accent={ANALYSIS_ACCENT}>
      <div className="px-5 pt-5 pb-5 flex flex-col gap-3">
        {ANALYSIS_ROWS.map((r, i) => {
          const lit = i === litIndex
          return (
            <div key={r.loc} className="flex items-center gap-3">
              <span
                className="block rounded-full shrink-0 transition-all duration-500"
                style={{
                  width: lit ? 8 : 6,
                  height: lit ? 8 : 6,
                  backgroundColor: lit ? ANALYSIS_ACCENT : LINE_D,
                  boxShadow: lit ? `0 0 8px ${ANALYSIS_ACCENT}` : 'none',
                }}
              />
              <span
                className="flex-1 min-w-0 text-[12px] truncate transition-colors duration-500"
                style={{ color: lit ? BONE : ASH, fontWeight: lit ? 600 : 400 }}
              >
                {r.loc}
              </span>
              <span className="text-[10px] font-mono truncate hidden sm:inline shrink-0" style={{ color: ASH }}>{r.type}</span>
              <span
                className="text-[9px] font-mono uppercase tracking-wider shrink-0 w-10 text-right transition-colors duration-500"
                style={{ color: lit ? ANALYSIS_ACCENT : ASH }}
              >
                {r.sev}
              </span>
            </div>
          )
        })}
      </div>
      <div className="px-5 pb-4 pt-3 border-t flex items-center justify-between" style={{ borderColor: LINE_D }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: ANALYSIS_ACCENT }}>Pattern detected</span>
        <span className="text-[11px] font-mono" style={{ color: BONE }}>A repeat, surfaced early</span>
      </div>
    </InstrumentFrame>
  )
}

export const INSTRUMENTS: Record<string, () => React.ReactElement> = {
  incidents: IntakeInstrument,
  hris: RosterInstrument,
  ir_analysis: AnalysisInstrument,
}
