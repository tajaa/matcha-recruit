import { ArrowRight, Check, ChevronDown, Minus } from 'lucide-react'
import { Reveal } from '../../../../components/marketing/kit/motion'
import { WRAP, display, mono } from '../../../../components/marketing/kit/styles'
import { BOARD, PAPER, hexA } from '../../../../components/marketing/kit/theme'
import { Accent, CellLabel, PrimaryButton } from '../sections/Chrome'
import { BuyerHeading } from './BuyerSections'
import { SCHEDULING_PLANS as PLANS } from './plans'

const FEATURES = [
  { label: 'Schedule editor, templates, and publishing', plans: [true, true, true] },
  { label: 'Employee access, availability, time off, and shift requests', plans: [true, true, true] },
  { label: 'Assignment checks and applicable scheduling guidance', plans: [true, true, true] },
  { label: 'Manual break plans and change history', plans: [true, true, true] },
  { label: 'Automatic break staggering and relief review', plans: [false, true, true] },
  { label: 'Planned break reminders', plans: [false, true, true] },
  { label: 'Scheduled labor cost and overtime projections', plans: [false, true, true] },
  { label: 'Credential and license tracking, with expiry checks on assignment', plans: [false, true, true] },
  { label: 'Sales- and weather-informed weekly drafts', plans: [false, false, true] },
  { label: 'Conversational changes and planning scenarios', plans: [false, false, true] },
  { label: 'Schedule intelligence, with relevant data', plans: [false, false, true] },
  { label: 'Native time clock and timesheet payroll export', plans: [false, false, false] },
  { label: 'Handbooks, incident cases, and broader compliance', plans: [false, false, false] },
] as const

const RULE = hexA(PAPER, 0.14)
const MUTED = hexA(PAPER, 0.65)

