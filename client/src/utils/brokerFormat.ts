// Shared formatters + severity-band tones for the Broker Portal.
//
// These were previously duplicated inline across BrokerWcPortfolio.tsx,
// BrokerRiskAlerts.tsx, BrokerRenewalRiskRadar.tsx and
// BrokerEligibilityExceptions.tsx. Centralized here so the Book of Business
// master view and the Action Center tabs render identically.

export type SeverityBand = 'good' | 'fair' | 'at_risk' | 'critical' | 'unknown'

/** WC severity-band visual tones (dot/text/bg/label). Mirrors the original
 *  BrokerWcPortfolio BAND_TONE map. */
export const BAND_TONE: Record<SeverityBand, { dot: string; text: string; bg: string; label: string }> = {
  critical: { dot: 'bg-red-500',     text: 'text-red-400',     bg: 'bg-red-500/10 border-red-500/20',         label: 'Critical' },
  at_risk:  { dot: 'bg-orange-500',  text: 'text-orange-400',  bg: 'bg-orange-500/10 border-orange-500/20',   label: 'At Risk' },
  fair:     { dot: 'bg-amber-500',   text: 'text-amber-400',   bg: 'bg-amber-500/10 border-amber-500/20',     label: 'Fair' },
  good:     { dot: 'bg-emerald-500', text: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20', label: 'Good' },
  unknown:  { dot: 'bg-zinc-600',    text: 'text-zinc-500',    bg: 'bg-zinc-800 border-white/5',              label: 'Unknown' },
}

/** Compact USD. e.g. 1_250_000 → "$1.3M", 18_000 → "$18K", 240 → "$240". */
export function fmtMoney(n: number): string {
  const abs = Math.abs(n)
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (abs >= 10_000) return `$${Math.round(n / 1000)}K`
  return `$${Math.round(n).toLocaleString()}`
}

/** One-decimal percent. */
export function fmtPct(n: number): string {
  return `${n.toFixed(1)}%`
}

/** Short locale date (M/D/YYYY) from an ISO string; em dash for null. */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', year: 'numeric' })
}

/** Clean-streak label from days-since-last-recordable. null = "∞" (never). */
export function streakLabel(days: number | null | undefined): string {
  if (days === null || days === undefined) return '∞'
  if (days < 60) return `${days}d`
  if (days < 730) return `${Math.floor(days / 30)}mo`
  return `${(days / 365).toFixed(1)}y`
}
