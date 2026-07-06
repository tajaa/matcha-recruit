// Ports server/tests/brokers/test_book_risk.py — guards the FE recompute against
// drift from the canonical Python helper (risk_index.weighted_book_risk).
import { describe, it, expect } from 'vitest'
import { computeWeightedBookRisk, computeBookLoss, buildLossCurve } from './bookRisk'
import type { BookRiskClient } from '../types/riskIndex'

function c(index: number, band: string, headcount: number | null = null, premium: number | null = null,
           confidence?: 'high' | 'moderate' | 'low'): BookRiskClient {
  return { id: `${index}-${band}`, source: 'platform', name: `c${index}`, industry: null, index, band, headcount, annual_premium: premium, confidence }
}

describe('computeWeightedBookRisk', () => {
  it('empty book', () => {
    const a = computeWeightedBookRisk([], 'headcount')
    expect(a.weighted_mean).toBeNull()
    expect(a.equal_weight_mean).toBeNull()
    expect(a.weighted_band).toBeNull()
    expect(a.total_weight).toBe(0)
    expect(a.band_mix).toEqual({ strong: 0, adequate: 0, developing: 0, exposed: 0 })
  })

  it('all basis missing keeps equal mean only', () => {
    const a = computeWeightedBookRisk([c(40, 'developing'), c(80, 'strong')], 'headcount')
    expect(a.weighted_mean).toBeNull()
    expect(a.weighted_band).toBeNull()
    expect(a.equal_weight_mean).toBe(60)
    expect(a.weighted_count).toBe(0)
    expect(a.missing_basis_count).toBe(2)
  })

  it('single client', () => {
    const a = computeWeightedBookRisk([c(72, 'adequate', 50)], 'headcount')
    expect(a.weighted_mean).toBe(72)
    expect(a.weighted_band).toBe('adequate')
    expect(a.total_weight).toBe(50)
    expect(a.band_mix.adequate).toBe(1)
  })

  it('big account dominates weighted mean', () => {
    const a = computeWeightedBookRisk([c(90, 'strong', 10), c(30, 'exposed', 90)], 'headcount')
    expect(a.equal_weight_mean).toBe(60)
    expect(a.weighted_mean).toBe(36)
    expect(a.weighted_band).toBe('developing')
  })

  it('premium basis uses annual_premium', () => {
    const a = computeWeightedBookRisk([c(80, 'strong', 5, 100_000), c(40, 'developing', 5, 300_000)], 'premium')
    expect(a.basis).toBe('premium')
    expect(a.weighted_mean).toBe(50)
    expect(a.total_weight).toBe(400_000)
  })

  it('mixed missing excluded from weight but in equal mean', () => {
    const a = computeWeightedBookRisk([c(90, 'strong', 100), c(30, 'exposed')], 'headcount')
    expect(a.weighted_mean).toBe(90)
    expect(a.equal_weight_mean).toBe(60)
    expect(a.weighted_count).toBe(1)
    expect(a.missing_basis_count).toBe(1)
    expect(a.band_mix.strong).toBe(1)
  })

  it('band mix sums to one', () => {
    const a = computeWeightedBookRisk([
      c(90, 'strong', 20), c(70, 'adequate', 30), c(50, 'developing', 10), c(20, 'exposed', 40),
    ], 'headcount')
    expect(a.band_mix.strong).toBeCloseTo(0.2)
    expect(a.band_mix.exposed).toBeCloseTo(0.4)
    expect(a.band_mix.strong + a.band_mix.adequate + a.band_mix.developing + a.band_mix.exposed).toBeCloseTo(1)
  })

  it('confidence mix sums to one and weights correctly', () => {
    const a = computeWeightedBookRisk([
      c(80, 'strong', 10, null, 'high'), c(60, 'adequate', 10, null, 'moderate'), c(40, 'developing', 20, null, 'low'),
    ], 'headcount')
    expect(a.confidence_mix.low).toBeCloseTo(0.5)
    expect(a.confidence_mix.high + a.confidence_mix.moderate + a.confidence_mix.low).toBeCloseTo(1)
  })

  it('confidence mix ignores clients missing a confidence signal', () => {
    const a = computeWeightedBookRisk([c(80, 'strong', 10, null, 'high'), c(60, 'adequate', 10)], 'headcount')
    expect(a.confidence_mix.high).toBeCloseTo(0.5)
    expect(a.confidence_mix.high + a.confidence_mix.moderate + a.confidence_mix.low).toBeCloseTo(0.5)
  })
})

describe('computeBookLoss', () => {
  it('expected loss = premium × loss ratio (premium basis)', () => {
    const L = computeBookLoss([c(50, 'developing', 5, 100_000)], 'premium')
    expect(L.expected_loss).toBe(65_000)      // 100k × 0.65
    expect(L.mu).not.toBeNull()
    expect(L.pml99).toBeGreaterThan(L.expected_loss)  // tail above the mean
    expect(L.modeled_count).toBe(1)
  })

  it('headcount basis uses the per-head premium assumption', () => {
    const L = computeBookLoss([c(50, 'developing', 100)], 'headcount')
    expect(L.expected_loss).toBe(78_000)      // 100 × 1200 × 0.65
  })

  it('no exposure → no curve, counted as missing', () => {
    const L = computeBookLoss([c(40, 'developing'), c(60, 'adequate')], 'headcount')
    expect(L.expected_loss).toBe(0)
    expect(L.mu).toBeNull()
    expect(L.missing_exposure_count).toBe(2)
  })

  it('a risky client raises both expected loss and the tail (PML)', () => {
    const safe = [c(85, 'strong', 0, 500_000)]
    const withRisky = [c(85, 'strong', 0, 500_000), c(5, 'exposed', 0, 100_000)]
    const a = computeBookLoss(safe, 'premium')
    const b = computeBookLoss(withRisky, 'premium')
    expect(b.expected_loss).toBeGreaterThan(a.expected_loss)
    expect(b.pml99).toBeGreaterThan(a.pml99)
  })
})

describe('buildLossCurve', () => {
  it('empty when nothing to model', () => {
    expect(buildLossCurve([], 'premium')).toEqual([])
    expect(buildLossCurve([c(50, 'developing')], 'headcount')).toEqual([])
  })

  it('peak-normalized density and monotone-decreasing exceedance', () => {
    const pts = buildLossCurve([c(50, 'developing', 5, 200_000), c(20, 'exposed', 5, 80_000)], 'premium')
    expect(pts.length).toBe(90)
    expect(Math.max(...pts.map((p) => p.density))).toBeCloseTo(1, 5)  // peak = 1
    for (let i = 1; i < pts.length; i++) expect(pts[i].exceed).toBeLessThanOrEqual(pts[i - 1].exceed)
    expect(pts[0].exceed).toBeGreaterThan(0.5)   // tiny loss almost certainly exceeded
    expect(pts[pts.length - 1].exceed).toBeLessThan(0.1)  // far tail unlikely
  })
})
