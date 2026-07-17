import type { MeClientProfile } from '../types/dashboard'

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
