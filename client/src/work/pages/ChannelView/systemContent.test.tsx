import { describe, it, expect } from 'vitest'
import { isValidElement } from 'react'
import { Link } from 'react-router-dom'
import { renderSystemContent, stripEmphasis, hasScheduleTokens, splitScheduleSegments } from './systemContent'

/** Mirrors the strings composed server-side by
 *  services/ems/event_intake.py:_confirmation_text and the two
 *  "Updated ... event" strings in werk/routes/channels_ws.py. */
const PILL = '📋 Logged **Operational** event (visible to HR admins in Ops).'

describe('renderSystemContent', () => {
  it('splits a Huume pill into plain / bold / plain', () => {
    const parts = renderSystemContent(PILL)
    expect(parts).toHaveLength(3)
    expect(parts[0]).toBe('📋 Logged ')
    expect(isValidElement(parts[1])).toBe(true)
    expect((parts[1] as React.ReactElement<{ children: string }>).props.children).toBe('Operational')
    expect(parts[2]).toBe(' event (visible to HR admins in Ops).')
  })

  it('leaves text with no markers as a single plain segment', () => {
    const parts = renderSystemContent('no emphasis here')
    expect(parts).toEqual(['no emphasis here'])
  })

  it('leaves an unbalanced marker literal rather than swallowing the rest', () => {
    // A stray `**` must not eat the tail of the sentence — better a visible
    // artifact than silently dropped content in a compliance-facing pill.
    const parts = renderSystemContent('half **open sentence')
    expect(parts).toEqual(['half **open sentence'])
  })

  it('handles a multi-line pill (the clarify-question form)', () => {
    const parts = renderSystemContent('📋 Logged **Safety** event.\n🤔 Who was involved?')
    expect(parts[2]).toContain('🤔')
  })

  it('renders a shift-link token as a Link to the deep-linked schedule route', () => {
    // Mirrors services/scheduling/schedule_chat.py:result_text's
    // `[[shift:<id>:<date>]]` token.
    const parts = renderSystemContent(
      '✅ Done — 1 shift is live (**Closer** Sat Aug 1 · Aisha Kim [[shift:26c4ef29-ca1d-4c59-9719-30219f8e9056:2026-08-01]]).',
    )
    const link = parts.find(
      (p): p is React.ReactElement<{ to: string; children: string }> =>
        isValidElement(p) && (p.props as { to?: string }).to?.startsWith('/ops/schedule') === true,
    )
    expect(link).toBeDefined()
    expect(link!.props.to).toBe(
      '/ops/schedule?date=2026-08-01&shift=26c4ef29-ca1d-4c59-9719-30219f8e9056',
    )
    expect(link!.props.children).toBe('View shift →')
  })

  it('handles bold and a shift-link token together in one pass', () => {
    // Regression guard: String.split() with two alternatives each carrying
    // capture groups interleaves ALL groups per match, breaking a naive
    // i % 2 alternation scheme — this pins the fix.
    const parts = renderSystemContent(
      '**Opener** Mon 8/3 · open [[shift:11111111-1111-1111-1111-111111111111:2026-08-03]] and **Closer** Tue 8/4 · open [[shift:22222222-2222-2222-2222-222222222222:2026-08-04]]',
    )
    const bolds = parts.filter(
      (p): p is React.ReactElement<{ children: string }> =>
        isValidElement(p) && p.type === 'strong',
    )
    expect(bolds.map((b) => b.props.children)).toEqual(['Opener', 'Closer'])
    const links = parts.filter(
      (p): p is React.ReactElement<{ to: string }> => isValidElement(p) && p.type === Link,
    )
    expect(links).toHaveLength(2)
    expect(links[0].props.to).toContain('11111111-1111-1111-1111-111111111111')
    expect(links[1].props.to).toContain('22222222-2222-2222-2222-222222222222')
  })

  it('renders a bar token as a positioned, titled colored bar', () => {
    // Mirrors services/scheduling/schedule_chat.py:schedule_strip's
    // `[[bar:<startMin>:<endMin>:<colorIdx>]]` token — window is 6:00-22:00
    // (360-1320 minutes), so 480-960 sits at (480-360)/960=12.5% width 50%.
    const parts = renderSystemContent('[[bar:480:960:0]] 08:00–16:00 opener · Aisha Kim')
    const bar = parts.find(
      (p): p is React.ReactElement<{ title: string }> =>
        isValidElement(p) && (p.props as { title?: string }).title === '08:00–16:00',
    )
    expect(bar).toBeDefined()
    const fill = (bar!.props as unknown as { children: React.ReactElement<{ style: { left: string; width: string } }> })
      .children
    expect(fill.props.style.left).toBe('12.5%')
    expect(fill.props.style.width).toBe('50.0%')
  })

  it('marks an overnight bar (endMin > 1440) in its title', () => {
    const parts = renderSystemContent('[[bar:1200:1560:1]] 20:00–02:00→+1d closer · Dana Whitfield')
    const bar = parts.find(
      (p): p is React.ReactElement<{ title: string }> =>
        isValidElement(p) && ((p.props as { title?: string }).title ?? '').includes('+1d'),
    )
    expect(bar).toBeDefined()
    expect(bar!.props.title).toBe('20:00–02:00 (+1d)')
  })

  it('renders a barruler token with the expected hour ticks', () => {
    const parts = renderSystemContent('[[barruler]]')
    const ruler = parts.find(isValidElement) as React.ReactElement<{
      children: React.ReactElement<{ children: string }>[]
    }>
    expect(ruler).toBeDefined()
    const tickLabels = ruler.props.children.map((tick) => tick.props.children)
    expect(tickLabels).toEqual(['6a', '9a', '12p', '3p', '6p', '9p'])
  })

  it('handles bold, a shift-link, and a bar token together in one pass', () => {
    // Regression guard: matchAll interleaves capture groups from ALL four
    // alternatives per match — this pins that bold/link/bar don't clobber
    // each other's group indices.
    const parts = renderSystemContent(
      '**Opener** [[shift:11111111-1111-1111-1111-111111111111:2026-08-03]] [[bar:480:960:0]]',
    )
    const hasBold = parts.some((p) => isValidElement(p) && p.type === 'strong')
    const hasLink = parts.some((p) => isValidElement(p) && p.type === Link)
    const hasBar = parts.some(
      (p) => isValidElement(p) && (p.props as { title?: string }).title === '08:00–16:00',
    )
    expect(hasBold).toBe(true)
    expect(hasLink).toBe(true)
    expect(hasBar).toBe(true)
  })
})

