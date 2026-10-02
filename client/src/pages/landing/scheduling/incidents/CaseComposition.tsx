/**
 * Remotion composition for the Incidents hero: Ana's report types in, the
 * handbook check marks the clause it breaks and fills past the 60% line, and
 * the case card rides the HR Cases board from New to Done while its history
 * fills in underneath.
 *
 * The board columns, stage names, checklist and threshold are the product's
 * own (hr_cases); the café, people and times are the illustrative case that
 * the rest of the tab tells.
 */
import type { CSSProperties, ReactNode } from 'react'
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { BOARD, BODY, MONO, hexA } from '../../../../components/marketing/kit/theme'
import type { Variant } from '../timeline'
import { CASE_DURATION, CASE_SIZES, COLUMNS, EVENTS, K, type Tone } from './timeline'

const INK = BOARD.INK
const SOFT = BOARD.INK_SOFT
const CARD = BOARD.CARD
const RULE = hexA(INK, 0.1)
const TONE: Record<Tone, string> = { red: BOARD.RED_PEN, amber: BOARD.AMBER, green: BOARD.STAMP }

const TEXT = 'Jonah missed his Tue, Thu and Sat opens. No call, no text. We covered the open each time.'
const POLICY = [
  { t: 'If you can’t work a scheduled shift, tell your shift lead at least 2 hours before it starts.', hit: false },
  { t: 'Three (3) no-call/no-shows within any rolling 30-day period is grounds for termination.', hit: true },
  { t: 'Absences protected by law are never counted.', hit: false },
]
const THRESHOLD = 60
const CONFIDENCE = 98

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const

type Kit = {
  frame: number
  s: number
  mono: (size: number, extra?: CSSProperties) => CSSProperties
  appear: (at: number) => CSSProperties
}

export default function CaseComposition({ variant }: { variant: Variant }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { s } = CASE_SIZES[variant]
  const wide = variant === 'wide'

  const appear = (at: number): CSSProperties => {
    const p = spring({ frame: frame - at, fps, config: { damping: 18, stiffness: 170 } })
    return { opacity: interpolate(frame, [at, at + 6], [0, 1], clamp), transform: `translateY(${(1 - p) * 12 * s}px)` }
  }
  const mono = (size: number, extra?: CSSProperties): CSSProperties => ({
    fontFamily: MONO,
    fontSize: size * s,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    ...extra,
  })
  const kit: Kit = { frame, s, mono, appear }

  // where the card is on the board: a float from 0 (New) to 4 (Done), each
  // stage change springing it one column along
  let pos = 0
  for (let i = 1; i < EVENTS.length; i++) {
    const d = EVENTS[i].col - EVENTS[i - 1].col
    if (d) pos += d * spring({ frame: frame - EVENTS[i].at, fps, config: { damping: 16, stiffness: 120 } })
  }
  const current = [...EVENTS].reverse().find((e) => frame >= e.at)
  const clock = current?.when ?? 'Tue 8:02 AM'
  const out = interpolate(frame, [K.fadeOut, CASE_DURATION], [1, 0], clamp)

  return (
    <AbsoluteFill style={{ backgroundColor: BOARD.PAPER, fontFamily: BODY, color: INK }}>
      <AbsoluteFill style={{ opacity: out, padding: (wide ? 0 : 28) * s, display: 'flex', flexDirection: 'column' }}>
        {/* header: the café's HR cases, and the clock the story runs on */}
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 16 * s, padding: wide ? `${6}px 48px 0` : 0 }}>
          <span style={{ fontWeight: 500, fontSize: 24 * s, letterSpacing: '-0.025em', opacity: interpolate(frame, [0, 10], [0, 1], clamp) }}>
            Juniper Café <span style={{ color: SOFT }}>· HR cases</span>
          </span>
          <span style={mono(11, { color: INK, fontVariantNumeric: 'tabular-nums' })}>{clock}</span>
        </div>

        {wide ? (
          <div style={{ flex: 1, display: 'flex', gap: 40, padding: '28px 48px 40px' }}>
            <div style={{ width: 520, display: 'flex', flexDirection: 'column', gap: 18 }}>
              <IncidentCard kit={kit} />
              <HandbookCard kit={kit} />
              <NoticeCard kit={kit} />
            </div>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 22 }}>
              <BoardColumns kit={kit} pos={pos} current={current} />
              <History kit={kit} />
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 18 * s, paddingTop: 22 * s }}>
            <IncidentCard kit={kit} compact />
            <HandbookCard kit={kit} compact />
            <BoardLanes kit={kit} pos={pos} current={current} />
          </div>
        )}
      </AbsoluteFill>
    </AbsoluteFill>
  )
}

