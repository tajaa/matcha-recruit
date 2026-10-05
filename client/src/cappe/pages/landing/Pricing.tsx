import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Check } from 'lucide-react'
import type { CappePublicAddon, CappePublicPlan } from '../../types'
import { EYEBROW, SIGNUP_PATH, WRAP, allInPlan, formatCents, useReveal, signupPath } from './shared'
import type { PricingState } from './shared'

type Interval = 'month' | 'year'

const FULFILLMENT_WORDS: Record<string, string> = {
  physical: 'physical products',
  digital: 'digital downloads',
  service: 'services',
  booking: 'bookings',
}

function listWords(items: string[]): string {
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} & ${items[items.length - 1]}`
}

function planPoints(plan: CappePublicPlan): string[] {
  const points: string[] = []
  const sells = plan.allowed_fulfillment.map((k) => FULFILLMENT_WORDS[k]).filter(Boolean)
  if (sells.length) points.push(`Sell ${listWords(sells)}`)
  points.push(plan.site_limit === null ? 'Unlimited sites' : `${plan.site_limit} site${plan.site_limit === 1 ? '' : 's'}`)
  if (sells.length && plan.platform_fee_bps > 0) points.push(`${plan.platform_fee_bps / 100}% fee per sale`)
  if (sells.length && plan.platform_fee_bps === 0) points.push('No Gummfit fee on sales')
  if (plan.mailbox_quota_included > 0) {
    points.push(`${plan.mailbox_quota_included} email mailbox${plan.mailbox_quota_included === 1 ? '' : 'es'} included`)
  }
  points.push('AI builder, forms, newsletter, blog & reviews')
  return points
}

function PriceLine({ plan, interval }: { plan: CappePublicPlan; interval: Interval }) {
  if (!plan.prices.length) {
    return <p className="flex items-baseline gap-1"><span className="text-5xl font-semibold tracking-[-0.06em]">$0</span><span className="text-sm opacity-60">forever</span></p>
  }
  const price = plan.prices.find((p) => p.interval === interval) ?? plan.prices.find((p) => p.interval === 'month') ?? plan.prices[0]
  const yearly = price.interval === 'year'
  return (
    <div>
      <p className="flex items-baseline gap-1">
        <span className="text-5xl font-semibold tracking-[-0.06em]">{formatCents(price.unit_amount_cents, price.currency)}</span>
        <span className="text-sm opacity-60">/{yearly ? 'yr' : 'mo'}</span>
      </p>
      {yearly && <p className="mt-1 text-xs opacity-60">≈ {formatCents(Math.round(price.unit_amount_cents / 12), price.currency)}/mo, billed yearly</p>}
    </div>
  )
}

function PlanCard({ plan, interval, featured }: { plan: CappePublicPlan; interval: Interval; featured: boolean }) {
  const tone = featured
    ? 'bg-[#d4ff72] text-[#182115] shadow-[0_30px_80px_rgba(212,255,114,0.18)]'
    : 'border border-white/10 bg-[#1a201a] text-[#f3f1e7]'
  return (
    <article data-testid={`plan-${plan.code}`} className={`relative flex flex-col rounded-[1.6rem] p-6 sm:p-7 ${tone}`}>
      <div className="flex min-h-7 items-center justify-between gap-3">
        <h3 className="text-xl font-semibold tracking-[-0.04em]">{plan.name}</h3>
        {featured && <span className="rounded-full bg-[#182115] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-[#d4ff72]">Full storefront</span>}
      </div>
      {plan.description && <p className="mt-2 text-sm leading-6 opacity-70">{plan.description}</p>}
      <div className="mt-6"><PriceLine plan={plan} interval={interval} /></div>
      {plan.intro_price_cents !== null && plan.intro_days && (
        <p className={`mt-3 w-fit rounded-full px-3 py-1 text-xs font-semibold ${featured ? 'bg-[#182115]/10' : 'bg-[#d4ff72]/10 text-[#dcff91]'}`}>
          {formatCents(plan.intro_price_cents)} for your first {plan.intro_days} days
        </p>
      )}
      <ul className="mt-6 space-y-2.5 text-sm">
        {planPoints(plan).map((point) => (
          <li key={point} className="flex items-start gap-2"><Check className={`mt-0.5 h-4 w-4 shrink-0 ${featured ? '' : 'text-[#d4ff72]'}`} /> {point}</li>
        ))}
      </ul>
      <Link
        // A paid card carries its plan and the interval actually on show (a
        // plan with no yearly price is quoted monthly even in yearly view).
        to={plan.prices.length
          ? signupPath(plan.code, plan.prices.some((p) => p.interval === interval) ? interval : 'month')
          : SIGNUP_PATH}
        className={`mt-8 inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 text-sm font-bold transition hover:-translate-y-0.5 ${
          featured ? 'bg-[#182115] text-[#e6f4b3] hover:bg-[#263219]' : 'bg-white/10 text-[#f3f1e7] hover:bg-white/15'
        }`}
      >
        {plan.prices.length ? `Start with ${plan.name}` : 'Start free'} <ArrowRight className="h-4 w-4" />
      </Link>
    </article>
  )
}

function AddonNote({ addons }: { addons: CappePublicAddon[] }) {
  const lines = addons
    .map((addon) => {
      const month = addon.prices.find((p) => p.interval === 'month')
      return month ? `${addon.name}: ${formatCents(month.unit_amount_cents, month.currency)}/${addon.unit_label}/mo` : null
    })
    .filter(Boolean)
  if (!lines.length) return null
  return <p className="mt-6 text-center text-sm text-[#b4bca9]">Optional extras — {lines.join(' · ')}</p>
}

export default function Pricing({ pricing }: { pricing: PricingState }) {
  const [interval, setBillingInterval] = useState<Interval>('month')
  const [attachReveal, revealClass] = useReveal<HTMLDivElement>()

  // Hidden, not broken, when the catalog can't load — same as DiscoverStrip.
  if (pricing.status === 'error') return null

  const plans = pricing.status === 'ready' ? [...pricing.pricing.plans].sort((a, b) => a.sort_order - b.sort_order) : []
  const hasYearly = plans.some((plan) => plan.prices.some((p) => p.interval === 'year'))
  const featuredCode = allInPlan(plans)?.code

  return (
    <section id="pricing" className={`scroll-mt-24 py-24 sm:py-32 ${WRAP}`}>
      <div className="mx-auto max-w-2xl text-center">
        <p className={`${EYEBROW} text-[#d4ff72]`}>Pricing</p>
        <h2 className="mt-4 text-4xl font-medium leading-[1.04] tracking-[-0.055em] text-[#f8f7f0] sm:text-5xl">A plan for your next chapter.</h2>
        <p className="mt-5 text-lg leading-8 text-[#afb3a7]">Choose the room you need to grow. The core tools are built in; selling options and allowances vary by plan.</p>
        {hasYearly && (
          <div role="group" aria-label="Billing interval" className="mx-auto mt-8 inline-flex rounded-full border border-white/10 bg-[#1a201a] p-1 text-sm font-semibold">
            {(['month', 'year'] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={interval === value}
                onClick={() => setBillingInterval(value)}
                className={`rounded-full px-4 py-2 transition ${interval === value ? 'bg-[#d4ff72] text-[#182115]' : 'text-[#c5c8bc] hover:text-white'}`}
              >
                {value === 'month' ? 'Monthly' : 'Yearly'}
              </button>
            ))}
          </div>
        )}
      </div>

      {pricing.status === 'loading' ? (
        <div className="mt-14 grid gap-4 md:grid-cols-3" aria-busy="true" aria-label="Loading plans">
          {[0, 1, 2].map((i) => <div key={i} className="h-[30rem] animate-pulse rounded-[1.6rem] bg-white/5" />)}
        </div>
      ) : (
        <>
          <div ref={attachReveal} className={`mx-auto mt-14 grid max-w-5xl gap-4 md:grid-cols-3 ${revealClass}`}>
            {plans.map((plan) => <PlanCard key={plan.code} plan={plan} interval={interval} featured={plan.code === featuredCode} />)}
          </div>
          <AddonNote addons={pricing.pricing.addons} />
          <p className="mx-auto mt-4 max-w-2xl text-center text-xs leading-6 text-[#a0ab93]">Domain registration and optional mailboxes cost extra unless included in your plan. Stripe processing fees apply to payments, alongside any Gummfit per-sale fee shown above.</p>
        </>
      )}
    </section>
  )
}
