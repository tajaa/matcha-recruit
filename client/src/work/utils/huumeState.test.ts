import { describe, it, expect } from 'vitest'
import { getHuumeState, hasHuumeContent, shouldShowHuumePanel, deriveHuumeArtifacts, defaultArtifactKey } from './huumeState'
import type { HuumeAction, HuumePlan } from '../types'

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
      huume_record: { record_type: 'incident', record_id: 'rec-1', label: 'IR-2026-004' },
    }
    const h = getHuumeState(state)
    expect(h.plans).toEqual(state.huume_plans)
    expect(h.offer).toEqual(state.huume_offer)
    expect(h.action).toEqual(state.huume_action)
    expect(h.legal).toEqual(state.huume_legal)
    expect(h.handbook).toEqual(state.huume_handbook)
    expect(h.record).toEqual(state.huume_record)
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

  it('is true when a record is open', () => {
    expect(hasHuumeContent({ plans: {}, record: { record_type: 'incident', record_id: 'r1' } })).toBe(true)
  })

  it('is true when only an offer is present', () => {
    expect(hasHuumeContent({ plans: {}, offer: { offer_id: 'o1', status: 'sent' } })).toBe(true)
  })

  it('is false when handbook has no pending drafts', () => {
    expect(hasHuumeContent({ plans: {}, handbook: { session_id: 's1', pending_drafts: [] } })).toBe(false)
  })

  it('is true when handbook has a pending draft', () => {
    expect(hasHuumeContent({ plans: {}, handbook: { session_id: 's1', pending_drafts: [{ draft_id: 'd1' }] } })).toBe(true)
  })
})

describe('shouldShowHuumePanel', () => {
  const staged = { huume_offer: { offer_id: 'o1', status: 'sent' } }

  it('is false when huume mode is off, regardless of content', () => {
    expect(shouldShowHuumePanel({ huumeMode: false, state: staged })).toBe(false)
  })

  it('is false without current_state', () => {
    expect(shouldShowHuumePanel({ huumeMode: true, state: null })).toBe(false)
    expect(shouldShowHuumePanel({ huumeMode: true, state: undefined })).toBe(false)
  })

  it('shows when content exists, even over a PDF or agent panel', () => {
    expect(shouldShowHuumePanel({ huumeMode: true, state: staged, pdfUrl: 'blob:x' })).toBe(true)
    expect(shouldShowHuumePanel({ huumeMode: true, state: staged, agentMode: true })).toBe(true)
  })

  it('yields to the PDF preview when nothing is staged (smoke case c)', () => {
    expect(shouldShowHuumePanel({ huumeMode: true, state: {}, pdfUrl: 'blob:x' })).toBe(false)
  })

  it('yields to the AgentPanel when nothing is staged (smoke case c)', () => {
    expect(shouldShowHuumePanel({ huumeMode: true, state: {}, agentMode: true })).toBe(false)
  })

  it('shows the empty state on a bare huume thread', () => {
    expect(shouldShowHuumePanel({ huumeMode: true, state: {} })).toBe(true)
  })
})

