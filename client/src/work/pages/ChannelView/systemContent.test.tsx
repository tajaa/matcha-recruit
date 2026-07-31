import { describe, it, expect } from 'vitest'
import { isValidElement } from 'react'
import { renderSystemContent, stripEmphasis } from './systemContent'

/** Mirrors the strings composed server-side by
 *  services/ems/event_intake.py:_confirmation_text and the two
 *  "Updated ... event" strings in werk/routes/channels_ws.py. */
const PILL = '📋 Logged **Operational** event (visible to HR admins in Events).'

describe('renderSystemContent', () => {
  it('splits a Huume pill into plain / bold / plain', () => {
    const parts = renderSystemContent(PILL)
    expect(parts).toHaveLength(3)
    expect(parts[0]).toBe('📋 Logged ')
    expect(isValidElement(parts[1])).toBe(true)
    expect((parts[1] as React.ReactElement<{ children: string }>).props.children).toBe('Operational')
    expect(parts[2]).toBe(' event (visible to HR admins in Events).')
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
})

describe('stripEmphasis', () => {
  it('removes the markers but keeps the word', () => {
    expect(stripEmphasis(PILL)).toBe(
      '📋 Logged Operational event (visible to HR admins in Events).',
    )
  })

  it('is a no-op on unmarked text', () => {
    expect(stripEmphasis('plain reply')).toBe('plain reply')
  })
})
