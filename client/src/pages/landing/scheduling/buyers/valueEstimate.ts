type ValueInputs = {
  hours: number
  rate: number
  payroll: number
  reduction: number
}

/** Capacity and cash stay separate. The payroll input excludes the manager
 * whose time is already valued. Labor reduction is a buyer assumption, not
 * an observed result or a forecast supplied by Matcha. */
export function estimateMonthlyValue(inputs: ValueInputs, monthlyPrice: number) {
  const bounds: Record<keyof ValueInputs, number> = { hours: 40, rate: 500, payroll: 10_000_000, reduction: 100 }
  for (const key of Object.keys(bounds) as (keyof ValueInputs)[]) {
    if (!Number.isFinite(inputs[key]) || inputs[key] < 0 || inputs[key] > bounds[key]) return null
  }
  if (!Number.isFinite(monthlyPrice) || monthlyPrice < 0) return null
  const capacity = inputs.hours * inputs.rate * 52 / 12
  const labor = inputs.payroll * inputs.reduction / 100
  return { capacity, labor, gross: capacity + labor, net: capacity + labor - monthlyPrice, cash: labor - monthlyPrice }
}
