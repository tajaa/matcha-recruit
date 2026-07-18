import type { Branding, LinkStatus } from './types'

export const STATUS_STYLE: Record<LinkStatus, string> = {
  active: 'text-emerald-400/80',
  revoked: 'text-red-400/80',
  expired: 'text-zinc-500',
}

// --- QR poster branding -----------------------------------------------------

export const DEFAULT_BRAND: Branding = { primary: '#4f9d72', secondary: '#f5a623' }