function Panel({ kit, title, right, children, style }: { kit: Kit; title: ReactNode; right?: ReactNode; children: ReactNode; style?: CSSProperties }) {
  const { s, mono } = kit
  return (
    <div style={{ backgroundColor: CARD, borderRadius: 18 * s, boxShadow: `inset 0 0 0 1px ${hexA(INK, 0.07)}`, padding: `${16 * s}px ${18 * s}px`, ...style }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 * s, ...mono(9.5, { color: SOFT }) }}>
        <span>{title}</span>
        {right && <span>{right}</span>}
      </div>
      {children}
    </div>
  )
}

function Dot({ s, color, size = 6 }: { s: number; color: string; size?: number }) {
  return <span style={{ display: 'inline-block', width: size * s, height: size * s, borderRadius: 99, backgroundColor: color, flexShrink: 0 }} />
}

/** Ana's report, typed on her phone and submitted. */
function IncidentCard({ kit, compact }: { kit: Kit; compact?: boolean }) {
  const { frame, s, mono, appear } = kit
  const typed = Math.floor(interpolate(frame, [K.type, K.typeEnd], [0, TEXT.length], clamp))
  const filed = frame >= K.submit
  const press = frame >= K.submit - 6 && frame < K.submit + 2 ? interpolate(frame, [K.submit - 6, K.submit - 3, K.submit + 2], [1, 0.93, 1], clamp) : 1
  return (
    <Panel kit={kit} title={<><span style={{ color: INK }}>Incident report</span> · Ana R., shift lead</>} right={filed ? 'IR-2026-10-3F78' : 'Draft'} style={appear(K.incident)}>
      <div style={{ marginTop: 12 * s, fontSize: (compact ? 15 : 17) * s, lineHeight: 1.5, minHeight: (compact ? 66 : 78) * s, color: INK }}>
        {TEXT.slice(0, typed)}
        {!filed && frame >= K.type - 8 && Math.floor(frame / 8) % 2 === 0 && (
          <span style={{ display: 'inline-block', width: 1.5 * s, height: 17 * s, marginLeft: 1, verticalAlign: 'text-bottom', backgroundColor: INK }} />
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 * s, marginTop: 12 * s }}>
        <span style={{ display: 'flex', gap: 8 * s }}>
          {['Jonah B.', 'Downtown'].map((c) => (
            <span key={c} style={{ ...mono(9, { color: SOFT }), padding: `${4 * s}px ${8 * s}px`, borderRadius: 99, backgroundColor: hexA(INK, 0.06) }}>
              {c}
            </span>
          ))}
        </span>
        {filed ? (
          <span style={{ ...mono(9.5, { color: BOARD.STAMP }), display: 'flex', alignItems: 'center', gap: 7 * s, ...appear(K.submit) }}>
            <Dot s={s} color={BOARD.STAMP} />
            Filed 8:02 AM
          </span>
        ) : (
          <span style={{ fontSize: 13 * s, fontWeight: 500, padding: `${6 * s}px ${14 * s}px`, borderRadius: 99, backgroundColor: typed === TEXT.length ? INK : hexA(INK, 0.12), color: BOARD.PAPER, transform: `scale(${press})` }}>
            Submit
          </span>
        )}
      </div>
    </Panel>
  )
}

/** The handbook check: a scan line passes over the policy, marks the clause
 *  it breaks, and the confidence fills past the opening threshold. */
