import type { MeClientProfile, ProductDefinition } from '../types/dashboard'

/**
 * True when the company is on a self-serve IR tier (free beta or paid Lite).
 *
 * Accepts signup_source='ir_only_self_serve' (free IR beta), 'matcha_lite'
 * (paid, headcount-based), and 'matcha_lite_essentials' (same page/checkout,
 * no-roster config — cheaper, no employees/osha_logs). All three route to
 * IrSidebar once the incidents feature is on. enabled_features.incidents must
 * be true so a matcha_lite(_essentials) company that hasn't completed payment
 * doesn't land here.
 */
export function isIrOnlyTier(profile: MeClientProfile | null | undefined): boolean {
  if (!profile) return false
  const src = profile.signup_source
  if (src !== 'ir_only_self_serve' && src !== 'matcha_lite' && src !== 'matcha_lite_essentials') return false
  return !!profile.enabled_features?.incidents
}

/**
 * True for a matcha_lite(_essentials) company that registered but hasn't
 * completed the Stripe checkout yet (incidents feature is still false).
 */
export function isMatchaLitePending(profile: MeClientProfile | null | undefined): boolean {
  if (!profile) return false
  const src = profile.signup_source
  return (src === 'matcha_lite' || src === 'matcha_lite_essentials') && !profile.enabled_features?.incidents
}

/**
 * True when the company is on the paid Matcha-X mid tier (incidents on).
 * Matcha-X is a clone of Matcha Lite at Lite parity; it drives a dedicated
 * MatchaXSidebar so its nav can diverge (HRIS, credentials) without touching
 * Lite. `incidents` must be true so a matcha_x company mid-checkout doesn't
 * land here — see isMatchaXPending.
 */
export function isMatchaX(profile: MeClientProfile | null | undefined): boolean {
  if (!profile) return false
  return profile.signup_source === 'matcha_x' && !!profile.enabled_features?.incidents
}

/**
 * True for a matcha_x company that registered but hasn't completed the
 * Stripe checkout yet (incidents feature is still false).
 */
export function isMatchaXPending(profile: MeClientProfile | null | undefined): boolean {
  if (!profile) return false
  return profile.signup_source === 'matcha_x' && !profile.enabled_features?.incidents
}

/**
 * True when the company is on the standalone Matcha Compliance product with
 * payment complete (full `compliance` feature on). Self-serve, Stripe-billed,
 * priced by headcount + jurisdiction count. Drives ComplianceSidebar.
 * `compliance` must be true so a company mid-checkout doesn't land here —
 * see isMatchaCompliancePending.
 */
export function isMatchaCompliance(profile: MeClientProfile | null | undefined): boolean {
  if (!profile) return false
  return profile.signup_source === 'matcha_compliance' && !!profile.enabled_features?.compliance
}

/**
 * True for a matcha_compliance company that registered but hasn't completed the
 * Stripe checkout yet (the `compliance` feature is still false).
 */
export function isMatchaCompliancePending(profile: MeClientProfile | null | undefined): boolean {
  if (!profile) return false
  return profile.signup_source === 'matcha_compliance' && !profile.enabled_features?.compliance
}

/**
 * True when the company signed up on an admin-composed product
 * (/admin/products → signup_source 'product:<slug>'). `profile.product`
 * carries the definition; without it we can't build the shell, so both are
 * required.
 */
export function isCustomProduct(profile: MeClientProfile | null | undefined): boolean {
  if (!profile) return false
  return !!profile.signup_source?.startsWith('product:') && !!profile.product
}

/**
 * True for a custom-product company that hasn't been activated yet: the paid
 * gate flag is still false. Covers both Stripe-billed products awaiting
 * checkout and contact-sales products awaiting an admin activation. Free
 * products have no gate and are never pending.
 */
export function isCustomProductPending(profile: MeClientProfile | null | undefined): boolean {
  if (!isCustomProduct(profile)) return false
  const product = profile!.product!
  const enabled = profile!.enabled_features ?? {}
  if (product.gate_feature) return !enabled[product.gate_feature]
  // contact_sales has no gate — the tell is whether the admin's
  // activate-tenant materialization has run (any granted feature on).
  // Mirrors server product_definitions.is_tenant_activated.
  if (product.pricing_model === 'contact_sales') {
    return !product.features.some((f) => enabled[f])
  }
  return false // free — active at signup
}

/** Monthly price in whole dollars for `headcount`, or null when not billed. */
export function productPriceDollars(product: ProductDefinition, headcount: number): number | null {
  if (product.pricing_model === 'free' || product.pricing_model === 'contact_sales') return null
  if (headcount < product.min_headcount || headcount > product.max_headcount) return null
  const cents = product.price_cents ?? 0
  if (product.pricing_model === 'flat') return Math.round(cents / 100)
  if (product.pricing_model === 'per_seat') return Math.round((cents * headcount) / 100)
  const blockSize = product.block_size || 1
  return Math.round((Math.ceil(headcount / blockSize) * cents) / 100)
}
