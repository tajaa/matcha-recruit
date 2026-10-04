import { useState, type ReactNode } from 'react'
import { ArrowRight, RotateCcw } from 'lucide-react'
import { Reveal } from '../../../../components/marketing/kit/motion'
import { WRAP, mono } from '../../../../components/marketing/kit/styles'
import { CARD, INK, INK_SOFT, PAPER, STAMP, hexA } from '../../../../components/marketing/kit/theme'
import { Accent, CellLabel, PrimaryButton } from '../sections/Chrome'
import { BuyerHeading } from './BuyerSections'
import { SCHEDULING_PLANS, TIME_TASKS, planById, type PlanId, type TimeTask } from './plans'
import { estimatePlanValue, inRange, VALUE_LIMITS, type PlanValue, type ValueBaseline } from './valueEstimate'
import { ValueResults } from './ValueResults'

type BaselineKey = Exclude<keyof ValueBaseline, 'minutes'>
type BaselineDraft = Record<BaselineKey, string> & { minutes: Record<TimeTask, string> }
type PlanDraft = { minutes: Record<TimeTask, string>; replaceSoftware: boolean; paidHoursAvoided: string; overtimeHoursRescheduled: string }
const currentMinutes = () => ({ schedule: '0', requests: '0', breaks: '0', cost: '0' })
const blankMinutes = () => ({ schedule: '', requests: '', breaks: '', cost: '' })
const emptyBaseline = (): BaselineDraft => ({ locations: '1', managerRate: '0', softwareMonthly: '0', staffHourlyCost: '0', overtimePremium: '0', setupCost: '0', setupHours: '0', minutes: currentMinutes() })
const emptyPlans = (): Record<PlanId, PlanDraft> => Object.fromEntries(SCHEDULING_PLANS.map(({ id }) => [id, { minutes: blankMinutes(), replaceSoftware: false, paidHoursAvoided: '0', overtimeHoursRescheduled: '0' }])) as Record<PlanId, PlanDraft>
const numberFrom = (value: string) => value.trim() === '' ? NaN : Number(value)
const RULE = hexA(INK, 0.13)

function NumberField({ id, label, value, onChange, max, min = 0, step = 1, note, fallback, disabled = false, whole = false }: {
  id: string; label: string; value: string; onChange: (value: string) => void; max: number
  min?: number; step?: number; note?: ReactNode; fallback?: number; disabled?: boolean; whole?: boolean
}) {
  const numeric = value.trim() === '' && fallback !== undefined ? fallback : numberFrom(value)
  const invalid = !inRange(numeric, max) || numeric < min || (whole && !Number.isInteger(numeric))
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="block text-sm font-medium leading-relaxed">{label}</label>
      <input id={id} type="number" inputMode={whole ? 'numeric' : 'decimal'} min={min} max={max} step={step} value={value} placeholder={fallback === undefined ? undefined : String(fallback)} disabled={disabled} onChange={(event) => onChange(event.target.value)} aria-invalid={invalid} aria-describedby={`${id}-help${invalid ? ` ${id}-error` : ''}`} className="sched-focus mt-2 min-h-12 w-full rounded-lg border px-3 py-2 text-xl tabular-nums" style={{ borderColor: RULE, backgroundColor: disabled ? 'transparent' : PAPER, color: disabled ? INK_SOFT : INK, colorScheme: 'light' }} />
      <div id={`${id}-help`} className="mt-2 text-xs leading-relaxed" style={{ color: INK_SOFT }}>{note}</div>
      {invalid && <p id={`${id}-error`} role="alert" className="mt-1 text-xs">Enter {whole ? 'a whole number' : 'a number'} from {min.toLocaleString()} to {max.toLocaleString()}.</p>}
    </div>
  )
}

