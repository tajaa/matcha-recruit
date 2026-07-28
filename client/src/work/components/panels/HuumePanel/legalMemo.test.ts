import { describe, it, expect } from 'vitest'
import { pickLatestMemo, tokenizeCids } from './legalMemo'
import type { MatterMessage } from '../../../../api/legal-defense/legalDefense'

function msg(role: MatterMessage['role'], content: string, metadata: MatterMessage['metadata'] = null): MatterMessage {
  return { role, content, metadata, created_at: '2026-07-28T00:00:00Z' }
}

describe('pickLatestMemo', () => {
  it('is null for an empty transcript', () => {
    expect(pickLatestMemo([])).toBeNull()
  })

  it('is null when only user messages exist', () => {
    expect(pickLatestMemo([msg('user', 'hi')])).toBeNull()
  })

  it('prefers the newest assistant message with a non-empty evidence_map, even if an older one', () => {
    const withEvidence = msg('assistant', 'older analysis', { evidence_map: [{ point: 'p', cited_ids: ['x'] }] })
    const newerNoEvidence = msg('assistant', 'newer chit-chat')
    const result = pickLatestMemo([withEvidence, newerNoEvidence])
    expect(result).toBe(withEvidence)
  })

  it('falls back to the newest assistant message when none has evidence_map', () => {
    const first = msg('assistant', 'first')
    const second = msg('assistant', 'second')
    expect(pickLatestMemo([first, second])).toBe(second)
  })
})

describe('tokenizeCids', () => {
  it('splits plain text with no tokens into one string part', () => {
    expect(tokenizeCids('nothing here')).toEqual(['nothing here'])
  })

  it('extracts a bracketed cid token', () => {
    const id = '11111111-1111-1111-1111-111111111111'
    const result = tokenizeCids(`see [incident:${id}] for detail`)
    expect(result).toEqual(['see ', { type: 'incident', id }, ' for detail'])
  })

  it('extracts an unbracketed cid token', () => {
    const id = '22222222-2222-2222-2222-222222222222'
    const result = tokenizeCids(`per discipline:${id}.`)
    expect(result).toEqual(['per ', { type: 'discipline', id }, '.'])
  })

  it('leaves an unrecognized prefix as plain text', () => {
    const text = 'see [foo:11111111-1111-1111-1111-111111111111]'
    expect(tokenizeCids(text)).toEqual([text])
  })

  it('handles multiple tokens in one string', () => {
    const a = '11111111-1111-1111-1111-111111111111'
    const b = '22222222-2222-2222-2222-222222222222'
    const result = tokenizeCids(`[incident:${a}] and [er_case:${b}]`)
    expect(result).toEqual([{ type: 'incident', id: a }, ' and ', { type: 'er_case', id: b }])
  })
})
