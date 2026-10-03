import { describe, expect, it } from 'vitest'
import { estimateMonthlyValue } from './valueEstimate'

describe('buyer value estimate', () => {
  it('keeps time returned out of cash savings when payroll does not change', () => {
    const result = estimateMonthlyValue({ hours: 2, rate: 35, payroll: 30000, reduction: 0 }, 149)!
    expect(result.capacity).toBeCloseTo(303.333333)
    expect(result.labor).toBe(0)
    expect(result.net).toBeCloseTo(154.333333)
    expect(result.cash).toBe(-149)
  })

  it('uses a percentage of staff payroll and subtracts the subscription once', () => {
    const result = estimateMonthlyValue({ hours: 2, rate: 35, payroll: 30000, reduction: 1 }, 149)!
    expect(result.labor).toBe(300)
    expect(result.cash).toBe(151)
    expect(result.net - result.cash).toBeCloseTo(result.capacity)
  })

  it('shows a loss when there is no improvement', () => {
    expect(estimateMonthlyValue({ hours: 0, rate: 35, payroll: 30000, reduction: 0 }, 149)).toEqual({ capacity: 0, labor: 0, gross: 0, net: -149, cash: -149 })
  })

  it.each([
    { hours: NaN, rate: 35, payroll: 30000, reduction: 0 },
    { hours: -1, rate: 35, payroll: 30000, reduction: 0 },
    { hours: 2, rate: Infinity, payroll: 30000, reduction: 0 },
    { hours: 2, rate: 35, payroll: -30000, reduction: 0 },
    { hours: 2, rate: 35, payroll: 30000, reduction: 101 },
  ])('rejects invalid assumptions rather than displaying a plausible total: %o', (inputs) => {
    expect(estimateMonthlyValue(inputs, 149)).toBeNull()
  })
})
