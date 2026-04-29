import type { MeClientProfile } from '../types/dashboard'

/**
 * True when the company is a self-serve Matcha IR free-beta tenant.
 *
 * Both signals must match: signup_source pins the path the company
 * came in through (so a partially-provisioned bespoke customer with
 * only `incidents` enabled doesn't fall into the slim layout), and
 * enabled_features.incidents confirms the IR feature is actually on.
 */
export function isIrOnlyTier(profile: MeClientProfile | null | undefined): boolean {
  if (!profile) return false
  return (
    profile.signup_source === 'ir_only_self_serve' &&
    !!profile.enabled_features?.incidents
  )
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
