import { display, mono } from '../../../../components/marketing/kit/styles'
import { CARD, INK, INK_SOFT, RED_PEN, STAMP, hexA } from '../../../../components/marketing/kit/theme'
import { CellLabel } from '../sections/Chrome'
import { SCHEDULING_PLANS, planById, type PlanId } from './plans'
import type { PlanValue } from './valueEstimate'

const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const detailedCurrency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })
const hours = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })
const money = (value: number | undefined, detailed = false) => value === undefined ? '—' : `${value < 0 ? '−' : ''}${(detailed ? detailedCurrency : currency).format(Math.abs(value))}`
const RULE = hexA(INK, 0.13)

export function ValueResults({ results, selected, locations, setupCost, managerRate }: {
  results: Record<PlanId, PlanValue | null>; selected: PlanId; locations: number; setupCost: number; managerRate: number
}) {
  const plan = planById(selected)
  const result = results[selected]
  const count = Number.isInteger(locations) && locations > 0 ? `${locations} ${locations === 1 ? 'location' : 'locations'}` : 'your locations'
  const ledger: [string, number | undefined][] = [
    ['Manager capacity returned', result?.managerCapacity],
    ['Paid labor savings', result?.paidLaborSavings],
    ['Software bills removed', result?.softwareSavings],
    [`${plan.name} subscription`, result ? -result.subscription : undefined],
  ]
  return (
    <div className="mt-14" role="region" aria-label="Plan value comparison">
      <p role="status" aria-label="Selected plan result" className="sr-only">{plan.name}: {result ? `${money(result.netValue, true)} net monthly value; ${money(result.netCash, true)} net monthly cash for ${count}.` : 'Check your inputs to calculate this estimate.'}</p>
      <CellLabel n="03">Compare your estimates</CellLabel>
      <div className="mt-5 flex flex-wrap items-baseline justify-between gap-4">
        <h3 style={{ ...display, fontSize: 'clamp(1.7rem, 3vw, 2.5rem)' }}>The value after the subscription.</h3>
        <p style={mono('10px', { color: INK_SOFT })}>Per month · {count} combined</p>
      </div>
      <p className="mt-4 max-w-2xl text-sm leading-relaxed" style={{ color: INK_SOFT }}>Net value includes the value of manager time. Net cash excludes that capacity and shows the change to paid labor and software bills.</p>
      <div className="mt-7 grid gap-3 md:grid-cols-3">
        {SCHEDULING_PLANS.map((item) => {
          const value = results[item.id]
          return (
            <article key={item.id} aria-label={`${item.name} estimate`} className="min-w-0 rounded-xl border p-5 sm:p-7" style={{ borderColor: selected === item.id ? STAMP : RULE, backgroundColor: selected === item.id ? hexA(STAMP, 0.06) : CARD }}>
              <div className="flex flex-wrap items-baseline justify-between gap-3"><h4 className="text-xl font-medium">{item.name}</h4><span className="text-xs" style={{ color: INK_SOFT }}>${item.price} / location / month</span></div>
              <p className="mt-6 text-sm" style={{ color: INK_SOFT }}>Net monthly value</p>
              <p className="mt-3 break-words tabular-nums" data-testid={`${item.id}-net-value`} style={{ ...display, fontSize: 'clamp(2.6rem, 4.5vw, 4.1rem)', fontWeight: 400, color: value && value.netValue > 0 ? STAMP : INK }}>{money(value?.netValue)}</p>
              <dl className="mt-6 space-y-4 border-t pt-5 text-sm" style={{ borderColor: RULE }}>
                <div className="flex flex-wrap justify-between gap-2"><dt style={{ color: INK_SOFT }}>Net monthly cash</dt><dd className="tabular-nums" data-testid={`${item.id}-net-cash`}>{money(value?.netCash)}</dd></div>
                <div className="flex flex-wrap justify-between gap-2"><dt style={{ color: INK_SOFT }}>Manager hours / week</dt><dd className="tabular-nums">{value ? `${hours.format(Math.abs(value.managerHoursPerWeek))} ${value.managerHoursPerWeek < 0 ? 'extra' : 'returned'}` : '—'}</dd></div>
                <div className="flex flex-wrap justify-between gap-2"><dt style={{ color: INK_SOFT }}>Monthly subscription</dt><dd className="tabular-nums">{money(value ? -value.subscription : undefined)}</dd></div>
              </dl>
              {!value && <p className="mt-4 text-xs leading-relaxed" style={{ color: RED_PEN }}>Check the inputs for this plan to see its estimate.</p>}
            </article>
          )
        })}
      </div>
      <div className="mt-8 grid gap-7 border-y py-7 lg:grid-cols-2 lg:gap-12" style={{ borderColor: RULE }}>
        <div>
          <h4 className="text-base font-medium">How {plan.name} adds up</h4>
          <p className="mt-2 text-xs" style={{ color: INK_SOFT }}>Monthly estimate for {count}. More work appears as a negative time value.</p>
          <dl className="mt-5 space-y-3 text-sm">
            {ledger.map(([label, value]) => <div key={label} className="flex justify-between gap-5"><dt style={{ color: INK_SOFT }}>{label}</dt><dd className="shrink-0 tabular-nums">{money(value, true)}</dd></div>)}
            <div className="flex justify-between gap-5 border-t pt-3 font-medium" style={{ borderColor: RULE }}><dt>Net monthly value</dt><dd className="shrink-0 tabular-nums">{money(result?.netValue, true)}</dd></div>
          </dl>
          {result && <p className="mt-5 text-xs leading-relaxed" style={{ color: INK_SOFT }}>Time value = {hours.format(result.managerHoursPerWeek)} hours returned / week across {count} × {money(managerRate, true)} / hour × 52 / 12. Paid labor = (removed regular hours × regular cost + rescheduled overtime × premium) × locations × 52 / 12.</p>}
        </div>
        <div className="border-t pt-7 lg:border-l lg:border-t-0 lg:pl-12 lg:pt-0" style={{ borderColor: RULE }}>
          <h4 className="text-base font-medium">Year one, including the switch</h4>
          <p className="mt-2 text-xs leading-relaxed" style={{ color: INK_SOFT }}>12 months of recurring results. Switching spend of {money(Number.isFinite(setupCost) ? setupCost : undefined)} reduces both totals once. Manager onboarding time is valued at {money(result?.switchingTimeValue)} and reduces only net value.</p>
          <dl className="mt-5 grid grid-cols-2 gap-5">
            <div><dt className="text-xs" style={{ color: INK_SOFT }}>Net first-year value</dt><dd className="mt-2 break-words text-2xl tracking-tight tabular-nums">{money(result?.firstYearValue)}</dd></div>
            <div><dt className="text-xs" style={{ color: INK_SOFT }}>Net first-year cash</dt><dd className="mt-2 break-words text-2xl tracking-tight tabular-nums">{money(result?.firstYearCash)}</dd></div>
          </dl>
          {result && <p className="mt-5 text-sm leading-relaxed" style={{ color: INK_SOFT }}>{result.breakEvenHoursPerWeek === null ? 'Enter a manager time value above $0 to calculate the time needed to cover the remaining monthly cost.' : result.breakEvenHoursPerWeek === 0 ? 'Your entered cash savings cover the monthly subscription before valuing manager time.' : <>To cover the remaining monthly cost, this plan needs <strong style={{ color: INK }}>{Math.ceil(result.breakEvenHoursPerWeek * 60).toLocaleString()} manager minutes / week</strong> returned across {count}, at your entered hourly value. Switching cost is additional.</>}</p>}
        </div>
      </div>
    </div>
  )
}
