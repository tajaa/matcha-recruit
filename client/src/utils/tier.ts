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
