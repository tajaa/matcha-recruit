import { api } from '../client'

// Lite add-ons — each rides its own Stripe subscription on top of the base
// Lite sub. Registry lives server-side (app/core/services/lite_addons.py);
// the list endpoint returns per-company eligibility + live PEPM pricing.

export type LiteAddonStatus = 'active' | 'available' | 'not_eligible'

export interface LiteAddonInfo {
  key: string
  name: string
  description: string
  status: LiteAddonStatus
  monthly_price_cents: number | null
  // True when the add-on rides a self-purchased Stripe sub (cancellable
  // here); false for admin-granted flags without a sub.
  cancellable: boolean
}

export function fetchLiteAddons() {
  return api.get<LiteAddonInfo[]>('/resources/lite-addons')
}

export function createLiteAddonCheckout(addonKey: string, successUrl: string, cancelUrl: string) {
  return api.post<{ checkout_url: string; stripe_session_id: string }>('/resources/checkout/lite-addon', {
    addon_key: addonKey,
    success_url: successUrl,
    cancel_url: cancelUrl,
  })
}

export function cancelLiteAddon(addonKey: string) {
  return api.post<{ canceled: boolean; message: string }>(`/resources/lite-addons/${addonKey}/cancel`, {})
}

export function createLiteUpgradeCheckout(successUrl: string, cancelUrl: string) {
  return api.post<{ checkout_url: string; stripe_session_id: string }>('/resources/checkout/lite-upgrade', {
    success_url: successUrl,
    cancel_url: cancelUrl,
  })
}
