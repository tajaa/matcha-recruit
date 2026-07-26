import { describe, it, expect } from 'vitest'
import { getHuumeState, hasHuumeContent } from './huumeState'

describe('getHuumeState', () => {
  it('returns empty plans for null/undefined state', () => {
    expect(getHuumeState(null)).toEqual({ plans: {} })
    expect(getHuumeState(undefined)).toEqual({ plans: {} })
  })

  it('returns empty plans for an empty object', () => {
    expect(getHuumeState({})).toEqual({ plans: {} })
  })

  it('round-trips every key when present', () => {
    const state = {
      huume_plans: { 'offer-1': { status: 'proposed' } },
      huume_offer: { offer_id: 'offer-1', status: 'sent' },
      huume_action: { type: 'send_offer', offer_id: 'offer-1', status: 'proposed' },
      huume_legal: { matter_id: 'matter-1', title: 'Test matter' },
      huume_handbook: { session_id: 'sess-1', pending_drafts: [{ draft_id: 'd1' }] },
    }
    const h = getHuumeState(state)
    expect(h.plans).toEqual(state.huume_plans)
    expect(h.offer).toEqual(state.huume_offer)
    expect(h.action).toEqual(state.huume_action)
    expect(h.legal).toEqual(state.huume_legal)
    expect(h.handbook).toEqual(state.huume_handbook)
  })
})

describe('hasHuumeContent', () => {
  it('is false when nothing is present', () => {
    expect(hasHuumeContent({ plans: {} })).toBe(false)
  })

  it('is true when plans exist', () => {
    expect(hasHuumeContent({ plans: { 'offer-1': {} as never } })).toBe(true)
  })

  it('is true when an action is staged', () => {
    expect(hasHuumeContent({ plans: {}, action: { type: 'send_offer', offer_id: 'x', status: 'proposed' } })).toBe(true)
  })

  it('is true when a legal matter is present', () => {
    expect(hasHuumeContent({ plans: {}, legal: { matter_id: 'm1' } })).toBe(true)
  })

  it('is false when handbook has no pending drafts', () => {
    expect(hasHuumeContent({ plans: {}, handbook: { session_id: 's1', pending_drafts: [] } })).toBe(false)
  })

  it('is true when handbook has a pending draft', () => {
    expect(hasHuumeContent({ plans: {}, handbook: { session_id: 's1', pending_drafts: [{ draft_id: 'd1' }] } })).toBe(true)
  })
})
