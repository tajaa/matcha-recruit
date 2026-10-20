import { describe, expect, it } from 'vitest'
import type { CappeProduct } from '../types'
import { MAX_VARIANTS, combinations, comboKey, rowsFromProduct, variantName, variantPayload } from './variants'

const size = { id: 'g-size', name: 'Size', select_type: 'single' as const, required: true, options: [{ id: 's', name: 'S' }, { id: 'm', name: 'M' }] }
const colour = { id: 'g-col', name: 'Colour', select_type: 'single' as const, required: true, options: [{ id: 'red', name: 'Red' }, { name: 'Blue' }] }
const extras = { name: 'Extras', select_type: 'multi' as const, required: false, options: [{ id: 'wrap', name: 'Gift wrap' }] }

const product = {
  id: 'p', name: 'Tee', option_groups: [
    { ...size, sort_order: 0, options: size.options.map((o) => ({ ...o, price_delta_cents: 0, sort_order: 0 })) },
    { ...colour, sort_order: 1, options: [{ id: 'red', name: 'Red', price_delta_cents: 0, sort_order: 0 }] },
  ],
  variants: [{ id: 'v1', option_ids: ['red', 'm'], sku: 'TEE-M-R', price_cents: 2500, inventory: 4, image_url: null, status: 'active', sort_order: 0 }],
} as unknown as CappeProduct

describe('the variant table', () => {
  it('is every combination of the required pick-one groups, in group order', () => {
    const { combos, tooMany } = combinations([size, colour, extras])
    expect(tooMany).toBe(false)
    expect(combos.map((c) => c.map((p) => p.option).join(' / '))).toEqual(['S / Red', 'S / Blue', 'M / Red', 'M / Blue'])
  })

  it('has no rows without a required pick-one group, and none past the cap', () => {
    expect(combinations([extras, { ...size, required: false }]).combos).toEqual([])
    const many = { ...size, options: Array.from({ length: 11 }, (_, i) => ({ id: `o${i}`, name: `O${i}` })) }
    expect(combinations([many, { ...many, name: 'Other' }])).toEqual({ combos: [], tooMany: true })
    expect(MAX_VARIANTS).toBe(100)
  })

  it('finds a saved variant whatever order its options are stored in', () => {
    const rows = rowsFromProduct(product)
    expect(rows[comboKey(['m', 'red'])]).toEqual({ id: 'v1', sku: 'TEE-M-R', price: '25', stock: '4', image_url: null, active: true })
  })
})

describe('the save request', () => {
  const combo = combinations([size, colour]).combos

  it('names each combination and sends stock only when it changed, with what the form showed', () => {
    const rows = rowsFromProduct(product)
    rows[comboKey(['s', 'new:1:Blue'])] = { sku: '', price: '', stock: '3', image_url: null, active: false }
    const out = variantPayload(combo, rows, product)
    if ('error' in out) throw new Error(out.error)
    const mRed = out.variants.find((v) => v.id === 'v1')
    expect(mRed).toEqual({ id: 'v1', options: [{ group: 'Size', option: 'M' }, { group: 'Colour', option: 'Red' }],
      sku: 'TEE-M-R', price_cents: 2500, image_url: null, status: 'active' })     // stock untouched: not sent
    const sBlue = out.variants.find((v) => v.options[0].option === 'S' && v.options[1].option === 'Blue')
    expect(sBlue).toMatchObject({ status: 'disabled', inventory: 3, price_cents: null })
    expect(sBlue).not.toHaveProperty('expected_inventory')

    rows[comboKey(['m', 'red'])] = { ...rows[comboKey(['m', 'red'])], stock: '' }
    const stopped = variantPayload(combo, rows, product)
    if ('error' in stopped) throw new Error(stopped.error)
    expect(stopped.variants.find((v) => v.id === 'v1')).toMatchObject({ inventory: null, expected_inventory: 4 })
  })

  it('refuses a price or a stock count it cannot read', () => {
    expect(variantPayload(combo, { [comboKey(['s', 'red'])]: { sku: '', price: '1,299.00', stock: '', image_url: null, active: true } }, null))
      .toEqual({ error: 'S / Red — enter the price as a plain amount, e.g. 29 or 29.99' })
    expect(variantPayload(combo, { [comboKey(['s', 'red'])]: { sku: '', price: '', stock: '2.5', image_url: null, active: true } }, null))
      .toEqual({ error: 'S / Red — stock is a whole number, 0 or more (blank = not tracked)' })
  })

  it('labels a saved variant by its options', () => {
    expect(variantName(product, ['red', 'm'])).toBe('M / Red')
    expect(variantName(product, ['gone'])).toBe('a removed combination')
  })
})
