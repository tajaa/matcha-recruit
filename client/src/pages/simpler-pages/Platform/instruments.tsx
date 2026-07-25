import { ASH, BONE, LINE_D } from '../../home/theme'
import { InstrumentFrame, useCyclingIndex, useReducedMotion } from '../../home/instruments/shared'

// ---------------------------------------------------------------------------
// Three pillar instruments (pillar 04 renders AgentReasoningAnimation instead
// — see PillarsGrid.tsx). Rebuilt on the shared noir InstrumentFrame so they
// get real lift/glow/pulse chrome instead of a flat bordered box.
//
// Unlike the old versions, every element here PAINTS COMPLETE AT REST — ambient
// cycling only changes which item is highlighted (color/opacity of an already-
// rendered element), never whether something exists at all. Motion that starts
// from opacity:0/width:0 screenshots as an empty instrument, which is exactly
// what the pre-rebuild audit flagged on this page and on /matcha-compliance.
// ---------------------------------------------------------------------------

const EHS_ACCENT = '#d9b65f'
const GRC_ACCENT = '#E2725B'
const ER_ACCENT = '#86efac'

// 01 — incident lifecycle. Base state (3 static steps + connector) always
// visible; cycling only moves which step is "active".
function IntakeInstrument() {
  const reduce = useReducedMotion()
  const step = useCyclingIndex(3, 1800, reduce)
  const steps = ['Reported', 'Scored', 'Routed']
  return (
    <InstrumentFrame label="Incident · intake" accent={EHS_ACCENT}>
      <div className="px-5 pt-6 pb-5">
        <div className="flex items-center justify-center gap-3">
          {steps.map((s, i) => {
            const active = i <= step
            return (
              <div key={s} className="flex items-center gap-3">
                <div className="flex flex-col items-center gap-2">
                  <span
                    className="rounded-full transition-colors duration-500"
                    style={{
                      width: 8,
                      height: 8,
                      backgroundColor: active ? EHS_ACCENT : LINE_D,
                      boxShadow: active ? `0 0 8px ${EHS_ACCENT}` : 'none',
                    }}
                  />
                  <span
                    className="text-[10px] font-mono uppercase tracking-wider transition-colors duration-500"
                    style={{ color: active ? BONE : ASH }}
                  >
                    {s}
                  </span>
                </div>
                {i < steps.length - 1 && (
                  <span
                    className="h-px w-8 transition-colors duration-500"
                    style={{ backgroundColor: i < step ? EHS_ACCENT : LINE_D }}
                  />
                )}
              </div>
            )
          })}
        </div>
      </div>
      <div className="px-5 pb-4 pt-3 border-t flex items-center justify-between" style={{ borderColor: LINE_D }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: ASH }}>Atlanta — Store 7</span>
        <span className="text-[11px] font-mono" style={{ color: BONE }}>In the right hands</span>
      </div>
    </InstrumentFrame>
  )
}

// 02 — compliance monitor rows, always rendered; cycling moves which row is
// flagged.
function GovernanceInstrument() {
  const reduce = useReducedMotion()
  const flaggedIndex = useCyclingIndex(4, 2600, reduce)
  const rows = [
    { j: 'A', label: 'Wage & hour rules' },
    { j: 'B', label: 'Break requirements' },
    { j: 'C', label: 'Leave policies' },
    { j: 'D', label: 'Scheduling rules' },
  ]
  return (
    <InstrumentFrame label="Compliance · monitor" accent={GRC_ACCENT}>
      <div className="px-5 pt-5 pb-5 flex flex-col gap-3.5">
        {rows.map((r, i) => {
          const lit = i === flaggedIndex
          return (
            <div key={r.label} className="flex items-center gap-3">
              <span className="w-9 shrink-0 text-[9px] font-mono uppercase tracking-wider" style={{ color: ASH }}>{r.j}</span>
              <span
                className="flex-1 min-w-0 text-[12px] truncate transition-colors duration-500"
                style={{ color: lit ? BONE : ASH, fontWeight: lit ? 600 : 400 }}
              >
                {r.label}
              </span>
              <span
                className="flex items-center gap-1.5 shrink-0 text-[9px] font-mono uppercase tracking-wider transition-colors duration-500"
                style={{ color: lit ? GRC_ACCENT : ASH }}
              >
                {lit && (
                  <span
                    className="w-1.5 h-1.5 rounded-full home-pulse"
                    style={{ backgroundColor: GRC_ACCENT }}
                  />
                )}
                {lit ? 'Flagged' : 'Clear'}
              </span>
            </div>
          )
        })}
      </div>
      <div className="px-5 pb-4 pt-3 border-t" style={{ borderColor: LINE_D }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.12em]" style={{ color: ASH }}>
          Deltas flagged before they take effect
        </span>
      </div>
    </InstrumentFrame>
  )
}

// 03 — case cluster. All 15 nodes always rendered; cycling moves which 3-node
// cluster (in scan order) is highlighted as the detected repeat.
const CLUSTERS = [
  [2, 7, 12],
  [1, 6, 11],
  [3, 8, 13],
]

function CaseInstrument() {
  const reduce = useReducedMotion()
  const clusterIndex = useCyclingIndex(CLUSTERS.length, 3000, reduce)
  const lit = new Set(CLUSTERS[clusterIndex])
  return (
    <InstrumentFrame label="Cases · pattern" accent={ER_ACCENT}>
      <div className="px-5 pt-6 pb-5">
        <div className="grid grid-cols-5 gap-y-4 gap-x-3 place-items-center py-1">
          {Array.from({ length: 15 }).map((_, i) => {
            const active = lit.has(i)
            return (
              <span
                key={i}
                className="block rounded-full transition-all duration-500"
                style={{
                  width: active ? 8 : 6,
                  height: active ? 8 : 6,
                  backgroundColor: active ? ER_ACCENT : LINE_D,
                  boxShadow: active ? `0 0 8px ${ER_ACCENT}` : 'none',
                }}
              />
            )
          })}
        </div>
      </div>
      <div className="px-5 pb-4 pt-3 border-t flex items-center justify-between" style={{ borderColor: LINE_D }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: ER_ACCENT }}>Pattern found</span>
        <span className="text-[11px] font-mono" style={{ color: BONE }}>A repeat, one location</span>
      </div>
    </InstrumentFrame>
  )
}

export const INSTRUMENTS: Record<string, () => React.ReactElement> = {
  ehs: IntakeInstrument,
  grc: GovernanceInstrument,
  er: CaseInstrument,
}
