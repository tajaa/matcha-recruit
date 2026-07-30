/**
 * Events-tab (EMS) review permissions. Mirrors channelPermissions.ts —
 * a single source of truth instead of a role check duplicated at every
 * EMS callsite (sidebar gate, route gate, promote button).
 */
export function canReviewEvents(role: string | undefined): boolean {
  return role === 'client' || role === 'admin'
}
