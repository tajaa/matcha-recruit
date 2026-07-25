import { ASH, BONE, LEAF, LINE_D } from '../../home/theme'
import { InstrumentFrame, useCyclingIndex, useReducedMotion } from '../../home/instruments/shared'
import { BAND_COLOR } from './data'

// ---------------------------------------------------------------------------
// Three pillar instruments, rebuilt on the shared noir InstrumentFrame. Every
// element PAINTS COMPLETE AT REST — ambient cycling only changes which item
// is highlighted, never whether something exists at all (the old versions
// animated in from opacity:0/width:0 on whileInView, which is exactly what
// screenshots as an empty instrument if the observer hasn't fired yet).
// ---------------------------------------------------------------------------

// 01 — risk-band ladder; bars always at full width, cycling moves which band
// is "the account", lit.
const BANDS = [
  { label: 'Strong', w: 30 },
  { label: 'Adequate', w: 52 },
  { label: 'Developing', w: 74 },
  { label: 'Exposed', w: 96 },
]

function RiskCurveInstrument() {
  const reduce = useReducedMotion()
  const litIndex = useCyclingIndex(BANDS.length, 2200, reduce)
  const accent = BAND_COLOR.critical
  return (
    <InstrumentFrame label="Book · risk curve" accent={accent}>
      <div className="px-5 pt-6 pb-5 flex flex-col gap-3">
        {BANDS.map((b, i) => {
          const lit = i === litIndex
          return (
            <div key={b.label} className="flex items-center gap-4">
              <div
                className="w-20 shrink-0 text-[10px] font-mono uppercase tracking-wider text-right transition-colors duration-500"
                style={{ color: lit ? BONE : ASH, fontWeight: lit ? 600 : 400 }}
              >
                {b.label}
              </div>
              <div className="relative flex-1 h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'rgba(245,242,237,0.04)' }}>
                <div
                  className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
                  style={{
                    width: `${b.w}%`,
                    backgroundColor: lit ? accent : LINE_D,
                    boxShadow: lit ? `0 0 8px ${accent}` : 'none',
                  }}
                />
              </div>
            </div>
          )
        })}
      </div>
      <div className="px-5 pb-4 pt-3 border-t" style={{ borderColor: LINE_D }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.12em]" style={{ color: ASH }}>
          The account deteriorating before its re-rate
        </span>
      </div>
    </InstrumentFrame>
  )
}

// 02 — WC portfolio rows, always rendered; cycling moves which client "needs
// a call".
const WC_ROWS = ['Northgate Logistics', 'Cedar Valley Mfg', 'Harbor Foods Co', 'Summit Builders']

function WcInstrument() {
  const reduce = useReducedMotion()
  const litIndex = useCyclingIndex(WC_ROWS.length, 2600, reduce)
  const accent = BAND_COLOR.elevated
  return (
    <InstrumentFrame label="The book · ranked" accent={accent}>
      <div className="px-5 pt-5 pb-5 flex flex-col gap-3.5">
        {WC_ROWS.map((client, i) => {
          const lit = i === litIndex
          return (
            <div key={client} className="flex items-center gap-3">
              <span
                className="flex-1 min-w-0 text-[12px] truncate transition-colors duration-500"
                style={{ color: lit ? BONE : ASH, fontWeight: lit ? 600 : 400 }}
              >
                {client}
              </span>
              {lit ? (
                <span className="flex items-center gap-1.5 shrink-0 w-24 justify-end">
                  <span className="w-1.5 h-1.5 rounded-full home-pulse" style={{ backgroundColor: accent }} />
                  <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: accent }}>Needs a call</span>
                </span>
              ) : (
                <span className="text-[9px] font-mono uppercase tracking-wider shrink-0 w-24 text-right" style={{ color: ASH }}>Stable</span>
              )}
            </div>
          )
        })}
      </div>
      <div className="px-5 pb-4 pt-3 border-t" style={{ borderColor: LINE_D }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.12em]" style={{ color: ASH }}>
          The account that needs you, first
        </span>
      </div>
    </InstrumentFrame>
  )
}

// 03 — action queue, always rendered; cycling moves which alert is urgent.
const ALERTS = [
  { client: 'Northgate Logistics', issue: 'Safety trend deteriorating' },
  { client: 'Cedar Valley Mfg', issue: 'Running above the book' },
  { client: 'Atlas Care Group', issue: 'Rising incident volume' },
]

function CommandInstrument() {
  const reduce = useReducedMotion()
  const litIndex = useCyclingIndex(ALERTS.length, 2400, reduce)
  const accent = BAND_COLOR.stable
  return (
    <InstrumentFrame label="Command center · queue" accent={accent}>
      <div className="px-5 pt-5 pb-5 flex flex-col gap-3.5">
        {ALERTS.map((a, i) => {
          const lit = i === litIndex
          return (
            <div key={a.client} className="flex items-start gap-3">
              <span
                className="mt-1 shrink-0 block rounded-full transition-all duration-500"
                style={{
                  width: lit ? 8 : 6,
                  height: lit ? 8 : 6,
                  backgroundColor: lit ? accent : 'transparent',
                  border: lit ? 'none' : `1px solid ${LINE_D}`,
                  boxShadow: lit ? `0 0 8px ${accent}` : 'none',
                }}
              />
              <div className="min-w-0 flex-1">
                <div className="text-[12px] transition-colors duration-500" style={{ color: lit ? BONE : ASH, fontWeight: lit ? 600 : 400 }}>{a.client}</div>
                <div className="text-[10.5px] mt-0.5" style={{ color: ASH }}>{a.issue}</div>
              </div>
              <span className="text-[9px] font-mono uppercase tracking-wider shrink-0 transition-colors duration-500" style={{ color: lit ? accent : ASH }}>
                {lit ? 'Urgent' : 'Advisory'}
              </span>
            </div>
          )
        })}
      </div>
      <div className="px-5 pb-4 pt-3 border-t" style={{ borderColor: LINE_D }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.12em]" style={{ color: ASH }}>
          Each flagged trend, an outreach already drafted
        </span>
      </div>
    </InstrumentFrame>
  )
}

