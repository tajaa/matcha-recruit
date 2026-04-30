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
