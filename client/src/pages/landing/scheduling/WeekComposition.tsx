/**
 * Remotion composition for the scheduling landing hero: a wall schedule that
 * drafts itself, gets checked, gets fixed, and goes out.
 *
 *   grid + crew → forecast per day → shifts highlighted in → rule check sweep
 *   → red-pen loops on the two problems → both shifts move to someone with room
 *   → labor settles → sent card, crew notified → fade to the blank sheet (loops cleanly)
 *
 * Rendered live in the browser by @remotion/player (SchedulePlayer.tsx); no
 * server-side render. Two layouts share one timeline — `narrow` shows Thu–Sun
 * (where both problems live) at a size that stays legible on a phone.
 */
import type { CSSProperties } from 'react'
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { BOARD, BOARD_GRID, BODY, DISPLAY, HILITE, INK as BAR_INK, MONO, hexA } from './theme'
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

// The hero sheet is a dark board (theme.ts BOARD): same instruments,
// inverted. Local names mirror theme.ts so the drawing code reads the same;
// only the highlighter shift bars keep dark ink (BAR_INK) on their yellow.
const { PAPER, PAPER_DEEP, CARD, INK, INK_SOFT, RED_PEN, STAMP } = BOARD

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
  const barTop = (row: number) => rowY(row) + L.rowH * 0.2
  const barH = L.rowH * 0.6

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
      ? { text: 'Drafting', fg: INK, bg: 'transparent' }
      : frame < T.resolve + 30
        ? { text: 'Checking rules', fg: RED_PEN, bg: 'transparent' }
        : { text: 'Ready to publish', fg: STAMP, bg: 'transparent' }

  const mono = (size: number, extra?: CSSProperties): CSSProperties => ({
    fontFamily: MONO,
    fontSize: size * s,
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
    ...extra,
  })

  return (
    <AbsoluteFill style={{ backgroundColor: PAPER, ...BOARD_GRID, overflow: 'hidden' }}>
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
            <div style={{ fontFamily: DISPLAY, fontWeight: 800, fontSize: 38 * s, lineHeight: 0.9, color: INK, textTransform: 'uppercase', letterSpacing: '0.01em' }}>
              {wide ? 'Juniper Café — Mission St.' : 'Juniper Café'}
            </div>
            <div style={mono(12, { color: INK_SOFT, marginTop: 8 * s })}>
              Week of Oct {DATES[0]}–{DATES[6]}
              {wide && ' · drafted from 8 weeks of sales'}
            </div>
          </div>
          <div
            style={mono(12, {
              flexShrink: 0,
              color: status.fg,
              backgroundColor: status.bg,
              border: `${1.5 * s}px solid ${status.fg}`,
              borderRadius: 999,
              padding: `${6 * s}px ${14 * s}px`,
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: 8 * s,
              opacity: chipOut,
            })}
          >
            <span
              style={{
                width: 7 * s,
                height: 7 * s,
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
              backgroundColor: hexA(INK, 0.16),
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
              backgroundColor: hexA(INK, 0.16),
            }}
          />
        ))}
        <div style={{ position: 'absolute', left: gridRight, top: L.dayHeadY, width: 1, height: (rowsBottom - L.dayHeadY) * gridIn, backgroundColor: hexA(INK, 0.16) }} />
        <div style={{ position: 'absolute', left: L.pad, top: L.rowsY - 1, height: 2, width: (L.w - L.pad * 2) * gridIn, backgroundColor: INK }} />

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
                <span style={{ fontFamily: DISPLAY, fontWeight: 800, fontSize: 26 * s, color: INK, textTransform: 'uppercase', lineHeight: 1 }}>
                  {DAYS[day]}
                </span>
                <span style={mono(11, { color: INK_SOFT })}>{DATES[day]}</span>
              </div>
              <div style={{ marginTop: 10 * s, height: 5 * s, backgroundColor: hexA(INK, 0.08), borderRadius: 3 }}>
                <div
                  style={{
                    height: '100%',
                    width: `${(FORECAST[day] / max) * 100 * f}%`,
                    backgroundColor: isSat ? STAMP : hexA(STAMP, 0.55),
                    borderRadius: 3,
                  }}
                />
              </div>
              <div style={mono(10.5, { color: INK_SOFT, marginTop: 6 * s, opacity: f, whiteSpace: 'nowrap' })}>
                ${(FORECAST[day] / 1000).toFixed(1)}k
                {isSat && (
                  <span style={{ color: STAMP, fontWeight: 700, display: wide ? 'inline' : 'block' }}>
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
            <div style={{ fontFamily: BODY, fontWeight: 600, fontSize: 19 * s, color: INK, lineHeight: 1.1, whiteSpace: 'nowrap' }}>{c.name}</div>
            <div style={mono(10, { color: INK_SOFT, marginTop: 3 * s })}>{c.role}</div>
          </div>
        ))}

        {/* ── unavailable blocks (an input, drawn before the draft) ──── */}
        {UNAVAILABLE.filter((u) => L.days.includes(u.day)).map((u) => (
          <div
            key={`un-${u.row}-${u.day}`}
            style={{
              position: 'absolute',
              left: dayX(u.day) + 4,
              top: rowY(u.row) + 4,
              width: colW - 8,
              height: L.rowH - 8,
              backgroundImage: `repeating-linear-gradient(135deg, ${hexA(INK, 0.14)} 0 1.5px, transparent 1.5px 8px)`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              opacity: interpolate(frame, [60, 80], [0, 1], clamp),
            }}
          >
            <span style={mono(10, { color: INK_SOFT, backgroundColor: PAPER, padding: `${2 * s}px ${6 * s}px` })}>Unavailable</span>
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
                fontFamily: MONO,
                fontWeight: 700,
                fontSize: 20 * s,
                color: over ? RED_PEN : INK,
                fontVariantNumeric: 'tabular-nums',
                opacity: frame < T.shifts ? 0 : 1,
              }}
            >
              {value}
              <span style={{ fontSize: 12 * s, fontWeight: 400, marginLeft: 2, color: over ? RED_PEN : INK_SOFT }}>h</span>
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
              height: 44 * s,
              transform: 'translateY(-100%)',
              background: `linear-gradient(to bottom, transparent, ${hexA(STAMP, 0.12)})`,
              borderBottom: `2px solid ${STAMP}`,
              opacity: interpolate(frame, [T.checkEnd, T.checkEnd + 6], [1, 0], clamp),
            }}
          />
        )}

        {/* ── red pen ────────────────────────────────────────────────── */}
        <svg width={L.w} height={L.h} viewBox={`0 0 ${L.w} ${L.h}`} style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
          <g opacity={flagOut}>
            <PenLoop
              frame={frame}
              start={T.flag}
              cx={gridRight + 12 * s + 20 * s}
              cy={rowY(FLAGS.overtime.row) + L.rowH / 2}
              rx={34 * s}
              ry={L.rowH * 0.42}
              seed={1}
              s={s}
            />
            <PenLoop
              frame={frame}
              start={T.flag + 10}
              cx={(hourX(SAT, 7) + hourX(SAT, 15)) / 2}
              cy={barTop(FLAGS.overtime.row) + barH / 2}
              rx={(hourX(SAT, 15) - hourX(SAT, 7)) / 2 + 12 * s}
              ry={barH * 0.72}
              seed={2}
              s={s}
            />
            <PenNote
              frame={frame}
              start={T.flag + 18}
              x={hourX(SAT, 7) - 4 * s}
              y={barTop(FLAGS.overtime.row) + barH + 22 * s}
              text={FLAGS.overtime.label}
              s={s}
            />
            <PenLoop
              frame={frame}
              start={T.flag + 22}
              cx={(hourX(3, 15) + hourX(4, 14)) / 2}
              cy={barTop(FLAGS.rest.row) + barH / 2}
              rx={(hourX(4, 14) - hourX(3, 15)) / 2 + 14 * s}
              ry={barH * 0.78}
              seed={3}
              s={s}
            />
            <PenNote
              frame={frame}
              start={T.flag + 34}
              x={hourX(3, 15)}
              y={barTop(FLAGS.rest.row) + barH + 22 * s}
              text={FLAGS.rest.label}
              s={s}
            />
          </g>
        </svg>

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
                top: barTop(to) + barH + 3 * s,
                color: STAMP,
                fontWeight: 700,
                opacity: o * interpolate(frame, [T.stamp, T.stamp + 12], [1, 0], clamp),
                whiteSpace: 'nowrap',
              })}
            >
              ✓ moved · {CREW[to].name.split(' ')[0]} {hoursAfter[to]}h
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
            height: 1.5 * s,
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
        <span style={{ fontFamily: BODY, fontWeight: 600, fontSize: 16 * s, color: INK }}>Sent to crew</span>
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
  return (
    <div style={{ position: 'absolute', left: x, top: y, width, height }}>
      {/* the shift: a clean highlighter block, drawn left to right */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          height: '100%',
          width: `${p * 100}%`,
          backgroundColor: HILITE,
          borderRadius: 5 * s,
          boxShadow: flagged ? `0 0 0 ${2 * s}px ${RED_PEN}` : 'none',
        }}
      />
      {labels && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: MONO,
            fontSize: 11.5 * s,
            fontWeight: 500,
            color: BAR_INK,
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
            marginBottom: 2 * s,
            fontFamily: MONO,
            fontSize: 9.5 * s,
            fontWeight: 700,
            letterSpacing: '0.06em',
            color: STAMP,
            opacity: interpolate(frame, [start + 8, start + 20], [0, 1], clamp),
            whiteSpace: 'nowrap',
            textTransform: 'uppercase',
          }}
        >
          + forecast
        </div>
      )}
    </div>
  )
}

