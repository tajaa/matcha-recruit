import type { Registration, Tab } from './types'

export function tierFromRegistration(r: Registration): Exclude<Tab, 'all'> {
  if (r.is_personal) return 'personal'
  if (r.signup_source === 'resources_free') return 'free'
  if (r.signup_source === 'matcha_lite') return 'lite'
  if (r.signup_source === 'matcha_x') return 'x'
  return 'platform'
}

export function fmtUsd(cents: number) {
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function relTime(iso: string | null) {
  if (!iso) return '—'
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (d === 0) return 'Today'
  if (d === 1) return 'Yesterday'
  return `${d}d ago`
}

export function fmtTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(n)
}

export function matchSearch(a: string, b: string | null, q: string) {
  if (!q.trim()) return true
  const needle = q.toLowerCase()
  return a.toLowerCase().includes(needle) || (b ?? '').toLowerCase().includes(needle)
}
