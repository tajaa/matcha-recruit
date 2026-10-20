import { describe, expect, it } from 'vitest'
import { newRateRow, rateBodies, rateRow } from './deliveryOptions'

describe('rateBodies', () => {
  it('sends a pickup with its instructions and no per-item price', () => {
    const row = { ...newRateRow('pickup'), amount: '2', perItem: '9', instructions: '  The back door  ', postal: '941' }
    expect(rateBodies([row], 'kg')).toEqual([expect.objectContaining({
      name: 'Pickup', method: 'pickup', amount_cents: 200, per_item_cents: 0, instructions: 'The back door', postal_codes: [],
    })])
  })

  it('converts the weight limits to grams in the store’s unit', () => {
    const row = { ...newRateRow(), name: 'Heavy', minWeight: '10', maxWeight: '' }
    const [body] = rateBodies([row], 'lb') as { min_weight_g: number | null; max_weight_g: number | null }[]
    expect(body.min_weight_g).toBe(4536)
    expect(body.max_weight_g).toBeNull()
  })

  it('refuses bands out of order, unreadable days and unnamed options', () => {
    expect(rateBodies([{ ...newRateRow(), minSubtotal: '50', maxSubtotal: '10' }], 'kg')).toContain('lowest order value')
    expect(rateBodies([{ ...newRateRow(), minDays: '1.5' }], 'kg')).toContain('whole days')
    expect(rateBodies([{ ...newRateRow(), name: ' ' }], 'kg')).toBe('Give every delivery option a name.')
  })

  it('round-trips a saved option', () => {
    const saved = {
      name: 'Express', method: 'ship' as const, amount_cents: 1500, per_item_cents: 250, min_subtotal_cents: null,
      max_subtotal_cents: 20000, min_weight_g: null, max_weight_g: 5000, free_over_cents: 10000,
      delivery_min_days: 1, delivery_max_days: 2, postal_codes: [], instructions: null,
    }
    expect(rateBodies([rateRow(saved, 'kg')], 'kg')).toEqual([saved])
  })
})
