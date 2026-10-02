import { useEffect, useState } from 'react'
import { fetchCappePricing } from '../../api'
import type { CappePublicPlan, CappePublicPricing } from '../../types'

export const WRAP = 'mx-auto max-w-7xl px-4 sm:px-8 lg:px-12'
export const LIME_BUTTON =
  'inline-flex items-center justify-center gap-2 rounded-full bg-[#d4ff72] px-6 py-3.5 text-sm font-bold text-[#182115] transition hover:-translate-y-0.5 hover:bg-[#e2ff9a]'
export const EYEBROW = 'text-xs font-bold uppercase tracking-[0.18em]'
export const SIGNUP_PATH = '/gummfit/website-setup'

/** Fade-and-rise as a section scrolls into view. Visible immediately when
 *  IntersectionObserver is missing (tests, old browsers); the motion itself is
 *  `motion-safe:`-only, so reduced-motion users get no transform. Returns
 *  `[attach, className]`: pass `attach` as the element's ref. */
export function useReveal<T extends HTMLElement>() {
  // A callback ref held in state (not useRef) so the effect re-runs when the
  // node mounts — the Pricing grid only appears after the catalog loads.
  const [node, setNode] = useState<T | null>(null)
  const [shown, setShown] = useState(() => typeof IntersectionObserver === 'undefined')

  useEffect(() => {
    if (shown || !node) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setShown(true)
          observer.disconnect()
        }
      },
      { rootMargin: '0px 0px -10% 0px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [node, shown])

  const className = `motion-safe:transition motion-safe:duration-700 motion-safe:ease-out ${
    shown ? 'opacity-100 translate-y-0' : 'opacity-0 motion-safe:translate-y-6'
  }`
  return [setNode, className] as const
}

export type PricingState =
  | { status: 'loading' }
  | { status: 'ready'; pricing: CappePublicPricing }
  | { status: 'error' }

/** One fetch for the whole page — Pricing and the stack comparison both quote it. */
export function usePublicPricing(): PricingState {
  const [state, setState] = useState<PricingState>({ status: 'loading' })
  useEffect(() => {
    let alive = true
    fetchCappePricing()
      .then((pricing) => alive && setState(pricing.plans.length ? { status: 'ready', pricing } : { status: 'error' }))
      .catch(() => alive && setState({ status: 'error' }))
    return () => {
      alive = false
    }
  }, [])
  return state
}

export function formatCents(cents: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: cents % 100 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(cents / 100)
}

export function monthlyPriceCents(plan: CappePublicPlan): number | null {
  return plan.prices.find((p) => p.interval === 'month')?.unit_amount_cents ?? null
}

/** Feature the cheapest paid plan covering every catalog fulfillment type.
 *  Derive it from the live lineup so the highlighted card follows catalog edits. */
export function allInPlan(plans: CappePublicPlan[]): CappePublicPlan | null {
  const kinds = new Set(plans.flatMap((p) => p.allowed_fulfillment))
  const candidates = plans
    .filter((p) => monthlyPriceCents(p) !== null && [...kinds].every((k) => p.allowed_fulfillment.includes(k)))
    .sort((a, b) => (monthlyPriceCents(a) ?? 0) - (monthlyPriceCents(b) ?? 0))
  return candidates[0] ?? null
}
