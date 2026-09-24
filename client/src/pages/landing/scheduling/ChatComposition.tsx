/**
 * Remotion composition for the "Change it in a sentence" section: a manager
 * asks @huume to move a shift, Huume proposes the edit with its effect on
 * hours and the checks it ran, the manager confirms, and the Tuesday column of
 * the schedule updates beside the chat.
 *
 * Same fictional café and crew as the hero (weekData.ts). Jonah's 32h → 40h is
 * his week *after* the hero's fixes, so the two animations agree.
 */
import type { CSSProperties } from 'react'
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { AMBER, BOARD, BODY, CARD, INK, INK_SOFT, MONO, PAPER, STAMP, hexA } from './theme'
import { C, CHAT_DURATION, CHAT_SIZES, type Variant } from './timeline'

const MESSAGE = '@huume give Dev’s Tuesday open to Jonah'
const MENTION = '@huume'
const CHECKS = ['available', 'qualified', '8h+ rest', 'no overtime']

const RULE = hexA(INK, 0.1)

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const

export default function ChatComposition({ variant }: { variant: Variant }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { s } = CHAT_SIZES[variant]
  const wide = variant === 'wide'

  const appear = (at: number): CSSProperties => {
    const p = spring({ frame: frame - at, fps, config: { damping: 18, stiffness: 170 } })
    return {
      opacity: interpolate(frame, [at, at + 6], [0, 1], clamp),
      transform: `translateY(${(1 - p) * 14 * s}px)`,
    }
  }
  const mono = (size: number, extra?: CSSProperties): CSSProperties => ({
    fontFamily: MONO,
    fontSize: size * s,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    ...extra,
  })

  const out = interpolate(frame, [C.fadeOut, CHAT_DURATION], [1, 0], clamp)
  const typedLen = Math.floor(interpolate(frame, [C.type, C.typeEnd], [0, MESSAGE.length], clamp))
  const sent = frame >= C.send
  const confirmed = frame >= C.confirmed
  const jonah = Math.round(interpolate(frame, [C.rows, C.rows + 22], [32, 40], clamp))
  const dev = Math.round(interpolate(frame, [C.rows, C.rows + 22], [32, 24], clamp))
  const pressScale = frame >= C.press && frame < C.press + 8 ? interpolate(frame, [C.press, C.press + 3, C.press + 8], [1, 0.92, 1], clamp) : 1
  const pulse = frame >= C.pulse && frame < C.press ? (Math.sin(((frame - C.pulse) / 30) * Math.PI * 2) + 1) / 2 : 0
  const move = spring({ frame: frame - C.confirmed - 6, fps, config: { damping: 15, stiffness: 110 } })

  return (
    <AbsoluteFill style={{ backgroundColor: PAPER }}>
      <AbsoluteFill
        style={{
          opacity: out,
          padding: (wide ? 34 : 28) * s,
          display: 'flex',
          flexDirection: wide ? 'row' : 'column',
          gap: (wide ? 34 : 26) * s,
          alignItems: 'stretch',
        }}
      >
        {/* ── channel window ───────────────────────────────────────────── */}
        <div
          style={{
            flex: wide ? '0 0 58%' : '1 1 auto',
            display: 'flex',
            flexDirection: 'column',
            backgroundColor: CARD,
            borderRadius: 14 * s,
            boxShadow: `0 0 0 1px ${RULE}, 0 1px 2px ${hexA(INK, 0.04)}, 0 30px 60px -36px ${hexA(INK, 0.3)}`,
            overflow: 'hidden',
            opacity: interpolate(frame, [0, 8], [0, 1], clamp),
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: `${16 * s}px ${22 * s}px`, borderBottom: `1px solid ${RULE}` }}>
            <span style={{ fontFamily: BODY, fontWeight: 500, fontSize: 20 * s, color: INK, letterSpacing: '-0.02em', lineHeight: 1 }}>
              <span style={{ color: INK_SOFT }}>#</span> mission-st
            </span>
            <span style={mono(11, { color: INK_SOFT })}>8 members</span>
          </div>

          {/* anchored to the composer like a real chat: any spare room reads as scrollback above */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 16 * s, padding: `${20 * s}px ${22 * s}px`, fontFamily: BODY, color: INK }}>
            {/* Ana */}
            <div style={{ display: 'flex', gap: 12 * s, ...appear(C.ana) }}>
              <Avatar s={s} bg={hexA(INK, 0.08)} fg={INK} text="AR" />
              <div>
                <div style={mono(10.5, { color: INK_SOFT })}>Ana R. · shift lead</div>
                <div style={{ fontSize: 17 * s, lineHeight: 1.4, marginTop: 4 * s }}>Dev’s at the dentist Tuesday morning. Can someone take his open?</div>
              </div>
            </div>

            {/* manager */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', ...(sent ? appear(C.send) : { opacity: 0 }) }}>
              <div style={{ maxWidth: '86%', backgroundColor: INK, color: PAPER, borderRadius: `${18 * s}px ${18 * s}px ${4 * s}px ${18 * s}px`, padding: `${10 * s}px ${16 * s}px`, fontSize: 17 * s, lineHeight: 1.35 }}>
                <span style={{ color: BOARD.STAMP, fontWeight: 500 }}>{MENTION}</span>
                {MESSAGE.slice(MENTION.length)}
              </div>
            </div>

            {/* huume */}
            <div style={{ display: 'flex', gap: 12 * s, position: 'relative' }}>
              <Avatar s={s} bg={INK} fg={PAPER} text="h" square style={{ opacity: interpolate(frame, [C.dots, C.dots + 6], [0, 1], clamp) }} />
              <div style={{ flex: 1, position: 'relative' }}>
                {frame >= C.dots && frame < C.card + 4 && (
                  <div style={{ position: 'absolute', top: 8 * s, display: 'flex', gap: 5 * s, opacity: interpolate(frame, [C.card, C.card + 4], [1, 0], clamp) }}>
                    {[0, 1, 2].map((i) => (
                      <span key={i} style={{ width: 8 * s, height: 8 * s, borderRadius: 99, backgroundColor: INK, opacity: 0.25 + 0.75 * Math.max(0, Math.sin((frame - C.dots) / 4 - i * 0.9)) }} />
                    ))}
                  </div>
                )}
                <div
                  style={{
                    ...appear(C.card),
                    backgroundColor: '#fff',
                    boxShadow: `0 0 0 ${1 * s}px ${confirmed ? hexA(STAMP, 0.6) : RULE}`,
                    borderRadius: 12 * s,
                    padding: `${14 * s}px ${16 * s}px`,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 * s, flexWrap: 'wrap' }}>
                    <span style={mono(10.5, { color: INK, display: 'flex', alignItems: 'center', gap: 7 * s })}>
                      <span style={{ width: 6 * s, height: 6 * s, borderRadius: 99, backgroundColor: confirmed ? STAMP : AMBER }} />
                      {confirmed ? 'Confirmed · reassign' : 'Proposed · reassign'}
                    </span>
                    <span style={mono(10.5, { color: INK_SOFT })}>Tue Oct 6 · 7a–3p · Barista</span>
                  </div>
                  <div style={{ fontSize: 21 * s, fontWeight: 500, letterSpacing: '-0.02em', marginTop: 10 * s }}>Dev P. → Jonah B.</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 14 * s, rowGap: 4 * s, marginTop: 10 * s, fontSize: 15 * s }}>
                    <span style={{ color: INK_SOFT }}>Jonah</span>
                    <span style={{ fontFamily: MONO }}>
                      32h → {jonah}h{' '}
                      <span style={{ color: INK_SOFT, opacity: interpolate(frame, [C.rows + 22, C.rows + 30], [0, 1], clamp) }}>· no overtime</span>
                    </span>
                    <span style={{ color: INK_SOFT }}>Dev</span>
                    <span style={{ fontFamily: MONO }}>32h → {dev}h</span>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: `${6 * s}px ${16 * s}px`, marginTop: 14 * s }}>
                    {CHECKS.map((c, i) => (
                      <span
                        key={c}
                        style={mono(10, {
                          color: INK_SOFT,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6 * s,
                          opacity: interpolate(frame, [C.checks + i * 8, C.checks + i * 8 + 6], [0, 1], clamp),
                        })}
                      >
                        <span style={{ width: 5 * s, height: 5 * s, borderRadius: 99, backgroundColor: STAMP }} />
                        {c}
                      </span>
                    ))}
                  </div>
                  <div style={{ marginTop: 14 * s, minHeight: 38 * s, display: 'flex', alignItems: 'center', gap: 8 * s }}>
                    {confirmed ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8 * s, fontSize: 15 * s, fontWeight: 500, color: INK, ...appear(C.confirmed) }}>
                        <span style={{ width: 6 * s, height: 6 * s, borderRadius: 99, backgroundColor: STAMP }} />
                        Confirmed by you · Jonah notified
                      </span>
                    ) : (
                      <>
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            height: 36 * s,
                            padding: `0 ${16 * s}px`,
                            borderRadius: 99,
                            backgroundColor: INK,
                            color: PAPER,
                            fontWeight: 500,
                            fontSize: 15 * s,
                            transform: `scale(${pressScale})`,
                            boxShadow: `0 0 0 ${pulse * 6 * s}px ${hexA(INK, 0.12 * (1 - pulse * 0.5))}`,
                          }}
                        >
                          Confirm
                        </span>
                        <span style={{ display: 'inline-flex', alignItems: 'center', height: 36 * s, padding: `0 ${16 * s}px`, borderRadius: 99, boxShadow: `inset 0 0 0 1px ${hexA(INK, 0.2)}`, fontSize: 15 * s }}>
                          Cancel
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div style={{ textAlign: 'center', ...mono(10, { color: INK_SOFT }), ...appear(C.system) }}>— schedule updated · Tue Oct 6 —</div>
          </div>

          {/* composer */}
          <div style={{ padding: `${14 * s}px ${22 * s}px`, borderTop: `1px solid ${RULE}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 * s, border: `1px solid ${hexA(INK, 0.16)}`, borderRadius: 99, padding: `${9 * s}px ${14 * s}px`, fontSize: 16 * s, fontFamily: BODY }}>
              <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', color: sent || typedLen === 0 ? hexA(INK, 0.4) : INK }}>
                {sent || typedLen === 0 ? (
                  'Message #mission-st'
                ) : (
                  <>
                    <span style={{ color: typedLen >= MENTION.length ? STAMP : INK, fontWeight: typedLen >= MENTION.length ? 500 : 400 }}>{MESSAGE.slice(0, Math.min(typedLen, MENTION.length))}</span>
                    {MESSAGE.slice(MENTION.length, Math.max(typedLen, MENTION.length))}
                  </>
                )}
                {!sent && frame >= C.type - 10 && Math.floor(frame / 8) % 2 === 0 && (
                  <span style={{ display: 'inline-block', width: 2 * s, height: 18 * s, marginLeft: 1, verticalAlign: 'text-bottom', backgroundColor: INK }} />
                )}
              </span>
              <span
                style={{
                  width: 28 * s,
                  height: 28 * s,
                  borderRadius: 99,
                  backgroundColor: typedLen > 0 && !sent ? INK : hexA(INK, 0.15),
                  color: PAPER,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 14 * s,
                }}
              >
                ↑
              </span>
            </div>
          </div>
        </div>

        {/* ── the schedule, Tuesday ────────────────────────────────────── */}
        <TuesdayStrip frame={frame} move={move} s={s} wide={wide} mono={mono} />
      </AbsoluteFill>
    </AbsoluteFill>
  )
}

function Avatar({ s, bg, fg, text, square, style }: { s: number; bg: string; fg: string; text: string; square?: boolean; style?: CSSProperties }) {
  return (
    <span
      style={{
        flexShrink: 0,
        width: 36 * s,
        height: 36 * s,
        borderRadius: square ? 9 * s : 99,
        backgroundColor: bg,
        color: fg,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: square ? BODY : MONO,
        fontWeight: square ? 600 : 500,
        fontSize: (square ? 18 : 11) * s,
        ...style,
      }}
    >
      {text}
    </span>
  )
}

function TuesdayStrip({
  frame,
  move,
  s,
  wide,
  mono,
}: {
  frame: number
  move: number
  s: number
  wide: boolean
  mono: (size: number, extra?: CSSProperties) => CSSProperties
}) {
  const rowH = 58 * s
  const barH = rowH * 0.44
  const barTop = (rowH - barH) / 2
  // 6a → midnight across the lane; Dev's open is 7a–3p
  const x = (h: number) => `${((h - 6) / 18) * 100}%`
  const rows = [
    { name: 'Dev P.', before: 32, after: 24 },
    { name: 'Jonah B.', before: 32, after: 40 },
  ]
  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-start',
        paddingTop: wide ? 18 * s : 0,
        opacity: interpolate(frame, [4, 16], [0, 1], clamp),
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <span style={mono(12, { color: INK, fontWeight: 500 })}>Tue 6</span>
        <span style={mono(10.5, { color: INK_SOFT })}>Hours this week</span>
      </div>
      <div style={{ position: 'relative', marginTop: 14 * s, borderTop: `1px solid ${hexA(INK, 0.2)}` }}>
        {rows.map((r) => {
          const hours = Math.round(r.before + (r.after - r.before) * move)
          return (
            <div key={r.name} style={{ display: 'flex', alignItems: 'center', height: rowH, borderBottom: `1px solid ${RULE}` }}>
              <span style={{ width: wide ? 84 * s : 120 * s, fontFamily: BODY, fontWeight: 500, fontSize: 16 * s, color: INK, flexShrink: 0 }}>{r.name}</span>
              <span style={{ flex: 1, position: 'relative', height: '100%', borderLeft: `1px solid ${RULE}`, borderRight: `1px solid ${RULE}` }} />
              <span style={{ width: 54 * s, textAlign: 'right', fontFamily: BODY, fontWeight: 400, fontSize: 20 * s, letterSpacing: '-0.03em', color: INK, fontVariantNumeric: 'tabular-nums' }}>
                {hours}
                <span style={{ fontFamily: MONO, fontSize: 11 * s, marginLeft: 2 * s, color: INK_SOFT }}>h</span>
              </span>
            </div>
          )
        })}
        {/* the shift itself, riding from Dev's lane to Jonah's */}
        <div
          style={{
            position: 'absolute',
            left: wide ? 84 * s : 120 * s,
            right: 54 * s,
            top: barTop + rowH * move,
            height: barH,
          }}
        >
          <div
            style={{
              position: 'absolute',
              left: x(7),
              width: `calc(${x(15)} - ${x(7)})`,
              top: 0,
              bottom: 0,
              // the moving shift in full ink, as in the hero
              backgroundColor: INK,
              borderRadius: 999,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: MONO,
              fontSize: 11 * s,
              letterSpacing: '0.04em',
              color: PAPER,
            }}
          >
            7a–3p
          </div>
        </div>
      </div>
      <div style={mono(10, { color: INK_SOFT, display: 'flex', alignItems: 'center', gap: 7 * s, marginTop: 14 * s, opacity: interpolate(frame, [C.system, C.system + 10], [0, 1], clamp) })}>
        <span style={{ width: 5 * s, height: 5 * s, borderRadius: 99, backgroundColor: STAMP }} />
        published · Jonah notified
      </div>
    </div>
  )
}
