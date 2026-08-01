import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

/** The TWO pieces of markup Huume's system messages may carry.
 *
 *  The backend composes these strings server-side
 *  (`services/ems/event_intake.py:_confirmation_text`, the two
 *  "Updated ... event" strings in `werk/routes/channels_ws.py`, and
 *  `services/scheduling/schedule_chat.py:result_text`), and the pill used to
 *  print `msg.content` raw — so a `**bold**` in the source showed up as
 *  literal asterisks in the channel. Rather than strip the emphasis (which
 *  left the event category visually indistinguishable from the rest of the
 *  sentence), parse exactly these two constructs.
 *
 *  Scope is intentional: `**bold**` and `[[shift:<id>:<date>]]`, nothing
 *  else. No italics, generic links, lists, or code. Anything richer belongs
 *  in a real renderer, and the content here is server-composed from a
 *  closed vocabulary — there is no user text in it to justify a parser with
 *  a larger attack surface. The link target is NEVER taken from the
 *  message text itself (that would be exactly the larger attack surface
 *  this scope note warns about) — only a UUID and an ISO date are, and this
 *  file builds the actual href from them.
 */
const TOKEN_RE = /\*\*(.+?)\*\*|\[\[shift:([0-9a-fA-F-]{36}):(\d{4}-\d{2}-\d{2})\]\]/g

export function stripEmphasis(text: string): string {
  // Compact single-line previews (the reply banner in MessageComposer, the
  // quoted stub above a reply) render plain strings, not nodes — without
  // this they'd show the raw `**`/`[[shift:...]]` a Huume pill carries.
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\s*\[\[shift:[0-9a-fA-F-]{36}:\d{4}-\d{2}-\d{2}\]\]/g, '')
}

/** Urgent (OSHA/severe) pills lead with 🚨 — the server-composed first
 *  character (event_intake._pill_emoji). Content is the ONE urgency signal
 *  that survives a REST history reload; the WS payload isn't re-sent. */
export function isUrgentSystemContent(text: string): boolean {
  return text.startsWith('\u{1F6A8}')
}

export function renderSystemContent(text: string): ReactNode[] {
  // Manual scan rather than String.split: split() interleaves EVERY capture
  // group (including the two from the shift-link alternative) into its
  // result array, so a bold match and a shift-link match no longer land at
  // predictable, alternating indices — the previous i % 2 scheme only
  // worked because there was exactly one capture group in play.
  const nodes: ReactNode[] = []
  let lastIndex = 0
  let key = 0
  for (const m of text.matchAll(TOKEN_RE)) {
    const index = m.index ?? 0
    if (index > lastIndex) nodes.push(text.slice(lastIndex, index))
    const [, bold, shiftId, shiftDate] = m
    if (bold !== undefined) {
      nodes.push(
        <strong key={key++} className="font-semibold text-w-text">
          {bold}
        </strong>,
      )
    } else {
      nodes.push(
        <Link
          key={key++}
          to={`/app/employee-schedule?date=${shiftDate}&shift=${shiftId}`}
          className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2"
        >
          View shift →
        </Link>,
      )
    }
    lastIndex = index + m[0].length
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}