describe('stripEmphasis', () => {
  it('removes the markers but keeps the word', () => {
    expect(stripEmphasis(PILL)).toBe(
      '📋 Logged Operational event (visible to HR admins in Ops).',
    )
  })

  it('is a no-op on unmarked text', () => {
    expect(stripEmphasis('plain reply')).toBe('plain reply')
  })

  it('drops a shift-link token entirely (a raw link is useless in a compact preview)', () => {
    expect(
      stripEmphasis(
        '✅ Done — 1 shift is live (**Closer** Sat Aug 1 · Aisha Kim [[shift:26c4ef29-ca1d-4c59-9719-30219f8e9056:2026-08-01]]).',
      ),
    ).toBe('✅ Done — 1 shift is live (Closer Sat Aug 1 · Aisha Kim).')
  })

  it('drops bar and barruler tokens entirely, keeping the surrounding text', () => {
    // \s* on each removal pattern eats the token's own leading newline/
    // whitespace too (same idiom as the shift-link stripper below) — no
    // orphan blank line left behind.
    expect(
      stripEmphasis('Mon Aug 10\n[[barruler]]\n[[bar:480:960:0]] 08:00–16:00 opener · Aisha Kim'),
    ).toBe('Mon Aug 10 08:00–16:00 opener · Aisha Kim')
  })
})

// hasScheduleTokens / splitScheduleSegments — used by MessageBubble.tsx to
// split a Huume THREAD bubble's markdown prose from the server-composed
// schedule token lines mixed into it (schedule_chat.py's result/edit-result
// text + strip), which the bubble previously ran through <Markdown> whole,
// showing raw `[[bar:...]]`/`[[barruler]]`/`[[shift:...]]` text.
describe('hasScheduleTokens', () => {
  it('is false for plain markdown, including bold-only text', () => {
    expect(hasScheduleTokens('**Opener** added Elena.')).toBe(false)
    expect(hasScheduleTokens('Nothing staged yet.')).toBe(false)
  })

  it('is true when any schedule token is present', () => {
    expect(hasScheduleTokens('✅ Done [[shift:26c4ef29-ca1d-4c59-9719-30219f8e9056:2026-08-01]]')).toBe(true)
    expect(hasScheduleTokens('Sat Aug 8\n[[barruler]]')).toBe(true)
    expect(hasScheduleTokens('[[bar:480:960:0]] 08:00–16:00 opener · Aisha Kim')).toBe(true)
  })
})

describe('splitScheduleSegments', () => {
  it('returns a single markdown segment for pure prose', () => {
    const segs = splitScheduleSegments('Staged: assign Elena to the 12:30 shift.')
    expect(segs).toEqual([{ kind: 'markdown', text: 'Staged: assign Elena to the 12:30 shift.' }])
  })

  it('groups consecutive token lines into one tokens segment, plain lines stay markdown', () => {
    // A plain (no-token) line breaks a token run at LINE granularity — "Sat
    // Aug 8" here has no token of its own, so it merges with the preceding
    // markdown line rather than the following token lines.
    const text = [
      'Staged: assign Elena to the 12:30 shift.',
      'Sat Aug 8',
      '[[barruler]]',
      '[[bar:480:960:0]] 08:00–16:00 opener · Elena +1',
    ].join('\n')
    const segs = splitScheduleSegments(text)
    expect(segs.map((s) => s.kind)).toEqual(['markdown', 'tokens'])
    expect(segs[0].text).toBe('Staged: assign Elena to the 12:30 shift.\nSat Aug 8')
    expect(segs[1].text).toBe('[[barruler]]\n[[bar:480:960:0]] 08:00–16:00 opener · Elena +1')
  })

  it('a summary line carrying a shift token is its own tokens segment', () => {
    const text =
      '✅ Done — 1 change is live (**Opener** added Elena [[shift:26c4ef29-ca1d-4c59-9719-30219f8e9056:2026-08-08]]).'
    const segs = splitScheduleSegments(text)
    expect(segs.map((s) => s.kind)).toEqual(['tokens'])
  })

  it('re-splits back to markdown after a token block ends', () => {
    const text = '[[barruler]]\n[[bar:480:960:0]] shift\nLet me know if you need anything else.'
    const segs = splitScheduleSegments(text)
    expect(segs.map((s) => s.kind)).toEqual(['tokens', 'markdown'])
    expect(segs[1].text).toBe('Let me know if you need anything else.')
  })
})
