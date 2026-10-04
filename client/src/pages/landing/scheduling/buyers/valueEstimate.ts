import { planById, TIME_TASKS, type PlanId, type TimeTask } from './plans'

export const WEEKS_PER_MONTH = 52 / 12
export const VALUE_LIMITS = {
  locations: 100, managerRate: 500, softwareMonthly: 10_000,
  staffHourlyCost: 500, overtimePremium: 500, setupCost: 1_000_000, setupHours: 10_000,
  minutes: 10_080, paidHours: 1_000,
} as const

export type ValueBaseline = {
  locations: number
  managerRate: number
  softwareMonthly: number
  staffHourlyCost: number
  overtimePremium: number
  setupCost: number
  setupHours: number
  minutes: Record<TimeTask, number>
}

export type PlanAssumptions = {
  minutes: Record<TimeTask, number>
  replaceSoftware: boolean
  paidHoursAvoided: number
  overtimeHoursRescheduled: number
}

export type PlanValue = {
  managerHoursPerWeek: number
  managerCapacity: number
  paidLaborSavings: number
  softwareSavings: number
  subscription: number
  netCash: number
  netValue: number
  firstYearValue: number
  firstYearCash: number
  switchingTimeValue: number
  breakEvenHoursPerWeek: number | null
}

export const inRange = (value: number, max: number) => Number.isFinite(value) && value >= 0 && value <= max

/** Inputs are per location, except setupCost and setupHours (business totals).
 * Remaining time includes all review and corrections. Overtime hours still
 * worked at regular pay save only the premium, never the whole wage.
 * Basic retains cost-review time and cannot claim labor-cost-review savings.
 */
export function estimatePlanValue(baseline: ValueBaseline, assumptions: PlanAssumptions, id: PlanId): PlanValue | null {
  const plan = planById(id)
  if (!Number.isInteger(baseline.locations) || baseline.locations < 1 || baseline.locations > VALUE_LIMITS.locations) return null
  for (const key of ['managerRate', 'softwareMonthly', 'staffHourlyCost', 'overtimePremium', 'setupCost', 'setupHours'] as const) {
    if (!inRange(baseline[key], VALUE_LIMITS[key])) return null
  }
  let minutesReturned = 0
  for (const { id: task } of TIME_TASKS) {
    const remaining = task === 'cost' && !plan.laborCost ? baseline.minutes[task] : assumptions.minutes[task]
    if (!inRange(baseline.minutes[task], VALUE_LIMITS.minutes) || !inRange(remaining, VALUE_LIMITS.minutes)) return null
    minutesReturned += baseline.minutes[task] - remaining
  }
  const paidHoursAvoided = plan.laborCost ? assumptions.paidHoursAvoided : 0
  if (!inRange(paidHoursAvoided, VALUE_LIMITS.paidHours) || !inRange(assumptions.overtimeHoursRescheduled, VALUE_LIMITS.paidHours)) return null
  if (paidHoursAvoided > 0 && baseline.staffHourlyCost === 0) return null
  if (assumptions.overtimeHoursRescheduled > 0 && baseline.overtimePremium === 0) return null

  const managerHoursPerWeek = minutesReturned / 60 * baseline.locations
  const managerCapacity = managerHoursPerWeek * WEEKS_PER_MONTH * baseline.managerRate
  const paidLaborSavings = (paidHoursAvoided * baseline.staffHourlyCost + assumptions.overtimeHoursRescheduled * baseline.overtimePremium) * WEEKS_PER_MONTH * baseline.locations
  const softwareSavings = assumptions.replaceSoftware ? baseline.softwareMonthly * baseline.locations : 0
  const subscription = plan.price * baseline.locations
  const netCash = paidLaborSavings + softwareSavings - subscription
  const netValue = netCash + managerCapacity
  const switchingTimeValue = baseline.setupHours * baseline.managerRate
  return {
    managerHoursPerWeek, managerCapacity, paidLaborSavings, softwareSavings,
    subscription, netCash, netValue,
    switchingTimeValue,
    firstYearValue: netValue * 12 - baseline.setupCost - switchingTimeValue,
    firstYearCash: netCash * 12 - baseline.setupCost,
    // Total hours/week across the business, at the entered manager time value.
    breakEvenHoursPerWeek: netCash >= 0 ? 0 : baseline.managerRate > 0 ? -netCash / (baseline.managerRate * WEEKS_PER_MONTH) : null,
  }
}
