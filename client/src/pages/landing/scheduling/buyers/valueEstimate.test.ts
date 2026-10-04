import { describe, expect, it } from 'vitest'
import { estimatePlanValue, VALUE_LIMITS, WEEKS_PER_MONTH, type PlanAssumptions, type ValueBaseline } from './valueEstimate'

const baseline = (patch: Partial<ValueBaseline> = {}): ValueBaseline => ({ locations: 1, managerRate: 35, softwareMonthly: 40, staffHourlyCost: 20, overtimePremium: 10, setupCost: 0, setupHours: 0, minutes: { schedule: 240, requests: 60, breaks: 60, cost: 60 }, ...patch })
const assumptions = (patch: Partial<PlanAssumptions> = {}): PlanAssumptions => ({ minutes: { schedule: 180, requests: 30, breaks: 30, cost: 30 }, replaceSoftware: false, paidHoursAvoided: 0, overtimeHoursRescheduled: 0, ...patch })

describe('plan value estimate', () => {
  it('uses each price, its own time estimate, and supported capabilities', () => {
    const basic = estimatePlanValue(baseline(), assumptions(), 'basic')!
    const pro = estimatePlanValue(baseline(), assumptions(), 'pro')!
    const auto = estimatePlanValue(baseline(), assumptions({ minutes: { schedule: 60, requests: 20, breaks: 30, cost: 30 } }), 'autopilot')!
    expect([basic.subscription, pro.subscription, auto.subscription]).toEqual([49, 99, 149])
    expect(basic.managerHoursPerWeek).toBe(2)
    expect(pro.managerHoursPerWeek).toBe(2.5)
    expect(auto.managerHoursPerWeek).toBeCloseTo(14 / 3)
    expect(pro.managerCapacity).toBeCloseTo(2.5 * 35 * 52 / 12)
    expect(pro.netCash).toBe(-99)
    expect(pro.netValue - pro.netCash).toBeCloseTo(pro.managerCapacity)
  })
  it('values removed hours at regular cost and rescheduled overtime at premium only', () => {
    const result = estimatePlanValue(baseline(), assumptions({ paidHoursAvoided: 2, overtimeHoursRescheduled: 3 }), 'pro')!
    expect(result.paidLaborSavings).toBeCloseTo((2 * 20 + 3 * 10) * WEEKS_PER_MONTH)
    expect(result.netCash).toBeCloseTo(70 * WEEKS_PER_MONTH - 99)
    expect(estimatePlanValue(baseline(), assumptions({ paidHoursAvoided: 50, overtimeHoursRescheduled: 2 }), 'basic')!.paidLaborSavings).toBeCloseTo(2 * 10 * WEEKS_PER_MONTH)
  })
  it('counts software only when canceled and scales recurring figures, not switching cost', () => {
    expect(estimatePlanValue(baseline(), assumptions(), 'pro')!.softwareSavings).toBe(0)
    const one = estimatePlanValue(baseline({ setupCost: 600 }), assumptions({ replaceSoftware: true, paidHoursAvoided: 1 }), 'pro')!
    const three = estimatePlanValue(baseline({ locations: 3, setupCost: 600 }), assumptions({ replaceSoftware: true, paidHoursAvoided: 1 }), 'pro')!
    expect(one.softwareSavings).toBe(40)
    expect(three.managerHoursPerWeek).toBe(one.managerHoursPerWeek * 3)
    expect(three.subscription).toBe(one.subscription * 3)
    expect(three.netCash).toBeCloseTo(one.netCash * 3)
    expect(three.netValue).toBeCloseTo(one.netValue * 3)
    expect(three.firstYearValue).toBeCloseTo(three.netValue * 12 - 600)
    expect(three.firstYearCash).toBeCloseTo(three.netCash * 12 - 600)
  })
  it('shows losses and extra work rather than manufacturing savings', () => {
    const base = baseline()
    const unchanged = estimatePlanValue(base, assumptions({ minutes: base.minutes }), 'autopilot')!
    expect(unchanged.netValue).toBe(-149)
    expect(unchanged.netCash).toBe(-149)
    const worse = estimatePlanValue(base, assumptions({ minutes: { schedule: 300, requests: 90, breaks: 90, cost: 90 } }), 'pro')!
    expect(worse.managerHoursPerWeek).toBe(-2.5)
    expect(worse.managerCapacity).toBeLessThan(0)
    expect(worse.netValue).toBeLessThan(worse.netCash)
  })
  it('deducts internal onboarding time once from value, without inventing a cash outlay', () => {
    const result = estimatePlanValue(baseline({ locations: 3, setupCost: 300, setupHours: 6 }), assumptions(), 'pro')!
    expect(result.switchingTimeValue).toBe(210)
    expect(result.firstYearValue).toBeCloseTo(result.netValue * 12 - 300 - 210)
    expect(result.firstYearCash).toBeCloseTo(result.netCash * 12 - 300)
  })
  it('calculates break-even after cash offsets and handles unvalued manager time', () => {
    expect(estimatePlanValue(baseline(), assumptions({ replaceSoftware: true }), 'pro')!.breakEvenHoursPerWeek).toBeCloseTo(59 / (35 * WEEKS_PER_MONTH))
    expect(estimatePlanValue(baseline({ managerRate: 0 }), assumptions(), 'pro')!.breakEvenHoursPerWeek).toBeNull()
    expect(estimatePlanValue(baseline({ softwareMonthly: 200, managerRate: 0 }), assumptions({ replaceSoftware: true }), 'pro')!.breakEvenHoursPerWeek).toBe(0)
  })
  it.each([0, -1, 1.5, NaN, Infinity, VALUE_LIMITS.locations + 1])('rejects invalid location count %s', (locations) => {
    expect(estimatePlanValue(baseline({ locations }), assumptions(), 'pro')).toBeNull()
  })
  it.each(['managerRate', 'softwareMonthly', 'staffHourlyCost', 'overtimePremium', 'setupCost', 'setupHours'] as const)('rejects invalid %s', (key) => {
    for (const value of [-1, NaN, Infinity, VALUE_LIMITS[key] + 1]) expect(estimatePlanValue(baseline({ [key]: value }), assumptions(), 'pro')).toBeNull()
  })
  it.each([-1, NaN, Infinity, VALUE_LIMITS.minutes + 1])('rejects invalid current and remaining minutes %s', (value) => {
    expect(estimatePlanValue(baseline({ minutes: { ...baseline().minutes, schedule: value } }), assumptions(), 'pro')).toBeNull()
    expect(estimatePlanValue(baseline(), assumptions({ minutes: { ...assumptions().minutes, schedule: value } }), 'pro')).toBeNull()
  })
  it.each([-1, NaN, Infinity, VALUE_LIMITS.paidHours + 1])('rejects invalid paid-hour assumptions %s', (value) => {
    expect(estimatePlanValue(baseline(), assumptions({ paidHoursAvoided: value }), 'pro')).toBeNull()
    expect(estimatePlanValue(baseline(), assumptions({ overtimeHoursRescheduled: value }), 'pro')).toBeNull()
  })
  it('requires a cost before claiming positive paid-labor savings', () => {
    expect(estimatePlanValue(baseline({ staffHourlyCost: 0 }), assumptions({ paidHoursAvoided: 1 }), 'pro')).toBeNull()
    expect(estimatePlanValue(baseline({ overtimePremium: 0 }), assumptions({ overtimeHoursRescheduled: 1 }), 'basic')).toBeNull()
  })
  it('accepts maximum inputs and produces finite results', () => {
    const result = estimatePlanValue(baseline({ locations: 100, managerRate: 500, softwareMonthly: 10_000, staffHourlyCost: 500, overtimePremium: 500, setupCost: 1_000_000, setupHours: 10_000, minutes: { schedule: 10_080, requests: 10_080, breaks: 10_080, cost: 10_080 } }), assumptions({ paidHoursAvoided: 1_000, overtimeHoursRescheduled: 1_000 }), 'pro')!
    expect(Object.values(result).every((value) => typeof value === 'number' && Number.isFinite(value))).toBe(true)
  })
})
