import { describe, expect, it } from 'vitest'

import type { ProductDefinition } from '../types/dashboard'
import { productPriceDollars } from './tier'


function product(overrides: Partial<ProductDefinition> = {}): ProductDefinition {
  return {
    slug: 'safety-pro',
    name: 'Safety Pro',
    description: '',
    features: ['incidents'],
    gate_feature: 'incidents',
    pricing_model: 'per_seat',
    price_cents: 300,
    block_size: null,
    min_headcount: 1,
    max_headcount: 300,
    nav: null,
    ...overrides,
  }
}


describe('productPriceDollars', () => {
  it('prices per-location products from locations rather than employees', () => {
    const perLocation = product({ pricing_model: 'per_location', price_cents: 250 })

    expect(productPriceDollars(perLocation, 40, 3)).toBe(7.5)
    expect(productPriceDollars(perLocation, 40)).toBeNull()
  })

  it('preserves existing pricing models', () => {
    expect(productPriceDollars(product(), 25)).toBe(75)
    expect(productPriceDollars(product({ pricing_model: 'flat', price_cents: 19900 }), 25)).toBe(199)
    expect(productPriceDollars(product({ pricing_model: 'block', price_cents: 5000, block_size: 10 }), 11)).toBe(100)
    expect(productPriceDollars(product({ pricing_model: 'free', price_cents: null, gate_feature: null }), 25)).toBeNull()
    expect(productPriceDollars(product({ pricing_model: 'contact_sales', price_cents: null, gate_feature: null }), 25)).toBeNull()
  })
})
