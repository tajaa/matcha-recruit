import type { WorkSurface } from '../routes/WorkSurfaceContext'

/**
 * Channel create/paid-create permissions.
 *
 * Single source of truth for what used to be four hand-copied role checks
 * (WorkSidebar, WerkLiteSidebar, ChannelBrowse, WerkLiteHome). The copies had
 * drifted: ChannelBrowse is routed by the werk-lite tree too, so a werk-lite
 * user saw `individual || admin` paid-create on /werk-lite/channels but
 * `admin`-only on /werk-lite and in the sidebar.
 */

const CHANNEL_CREATOR_ROLES = ['client', 'admin', 'individual']

export function canCreateChannel(role: string | undefined): boolean {
  return CHANNEL_CREATOR_ROLES.includes(role ?? '')
}

/**
 * Paid channels are a personal-Werk monetization surface (creator-owned).
 * On werk-lite — a business product with no creator economy — only an admin
 * may open the paid wizard, which is the stricter rule the werk-lite pages
 * already intended.
 */
export function canCreatePaidChannel(
  role: string | undefined,
  surface: WorkSurface,
): boolean {
  if (surface === 'werk-lite') return role === 'admin'
  return role === 'individual' || role === 'admin'
}
