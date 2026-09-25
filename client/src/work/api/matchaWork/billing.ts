import { api } from '../../../api/client'

// ── Billing ──

export interface MWSubscription {
  active: boolean
  pack_id?: string | null
  tokens_per_cycle?: number | null
  amount_cents?: number | null
  status?: string | null
  current_period_end?: string | null
}

export function getMWSubscription() {
  return api.get<MWSubscription>('/matcha-work/billing/subscription')
}

export function startPersonalCheckout(plan: 'lite' | 'pro' = 'pro') {
  const successUrl = `${window.location.origin}/espresso?upgraded=1`
  const cancelUrl = `${window.location.origin}/espresso?canceled=1`
  return api.post<{ checkout_url: string; stripe_session_id: string }>(
    '/matcha-work/billing/checkout/personal',
    { success_url: successUrl, cancel_url: cancelUrl, plan },
  )
}
