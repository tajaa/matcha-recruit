import { describe, expect, it } from 'vitest'
import { compareMessages, mergeMessages, upsertMessage } from './channelMessages'
import type { ChannelMessage } from './channels'

function msg(over: Partial<ChannelMessage>): ChannelMessage {
  return {
    id: 'id-' + Math.random(), channel_id: 'ch1', sender_id: 'u1',
    sender_name: 'U', sender_avatar_url: null, content: 'x',
    created_at: '2026-08-01T10:00:00+00:00', edited_at: null, ...over,
  }
}

describe('mergeMessages', () => {
  it('keeps a WS arrival that landed while the refetch was in flight', () => {
    const wsArrival = msg({ id: 'ws1', created_at: '2026-08-01T10:00:05+00:00' })
    const merged = mergeMessages([wsArrival], [msg({ id: 'r1' })])
    expect(merged.map((m) => m.id)).toContain('ws1')
  })

  it('drops a pending row whose cmid appears in the fetch (it landed)', () => {
    const pending = msg({ id: 'cmid-1', client_message_id: 'cmid-1', pending: true })
    const landed = msg({ id: 'srv-1', client_message_id: 'cmid-1' })
    const merged = mergeMessages([pending], [landed])
    expect(merged).toHaveLength(1)
    expect(merged[0].id).toBe('srv-1')
  })

  it('keeps an unlanded pending row', () => {
    const pending = msg({ id: 'cmid-2', client_message_id: 'cmid-2', pending: true })
    const merged = mergeMessages([pending], [msg({ id: 'r1' })])
    expect(merged.some((m) => m.id === 'cmid-2')).toBe(true)
  })

  it('prefers the server copy when both sides carry the same id', () => {
    const stale = msg({ id: 'same', content: 'old' })
    const fresh = msg({ id: 'same', content: 'edited' })
    const merged = mergeMessages([stale], [fresh])
    expect(merged).toHaveLength(1)
    expect(merged[0].content).toBe('edited')
  })

  it('yields one deterministic (created_at, id) order regardless of input order', () => {
    const a = msg({ id: 'a', created_at: '2026-08-01T10:00:01+00:00' })
    const b = msg({ id: 'b', created_at: '2026-08-01T10:00:01+00:00' })
    const c = msg({ id: 'c', created_at: '2026-08-01T10:00:00+00:00' })
    expect(mergeMessages([b, a], [c]).map((m) => m.id)).toEqual(['c', 'a', 'b'])
    expect(mergeMessages([c], [a, b]).map((m) => m.id)).toEqual(['c', 'a', 'b'])
  })
})

describe('upsertMessage', () => {
  it('replaces the pending row on echo (same cmid) instead of duplicating', () => {
    const pending = msg({ id: 'cmid-3', client_message_id: 'cmid-3', pending: true })
    const echo = msg({ id: 'srv-3', client_message_id: 'cmid-3' })
    const next = upsertMessage([pending], echo)
    expect(next).toHaveLength(1)
    expect(next[0].id).toBe('srv-3')
    expect(next[0].pending).toBeUndefined()
  })

  it('refreshes an existing row from a live replay', () => {
    const snapshot = msg({ id: 'dup', message_type: 'system' })
    const live = msg({
      id: 'dup',
      message_type: 'system',
      metadata: { action: { kind: 'event_draft', id: 'draft-1', status: 'pending' } },
    })
    const next = upsertMessage([snapshot], live)
    expect(next).toHaveLength(1)
    expect(next[0].metadata?.action).toEqual({ kind: 'event_draft', id: 'draft-1', status: 'pending' })
  })

  it('inserts out-of-order arrivals into (created_at, id) position', () => {
    const late = msg({ id: 'late', created_at: '2026-08-01T09:59:00+00:00' })
    const cur = msg({ id: 'cur', created_at: '2026-08-01T10:00:00+00:00' })
    expect(upsertMessage([cur], late).map((m) => m.id)).toEqual(['late', 'cur'])
  })
})

describe('compareMessages', () => {
  it('ties on created_at break by id', () => {
    const a = msg({ id: 'a' }); const b = msg({ id: 'b' })
    expect(compareMessages(a, b)).toBeLessThan(0)
  })
})
