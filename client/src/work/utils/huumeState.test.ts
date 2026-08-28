import { describe, it, expect } from 'vitest'
import { getHuumeState, hasHuumeContent, shouldShowHuumePanel, deriveHuumeArtifacts, defaultArtifactKey } from './huumeState'
import type { HuumeAction, HuumePlan } from '../types'

describe('getHuumeState', () => {
  it('returns empty plans for null/undefined state', () => {
    expect(getHuumeState(null)).toEqual({ plans: {}, records: [] })
    expect(getHuumeState(undefined)).toEqual({ plans: {}, records: [] })
  })

  it('returns empty plans for an empty object', () => {
    expect(getHuumeState({})).toEqual({
      plans: {}, records: [], offer: undefined, action: undefined, legal: undefined, handbook: undefined,
    })
  })

  it('round-trips every key when present', () => {
    const state = {
      huume_plans: { 'offer-1': { status: 'proposed' } },
      huume_offer: { offer_id: 'offer-1', status: 'sent' },
      huume_action: { type: 'send_offer', offer_id: 'offer-1', status: 'proposed' },
      huume_legal: { matter_id: 'matter-1', title: 'Test matter' },
      huume_handbook: { session_id: 'sess-1', pending_drafts: [{ draft_id: 'd1' }] },
      huume_records: [{ record_type: 'incident', record_id: 'rec-1', label: 'IR-2026-004' }],
    }
    const h = getHuumeState(state)
    expect(h.plans).toEqual(state.huume_plans)
    expect(h.offer).toEqual(state.huume_offer)
    expect(h.action).toEqual(state.huume_action)
    expect(h.legal).toEqual(state.huume_legal)
    expect(h.handbook).toEqual(state.huume_handbook)
    expect(h.records).toEqual(state.huume_records)
  })

  it('defaults records to [] when huume_records is absent or not an array', () => {
    expect(getHuumeState({}).records).toEqual([])
    expect(getHuumeState({ huume_records: 'not-an-array' }).records).toEqual([])
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
    expect(hasHuumeContent({ plans: {}, records: [{ record_type: 'incident', record_id: 'r1' }] })).toBe(true)
  })

  it('is false when records is an empty array', () => {
    expect(hasHuumeContent({ plans: {}, records: [] })).toBe(false)
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

  // Regression: the idKey ternary only handled 6 of the 8 non-offer action
  // types and threw 'unreachable' for the rest — discipline_from_incident/
  // discipline_decision were already silently broken, and adding
  // ems_promote without a case here would have crashed the panel the same
  // way instead of the "renders blank" bug it was meant to fix.
  it('yields an action artifact for discipline_from_incident', () => {
    const action: HuumeAction = {
      type: 'discipline_from_incident', status: 'proposed', confirm_id: 'c1',
      employee_id: 'e1', infraction_type: 'attendance',
    }
    const result = deriveHuumeArtifacts({ plans: {}, action })
    expect(result).toEqual([{ kind: 'action', key: 'action:discipline_from_incident:c1', action }])
  })

  it('yields an action artifact for discipline_decision', () => {
    const action: HuumeAction = { type: 'discipline_decision', status: 'proposed', record_id: 'r1' }
    const result = deriveHuumeArtifacts({ plans: {}, action })
    expect(result).toEqual([{ kind: 'action', key: 'action:discipline_decision:r1', action }])
  })

  it('yields an action artifact for ems_promote', () => {
    const action: HuumeAction = { type: 'ems_promote', status: 'proposed', event_id: 'ev1' }
    const result = deriveHuumeArtifacts({ plans: {}, action })
    expect(result).toEqual([{ kind: 'action', key: 'action:ems_promote:ev1', action }])
  })

  it('yields an action artifact for inventory_movement', () => {
    const action: HuumeAction = {
      type: 'inventory_movement', status: 'proposed', confirm_id: 'c1', kind: 'in',
      item_id: 'i1', quantity: 5,
    }
    const result = deriveHuumeArtifacts({ plans: {}, action })
    expect(result).toEqual([{ kind: 'action', key: 'action:inventory_movement:c1', action }])
  })

  it('yields an action artifact for inventory_order_decision', () => {
    const action: HuumeAction = {
      type: 'inventory_order_decision', status: 'proposed', order_id: 'o1', decision: 'approve',
    }
    const result = deriveHuumeArtifacts({ plans: {}, action })
    expect(result).toEqual([{ kind: 'action', key: 'action:inventory_order_decision:o1', action }])
  })

  it('yields an action artifact for inventory_item_create', () => {
    const action: HuumeAction = {
      type: 'inventory_item_create', status: 'proposed', confirm_id: 'c1', name: 'Gloves',
    }
    const result = deriveHuumeArtifacts({ plans: {}, action })
    expect(result).toEqual([{ kind: 'action', key: 'action:inventory_item_create:c1', action }])
  })

  it('yields an action artifact for inventory_item_archive', () => {
    const action: HuumeAction = { type: 'inventory_item_archive', status: 'proposed', item_id: 'i1' }
    const result = deriveHuumeArtifacts({ plans: {}, action })
    expect(result).toEqual([{ kind: 'action', key: 'action:inventory_item_archive:i1', action }])
  })

  it('yields an action artifact for inventory_receipt', () => {
    const action: HuumeAction = {
      type: 'inventory_receipt', status: 'proposed', confirm_id: 'c1',
      lines: [{ item_id: 'i1', quantity: 10 }],
    }
    const result = deriveHuumeArtifacts({ plans: {}, action })
    expect(result).toEqual([{ kind: 'action', key: 'action:inventory_receipt:c1', action }])
  })

  it('yields an action artifact for a generated weekly schedule', () => {
    const action: HuumeAction = {
      type: 'schedule_week_draft', status: 'proposed', confirm_id: 'c1',
      generation_run_id: 'g1', location_id: 'l1', week_start: '2026-08-23',
      source_mode: 'existing', metrics: { filled_positions: 8, required_positions: 10 },
    }
    const result = deriveHuumeArtifacts({ plans: {}, action })
    expect(result).toEqual([{ kind: 'action', key: 'action:schedule_week_draft:c1', action }])
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
      records: [{ record_type: 'incident', record_id: 'r1', label: 'IR-2026-004' }],
    })
    expect(result.map((a) => a.kind)).toEqual(['offer', 'plan', 'action', 'handbook', 'legal', 'record'])
  })

  it('yields a record artifact keyed record:<type>:<id>', () => {
    const result = deriveHuumeArtifacts({ plans: {}, records: [{ record_type: 'er_case', record_id: 'r1', label: 'ER-2026-002' }] })
    expect(result).toEqual([{ kind: 'record', key: 'record:er_case:r1', recordType: 'er_case', recordId: 'r1', label: 'ER-2026-002' }])
  })

  it('yields one artifact per open record, in list order', () => {
    const result = deriveHuumeArtifacts({
      plans: {},
      records: [
        { record_type: 'incident', record_id: 'r1', label: 'IR-1' },
        { record_type: 'incident', record_id: 'r2', label: 'IR-2' },
        { record_type: 'employee', record_id: 'e1', label: 'Jane Doe' },
      ],
    })
    expect(result.map((a) => a.key)).toEqual(['record:incident:r1', 'record:incident:r2', 'record:employee:e1'])
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
