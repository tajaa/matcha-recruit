import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Reveal } from '../../../../components/marketing/kit/motion'
import { WRAP, display, mono } from '../../../../components/marketing/kit/styles'
import { INK, INK_SOFT, STAMP, hexA } from '../../../../components/marketing/kit/theme'
import { Accent, CellLabel, PrimaryButton } from '../sections/Chrome'
import { BuyerHeading } from './BuyerSections'
import { AUTOPILOT_PREVIEW_PRICE } from './Pricing'
import { estimateMonthlyValue } from './valueEstimate'

const FIELDS = [
  { key: 'hours', label: 'Manager hours returned / week', max: 40, step: 0.25 },
  { key: 'rate', label: 'Manager time value / hour ($)', max: 500, step: 1 },
  { key: 'payroll', label: 'Monthly staff payroll ($)', max: 10_000_000, step: 100 },
  { key: 'reduction', label: 'Payroll reduction to test (%)', max: 100, step: 0.1 },
] as const

const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const format = (value: number | undefined) => value === undefined ? '—' : value < 0 ? `−${money.format(Math.abs(value))}` : money.format(value)
const numberFrom = (value: string) => value.trim() === '' ? NaN : Number(value)

export function Value({ onContact }: { onContact: () => void }) {
  const [values, setValues] = useState({ hours: '2', rate: '35', payroll: '30000', reduction: '0' })
  const numeric = { hours: numberFrom(values.hours), rate: numberFrom(values.rate), payroll: numberFrom(values.payroll), reduction: numberFrom(values.reduction) }
  const result = estimateMonthlyValue({ hours: numeric.hours, rate: numeric.rate, payroll: numeric.payroll, reduction: numeric.reduction }, AUTOPILOT_PREVIEW_PRICE)
  const invalid = result === null
  return (
    <section id="value" className={`${WRAP} py-28 sm:py-44`}>
      <BuyerHeading eyebrow="Time & money" label="Make it measurable" title={<>Put a value on time <Accent>back.</Accent></>}>
        Start with your current workflow. Estimate the time returned, then validate any labor savings against actual records. The value should hold up after the subscription.
      </BuyerHeading>
      <div className="mt-16 grid border-y lg:grid-cols-2" style={{ borderColor: hexA(INK, 0.12) }}>
        <Reveal className="min-w-0 py-10 sm:py-12 lg:pr-14">
          <CellLabel n="01">Your assumptions · one location</CellLabel>
          <div className="mt-10 grid gap-x-8 gap-y-9 sm:grid-cols-2">
            {FIELDS.map((field) => {
              const value = numeric[field.key]
              const fieldInvalid = !Number.isFinite(value) || value < 0 || value > field.max
              return (
                <label key={field.key} htmlFor={`value-${field.key}`} className="block min-w-0 text-sm leading-relaxed" style={{ color: INK_SOFT }}>
                  {field.label}
                  <input id={`value-${field.key}`} type="number" inputMode="decimal" min={0} max={field.max} step={field.step} value={values[field.key]} onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))} aria-invalid={fieldInvalid} aria-describedby={fieldInvalid ? 'value-error' : field.key === 'payroll' ? 'payroll-basis' : field.key === 'reduction' ? 'value-assumptions' : undefined} className="sched-focus mt-3 min-h-14 w-full rounded-none border-0 border-b bg-transparent px-0 py-2 text-[2.4rem] font-normal tracking-[-0.04em] tabular-nums" style={{ borderColor: hexA(INK, 0.25), color: INK }} />
                </label>
              )
            })}
          </div>
          <p id="payroll-basis" className="mt-6 max-w-sm text-xs leading-[1.7]" style={{ color: INK_SOFT }}>Staff payroll excludes the manager whose time is valued above.</p>
          {invalid && <p id="value-error" role="alert" className="mt-3 text-sm" style={{ color: INK }}>Enter a number within each field’s allowed range to see the estimate.</p>}
          <p id="value-assumptions" className="mt-6 max-w-md text-xs leading-[1.7]" style={{ color: INK_SOFT }}>Illustrative assumptions, not measured customer results. Labor reduction starts at 0% until payroll supports it. Manager time uses 52 weeks / 12 months. Setup costs and compliance risk are excluded; actual savings vary.</p>
        </Reveal>
        <Reveal delay={120} className="min-w-0 border-t py-10 sm:py-12 lg:border-l lg:border-t-0 lg:pl-14" style={{ borderColor: hexA(INK, 0.12) }}>
          <CellLabel n="02">After the Autopilot subscription</CellLabel>
          <div aria-live="polite" aria-atomic="true">
            <p className="mt-9 text-sm" style={{ color: INK_SOFT }}>Net monthly value</p>
            <p className="mt-4 break-words tabular-nums" style={{ ...display, fontWeight: 400, fontSize: 'clamp(3.4rem, 7vw, 6.8rem)', letterSpacing: '-0.055em', color: STAMP }}>{format(result?.net)}</p>
            <p className="mt-4 text-sm" style={{ color: INK_SOFT }}>Including the value of manager time returned.</p>
            <div className="mt-9 flex flex-wrap items-end justify-between gap-4 border-y py-6" style={{ borderColor: hexA(INK, 0.12) }}>
              <div><p className="text-sm">Net monthly cash impact</p><p className="mt-1 text-xs" style={{ color: INK_SOFT }}>Excludes manager capacity</p></div>
              <p className="break-all tabular-nums" style={{ ...display, fontSize: '2.5rem', fontWeight: 400 }}>{format(result?.cash)}</p>
            </div>
          </div>
          <dl className="mt-6 space-y-3 text-sm">
            <div className="flex justify-between gap-5"><dt style={{ color: INK_SOFT }}>Manager capacity returned</dt><dd className="tabular-nums">{format(result?.capacity)}</dd></div>
            <div className="flex justify-between gap-5"><dt style={{ color: INK_SOFT }}>Assumed staff payroll reduction</dt><dd className="tabular-nums">{format(result?.labor)}</dd></div>
            <div className="flex justify-between gap-5"><dt style={{ color: INK_SOFT }}>Autopilot preview price</dt><dd className="tabular-nums">−${AUTOPILOT_PREVIEW_PRICE}</dd></div>
          </dl>
        </Reveal>
      </div>
      <Reveal className="mt-9 grid gap-9 lg:grid-cols-2 lg:gap-28">
        <div>
          <p className="mb-6 max-w-md text-sm leading-[1.7]" style={{ color: INK_SOFT }}>Already using scheduling software? Compare against that workflow. The estimate should reflect the improvement Matcha adds.</p>
          <PrimaryButton onClick={onContact}>Discuss a measured pilot</PrimaryButton>
        </div>
        <details className="group self-start border-b pb-6" style={{ borderColor: hexA(INK, 0.12) }}>
          <summary className="sched-focus flex cursor-pointer list-none items-center justify-between gap-5 py-2 text-base font-medium [&::-webkit-details-marker]:hidden">How to measure a better week<ChevronDown size={17} className="shrink-0 transition-transform group-open:rotate-180" aria-hidden /></summary>
          <ol className="mt-7 space-y-6">
            {[
              ['Set a baseline', 'Record time spent building schedules, planning breaks, handling requests, and reviewing findings in your current system.'],
              ['Measure the full workflow', 'Include draft review, corrections, and publication—not just the first click. Compare weeks with similar demand and service.'],
              ['Count the improvement once', 'Separate manager capacity from lower paid labor expenses. Keep hypothetical fines and lawsuits outside the savings total.'],
            ].map(([title, detail], i) => <li key={title} className="flex gap-4"><span className="pt-1" style={mono('10px', { color: STAMP })}>0{i + 1}</span><div><h3 className="text-sm font-medium">{title}</h3><p className="mt-2 text-sm leading-[1.65]" style={{ color: INK_SOFT }}>{detail}</p></div></li>)}
          </ol>
        </details>
      </Reveal>
    </section>
  )
}
