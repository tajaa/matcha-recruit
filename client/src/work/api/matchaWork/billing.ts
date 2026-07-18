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

export function startPersonalCheckout() {
  const successUrl = `${window.location.origin}/werk?upgraded=1`
  const cancelUrl = `${window.location.origin}/werk?canceled=1`
  return api.post<{ checkout_url: string; stripe_session_id: string }>(
    '/matcha-work/billing/checkout/personal',
    { success_url: successUrl, cancel_url: cancelUrl },
  )
}