/** Hand-drawn loop: a wobbly ellipse that overshoots its own start, drawn on. */
function PenLoop({
  frame,
  start,
  cx,
  cy,
  rx,
  ry,
  seed,
  s,
}: {
  frame: number
  start: number
  cx: number
  cy: number
  rx: number
  ry: number
  seed: number
  s: number
}) {
  const p = interpolate(frame, [start, start + 16], [0, 1], { ...clamp, easing: Easing.inOut(Easing.quad) })
  if (p === 0) return null
  const pts: string[] = []
  const a0 = -2.2 + seed * 0.7
  const steps = 56
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const a = a0 + t * (Math.PI * 2 + 0.55)
    const wobble = 1 + 0.045 * Math.sin(3 * a + seed) + 0.03 * t
    pts.push(`${(cx + Math.cos(a) * rx * wobble).toFixed(1)},${(cy + Math.sin(a) * ry * wobble).toFixed(1)}`)
  }
  return (
    <path
      d={`M${pts.join(' L')}`}
      fill="none"
      stroke={RED_PEN}
      strokeWidth={2.6 * s}
      strokeLinecap="round"
      strokeLinejoin="round"
      pathLength={1}
      strokeDasharray={1}
      strokeDashoffset={1 - p}
    />
  )
}

function PenNote({ frame, start, x, y, text, s }: { frame: number; start: number; x: number; y: number; text: string; s: number }) {
  const o = interpolate(frame, [start, start + 8], [0, 1], clamp)
  return (
    <text
      x={x}
      y={y}
      opacity={o}
      fill={RED_PEN}
      fontFamily={MONO}
      fontWeight={700}
      fontSize={12 * s}
      letterSpacing="0.06em"
      transform={`rotate(-3 ${x} ${y})`}
      style={{ paintOrder: 'stroke', stroke: PAPER, strokeWidth: 4 * s }}
    >
      {text}
    </text>
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
          const color = !seen ? hexA(INK, 0.35) : bad ? RED_PEN : c.flagged ? STAMP : INK
          return (
            <div key={c.label} style={mono(11, { color, display: 'flex', alignItems: 'center', gap: 7 * s, whiteSpace: 'nowrap', fontWeight: seen ? 700 : 400 })}>
              <span
                style={{
                  width: 16 * s,
                  height: 16 * s,
                  border: `${1.5 * s}px solid ${color}`,
                  borderRadius: 3 * s,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 11 * s,
                  lineHeight: 1,
                  backgroundColor: bad ? hexA(RED_PEN, 0.1) : 'transparent',
                }}
              >
                {!seen ? '' : bad ? '✕' : '✓'}
              </span>
              {c.label}
              {c.flagged && fixed && <span style={{ fontWeight: 400 }}>· fixed</span>}
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
      <div style={{ fontFamily: DISPLAY, fontWeight: 800, fontSize: 44 * s, lineHeight: 1, color, fontVariantNumeric: 'tabular-nums', marginTop: 4 * s }}>{value}</div>
    </div>
  )
}

export default WeekComposition
