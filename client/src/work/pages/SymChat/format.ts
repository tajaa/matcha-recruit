import type { SymChatKind, SymChatResolution, SymChatStatus } from '../../api/matchaWork/symChat'

export const KIND_LABEL: Record<SymChatKind, string> = {
  schedule: 'Find a time',
  decide: 'Decide together',
}

export const STATUS_LABEL: Record<SymChatStatus, string> = {
  open: 'Open',
  resolved: 'Settled',
  cancelled: 'Cancelled',
}

/** '14:00' → '2:00 PM'. Mirrors services/sym_chat/narrate.fmt_time. */
export function fmtTime(hhmm: string | null | undefined): string {
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm ?? '')
  if (!m) return hhmm ?? ''
  const hours = Number(m[1]) % 24
  const suffix = hours < 12 ? 'AM' : 'PM'
  return `${hours % 12 || 12}:${m[2]} ${suffix}`
}

/** '2026-09-29' → 'Tue, Sep 29' — read as a calendar date, never shifted by the viewer's timezone. */
export function fmtDate(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso ?? '')
  if (!m) return iso ?? ''
  const day = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])))
  return day.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' })
}

export function resolutionText(resolution: SymChatResolution | null | undefined): string {
  if (!resolution) return ''
  if (resolution.kind === 'schedule') {
    return `${fmtTime(resolution.start)}–${fmtTime(resolution.end)} on ${fmtDate(resolution.date)} (${resolution.timezone})`
  }
  return resolution.choice
}

export function statusClass(status: SymChatStatus): string {
  if (status === 'resolved') return 'bg-emerald-500/15 text-emerald-400'
  if (status === 'cancelled') return 'bg-w-surface2 text-w-faint'
  return 'bg-w-accent/15 text-w-accent'
}
