/**
 * Remotion composition for the scheduling landing hero: a wall schedule that
 * drafts itself, gets checked, gets fixed, and goes out.
 *
 *   grid + crew → forecast per day → shifts drawn in → rule check sweep
 *   → red rings on the two problems → both shifts move to someone with room
 *   → labor settles → sent card, crew notified → fade to the blank sheet (loops cleanly)
 *
 * Rendered live in the browser by @remotion/player (SchedulePlayer.tsx); no
 * server-side render. Two layouts share one timeline — `narrow` shows Thu–Sun
 * (where both problems live) at a size that stays legible on a phone.
 */
import type { CSSProperties } from 'react'
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { BOARD, BODY, MONO, hexA } from './theme'
import {
  CREW,
  DATES,
  DAYS,
  FLAGS,
  FORECAST,
  FORECAST_TOTAL,
  MOVES,
  SAT,
  SHIFTS,
  UNAVAILABLE,
  clock,
  initials,
  laborCost,
  weeklyHours,
  type Shift,
} from './weekData'
import { DURATION, LAYOUTS, T, type Layout, type Variant } from './timeline'

// The hero sheet is the Draft section's language inverted onto a dark board
// (theme.ts BOARD): grayscale ink at a few alphas, hairlines, mono labels,
// Hanken for names and figures. Green means only ok/fixed/sent, red only a
// problem. Local names mirror theme.ts so the drawing code reads the same.
const { PAPER, PAPER_DEEP, CARD, INK, INK_SOFT, RED_PEN, STAMP } = BOARD
const RULE = hexA(INK, 0.08)
const REST = hexA(INK, 0.14) // a resting mark: shift pill, forecast fill

export type WeekProps = { variant: Variant }

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const
const easeOut = Easing.out(Easing.cubic)