export function Value({ onContact }: { onContact: () => void }) {
  const [baseline, setBaseline] = useState(emptyBaseline)
  const [plans, setPlans] = useState(emptyPlans)
  const [selected, setSelected] = useState<PlanId>('pro')
  const [example, setExample] = useState(false)
  const plan = planById(selected)
  const draft = plans[selected]
  const numeric: ValueBaseline = {
    locations: numberFrom(baseline.locations), managerRate: numberFrom(baseline.managerRate),
    softwareMonthly: numberFrom(baseline.softwareMonthly), staffHourlyCost: numberFrom(baseline.staffHourlyCost),
    overtimePremium: numberFrom(baseline.overtimePremium), setupCost: numberFrom(baseline.setupCost), setupHours: numberFrom(baseline.setupHours),
    minutes: Object.fromEntries(TIME_TASKS.map(({ id }) => [id, numberFrom(baseline.minutes[id])])) as Record<TimeTask, number>,
  }
  const results = Object.fromEntries(SCHEDULING_PLANS.map(({ id }) => [id, estimatePlanValue(numeric, {
    minutes: Object.fromEntries(TIME_TASKS.map(({ id: task }) => [task, plans[id].minutes[task].trim() === '' ? numeric.minutes[task] : numberFrom(plans[id].minutes[task])])) as Record<TimeTask, number>,
    replaceSoftware: plans[id].replaceSoftware,
    paidHoursAvoided: numberFrom(plans[id].paidHoursAvoided),
    overtimeHoursRescheduled: numberFrom(plans[id].overtimeHoursRescheduled),
  }, id)])) as Record<PlanId, PlanValue | null>

  function updateBaseline(key: BaselineKey, value: string) { setBaseline((current) => ({ ...current, [key]: value })) }
  function updatePlan(patch: Partial<PlanDraft>) { setPlans((current) => ({ ...current, [selected]: { ...current[selected], ...patch } })) }
  function loadExample() {
    setBaseline({ locations: '1', managerRate: '35', softwareMonthly: '0', staffHourlyCost: '20', overtimePremium: '10', setupCost: '0', setupHours: '0', minutes: { schedule: '240', requests: '60', breaks: '60', cost: '60' } })
    const next = emptyPlans()
    next.basic.minutes = { schedule: '180', requests: '30', breaks: '60', cost: '' }
    next.pro.minutes = { schedule: '180', requests: '30', breaks: '30', cost: '30' }
    next.autopilot.minutes = { schedule: '60', requests: '20', breaks: '30', cost: '30' }
    setPlans(next)
    setExample(true)
  }

  return (
    <section id="value" className={`${WRAP} py-28 sm:py-44`}>
      <BuyerHeading eyebrow="Time & money" label="Compare the value" title={<>What would a better week be <Accent>worth?</Accent></>}>
        Start with the work you do today. Estimate what changes with each plan, then compare time returned and cash impact after the subscription.
      </BuyerHeading>
      <div className="mt-12 grid gap-7 border-y py-7 md:grid-cols-3" style={{ borderColor: RULE }}>
        {[
          ['01', 'Measure your current week', 'Use a typical week at one location. Include every manager’s time; count each task once.'],
          ['02', 'Estimate each plan separately', 'Enter the minutes still needed with Basic, Pro, and Autopilot, including review and corrections. Blank means no time saved.'],
          ['03', 'Compare the full picture', 'Manager time is capacity returned. Cash changes only when paid hours or bills actually fall. Prices scale with locations.'],
        ].map(([n, title, text]) => <div key={n}><p style={mono('10px', { color: STAMP })}>{n} / How to use this</p><h3 className="mt-3 text-base font-medium">{title}</h3><p className="mt-2 max-w-sm text-sm leading-relaxed" style={{ color: INK_SOFT }}>{text}</p></div>)}
      </div>
      <div className="mt-7 flex flex-wrap items-center justify-between gap-4">
        <p role="status" aria-label="Scenario" className="max-w-xl text-sm leading-relaxed" style={{ color: INK_SOFT }}>{example ? 'Editable café example. These are illustrative assumptions, not measured customer results. Paid labor savings start at $0; change them only with evidence.' : 'Your assumptions. Start with zero savings, or load an example to see how the comparison works.'}</p>
        <div className="flex flex-wrap gap-5">
          <button type="button" onClick={loadExample} className="sched-focus sched-link inline-flex min-h-11 items-center gap-2 rounded text-sm font-medium">Load café example<ArrowRight size={14} aria-hidden /></button>
          <button type="button" onClick={() => { setBaseline(emptyBaseline()); setPlans(emptyPlans()); setExample(false) }} className="sched-focus sched-link inline-flex min-h-11 items-center gap-2 rounded text-sm" style={{ color: INK_SOFT }}><RotateCcw size={13} aria-hidden />Clear assumptions</button>
        </div>
      </div>
      <div className="mt-9 grid rounded-2xl border lg:grid-cols-2" style={{ borderColor: RULE, backgroundColor: CARD }}>
        <Reveal className="min-w-0 p-5 sm:p-8 lg:p-10">
          <CellLabel n="01">Your current operation</CellLabel>
          <div className="mt-7 grid gap-6 sm:grid-cols-2">
            <NumberField id="value-locations" label="Locations to include" value={baseline.locations} onChange={(value) => updateBaseline('locations', value)} max={VALUE_LIMITS.locations} min={1} whole note="Use an average location below. Results cover all included locations." />
            <NumberField id="value-manager-rate" label="Value of manager time ($ / hour)" value={baseline.managerRate} onChange={(value) => updateBaseline('managerRate', value)} max={VALUE_LIMITS.managerRate} note="Use hourly cost or your own time value. Salary does not fall automatically." />
          </div>
          <fieldset className="mt-9 border-t pt-7" style={{ borderColor: RULE }}>
            <legend className="pr-3 text-base font-medium">Manager minutes / week / location</legend>
            <p className="mb-5 mt-1 text-sm leading-relaxed" style={{ color: INK_SOFT }}>Include planning, review, corrections, and follow-up. Allocate shared-manager time across stores so it is counted once.</p>
            <div className="grid gap-6 sm:grid-cols-2">
              {TIME_TASKS.map(({ id, label }) => <NumberField key={id} id={`value-current-${id}`} label={label} value={baseline.minutes[id]} onChange={(value) => setBaseline((current) => ({ ...current, minutes: { ...current.minutes, [id]: value } }))} max={VALUE_LIMITS.minutes} step={5} note="Minutes in a typical week; 60 minutes = 1 hour." />)}
            </div>
          </fieldset>
          <div className="mt-8 grid gap-6 border-t pt-7 sm:grid-cols-2" style={{ borderColor: RULE }}>
            <NumberField id="value-software" label="Current scheduler ($ / month / location)" value={baseline.softwareMonthly} onChange={(value) => updateBaseline('softwareMonthly', value)} max={VALUE_LIMITS.softwareMonthly} note="Only bills you can cancel. Keep time-clock and payroll costs out." />
            <NumberField id="value-setup" label="One-time switching spend ($ / business)" value={baseline.setupCost} onChange={(value) => updateBaseline('setupCost', value)} max={VALUE_LIMITS.setupCost} note="Extra cash outlay: setup, training, or migration fees. Deducted once from year one." />
            <div className="sm:col-span-2"><NumberField id="value-setup-hours" label="Manager onboarding hours / business" value={baseline.setupHours} onChange={(value) => updateBaseline('setupHours', value)} max={VALUE_LIMITS.setupHours} step={0.25} note="Total internal manager time for the switch, across all locations. Valued at your hourly amount; reduces first-year value, not cash. Exclude time already counted in switching spend." /></div>
          </div>
        </Reveal>
        <Reveal delay={80} className="min-w-0 border-t p-5 sm:p-8 lg:border-l lg:border-t-0 lg:p-10" style={{ borderColor: RULE }}>
          <CellLabel n="02">Your estimate with each plan</CellLabel>
          <div role="group" aria-label="Plan assumptions" className="mt-7 grid grid-cols-3 gap-2">
            {SCHEDULING_PLANS.map((item) => <button key={item.id} type="button" aria-label={`Edit ${item.name} assumptions`} aria-pressed={selected === item.id} onClick={() => setSelected(item.id)} className="sched-focus min-h-16 rounded-lg border px-2 py-3 text-center transition-colors" style={{ borderColor: selected === item.id ? STAMP : RULE, backgroundColor: selected === item.id ? hexA(STAMP, 0.08) : 'transparent' }}><span className="block text-sm font-medium">{item.name}</span><span className="mt-1 block text-xs" style={{ color: INK_SOFT }}>${item.price} / location</span></button>)}
          </div>
          <p className="mt-5 text-sm leading-relaxed" style={{ color: INK_SOFT }}>Edit {plan.name} below, then switch plans. Each plan keeps its own assumptions.</p>
          <fieldset className="mt-7 space-y-5">
            <legend className="mb-5 text-base font-medium">Minutes still needed with {plan.name}</legend>
            {TIME_TASKS.map(({ id, label }) => {
              const unavailable = id === 'cost' && !plan.laborCost
              return <NumberField key={id} id={`value-after-${selected}-${id}`} label={label} value={unavailable ? baseline.minutes[id] : draft.minutes[id]} disabled={unavailable} fallback={numeric.minutes[id]} onChange={(value) => updatePlan({ minutes: { ...draft.minutes, [id]: value } })} max={VALUE_LIMITS.minutes} step={5} note={<>{plan.methods[id]}<span className="mt-1 block">Current: {baseline.minutes[id] || '—'} min / week. {unavailable ? 'Current time retained for Basic.' : 'Leave blank to assume the same time.'}</span></>} />
            })}
          </fieldset>
          <label className="mt-7 flex items-start gap-3 rounded-lg border p-4 text-sm leading-relaxed" style={{ borderColor: RULE }}>
            <input type="checkbox" checked={draft.replaceSoftware} onChange={(event) => updatePlan({ replaceSoftware: event.target.checked })} className="sched-focus mt-1 h-4 w-4 shrink-0 accent-[#3F6B2A]" />
            <span>Cancel my current scheduler with {plan.name}<span className="mt-1 block text-xs" style={{ color: INK_SOFT }}>Only count the saving if this bill will stop. Your time-clock and payroll bills stay outside the estimate.</span></span>
          </label>
          <details className="group mt-6 border-t pt-5" style={{ borderColor: RULE }}>
            <summary className="sched-focus cursor-pointer rounded text-sm font-medium">Add measured paid-labor savings <span className="font-normal" style={{ color: INK_SOFT }}>(optional)</span></summary>
            <p className="mt-4 text-xs leading-relaxed" style={{ color: INK_SOFT }}>Leave these at zero until a pilot supports the change. Exclude manager time. Removed regular hours and rescheduled overtime must be different hours; maintain required coverage.</p>
            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <NumberField id="value-staff-cost" label="Regular staff cost ($ / hour)" value={baseline.staffHourlyCost} onChange={(value) => updateBaseline('staffHourlyCost', value)} max={VALUE_LIMITS.staffHourlyCost} note="Use the cost of a regular paid hour. Shared across plans." />
              <NumberField id="value-premium" label="Overtime premium ($ / hour)" value={baseline.overtimePremium} onChange={(value) => updateBaseline('overtimePremium', value)} max={VALUE_LIMITS.overtimePremium} note="Only the extra cost: $30 overtime − $20 regular = $10 premium." />
              <NumberField id={`value-paid-${selected}`} label="Regular paid hours removed / week / location" value={plan.laborCost ? draft.paidHoursAvoided : '0'} disabled={!plan.laborCost} onChange={(value) => updatePlan({ paidHoursAvoided: value })} max={VALUE_LIMITS.paidHours} step={0.25} note={plan.laborCost ? 'From labor-cost review. Exclude overtime hours and manager time.' : 'Labor-cost review is available in Pro and Autopilot; not counted for Basic.'} />
              <NumberField id={`value-overtime-${selected}`} label="Overtime hours moved to regular pay / week / location" value={draft.overtimeHoursRescheduled} onChange={(value) => updatePlan({ overtimeHoursRescheduled: value })} max={VALUE_LIMITS.paidHours} step={0.25} note="The hours are still worked. Only the entered overtime premium is saved." />
            </div>
            {(plan.laborCost && numberFrom(draft.paidHoursAvoided) > 0 && numeric.staffHourlyCost === 0) && <p role="alert" className="mt-3 text-sm">Enter a regular staff cost above $0 to value removed paid hours.</p>}
            {(numberFrom(draft.overtimeHoursRescheduled) > 0 && numeric.overtimePremium === 0) && <p role="alert" className="mt-3 text-sm">Enter an overtime premium above $0 to value rescheduled overtime.</p>}
          </details>
        </Reveal>
      </div>
      <ValueResults results={results} selected={selected} locations={numeric.locations} setupCost={numeric.setupCost} managerRate={numeric.managerRate} />
      <div className="mt-9 flex flex-wrap items-center justify-between gap-6 border-t pt-7" style={{ borderColor: RULE }}>
        <p className="max-w-2xl text-xs leading-[1.7]" style={{ color: INK_SOFT }}>This is a scenario, not a forecast or a savings guarantee. Use 52 weeks / 12 months for recurring weekly work. Compare similar weeks against your current workflow. Proposed prices and inclusions need confirmation; volume discounts, taxes, growth, and speculative compliance savings are excluded.</p>
        <PrimaryButton onClick={onContact}>Discuss my assumptions</PrimaryButton>
      </div>
    </section>
  )
}