export function Pricing({ onContact }: { onContact: () => void }) {
  return (
    <section id="pricing" className="sched-dark" style={{ backgroundColor: BOARD.PAPER, color: PAPER }}>
      <div className={`${WRAP} py-28 sm:py-44`}>
        <BuyerHeading dark eyebrow="Your plan" label="Pricing preview" title={<>A little help. Or a whole week <Accent dark>ahead.</Accent></>}>
          Build it yourself, bring breaks and cost into view, or start with a draft. Three ways to run the week. One price per location.
        </BuyerHeading>
        <div className="mt-16 flex flex-wrap items-center justify-between gap-4 border-b pb-5" style={{ borderColor: RULE }}>
          <p className="flex items-center gap-2 text-sm" style={{ color: MUTED }}><Check size={14} style={{ color: BOARD.STAMP }} aria-hidden />Core assignment checks in every plan</p>
          <p style={mono('10px', { color: MUTED })}>Monthly · per location · USD</p>
        </div>
        <div className="grid md:grid-cols-3">
          {PLANS.map((plan, i) => (
            <Reveal key={plan.name} delay={i * 100} className="flex min-w-0 flex-col border-b py-10 md:py-12 md:[&+div]:border-l md:[&+div]:pl-7 md:[&:not(:last-child)]:pr-7 lg:[&+div]:pl-10 lg:[&:not(:last-child)]:pr-10" style={{ borderColor: RULE }}>
              <CellLabel n={`0${i + 1}`} dark><span style={{ color: plan.featured ? BOARD.STAMP : undefined }}>{plan.name}</span></CellLabel>
              <h3 className="mt-7 text-[1.6rem] font-normal leading-tight tracking-[-0.03em]">{plan.audience}</h3>
              <div className="mt-9 flex items-start" style={{ fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.06em', lineHeight: 0.85, fontWeight: 400 }}>
                <span className="mr-1 mt-1 text-[2rem] sm:text-[2.5rem]">$</span>
                <span className="text-[clamp(5rem,8.5vw,7.5rem)]">{plan.price}</span>
              </div>
              <p className="mt-5 text-sm" style={{ color: MUTED }}>per location, per month</p>
              <p className="mt-8 min-h-12 max-w-[26ch] text-[0.95rem] leading-[1.6]" style={{ color: MUTED }}>{plan.detail}</p>
              <ul className="mb-10 mt-8 space-y-4 border-t pt-7 text-[0.9rem] leading-[1.6]" style={{ borderColor: RULE, color: hexA(PAPER, 0.82) }}>
                {plan.features.map((feature) => <li key={feature} className="flex gap-3"><span aria-hidden className="mt-[0.7em] h-px w-3 shrink-0" style={{ backgroundColor: hexA(PAPER, 0.35) }} />{feature}</li>)}
              </ul>
              <button type="button" onClick={onContact} className={`group sched-focus mt-auto inline-flex min-h-12 items-center justify-between gap-4 rounded-full px-5 text-sm font-medium ${plan.featured ? 'sched-btn sched-btn-paper' : 'border transition-colors hover:bg-white/5'}`} style={{ borderColor: hexA(PAPER, 0.3) }}>
                Discuss {plan.name}<ArrowRight size={16} className="transition-transform duration-300 group-hover:translate-x-1" aria-hidden />
              </button>
            </Reveal>
          ))}
        </div>
        <div className="mt-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
          <p className="max-w-2xl text-xs leading-[1.7]" style={{ color: MUTED }}>Pricing preview: prices and inclusions are proposed. Confirm plan availability, employee allowances, integrations, and final terms with our team before purchasing.</p>
          <a href="#value" className="sched-link sched-focus shrink-0 self-start text-sm">Work out the value ↑</a>
        </div>
        <details className="group mt-12 border-y" style={{ borderColor: RULE }}>
          <summary className="sched-focus flex cursor-pointer list-none items-center justify-between gap-4 py-7 text-base font-medium [&::-webkit-details-marker]:hidden">Compare the proposed features<ChevronDown size={18} className="shrink-0 transition-transform group-open:rotate-180" aria-hidden /></summary>
          <div className="overflow-x-auto pb-6" role="region" aria-label="Proposed plan feature comparison" tabIndex={0}>
            <table className="w-full min-w-[560px] text-left text-sm">
              <caption className="sr-only">Proposed scheduling plan inclusions. Native timekeeping is unavailable; broader HR modules are separately scoped.</caption>
              <thead><tr style={{ borderBottom: `1px solid ${RULE}` }}><th scope="col" className="py-4 pr-6 font-medium">Feature</th>{PLANS.map((plan) => <th key={plan.name} scope="col" className="px-4 py-4 text-center font-medium">{plan.name}</th>)}</tr></thead>
              <tbody>{FEATURES.map((feature) => (
                <tr key={feature.label} style={{ borderBottom: `1px solid ${RULE}` }}>
                  <th scope="row" className="py-4 pr-6 font-normal" style={{ color: MUTED }}>{feature.label}</th>
                  {feature.plans.map((included, i) => <td key={PLANS[i].name} className="px-4 py-4 text-center">{included ? <Check size={17} className="mx-auto" style={{ color: BOARD.STAMP }} aria-hidden /> : <Minus size={16} className="mx-auto" style={{ color: MUTED }} aria-hidden />}<span className="sr-only">{included ? 'Proposed inclusion' : 'Not included'}</span></td>)}
                </tr>
              ))}</tbody>
            </table>
          </div>
        </details>
        <Reveal className="mt-14 grid gap-8 lg:grid-cols-12 lg:items-end">
          <div className="lg:col-span-7">
            <p style={mono('10px', { color: MUTED })}>For a bigger operation</p>
            <h3 className="mt-5 max-w-[20ch]" style={{ ...display, fontSize: 'clamp(2rem, 3.5vw, 3rem)' }}>More locations. A plan of <Accent dark>your own.</Accent></h3>
          </div>
          <div className="lg:col-span-5">
            <p className="mb-7 max-w-md text-sm leading-[1.7]" style={{ color: MUTED }}>Discuss volume pricing, shared employees, and rollout support. Handbook, incident, and broader compliance workflows are scoped separately, along with custom migration and integration work.</p>
            <PrimaryButton tone="paper" onClick={onContact}>Talk through a quote</PrimaryButton>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
