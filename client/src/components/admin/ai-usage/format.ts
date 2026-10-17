// Formatters shared by the AI Usage page (pages/admin/AiUsage.tsx) and its panels.

import type { ApiQuota } from '../../../types/aiUsage'

export function fmtCost(v: number | null): string {
  if (v == null) return '—'
  return v >= 1 ? `$${v.toFixed(2)}` : `$${v.toFixed(4)}`
}

export function fmtTokens(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}k`
  return String(v)
}

export function fmtMs(v: number | null): string {
  if (v == null) return '—'
  return `${Math.round(v)}ms`
}

export function fmtPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`
}

export function fmtCount(v: number | null): string {
  return v == null ? '—' : v.toLocaleString('en-US')
}

export function fmtSeconds(v: number | null): string {
  if (v == null) return '—'
  if (v < 60) return `${v.toFixed(v < 10 ? 1 : 0)}s`
  return `${Math.floor(v / 60)}m ${Math.round(v % 60)}s`
}

export function relTime(iso: string, now: number = Date.now()): string {
  const ms = now - new Date(iso).getTime()
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

/** "in 3d", "in 5h", "today", or "passed" for a reset date (ISO date or timestamp). */
export function fmtUntil(iso: string, now: number = Date.now()): string {
  const at = new Date(iso).getTime()
  if (Number.isNaN(at)) return iso
  const ms = at - now
  if (ms <= 0) return 'passed'
  const h = Math.floor(ms / 3_600_000)
  if (h < 1) return 'within the hour'
  if (h < 24) return `in ${h}h`
  return `in ${Math.floor(h / 24)}d`
}

export type QuotaView = {
  /** The big number: "1,849 left", "Not set up", "Unavailable". */
  headline: string
  /** "of 2,000 · resets in 15d". */
  detail: string | null
  /** Share of the period's searches still left, 0..1, when both numbers are known. */
  leftShare: number | null
  tone: 'ok' | 'low' | 'out' | 'muted' | 'error'
}

/** How one search API's quota reads on its card. Low is under 10% left. */
export function quotaView(q: ApiQuota, now: number = Date.now()): QuotaView {
  if (!q.configured) return { headline: 'Not set up', detail: 'No API key on this server', leftShare: null, tone: 'muted' }
  if (q.error) return { headline: 'Unavailable', detail: q.error, leftShare: null, tone: 'error' }
  const parts: string[] = []
  if (q.limit != null) parts.push(`of ${fmtCount(q.limit)} this period`)
  if (q.resets_at) {
    const until = fmtUntil(q.resets_at, now)
    parts.push(until === 'passed' ? 'reset since last seen' : `resets ${until}`)
  }
  if (q.remaining == null) {
    return {
      headline: q.source === 'headers' ? 'Not seen yet' : 'Unknown',
      detail: parts.join(' · ') || null,
      leftShare: null,
      tone: 'muted',
    }
  }
  const leftShare = q.limit ? Math.max(0, Math.min(1, q.remaining / q.limit)) : null
  const tone = q.remaining <= 0 ? 'out' : leftShare != null && leftShare < 0.1 ? 'low' : 'ok'
  return { headline: `${fmtCount(q.remaining)} left`, detail: parts.join(' · ') || null, leftShare, tone }
}
