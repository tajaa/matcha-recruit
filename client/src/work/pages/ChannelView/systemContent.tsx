import type { ReactNode } from 'react'

/** The ONE piece of markup Huume's system messages may carry.
 *
 *  The backend composes these strings server-side
 *  (`services/ems/event_intake.py:_confirmation_text`, and the two
 *  "Updated ... event" strings in `werk/routes/channels_ws.py`), and the
 *  pill used to print `msg.content` raw — so a `**bold**` in the source
 *  showed up as literal asterisks in the channel. Rather than strip the
 *  emphasis (which left the event category visually indistinguishable from
 *  the rest of the sentence), parse exactly this one construct.
 *
 *  Scope is intentional: `**` pairs and nothing else. No italics, links,
 *  lists, or code. Anything richer belongs in a real renderer, and the
 *  content here is server-composed from a closed vocabulary — there is no
 *  user text in it to justify a parser with a larger attack surface.
 */
export function stripEmphasis(text: string): string {
  // Compact single-line previews (the reply banner in MessageComposer, the
  // quoted stub above a reply) render plain strings, not nodes — without
  // this they'd show the raw `**` a Huume pill carries.
  return text.replace(/\*\*(.+?)\*\*/g, '$1')
}

export function renderSystemContent(text: string): ReactNode[] {
  // Split keeps the capture group, so segments alternate
  // plain / bold / plain / bold / … starting at plain.
  const parts = text.split(/\*\*(.+?)\*\*/g)
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <strong key={i} className="font-semibold text-w-text">
        {part}
      </strong>
    ) : (
      part
    ),
  )
}
