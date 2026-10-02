import { Check, X } from 'lucide-react'
import { EYEBROW, WRAP, allInPlan, formatCents, monthlyPriceCents, useReveal } from './shared'
import type { PricingState } from './shared'

// Typical monthly list prices for the standalone tools a small business stacks
// up to get what Gummfit ships as one product. Deliberately generic categories
// (no vendor names) and round, conservative figures — this is the one place to
// tune them, and the footnote below says they're typical, not a quote.
const TYPICAL_STACK: { tool: string; monthlyCents: number }[] = [
  { tool: 'Website builder', monthlyCents: 2300 },
  { tool: 'E-commerce plan', monthlyCents: 3900 },
  { tool: 'Booking & scheduling app', monthlyCents: 3000 },
  { tool: 'Email marketing tool', monthlyCents: 2000 },
  { tool: 'Business email mailbox', monthlyCents: 700 },
  { tool: 'Reviews & forms plugins', monthlyCents: 1500 },
]

const STACK_TOTAL_CENTS = TYPICAL_STACK.reduce((sum, item) => sum + item.monthlyCents, 0)

export default function StackComparison({ pricing }: { pricing: PricingState }) {
  const [attachReveal, revealClass] = useReveal<HTMLDivElement>()
  const plan = pricing.status === 'ready' ? allInPlan(pricing.pricing.plans) : null
  const planCents = plan ? monthlyPriceCents(plan) : null

  return (
    <section className="bg-[#e8e1d2] py-24 text-[#20261e] sm:py-32">
      <div className={`grid gap-14 lg:grid-cols-[0.85fr_1.15fr] lg:gap-20 ${WRAP}`}>
        <div>
          <p className={`${EYEBROW} text-[#647c28]`}>Why we cost less</p>
          <h2 className="mt-5 text-4xl font-semibold leading-[0.97] tracking-[-0.065em] sm:text-5xl">No middlemen. No markup on markup.</h2>
          <p className="mt-6 max-w-md text-lg leading-8 text-[#5c6256]">
            Other builders lean on an app store — and every app is another vendor with its own monthly fee. We build each feature ourselves, so there's nobody else to pay, and we pass that on.
          </p>
        </div>

        <div ref={attachReveal} className={`grid gap-3 sm:grid-cols-2 ${revealClass}`}>
          <div className="rounded-[1.6rem] border border-[#bdb8aa] bg-[#f1ece1] p-6 sm:p-7">
            <p className={`${EYEBROW} text-[#7a7d72]`}>The usual stack</p>
            <ul className="mt-5 space-y-3 text-sm">
              {TYPICAL_STACK.map((item) => (
                <li key={item.tool} className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2 text-[#4f554a]"><X className="h-3.5 w-3.5 shrink-0 text-[#b0603f]" /> {item.tool}</span>
                  <span className="font-semibold tabular-nums">{formatCents(item.monthlyCents)}</span>
                </li>
              ))}
            </ul>
            <div className="mt-5 flex items-baseline justify-between border-t border-[#bdb8aa] pt-4">
              <span className="text-sm font-semibold">Six bills a month</span>
              <span className="text-2xl font-semibold tracking-[-0.04em] tabular-nums">{formatCents(STACK_TOTAL_CENTS)}<span className="text-sm font-medium text-[#7a7d72]">/mo</span></span>
            </div>
          </div>

          <div className="flex flex-col rounded-[1.6rem] bg-[#293229] p-6 text-[#f3f1e7] shadow-[0_25px_60px_rgba(41,50,41,0.35)] sm:p-7">
            <p className={`${EYEBROW} text-[#d4ff72]`}>Gummfit</p>
            <ul className="mt-5 space-y-3 text-sm">
              {TYPICAL_STACK.map((item) => (
                <li key={item.tool} className="flex items-center gap-2 text-[#d8d9d0]"><Check className="h-3.5 w-3.5 shrink-0 text-[#d4ff72]" /> {item.tool.replace(/ (app|tool|plan|plugins|mailbox)$/, '')}</li>
              ))}
            </ul>
            <div className="mt-auto flex items-baseline justify-between border-t border-white/10 pt-4">
              <span className="text-sm font-semibold">{plan ? `One bill · ${plan.name}` : 'One plan, everything in'}</span>
              {planCents !== null && (
                <span className="text-2xl font-semibold tracking-[-0.04em] text-[#d4ff72] tabular-nums">{formatCents(planCents)}<span className="text-sm font-medium text-[#b3bbac]">/mo</span></span>
              )}
            </div>
          </div>
          <p className="text-xs leading-5 text-[#7a7d72] sm:col-span-2">
            Typical published monthly prices for standalone tools in each category; your stack may vary. Mailboxes are an optional Gummfit add-on.
          </p>
        </div>
      </div>
    </section>
  )
}
