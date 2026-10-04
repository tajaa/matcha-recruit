import { describe, expect, it } from 'vitest'
import { estimateSchedulingCost, VALUE_LIMITS, VALUE_PLAN } from './valueEstimate'

describe('scheduling cost estimate', () => {
  it('prices the highest plan', () => {
    expect(VALUE_PLAN.id).toBe('autopilot')
    expect(VALUE_PLAN.price).toBe(149)
  })
  it('converts weekly manager time to a monthly cost', () => {
    const result = estimateSchedulingCost({ locations: 1, managerRate: 25, hoursPerWeek: 4 })!
    expect(result.hoursPerMonth).toBeCloseTo(17.33, 2)
    expect(result.currentMonthly).toBeCloseTo(433.33, 2)
    expect(result.subscription).toBe(149)
    expect(result.breakEvenMinutes).toBeCloseTo(82.52, 2)
    expect(result.coversItself).toBe(true)
  })
  it('scales cost and subscription with locations, not the per-location break-even', () => {
    const one = estimateSchedulingCost({ locations: 1, managerRate: 30, hoursPerWeek: 5 })!
    const four = estimateSchedulingCost({ locations: 4, managerRate: 30, hoursPerWeek: 5 })!
    expect(four.currentMonthly).toBeCloseTo(one.currentMonthly * 4)
    expect(four.subscription).toBe(596)
    expect(four.breakEvenMinutes).toBe(one.breakEvenMinutes)
  })
  it('says when the time entered cannot cover the subscription', () => {
    const result = estimateSchedulingCost({ locations: 1, managerRate: 25, hoursPerWeek: 1 })!
    expect(result.breakEvenMinutes).toBeGreaterThan(60)
    expect(result.coversItself).toBe(false)
  })
  it('has no break-even without a wage', () => {
    const result = estimateSchedulingCost({ locations: 2, managerRate: 0, hoursPerWeek: 4 })!
    expect(result.currentMonthly).toBe(0)
    expect(result.breakEvenMinutes).toBeNull()
    expect(result.coversItself).toBe(false)
  })
  it('rejects blank, fractional-location, negative, and out-of-range inputs', () => {
    expect(estimateSchedulingCost({ locations: 1.5, managerRate: 25, hoursPerWeek: 4 })).toBeNull()
    expect(estimateSchedulingCost({ locations: 0, managerRate: 25, hoursPerWeek: 4 })).toBeNull()
    expect(estimateSchedulingCost({ locations: 1, managerRate: NaN, hoursPerWeek: 4 })).toBeNull()
    expect(estimateSchedulingCost({ locations: 1, managerRate: 25, hoursPerWeek: -1 })).toBeNull()
    expect(estimateSchedulingCost({ locations: VALUE_LIMITS.locations + 1, managerRate: 25, hoursPerWeek: 4 })).toBeNull()
  })
  it('accepts maximum inputs and produces finite results', () => {
    const result = estimateSchedulingCost({ locations: VALUE_LIMITS.locations, managerRate: VALUE_LIMITS.managerRate, hoursPerWeek: VALUE_LIMITS.hoursPerWeek })!
    expect(Number.isFinite(result.currentMonthly)).toBe(true)
  })
})