function HandbookCard({ kit, compact }: { kit: Kit; compact?: boolean }) {
  const { frame, s, mono, appear } = kit
  const lines = compact ? POLICY.slice(0, 2) : POLICY
  const scan = interpolate(frame, [K.scan, K.scanEnd], [0, 1], clamp)
  const scanning = frame >= K.scan && frame < K.scanEnd + 4
  const mark = interpolate(frame, [K.mark, K.mark + 14], [0, 100], clamp)
  const conf = interpolate(frame, [K.bar, K.barEnd], [0, CONFIDENCE], clamp)
  const opened = frame >= K.opened
  return (
    <Panel kit={kit} title={<><span style={{ color: INK }}>Handbook check</span> · Attendance and Punctuality</>} right={frame >= K.barEnd ? '+10 s' : frame >= K.check ? 'Reading…' : ''} style={appear(K.check)}>
      <div style={{ position: 'relative', marginTop: 12 * s, display: 'flex', flexDirection: 'column', gap: 8 * s }}>
        {lines.map((l) => (
          <p key={l.t} style={{ margin: 0, fontSize: (compact ? 13.5 : 15) * s, lineHeight: 1.5, color: l.hit && frame >= K.mark ? INK : SOFT }}>
            <span
              style={
                l.hit
                  ? {
                      backgroundImage: `linear-gradient(${hexA(BOARD.RED_PEN, 0.26)}, ${hexA(BOARD.RED_PEN, 0.26)})`,
                      backgroundRepeat: 'no-repeat',
                      backgroundSize: `${mark}% 100%`,
                      boxShadow: frame >= K.mark + 10 ? `inset 0 -${1.5 * s}px 0 ${BOARD.RED_PEN}` : undefined,
                      padding: `0 ${2 * s}px`,
                      WebkitBoxDecorationBreak: 'clone',
                      boxDecorationBreak: 'clone',
                    }
                  : undefined
              }
            >
              {l.t}
            </span>
          </p>
        ))}
        {scanning && (
          <span
            style={{ position: 'absolute', left: -6 * s, right: -6 * s, top: `${scan * 100}%`, height: 2 * s, backgroundColor: BOARD.STAMP, boxShadow: `0 0 ${14 * s}px ${hexA(BOARD.STAMP, 0.7)}`, borderRadius: 99 }}
          />
        )}
      </div>
      <div style={{ marginTop: 16 * s, opacity: interpolate(frame, [K.bar - 4, K.bar + 4], [0, 1], clamp) }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', ...mono(9.5, { color: SOFT }) }}>
          <span>
            <span style={{ color: BOARD.RED_PEN }}>Violated</span> · {Math.round(conf)}%
          </span>
          <span>Opens a case at {THRESHOLD}%</span>
        </div>
        <div style={{ position: 'relative', height: 6 * s, marginTop: 8 * s, borderRadius: 99, backgroundColor: hexA(INK, 0.08) }}>
          <div style={{ height: '100%', width: `${conf}%`, borderRadius: 99, backgroundColor: conf >= THRESHOLD ? BOARD.RED_PEN : SOFT }} />
          <span style={{ position: 'absolute', left: `${THRESHOLD}%`, top: -4 * s, width: 1.5 * s, height: 14 * s, backgroundColor: INK }} />
        </div>
      </div>
      <div style={{ marginTop: 14 * s, minHeight: 22 * s }}>
        {opened && (
          <span style={{ ...mono(9.5, { color: INK }), display: 'inline-flex', alignItems: 'center', gap: 7 * s, ...appear(K.opened) }}>
            <Dot s={s} color={BOARD.RED_PEN} />
            Case HRC-2026-0001 opened
          </span>
        )}
      </div>
    </Panel>
  )
}

/** Who hears about it, and what the notice says: numbers and policy names,
 *  never the incident's narrative. */
function NoticeCard({ kit }: { kit: Kit }) {
  const { s, mono, appear } = kit
  const at = K.opened + 10
  return (
    <Panel kit={kit} title={<><span style={{ color: INK }}>Notified</span> · Tue 8:02 AM</>} style={{ ...appear(at), flex: 1 }}>
      <div style={{ marginTop: 12 * s, display: 'flex', flexDirection: 'column', gap: 10 * s }}>
        {[
          { who: 'AR', name: 'Ana R.', role: 'reported it' },
          { who: 'HR', name: 'HR', role: 'case owner' },
        ].map((r, i) => (
          <div key={r.who} style={{ display: 'flex', alignItems: 'center', gap: 12 * s, ...appear(at + 4 + i * 6) }}>
            <span style={{ width: 28 * s, height: 28 * s, borderRadius: 99, backgroundColor: hexA(INK, 0.1), display: 'inline-flex', alignItems: 'center', justifyContent: 'center', ...mono(9, { color: INK, letterSpacing: '0.02em' }) }}>
              {r.who}
            </span>
            <span style={{ fontSize: 15 * s }}>
              {r.name} <span style={{ color: SOFT }}>· {r.role}</span>
            </span>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 14 * s, ...mono(9, { color: SOFT, lineHeight: 1.6 }), ...appear(at + 18) }}>
        IR-2026-10-3F78 · HRC-2026-0001 · Attendance and Punctuality
        <div style={{ color: INK, marginTop: 4 * s }}>Numbers and policy names. Never the story.</div>
      </div>
    </Panel>
  )
}

/** The case card itself, as it sits on the board. */
function CaseCard({ kit, current, width }: { kit: Kit; current?: (typeof EVENTS)[number]; width: number | string }) {
  const { frame, s, mono } = kit
  const tone = current ? TONE[current.tone] : BOARD.RED_PEN
  const done = current?.done ?? 1
  const closed = frame >= K.closed
  return (
    <div
      style={{
        width,
        backgroundColor: hexA(INK, 0.97),
        color: BOARD.PAPER,
        borderRadius: 14 * s,
        padding: `${12 * s}px ${13 * s}px`,
        boxShadow: `0 ${18 * s}px ${36 * s}px -${16 * s}px rgba(0,0,0,.65), 0 0 0 ${closed ? 2 * s : 0}px ${BOARD.STAMP}`,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 * s, ...mono(8.5, { color: hexA(BOARD.PAPER, 0.6) }) }}>
        <span>HRC-2026-0001</span>
      </div>
      <div style={{ marginTop: 6 * s, fontSize: 16 * s, fontWeight: 600, letterSpacing: '-0.02em' }}>Jonah B.</div>
      <div style={{ marginTop: 2 * s, fontSize: 12 * s, color: hexA(BOARD.PAPER, 0.62) }}>Attendance and Punctuality</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 * s, marginTop: 10 * s, ...mono(8.5, { color: BOARD.PAPER, fontWeight: 600 }) }}>
        <span style={{ display: 'inline-block', width: 6 * s, height: 6 * s, borderRadius: 99, backgroundColor: tone }} />
        {current?.stage ?? 'Flagged'}
      </div>
      <div style={{ display: 'flex', gap: 3 * s, marginTop: 10 * s }}>
        {Array.from({ length: 7 }, (_, i) => (
          <span key={i} style={{ flex: 1, height: 3 * s, borderRadius: 99, backgroundColor: i < done ? (closed ? BOARD.STAMP : BOARD.PAPER) : hexA(BOARD.PAPER, 0.18) }} />
        ))}
      </div>
    </div>
  )
}

