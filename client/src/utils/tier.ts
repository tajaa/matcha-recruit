import type { MeClientProfile } from '../types/dashboard'

/**
 * True when the company is on a self-serve IR tier (free beta or paid Lite).
 *
 * Accepts both signup_source='ir_only_self_serve' (free IR beta) and
 * 'matcha_lite' (paid, headcount-based). Both route to IrSidebar once
 * the incidents feature is on. enabled_features.incidents must be true
 * so a matcha_lite company that hasn't completed payment doesn't land here.
 */
export function isIrOnlyTier(profile: MeClientProfile | null | undefined): boolean {
  if (!profile) return false
  const src = profile.signup_source
  if (src !== 'ir_only_self_serve' && src !== 'matcha_lite') return false
  return !!profile.enabled_features?.incidents
}

/**
 * True for a matcha_lite company that registered but hasn't completed
 * the Stripe checkout yet (incidents feature is still false).
 */
export function isMatchaLitePending(profile: MeClientProfile | null | undefined): boolean {
  if (!profile) return false
  return profile.signup_source === 'matcha_lite' && !profile.enabled_features?.incidents
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
 * True for the free Resources-tier signup. They get access to the marketing
 * resource hub (templates, calculators, audit) but no paid features. Sidebar
 * surfaces the upgrade-to-IR + contact-for-full-platform CTAs for them.
 */
export function isResourcesFreeTier(profile: MeClientProfile | null | undefined): boolean {
  if (!profile) return false
  if (profile.signup_source !== 'resources_free') return false
  // Defensive: if an admin has manually upgraded a resources_free tenant
  // by enabling a feature, fall back to the standard sidebar.
  const features = profile.enabled_features ?? {}
  const anyEnabled = Object.values(features).some(Boolean)
  return !anyEnabled
}
