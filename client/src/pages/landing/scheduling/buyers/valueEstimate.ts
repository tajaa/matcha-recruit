import { planById } from './plans'

export const WEEKS_PER_MONTH = 52 / 12
export const VALUE_LIMITS = { locations: 100, managerRate: 500, hoursPerWeek: 168 } as const
/** The estimate always prices the highest plan. */
export const VALUE_PLAN = planById('autopilot')

export type SchedulingCostInput = { locations: number; managerRate: number; hoursPerWeek: number }

export type SchedulingCost = {
  /** Manager hours spent building schedules, per month, all locations. */
  hoursPerMonth: number
  /** What that time costs at the entered wage, per month, all locations. */
  currentMonthly: number
  subscription: number
  /** Minutes saved per week, per location, that cover the subscription. Null when the wage is $0. */
  breakEvenMinutes: number | null
  /** Break-even fits inside the time entered. */
  coversItself: boolean
}

export const inRange = (value: number, max: number) => Number.isFinite(value) && value >= 0 && value <= max

/** Wage and hours are per location. No saving is assumed: the result is today's
 * cost, the subscription, and the time that would have to come back to cover it.
 */
export function estimateSchedulingCost({ locations, managerRate, hoursPerWeek }: SchedulingCostInput): SchedulingCost | null {
  if (!Number.isInteger(locations) || locations < 1 || locations > VALUE_LIMITS.locations) return null
  if (!inRange(managerRate, VALUE_LIMITS.managerRate) || !inRange(hoursPerWeek, VALUE_LIMITS.hoursPerWeek)) return null
  const hoursPerMonth = hoursPerWeek * WEEKS_PER_MONTH * locations
  const breakEvenMinutes = managerRate > 0 ? VALUE_PLAN.price / (managerRate * WEEKS_PER_MONTH) * 60 : null
  return {
    hoursPerMonth,
    currentMonthly: hoursPerMonth * managerRate,
    subscription: VALUE_PLAN.price * locations,
    breakEvenMinutes,
    coversItself: breakEvenMinutes !== null && breakEvenMinutes <= hoursPerWeek * 60,
  }
}