/** Other cases on the board, as skeletons: the board is a real queue, but
 *  only this case is the story. */
function Ghost({ s, h = 70 }: { s: number; h?: number }) {
  return (
    <div style={{ height: h * s, borderRadius: 14 * s, backgroundColor: hexA(INK, 0.04), boxShadow: `inset 0 0 0 1px ${hexA(INK, 0.05)}`, padding: 12 * s }}>
      <div style={{ width: '42%', height: 6 * s, borderRadius: 99, backgroundColor: hexA(INK, 0.1) }} />
      <div style={{ width: '70%', height: 8 * s, borderRadius: 99, backgroundColor: hexA(INK, 0.08), marginTop: 10 * s }} />
    </div>
  )
}

const GHOSTS = [0, 1, 0, 0, 2] // per column, under the case's slot

function BoardColumns({ kit, pos, current }: { kit: Kit; pos: number; current?: (typeof EVENTS)[number] }) {
  const { frame, s, mono, appear } = kit
  const gap = 12
  const colW = (1600 - 48 - 48 - 520 - 40 - gap * 4) / 5
  const occupied = Math.round(pos)
  return (
    <div style={{ position: 'relative', display: 'flex', gap, flex: 1, opacity: interpolate(frame, [4, 16], [0, 1], clamp) }}>
      {COLUMNS.map((c, i) => (
        <div key={c} style={{ width: colW, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', ...mono(9.5, { color: frame >= K.opened && occupied === i ? INK : SOFT }) }}>
            <span>{c}</span>
            <span>{GHOSTS[i] + (frame >= K.opened && occupied === i ? 1 : 0)}</span>
          </div>
          <div style={{ flex: 1, borderRadius: 16, backgroundColor: hexA(INK, 0.025), padding: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ height: 150 }} />
            {Array.from({ length: GHOSTS[i] }, (_, g) => (
              <Ghost key={g} s={s} />
            ))}
          </div>
        </div>
      ))}
      {frame >= K.opened && (
        <div style={{ position: 'absolute', top: 32, left: 8 + pos * (colW + gap), ...appear(K.opened) }}>
          <CaseCard kit={kit} current={current} width={colW - 16} />
        </div>
      )}
    </div>
  )
}

function History({ kit }: { kit: Kit }) {
  const { frame, s, mono, appear } = kit
  const shown = EVENTS.filter((e) => frame >= e.at).slice(-4)
  return (
    <div style={{ height: 196, borderTop: `1px solid ${RULE}`, paddingTop: 14 }}>
      <div style={mono(9.5, { color: SOFT })}>Case history</div>
      <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 9 }}>
        {shown.map((e) => (
          <div key={e.at} style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 15 * s, ...appear(e.at) }}>
            <span style={{ width: 120, ...mono(10, { color: SOFT }) }}>{e.when}</span>
            <Dot s={s} color={TONE[e.tone]} />
            <span>{e.text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Phone: the board's columns as stacked lanes, the card riding down. */
function BoardLanes({ kit, pos, current }: { kit: Kit; pos: number; current?: (typeof EVENTS)[number] }) {
  const { frame, s, mono, appear } = kit
  const laneH = 80 * s
  const labelW = 150 * s
  const occupied = Math.round(pos)
  return (
    <div style={{ opacity: interpolate(frame, [4, 16], [0, 1], clamp) }}>
      <div style={{ position: 'relative', borderTop: `1px solid ${RULE}` }}>
        {COLUMNS.map((c, i) => (
          <div key={c} style={{ height: laneH, display: 'flex', alignItems: 'center', borderBottom: `1px solid ${RULE}` }}>
            <span style={{ width: labelW, ...mono(9.5, { color: frame >= K.opened && occupied === i ? INK : SOFT }) }}>{c}</span>
          </div>
        ))}
        {frame >= K.opened && (
          <div style={{ position: 'absolute', left: labelW, right: 0, top: pos * laneH + 8 * s, height: laneH - 16 * s, display: 'flex', alignItems: 'center', ...appear(K.opened) }}>
            <LaneCard kit={kit} current={current} />
          </div>
        )}
      </div>
      <div style={{ marginTop: 14 * s, minHeight: 24 * s, display: 'flex', alignItems: 'center', gap: 10 * s, fontSize: 14 * s }}>
        {current && (
          <>
            <span style={mono(9.5, { color: SOFT })}>{current.when}</span>
            <Dot s={s} color={TONE[current.tone]} />
            <span key={current.at} style={appear(current.at)}>
              {current.text}
            </span>
          </>
        )}
      </div>
    </div>
  )
}

/** The lane version of the case card: one row, so it fits a lane. */
function LaneCard({ kit, current }: { kit: Kit; current?: (typeof EVENTS)[number] }) {
  const { frame, s, mono } = kit
  const tone = current ? TONE[current.tone] : BOARD.RED_PEN
  const closed = frame >= K.closed
  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        backgroundColor: hexA(INK, 0.97),
        color: BOARD.PAPER,
        borderRadius: 12 * s,
        padding: `0 ${12 * s}px`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 10 * s,
        boxShadow: `0 ${12 * s}px ${26 * s}px -${12 * s}px rgba(0,0,0,.6), 0 0 0 ${closed ? 2 * s : 0}px ${BOARD.STAMP}`,
      }}
    >
      <span style={{ fontSize: 14 * s, fontWeight: 600, letterSpacing: '-0.02em' }}>Jonah B.</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 6 * s, ...mono(8.5, { color: BOARD.PAPER, fontWeight: 600 }) }}>
        <span style={{ display: 'inline-block', width: 6 * s, height: 6 * s, borderRadius: 99, backgroundColor: tone }} />
        {current?.stage ?? 'Flagged'}
      </span>
    </div>
  )
}