// 04 — submission packet preview; always rendered, cycling moves which stat
// chip is emphasized (mirrors the real /broker/clients/:id Submission tab's
// preview chips, without showing how readiness is scored).
const PACKET_CHIPS = [
  { label: 'TRIR', value: '2.8' },
  { label: 'DART', value: '1.4' },
  { label: 'Exp. mod', value: '1.12' },
  { label: 'EPL', value: '62/100' },
  { label: 'Readiness', value: '78%' },
]
const PACKET_SECTIONS = ['Loss summary', 'EPL readiness', 'Controls evidence', 'Broker commentary']

function SubmissionInstrument() {
  const reduce = useReducedMotion()
  const litIndex = useCyclingIndex(PACKET_CHIPS.length, 2200, reduce)
  const accent = BAND_COLOR.critical
  return (
    <InstrumentFrame label="Submission · packet preview" accent={accent}>
      <div className="px-5 pt-5 grid grid-cols-3 gap-3">
        {PACKET_CHIPS.map((c, i) => {
          const lit = i === litIndex
          return (
            <div
              key={c.label}
              className="rounded-lg px-3 py-2.5 text-center transition-colors duration-500"
              style={{ backgroundColor: lit ? 'rgba(245,242,237,0.05)' : 'rgba(245,242,237,0.02)', border: `1px solid ${lit ? accent : LINE_D}` }}
            >
              <div className="text-[13px] tabular-nums" style={{ color: lit ? BONE : ASH, fontWeight: lit ? 600 : 400 }}>{c.value}</div>
              <div className="text-[8.5px] font-mono uppercase tracking-wider mt-0.5" style={{ color: ASH }}>{c.label}</div>
            </div>
          )
        })}
      </div>
      <div className="px-5 pt-4 pb-5 flex flex-col gap-2">
        <div className="text-[9px] font-mono uppercase tracking-[0.14em]" style={{ color: ASH }}>Sections included</div>
        <div className="flex flex-wrap gap-1.5">
          {PACKET_SECTIONS.map((s) => (
            <span key={s} className="text-[10px] px-2.5 py-1 rounded-full" style={{ color: ASH, border: `1px solid ${LINE_D}` }}>
              {s}
            </span>
          ))}
        </div>
      </div>
      <div className="px-5 pb-4 pt-3 border-t" style={{ borderColor: LINE_D }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.12em]" style={{ color: ASH }}>
          The terms-winning artifact, one export away
        </span>
      </div>
    </InstrumentFrame>
  )
}

// 05 — Broker Pilot console preview; always rendered, cycling moves which
// grounded observation is highlighted. Citation chips are illustrative
// record ids, not the platform's real cid namespace.
const PILOT_OBSERVATIONS = [
  { text: 'Quoted premium sits 14% below the loss-supported range.', cite: 'loss-run:2026' },
  { text: 'Indemnity clause requires $2M; client carries $1M.', cite: 'contract:p.4' },
  { text: 'EPL readiness data is thin for two of five factors.', cite: 'epl:readiness' },
]

function PilotInstrument() {
  const reduce = useReducedMotion()
  const litIndex = useCyclingIndex(PILOT_OBSERVATIONS.length, 2600, reduce)
  const accent = BAND_COLOR.elevated
  return (
    <InstrumentFrame label="Broker Pilot · console" accent={accent}>
      <div className="px-5 pt-5">
        <div className="text-[11.5px] leading-relaxed" style={{ color: ASH }}>
          The record is assembled —{' '}
          <span style={{ color: BONE, fontWeight: 600 }}>1,284 records</span> across{' '}
          <span style={{ color: BONE, fontWeight: 600 }}>23 systems</span> are in scope.
        </div>
      </div>
      <div className="px-5 pt-4 pb-5 flex flex-col gap-3">
        {PILOT_OBSERVATIONS.map((o, i) => {
          const lit = i === litIndex
          return (
            <div key={o.cite} className="flex items-start gap-2.5">
              <span
                className="mt-1.5 shrink-0 block rounded-full transition-all duration-500"
                style={{
                  width: lit ? 6 : 5,
                  height: lit ? 6 : 5,
                  backgroundColor: lit ? LEAF : 'transparent',
                  border: lit ? 'none' : `1px solid ${LINE_D}`,
                }}
              />
              <div className="min-w-0 flex-1">
                <div className="text-[12px] transition-colors duration-500" style={{ color: lit ? BONE : ASH, fontWeight: lit ? 600 : 400 }}>
                  {o.text}
                </div>
                <div className="text-[9.5px] font-mono mt-0.5" style={{ color: lit ? LEAF : ASH }}>[{o.cite}]</div>
              </div>
            </div>
          )
        })}
      </div>
      <div className="px-5 pb-4 pt-3 border-t" style={{ borderColor: LINE_D }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.12em]" style={{ color: ASH }}>
          Every answer cites the record it came from
        </span>
      </div>
    </InstrumentFrame>
  )
}

export const INSTRUMENTS: Record<string, () => React.ReactElement> = {
  'risk-curve': RiskCurveInstrument,
  wc: WcInstrument,
  command: CommandInstrument,
  submission: SubmissionInstrument,
  pilot: PilotInstrument,
}
