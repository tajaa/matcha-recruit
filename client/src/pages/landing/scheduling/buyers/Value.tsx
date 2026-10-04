import { useState } from 'react'
import { Reveal } from '../../../../components/marketing/kit/motion'
import { WRAP, display, mono } from '../../../../components/marketing/kit/styles'
import { CARD, INK, INK_SOFT, PAPER, STAMP, hexA } from '../../../../components/marketing/kit/theme'
import { Accent, CellLabel, PrimaryButton } from '../sections/Chrome'
import { BuyerHeading } from './BuyerSections'
import { estimateSchedulingCost, inRange, VALUE_LIMITS, VALUE_PLAN } from './valueEstimate'

const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const hours = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 })
const numberFrom = (value: string) => value.trim() === '' ? NaN : Number(value)
const RULE = hexA(INK, 0.13)

function NumberField({ id, label, value, onChange, max, min = 0, step = 1, note, whole = false }: {
  id: string; label: string; value: string; onChange: (value: string) => void; max: number
  min?: number; step?: number; note: string; whole?: boolean
}) {
  const numeric = numberFrom(value)
  const invalid = !inRange(numeric, max) || numeric < min || (whole && !Number.isInteger(numeric))
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="block text-sm font-medium leading-relaxed">{label}</label>
      <input id={id} type="number" inputMode={whole ? 'numeric' : 'decimal'} min={min} max={max} step={step} value={value} onChange={(event) => onChange(event.target.value)} aria-invalid={invalid} aria-describedby={`${id}-help${invalid ? ` ${id}-error` : ''}`} className="sched-focus mt-2 min-h-12 w-full rounded-lg border px-3 py-2 text-xl tabular-nums" style={{ borderColor: RULE, backgroundColor: PAPER, color: INK, colorScheme: 'light' }} />
      <p id={`${id}-help`} className="mt-2 text-xs leading-relaxed" style={{ color: INK_SOFT }}>{note}</p>
      {invalid && <p id={`${id}-error`} role="alert" className="mt-1 text-xs">Enter {whole ? 'a whole number' : 'a number'} from {min.toLocaleString()} to {max.toLocaleString()}.</p>}
    </div>
  )
}

export function Value({ onContact }: { onContact: () => void }) {
  // Editable starting figures, so the result is visible before anything is typed.
  const [locations, setLocations] = useState('1')
  const [managerRate, setManagerRate] = useState('25')
  const [hoursPerWeek, setHoursPerWeek] = useState('4')
  const result = estimateSchedulingCost({ locations: numberFrom(locations), managerRate: numberFrom(managerRate), hoursPerWeek: numberFrom(hoursPerWeek) })
  const count = result ? `${numberFrom(locations)} ${numberFrom(locations) === 1 ? 'location' : 'locations'}` : 'your locations'
  const breakEven = result?.breakEvenMinutes == null ? null : Math.ceil(result.breakEvenMinutes)
  const spentMinutes = numberFrom(hoursPerWeek) * 60

  return (
    <section id="value" className={`${WRAP} py-28 sm:py-44`}>
      <BuyerHeading eyebrow="Time & money" label="Work out the value" title={<>What does the schedule cost you <Accent>now?</Accent></>}>
        Three numbers. See what building the schedule costs today, and how much of that time has to come back for Matcha to pay for itself.
      </BuyerHeading>
      <div className="mt-12 grid rounded-2xl border lg:grid-cols-2" style={{ borderColor: RULE, backgroundColor: CARD }}>
        <Reveal className="min-w-0 p-5 sm:p-8 lg:p-10">
          <CellLabel n="01">Your operation</CellLabel>
          <div className="mt-7 space-y-7">
            <NumberField id="value-locations" label="Number of locations" value={locations} onChange={setLocations} max={VALUE_LIMITS.locations} min={1} whole note="Every location you build a schedule for." />
            <NumberField id="value-manager-rate" label="Average hourly wage for managers creating schedules ($)" value={managerRate} onChange={setManagerRate} max={VALUE_LIMITS.managerRate} step={0.5} note="For salaried managers, use annual pay ÷ 2,080." />
            <NumberField id="value-hours" label="Time spent building the schedule, start to finish, per location (hours / week)" value={hoursPerWeek} onChange={setHoursPerWeek} max={VALUE_LIMITS.hoursPerWeek} step={0.25} note="Drafting, checking, changes, and publishing in a typical week." />
          </div>
        </Reveal>
        <Reveal delay={80} className="flex min-w-0 flex-col border-t p-5 sm:p-8 lg:border-l lg:border-t-0 lg:p-10" style={{ borderColor: RULE }}>
          <CellLabel n="02">What it costs today</CellLabel>
          <div role="status" aria-label="Estimate" className="mt-7 flex flex-1 flex-col">
            <p className="break-words tabular-nums" data-testid="current-monthly" style={{ ...display, fontSize: 'clamp(3.2rem, 7vw, 5.5rem)', fontWeight: 400, color: result ? STAMP : INK }}>{result ? currency.format(result.currentMonthly) : '—'}</p>
            <p className="mt-3 text-sm" style={{ color: INK_SOFT }}>of manager time a month, across {count}</p>
            <dl className="mt-8 space-y-4 border-t pt-6 text-sm" style={{ borderColor: RULE }}>
              <div className="flex flex-wrap justify-between gap-2"><dt style={{ color: INK_SOFT }}>Manager hours a month</dt><dd className="tabular-nums" data-testid="hours-monthly">{result ? hours.format(result.hoursPerMonth) : '—'}</dd></div>
              <div className="flex flex-wrap justify-between gap-2"><dt style={{ color: INK_SOFT }}>{VALUE_PLAN.name} a month</dt><dd className="tabular-nums" data-testid="subscription">{result ? currency.format(result.subscription) : '—'}</dd></div>
            </dl>
            <p className="mt-7 border-t pt-6 text-base leading-relaxed" data-testid="break-even" style={{ borderColor: RULE }}>
              {!result ? 'Check the three numbers to see your estimate.'
                : breakEven === null ? 'Enter an hourly wage above $0 to see the time that covers the subscription.'
                : result.coversItself ? <>{VALUE_PLAN.name} pays for itself once it saves <strong>{breakEven.toLocaleString()} minutes a week</strong> per location, out of the {spentMinutes.toLocaleString()} you spend now.</>
                : <>{VALUE_PLAN.name} would need to save <strong>{breakEven.toLocaleString()} minutes a week</strong> per location, more than the {spentMinutes.toLocaleString()} you spend now. On schedule-building time alone, it would not pay for itself.</>}
            </p>
            <p className="mt-auto pt-7" style={mono('10px', { color: INK_SOFT })}>Assumes {VALUE_PLAN.name}, our highest plan · ${VALUE_PLAN.price} / location / month</p>
          </div>
        </Reveal>
      </div>
      <div className="mt-9 flex flex-wrap items-center justify-between gap-6">
        <p className="max-w-2xl text-xs leading-[1.7]" style={{ color: INK_SOFT }}>An estimate from your own numbers, not a savings guarantee. Weekly time is converted to months at 52 / 12. Proposed prices need confirmation; volume discounts and taxes are excluded.</p>
        <PrimaryButton onClick={onContact}>Talk through my numbers</PrimaryButton>
      </div>
    </section>
  )
}
