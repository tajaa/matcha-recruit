import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

/** The FOUR pieces of markup Huume's system messages may carry.
 *
 *  The backend composes these strings server-side
 *  (`services/ems/event_intake.py:_confirmation_text`, the two
 *  "Updated ... event" strings in `werk/routes/channels_ws.py`, and
 *  `services/scheduling/schedule_chat.py:result_text`/`schedule_strip`), and
 *  the pill used to print `msg.content` raw — so a `**bold**` in the source
 *  showed up as literal asterisks in the channel. Rather than strip the
 *  emphasis (which left the event category visually indistinguishable from
 *  the rest of the sentence), parse exactly these four constructs.
 *
 *  Scope is intentional: `**bold**`, `[[shift:<id>:<date>]]`,
 *  `[[bar:<startMin>:<endMin>:<colorIdx>]]`, and `[[barruler]]` — nothing
 *  else. No italics, generic links, lists, or code. Anything richer belongs
 *  in a real renderer, and the content here is server-composed from a
 *  closed vocabulary — there is no user text in it to justify a parser with
 *  a larger attack surface. The link target is NEVER taken from the
 *  message text itself (that would be exactly the larger attack surface
 *  this scope note warns about) — a shift link is built from a UUID + ISO
 *  date, and a bar is built from three small integers; this file is what
 *  turns those numbers into markup, never the message text.
 */
const TOKEN_RE =
  /\*\*(.+?)\*\*|\[\[shift:([0-9a-fA-F-]{36}):(\d{4}-\d{2}-\d{2})\]\]|\[\[bar:(\d{1,4}):(\d{1,4}):(\d)\]\]|\[\[barruler\]\]/g

export function stripEmphasis(text: string): string {
  // Compact single-line previews (the reply banner in MessageComposer, the
  // quoted stub above a reply) render plain strings, not nodes — without
  // this they'd show the raw `**`/`[[shift:...]]`/`[[bar:...]]` a Huume
  // pill carries.
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\s*\[\[shift:[0-9a-fA-F-]{36}:\d{4}-\d{2}-\d{2}\]\]/g, '')
    .replace(/\s*\[\[bar:\d{1,4}:\d{1,4}:\d\]\]/g, '')
    .replace(/\s*\[\[barruler\]\]/g, '')
}

/** Urgent (OSHA/severe) pills lead with 🚨 — the server-composed first
 *  character (event_intake._pill_emoji). Content is the ONE urgency signal
 *  that survives a REST history reload; the WS payload isn't re-sent. */
export function isUrgentSystemContent(text: string): boolean {
  return text.startsWith('\u{1F6A8}')
}

// The bar/ruler pair share one width so their columns line up, and one
// display window — schedule_strip emits real, unrounded minutes; clamping
// a shift into the visible window (and giving it a minimum visible sliver)
// is display-only and belongs here, not server-side.
const BAR_TRACK_WIDTH = 'w-44'
const WINDOW_START_MIN = 6 * 60
const WINDOW_END_MIN = 22 * 60
const MIN_VISIBLE_SPAN = 30
const BAR_COLORS = ['bg-emerald-500', 'bg-sky-500', 'bg-violet-500', 'bg-amber-500', 'bg-rose-500']
const RULER_TICKS: Array<{ min: number; label: string }> = [
  { min: 360, label: '6a' },
  { min: 540, label: '9a' },
  { min: 720, label: '12p' },
  { min: 900, label: '3p' },
  { min: 1080, label: '6p' },
  { min: 1260, label: '9p' },
]

function percentOnWindow(min: number): string {
  const clamped = Math.max(WINDOW_START_MIN, Math.min(min, WINDOW_END_MIN))
  return `${(((clamped - WINDOW_START_MIN) / (WINDOW_END_MIN - WINDOW_START_MIN)) * 100).toFixed(1)}%`
}

function formatClockMinutes(totalMin: number): string {
  const wrapped = ((totalMin % 1440) + 1440) % 1440
  const h = Math.floor(wrapped / 60)
  const m = wrapped % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

function renderRuler(key: number): ReactNode {
  return (
    <span
      key={key}
      className={`${BAR_TRACK_WIDTH} relative inline-block h-4 align-middle border-b border-w-line`}
    >
      {RULER_TICKS.map(({ min, label }) => (
        <span
          key={label}
          className="absolute bottom-0 -translate-x-1/2 text-[9px] leading-none text-w-dim"
          style={{ left: percentOnWindow(min) }}
        >
          {label}
        </span>
      ))}
    </span>
  )
}

function renderBar(key: number, startMin: number, endMin: number, colorIdx: number): ReactNode {
  const loPct = percentOnWindow(startMin)
  const hiClamped = Math.max(startMin + MIN_VISIBLE_SPAN, endMin)
  const widthPct = (
    (Math.max(WINDOW_START_MIN, Math.min(hiClamped, WINDOW_END_MIN)) -
      Math.max(WINDOW_START_MIN, Math.min(startMin, WINDOW_END_MIN))) /
    (WINDOW_END_MIN - WINDOW_START_MIN) *
    100
  ).toFixed(1)
  const overnight = endMin > 1440
  const title = `${formatClockMinutes(startMin)}–${formatClockMinutes(endMin)}${overnight ? ' (+1d)' : ''}`
  const color = BAR_COLORS[colorIdx] ?? BAR_COLORS[0]
  return (
    <span
      key={key}
      title={title}
      className={`${BAR_TRACK_WIDTH} relative inline-block h-2.5 align-middle rounded-full bg-w-surface2`}
    >
      <span
        className={`absolute inset-y-0 rounded-full ${color}`}
        style={{ left: loPct, width: `${widthPct}%` }}
      />
    </span>
  )
}

export function renderSystemContent(text: string): ReactNode[] {
  // Manual scan rather than String.split: split() interleaves EVERY capture
  // group (including every alternative's own groups) into its result
  // array, so matches no longer land at predictable, alternating indices —
  // the original i % 2 scheme only worked with exactly one capture group.
  const nodes: ReactNode[] = []
  let lastIndex = 0
  let key = 0
  for (const m of text.matchAll(TOKEN_RE)) {
    const index = m.index ?? 0
    if (index > lastIndex) nodes.push(text.slice(lastIndex, index))
    const [full, bold, shiftId, shiftDate, barStart, barEnd, barColor] = m
    if (bold !== undefined) {
      nodes.push(
        <strong key={key++} className="font-semibold text-w-text">
          {bold}
        </strong>,
      )
    } else if (shiftId !== undefined) {
      nodes.push(
        <Link
          key={key++}
          to={`/app/employee-schedule?date=${shiftDate}&shift=${shiftId}`}
          className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2"
        >
          View shift →
        </Link>,
      )
    } else if (barStart !== undefined) {
      nodes.push(renderBar(key++, Number(barStart), Number(barEnd), Number(barColor)))
    } else if (full === '[[barruler]]') {
      nodes.push(renderRuler(key++))
    }
    lastIndex = index + m[0].length
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}