export function WeekComposition({ variant }: WeekProps) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const L = LAYOUTS[variant]
  const s = L.s
  const wide = variant === 'wide'

  const gridLeft = L.pad + L.nameW
  const gridRight = L.w - L.pad - L.hoursW
  const colW = (gridRight - gridLeft) / L.days.length
  const rowsBottom = L.rowsY + CREW.length * L.rowH
  const inset = 6
  const dayX = (day: number) => gridLeft + L.days.indexOf(day) * colW
  const hourX = (day: number, h: number) => dayX(day) + inset + ((h - 6) / 18) * (colW - inset * 2)
  const rowY = (row: number) => L.rowsY + row * L.rowH
  const barH = L.rowH * 0.42
  const barTop = (row: number) => rowY(row) + (L.rowH - barH) / 2

  // ── timeline scalars ────────────────────────────────────────────────────
  const gridIn = interpolate(frame, [0, 28], [0, 1], { ...clamp, easing: easeOut })
  const contentOut = interpolate(frame, [T.fadeOut, DURATION], [1, 0], clamp)
  const build = interpolate(frame, [T.shifts, T.shifts + T.shiftsSpan + 10], [0, 1], clamp)
  const moveP = (delay: number) =>
    spring({ frame: frame - T.resolve - delay, fps, config: { damping: 15, stiffness: 110 } })
  const resolved = moveP(0)
  const flagOut = interpolate(frame, [T.resolve + 24, T.resolve + 44], [1, 0], clamp)
  // the status chip hands off to the sent card in the same corner
  const chipOut = interpolate(frame, [T.stamp - 6, T.stamp + 4], [1, 0], clamp)

  const visibleShifts = SHIFTS.filter((x) => L.days.includes(x.day)).sort((a, b) => a.day - b.day || a.row - b.row)
  const stagger = T.shiftsSpan / visibleShifts.length
  const revealAt = new Map(visibleShifts.map((x, i) => [x.id, T.shifts + i * stagger]))

  const hoursBefore = weeklyHours(false)
  const hoursAfter = weeklyHours(true)
  const costBefore = laborCost(false)
  const costAfter = laborCost(true)

  const status =
    frame < T.check
      ? { text: 'Drafting', fg: INK }
      : frame < T.resolve + 30
        ? { text: 'Checking rules', fg: RED_PEN }
        : { text: 'Ready to publish', fg: STAMP }

  const mono = (size: number, extra?: CSSProperties): CSSProperties => ({
    fontFamily: MONO,
    fontSize: size * s,
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
    ...extra,
  })

  return (
    <AbsoluteFill style={{ backgroundColor: PAPER, overflow: 'hidden' }}>
      <AbsoluteFill style={{ opacity: contentOut }}>
        {/* ── header ─────────────────────────────────────────────────── */}
        <div
          style={{
            position: 'absolute',
            left: L.pad,
            right: L.pad,
            top: L.pad * 0.8,
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 16,
            opacity: interpolate(frame, [4, 22], [0, 1], clamp),
          }}
        >
          <div>
            <div style={{ fontFamily: BODY, fontWeight: 500, fontSize: 34 * s, lineHeight: 1, color: INK, letterSpacing: '-0.035em' }}>
              Juniper Café{wide && <span style={{ color: INK_SOFT }}> · Mission St.</span>}
            </div>
            <div style={mono(11, { color: INK_SOFT, marginTop: 12 * s })}>
              Week of Oct {DATES[0]}–{DATES[6]}
              {wide && ' · drafted from 8 weeks of sales'}
            </div>
          </div>
          <div
            style={mono(11, {
              flexShrink: 0,
              color: status.fg,
              paddingTop: 8 * s,
              display: 'flex',
              alignItems: 'center',
              gap: 8 * s,
              opacity: chipOut,
            })}
          >
            <span
              style={{
                width: 6 * s,
                height: 6 * s,
                borderRadius: 99,
                backgroundColor: status.fg,
                opacity: 0.4 + 0.6 * Math.abs(Math.sin(frame / 9)),
              }}
            />
            {status.text}
          </div>
        </div>

        {/* ── sheet rules ────────────────────────────────────────────── */}
        {CREW.map((_, r) => (
          <div
            key={`row-${r}`}
            style={{
              position: 'absolute',
              left: L.pad,
              top: rowY(r + 1) - 1,
              height: 1,
              width: (L.w - L.pad * 2) * interpolate(frame, [r * 2, 26 + r * 2], [0, 1], { ...clamp, easing: easeOut }),
              backgroundColor: RULE,
            }}
          />
        ))}
        {L.days.map((day) => (
          <div
            key={`col-${day}`}
            style={{
              position: 'absolute',
              left: dayX(day),
              top: L.dayHeadY,
              width: 1,
              height: (rowsBottom - L.dayHeadY) * gridIn,
              backgroundColor: RULE,
            }}
          />
        ))}
        <div style={{ position: 'absolute', left: gridRight, top: L.dayHeadY, width: 1, height: (rowsBottom - L.dayHeadY) * gridIn, backgroundColor: RULE }} />
        <div style={{ position: 'absolute', left: L.pad, top: L.rowsY - 1, height: 1, width: (L.w - L.pad * 2) * gridIn, backgroundColor: hexA(INK, 0.2) }} />

        {/* ── day headers + forecast ─────────────────────────────────── */}
        {L.days.map((day, i) => {
          const f = interpolate(frame, [T.forecast + i * 7, T.forecast + i * 7 + 24], [0, 1], { ...clamp, easing: easeOut })
          const max = Math.max(...FORECAST)
          const isSat = day === SAT
          return (
            <div
              key={`head-${day}`}
              style={{
                position: 'absolute',
                left: dayX(day) + 10 * s,
                top: L.dayHeadY,
                width: colW - 20 * s,
                height: L.dayHeadH,
                opacity: interpolate(frame, [8 + i * 3, 24 + i * 3], [0, 1], clamp),
              }}
            >
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 * s }}>
                <span style={mono(12, { color: INK, fontWeight: isSat ? 700 : 500 })}>{DAYS[day]}</span>
                <span style={mono(11, { color: INK_SOFT })}>{DATES[day]}</span>
              </div>
              <div style={{ marginTop: 14 * s, height: 2 * s, backgroundColor: RULE, borderRadius: 99 }}>
                <div
                  style={{
                    height: '100%',
                    width: `${(FORECAST[day] / max) * 100 * f}%`,
                    backgroundColor: isSat ? INK : hexA(INK, 0.28),
                    borderRadius: 99,
                  }}
                />
              </div>
              <div style={mono(10.5, { color: INK_SOFT, marginTop: 8 * s, opacity: f, whiteSpace: 'nowrap' })}>
                ${(FORECAST[day] / 1000).toFixed(1)}k
                {isSat && (
                  <span style={{ color: INK, display: wide ? 'inline' : 'block' }}>
                    {wide && ' · '}
                    74° sun
                  </span>
                )}
              </div>
            </div>
          )
        })}
        <div
          style={mono(10.5, {
            position: 'absolute',
            left: gridRight + 12 * s,
            top: L.dayHeadY + 8 * s,
            color: INK_SOFT,
            opacity: interpolate(frame, [20, 36], [0, 1], clamp),
          })}
        >
          Hours
        </div>

        {/* ── crew names ─────────────────────────────────────────────── */}
        {CREW.map((c, r) => (
          <div
            key={c.name}
            style={{
              position: 'absolute',
              left: L.pad,
              top: rowY(r),
              height: L.rowH,
              width: L.nameW - 12,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              opacity: interpolate(frame, [14 + r * 3, 30 + r * 3], [0, 1], clamp),
              transform: `translateX(${interpolate(frame, [14 + r * 3, 30 + r * 3], [-12, 0], { ...clamp, easing: easeOut })}px)`,
            }}
          >
            <div style={{ fontFamily: BODY, fontWeight: 500, fontSize: 17 * s, color: INK, lineHeight: 1.1, letterSpacing: '-0.01em', whiteSpace: 'nowrap' }}>{c.name}</div>
            <div style={mono(10, { color: INK_SOFT, marginTop: 3 * s })}>{c.role}</div>
          </div>
        ))}

        {/* ── unavailable blocks (an input, drawn before the draft) ──── */}
        {UNAVAILABLE.filter((u) => L.days.includes(u.day)).map((u) => (
          <div
            key={`un-${u.row}-${u.day}`}
            style={{
              position: 'absolute',
              left: dayX(u.day) + inset,
              top: barTop(u.row),
              width: colW - inset * 2,
              height: barH,
              borderRadius: 999,
              boxShadow: `inset 0 0 0 1px ${hexA(INK, 0.16)}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              opacity: interpolate(frame, [60, 80], [0, 1], clamp),
            }}
          >
            <span style={mono(10, { color: INK_SOFT })}>Away</span>
          </div>
        ))}

        {/* ── shifts ─────────────────────────────────────────────────── */}
        {visibleShifts.map((shift) => (
          <ShiftBar
            key={shift.id}
            shift={shift}
            frame={frame}
            start={revealAt.get(shift.id) ?? 0}
            x={hourX(shift.day, shift.start)}
            width={hourX(shift.day, shift.end) - hourX(shift.day, shift.start)}
            fromY={barTop(shift.row)}
            toY={MOVES[shift.id] !== undefined ? barTop(MOVES[shift.id]) : barTop(shift.row)}
            moveP={moveP(shift.id === 'dev-fri' ? 8 : 0)}
            flagged={frame >= T.flag && frame < T.resolve + 30 && MOVES[shift.id] !== undefined}
            height={barH}
            s={s}
            labels={L.barLabels}
          />
        ))}

        {/* ── weekly hours ───────────────────────────────────────────── */}
        {CREW.map((c, r) => {
          const raw = hoursBefore[r] * build + (hoursAfter[r] - hoursBefore[r]) * resolved
          const value = Math.round(raw)
          const over = value > 40
          return (
            <div
              key={`hrs-${c.name}`}
              style={{
                position: 'absolute',
                left: gridRight + 12 * s,
                top: rowY(r),
                height: L.rowH,
                display: 'flex',
                alignItems: 'center',
                fontFamily: BODY,
                fontWeight: 400,
                fontSize: 22 * s,
                letterSpacing: '-0.03em',
                color: over ? RED_PEN : INK,
                fontVariantNumeric: 'tabular-nums',
                opacity: frame < T.shifts ? 0 : 1,
              }}
            >
              {value}
              <span style={{ fontFamily: MONO, fontSize: 11 * s, marginLeft: 3 * s, color: over ? RED_PEN : INK_SOFT }}>h</span>
            </div>
          )
        })}

        {/* ── rule-check sweep ───────────────────────────────────────── */}
        {frame >= T.check && frame < T.checkEnd + 6 && (
          <div
            style={{
              position: 'absolute',
              left: L.pad,
              right: L.pad,
              top: interpolate(frame, [T.check, T.checkEnd], [L.rowsY, rowsBottom], { ...clamp, easing: Easing.inOut(Easing.quad) }),
              height: 1,
              backgroundColor: hexA(INK, 0.5),
              opacity: interpolate(frame, [T.checkEnd, T.checkEnd + 6], [1, 0], clamp),
            }}
          />
        )}

        {/* ── problems: a red ring on the shift (ShiftBar), a note under it ── */}
        <FlagNote
          frame={frame}
          start={T.flag + 10}
          out={flagOut}
          x={hourX(SAT, 7)}
          y={barTop(FLAGS.overtime.row) + barH + 6 * s}
          text={FLAGS.overtime.label}
          s={s}
        />
        <FlagNote
          frame={frame}
          start={T.flag + 22}
          out={flagOut}
          x={hourX(3, 15)}
          y={barTop(FLAGS.rest.row) + barH + 6 * s}
          text={FLAGS.rest.label}
          s={s}
        />

        {/* ── fixed notes ────────────────────────────────────────────── */}
        {wide && (['mar-sat', 'dev-fri'] as const).map((id, i) => {
          const shift = SHIFTS.find((x) => x.id === id) as Shift
          const to = MOVES[id]
          const o = interpolate(frame, [T.resolve + 26 + i * 8, T.resolve + 40 + i * 8], [0, 1], clamp)
          return (
            <div
              key={`fix-${id}`}
              style={mono(10, {
                position: 'absolute',
                left: hourX(shift.day, shift.start),
                top: barTop(to) + barH + 6 * s,
                color: INK_SOFT,
                display: 'flex',
                alignItems: 'center',
                gap: 6 * s,
                opacity: o * interpolate(frame, [T.stamp, T.stamp + 12], [1, 0], clamp),
                whiteSpace: 'nowrap',
              })}
            >
              <span style={{ width: 5 * s, height: 5 * s, borderRadius: 99, backgroundColor: STAMP }} />
              moved to {CREW[to].name.split(' ')[0]} · {hoursAfter[to]}h
            </div>
          )
        })}

        {/* ── bottom strip: checks + cost ────────────────────────────── */}
        <BottomStrip
          frame={frame}
          L={L}
          build={build}
          resolved={resolved}
          costBefore={costBefore}
          costAfter={costAfter}
          mono={mono}
        />

        {/* ── publish: a hairline under the header, then the sent card ── */}
        <div
          style={{
            position: 'absolute',
            left: L.pad,
            right: L.pad,
            top: L.dayHeadY - 12 * s,
            height: 1,
            backgroundColor: STAMP,
            transformOrigin: '0 50%',
            transform: `scaleX(${interpolate(frame, [T.stamp - 4, T.stamp + 18], [0, 1], { ...clamp, easing: easeOut })})`,
          }}
        />
        {frame >= T.stamp && <SentCard frame={frame} L={L} s={s} />}
      </AbsoluteFill>
    </AbsoluteFill>
  )
}

/** The publish beat: a quiet confirmation card where the status chip was,
 *  then each crew member's initials turn green as their notification lands. */
function SentCard({ frame, L, s }: { frame: number; L: Layout; s: number }) {
  const inP = interpolate(frame, [T.stamp, T.stamp + 14], [0, 1], { ...clamp, easing: easeOut })
  const check = interpolate(frame, [T.stamp + 6, T.stamp + 18], [0, 1], { ...clamp, easing: easeOut })
  const dotAt = (i: number) => T.stamp + 12 + i * 5
  const sent = CREW.filter((_, i) => frame >= dotAt(i) + 3).length
  const dot = 24 * s
  const mono = (size: number, extra?: CSSProperties): CSSProperties => ({
    fontFamily: MONO,
    fontSize: size * s,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    ...extra,
  })
  return (
    <div
      style={{
        position: 'absolute',
        right: L.pad,
        top: L.pad * 0.7,
        width: Math.min(340 * s, L.w * 0.5),
        padding: `${14 * s}px ${16 * s}px`,
        backgroundColor: CARD,
        borderRadius: 12 * s,
        boxShadow: `0 0 0 1px ${hexA(INK, 0.1)}, 0 24px 48px -20px rgba(0, 0, 0, 0.7)`,
        opacity: inP,
        transform: `translateY(${(1 - inP) * -8 * s}px)`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 * s }}>
        <svg width={18 * s} height={18 * s} viewBox="0 0 18 18" style={{ flexShrink: 0 }}>
          <circle cx={9} cy={9} r={9} fill={STAMP} />
          <path
            d="M5 9.4 L7.8 12 L13 6.4"
            fill="none"
            stroke={PAPER}
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
            pathLength={1}
            strokeDasharray={1}
            strokeDashoffset={1 - check}
          />
        </svg>
        <span style={{ fontFamily: BODY, fontWeight: 500, fontSize: 16 * s, color: INK, letterSpacing: '-0.01em' }}>Sent to crew</span>
        <span style={mono(11, { marginLeft: 'auto', color: INK_SOFT })}>Sun · 4:12 PM</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', marginTop: 12 * s }}>
        {CREW.map((c, i) => {
          const on = interpolate(frame, [dotAt(i), dotAt(i) + 6], [0, 1], clamp)
          return (
            <span
              key={c.name}
              style={{
                width: dot,
                height: dot,
                marginLeft: i ? -5 * s : 0,
                borderRadius: 99,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: BODY,
                fontWeight: 600,
                fontSize: 9.5 * s,
                boxShadow: `0 0 0 ${2 * s}px ${CARD}`,
                backgroundColor: on > 0.5 ? STAMP : PAPER_DEEP,
                color: on > 0.5 ? PAPER : INK_SOFT,
                transform: `scale(${1 + Math.sin(on * Math.PI) * 0.12})`,
              }}
            >
              {initials(c.name)}
            </span>
          )
        })}
        <span style={mono(11, { marginLeft: 'auto', color: sent === CREW.length ? STAMP : INK_SOFT, fontWeight: 700 })}>
          {sent} notified
        </span>
      </div>
    </div>
  )
}

function ShiftBar({
  shift,
  frame,
  start,
  x,
  width,
  fromY,
  toY,
  moveP,
  flagged,
  height,
  s,
  labels,
}: {
  shift: Shift
  frame: number
  start: number
  x: number
  width: number
  fromY: number
  toY: number
  moveP: number
  flagged: boolean
  height: number
  s: number
  labels: boolean
}) {
  const p = interpolate(frame, [start, start + 11], [0, 1], { ...clamp, easing: easeOut })
  if (p === 0) return null
  const y = fromY + (toY - fromY) * moveP
  // what changed is the one thing drawn in full ink — the Draft chart's peak bars
  const moved = MOVES[shift.id] !== undefined && moveP > 0.5
  return (
    <div style={{ position: 'absolute', left: x, top: y, width, height }}>
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          height: '100%',
          width: `${p * 100}%`,
          backgroundColor: moved ? INK : REST,
          borderRadius: 999,
          boxShadow: flagged ? `0 0 0 ${1.5 * s}px ${RED_PEN}` : 'none',
        }}
      />
      {/* a label only where it fits inside the pill — a 4h shift stays bare */}
      {labels && width >= 44 * s && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: MONO,
            fontSize: 11 * s,
            letterSpacing: '0.04em',
            color: moved ? PAPER : hexA(INK, 0.85),
            opacity: interpolate(p, [0.6, 1], [0, 1], clamp),
            whiteSpace: 'nowrap',
          }}
        >
          {clock(shift.start)}–{clock(shift.end)}
        </div>
      )}
      {shift.forecast && (
        <div
          style={{
            position: 'absolute',
            left: 0,
            bottom: '100%',
            marginBottom: 5 * s,
            display: 'flex',
            alignItems: 'center',
            gap: 5 * s,
            fontFamily: MONO,
            fontSize: 9 * s,
            letterSpacing: '0.08em',
            color: INK_SOFT,
            opacity: interpolate(frame, [start + 8, start + 20], [0, 1], clamp),
            whiteSpace: 'nowrap',
            textTransform: 'uppercase',
          }}
        >
          <span style={{ width: 4 * s, height: 4 * s, borderRadius: 99, backgroundColor: INK }} />
          forecast
        </div>
      )}
    </div>
  )
}

/** A problem, stated plainly under the shift it's about: red dot, mono note. */
function FlagNote({ frame, start, out, x, y, text, s }: { frame: number; start: number; out: number; x: number; y: number; text: string; s: number }) {
  const inP = interpolate(frame, [start, start + 8], [0, 1], { ...clamp, easing: easeOut })
  const o = inP * out
  if (o === 0) return null
  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y,
        display: 'flex',
        alignItems: 'center',
        gap: 6 * s,
        opacity: o,
        transform: `translateY(${(1 - inP) * 4 * s}px)`,
        fontFamily: MONO,
        fontSize: 10.5 * s,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        color: RED_PEN,
        whiteSpace: 'nowrap',
      }}
    >
      <span style={{ width: 5 * s, height: 5 * s, borderRadius: 99, backgroundColor: RED_PEN }} />
      {text}
    </div>
  )
}

const CHECKS: { label: string; flagged: boolean }[] = [
  { label: 'No double-booking', flagged: false },
  { label: 'Inside availability', flagged: false },
  { label: 'Qualified for the job', flagged: false },
  { label: '8h between shifts', flagged: true },
  { label: 'Weekly overtime', flagged: true },
]

function BottomStrip({
  frame,
  L,
  build,
  resolved,
  costBefore,
  costAfter,
  mono,
}: {
  frame: number
  L: Layout
  build: number
  resolved: number
  costBefore: { total: number; overtime: number }
  costAfter: { total: number; overtime: number }
  mono: (size: number, extra?: CSSProperties) => CSSProperties
}) {
  const s = L.s
  const cost = costBefore.total * build + (costAfter.total - costBefore.total) * resolved
  const overtime = frame < T.check ? 0 : Math.max(0, costBefore.overtime + (costAfter.overtime - costBefore.overtime) * resolved)
  const pct = (cost / FORECAST_TOTAL) * 100
  const money = (n: number) => `$${Math.round(n).toLocaleString('en-US')}`
  const wide = L.days.length === 7

  return (
    <>
    <div style={{ position: 'absolute', left: L.pad, right: L.pad, top: L.bottomY - 16 * s, height: 1, backgroundColor: RULE, opacity: interpolate(frame, [T.shifts, T.shifts + 20], [0, 1], clamp) }} />
    <div
      style={{
        position: 'absolute',
        left: L.pad,
        right: L.pad,
        top: L.bottomY,
        bottom: L.pad * 0.8,
        display: 'flex',
        flexDirection: wide ? 'row' : 'column',
        justifyContent: 'space-between',
        alignItems: wide ? 'flex-end' : 'stretch',
        gap: 18 * s,
        opacity: interpolate(frame, [T.shifts, T.shifts + 20], [0, 1], clamp),
      }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: wide ? 'repeat(5, auto)' : 'repeat(2, auto)', gap: `${8 * s}px ${22 * s}px`, alignContent: 'end', justifyContent: 'start' }}>
        {CHECKS.map((c, i) => {
          const at = T.check + 6 + i * 9
          const seen = frame >= at
          const fixed = frame >= T.resolve + 24
          const bad = seen && c.flagged && !fixed
          const dot = !seen ? hexA(INK, 0.25) : bad ? RED_PEN : c.flagged ? STAMP : INK
          const color = !seen ? INK_SOFT : bad ? RED_PEN : INK
          return (
            <div key={c.label} style={mono(11, { color, display: 'flex', alignItems: 'center', gap: 8 * s, whiteSpace: 'nowrap' })}>
              <span style={{ width: 6 * s, height: 6 * s, borderRadius: 99, backgroundColor: dot }} />
              {c.label}
              {c.flagged && fixed && <span style={{ color: INK_SOFT }}>· fixed</span>}
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', gap: 28 * s, alignItems: 'flex-end', justifyContent: wide ? 'flex-end' : 'space-between' }}>
        <Figure label="Scheduled labor" value={money(cost)} mono={mono} s={s} />
        <Figure label="Of forecast sales" value={`${pct.toFixed(1)}%`} mono={mono} s={s} />
        <Figure label="Overtime" value={money(overtime)} mono={mono} s={s} color={overtime > 0.5 ? RED_PEN : INK} />
      </div>
    </div>
    </>
  )
}

function Figure({
  label,
  value,
  mono,
  s,
  color = INK,
}: {
  label: string
  value: string
  mono: (size: number, extra?: CSSProperties) => CSSProperties
  s: number
  color?: string
}) {
  return (
    <div>
      <div style={mono(10, { color: INK_SOFT })}>{label}</div>
      <div style={{ fontFamily: BODY, fontWeight: 400, fontSize: 44 * s, lineHeight: 1, letterSpacing: '-0.04em', color, fontVariantNumeric: 'tabular-nums', marginTop: 8 * s }}>{value}</div>
    </div>
  )
}

export default WeekComposition