describe('deriveHuumeArtifacts', () => {
  const plan: HuumePlan = {
    status: 'proposed', offer_id: 'o1',
    employee: { first_name: 'Francesca' }, employee_id: null, steps: [],
  }

  it('is empty for no content', () => {
    expect(deriveHuumeArtifacts({ plans: {} })).toEqual([])
  })

  it('yields an offer artifact from huume_offer', () => {
    const result = deriveHuumeArtifacts({ plans: {}, offer: { offer_id: 'o1', status: 'draft' } })
    expect(result).toEqual([{ kind: 'offer', key: 'offer:o1', offerId: 'o1' }])
  })

  it('synthesizes the offer artifact from a staged send_offer action when huume_offer is absent', () => {
    const action: HuumeAction = { type: 'send_offer', offer_id: 'o1', status: 'proposed' }
    const result = deriveHuumeArtifacts({ plans: {}, action })
    expect(result).toEqual([{ kind: 'offer', key: 'offer:o1', offerId: 'o1' }])
  })

  it('does not duplicate the offer artifact when both huume_offer and a send_offer action share an id', () => {
    const action: HuumeAction = { type: 'send_offer', offer_id: 'o1', status: 'sent' }
    const result = deriveHuumeArtifacts({ plans: {}, offer: { offer_id: 'o1', status: 'sent' }, action })
    expect(result.filter((a) => a.kind === 'offer')).toHaveLength(1)
  })

  it('yields two offer artifacts when huume_offer and a staged send_offer name different ids', () => {
    // draft A -> send A -> draft B (huume_offer now points at B) ->
    // send_offer re-staged against A. The panel must still be able to show
    // A's letter for the pending confirm, not just B's latest draft.
    const action: HuumeAction = { type: 'send_offer', offer_id: 'o1', status: 'proposed' }
    const result = deriveHuumeArtifacts({ plans: {}, offer: { offer_id: 'o2', status: 'draft' }, action })
    const offers = result.filter((a) => a.kind === 'offer')
    expect(offers.map((a) => a.offerId)).toEqual(['o2', 'o1'])
  })

  it('yields one artifact per plan, after the offer', () => {
    const plan2: HuumePlan = { ...plan, offer_id: 'o2', employee: { first_name: 'Marcus' } }
    const result = deriveHuumeArtifacts({
      plans: { o1: plan, o2: plan2 },
      offer: { offer_id: 'o1', status: 'accepted' },
    })
    expect(result.map((a) => a.kind)).toEqual(['offer', 'plan', 'plan'])
    expect(result[1]).toEqual({ kind: 'plan', key: 'plan:o1', offerId: 'o1', plan })
  })

  it('yields an action artifact for a proposed non-offer action', () => {
    const action: HuumeAction = {
      type: 'discipline_draft', status: 'proposed', confirm_id: 'c1', employee_name: 'Jane',
    }
    const result = deriveHuumeArtifacts({ plans: {}, action })
    expect(result).toEqual([{ kind: 'action', key: 'action:discipline_draft:c1', action }])
  })

  it('send_offer never yields a kind:action artifact', () => {
    const action: HuumeAction = { type: 'send_offer', offer_id: 'o1', status: 'proposed' }
    const result = deriveHuumeArtifacts({ plans: {}, action })
    expect(result.some((a) => a.kind === 'action')).toBe(false)
  })

  it('omits a cancelled action', () => {
    const action: HuumeAction = { type: 'discipline_draft', status: 'cancelled', confirm_id: 'c1' }
    expect(deriveHuumeArtifacts({ plans: {}, action })).toEqual([])
  })

  it('omits handbook when pending_drafts is empty', () => {
    const result = deriveHuumeArtifacts({ plans: {}, handbook: { session_id: 's1', pending_drafts: [] } })
    expect(result).toEqual([])
  })

  it('orders offer, plan, action, handbook, legal, record', () => {
    const action: HuumeAction = { type: 'ir_report', status: 'proposed', confirm_id: 'c1' }
    const result = deriveHuumeArtifacts({
      plans: { o1: plan },
      offer: { offer_id: 'o1', status: 'sent' },
      action,
      handbook: { session_id: 's1', pending_drafts: [{ draft_id: 'd1' }] },
      legal: { matter_id: 'm1' },
      record: { record_type: 'incident', record_id: 'r1', label: 'IR-2026-004' },
    })
    expect(result.map((a) => a.kind)).toEqual(['offer', 'plan', 'action', 'handbook', 'legal', 'record'])
  })

  it('yields a record artifact keyed record:<type>:<id>', () => {
    const result = deriveHuumeArtifacts({ plans: {}, record: { record_type: 'er_case', record_id: 'r1', label: 'ER-2026-002' } })
    expect(result).toEqual([{ kind: 'record', key: 'record:er_case:r1', recordType: 'er_case', recordId: 'r1', label: 'ER-2026-002' }])
  })
})

describe('defaultArtifactKey', () => {
  it('picks the offer artifact for a proposed send_offer', () => {
    const action: HuumeAction = { type: 'send_offer', offer_id: 'o1', status: 'proposed' }
    const artifacts = deriveHuumeArtifacts({ plans: {}, action })
    expect(defaultArtifactKey(artifacts, action)).toBe('offer:o1')
  })

  it('picks the action artifact for a proposed non-offer action', () => {
    const action: HuumeAction = { type: 'discipline_draft', status: 'proposed', confirm_id: 'c1' }
    const artifacts = deriveHuumeArtifacts({ plans: {}, action })
    expect(defaultArtifactKey(artifacts, action)).toBe('action:discipline_draft:c1')
  })

  it('picks the offer_id-matching artifact when a proposed send_offer diverges from huume_offer', () => {
    const action: HuumeAction = { type: 'send_offer', offer_id: 'o1', status: 'proposed' }
    const artifacts = deriveHuumeArtifacts({ plans: {}, offer: { offer_id: 'o2', status: 'draft' }, action })
    expect(defaultArtifactKey(artifacts, action)).toBe('offer:o1')
  })

  it('falls back to the first artifact when there is no proposed action', () => {
    const artifacts = deriveHuumeArtifacts({ plans: {}, legal: { matter_id: 'm1' } })
    expect(defaultArtifactKey(artifacts)).toBe('legal:m1')
  })

  it('is null when there are no artifacts', () => {
    expect(defaultArtifactKey([])).toBeNull()
  })
})
