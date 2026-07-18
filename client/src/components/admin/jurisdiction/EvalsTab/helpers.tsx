// ── Helpers ───────────────────────────────────────────────────────────────────

/** Unmeasured renders as a dash, never as zero — the eval must not imply a verdict it never reached. */
export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'text-zinc-600'
  if (score >= 90) return 'text-emerald-400'
  if (score >= 75) return 'text-amber-400'
  return 'text-red-400'
}

export function scoreCellBg(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'bg-zinc-800/40'
  if (score >= 90) return 'bg-emerald-500/20'
  if (score >= 75) return 'bg-amber-500/20'
  if (score >= 50) return 'bg-orange-500/20'
  return 'bg-red-500/20'
}

export function fmtScore(score: number | null | undefined): string {
  return score === null || score === undefined ? '—' : String(Math.round(score))
}

export function statusBadge(status: string | null | undefined) {
  const map: Record<string, string> = {
    READY: 'bg-emerald-500/20 text-emerald-300',
    DEGRADED: 'bg-amber-500/20 text-amber-300',
    NOT_READY: 'bg-red-500/20 text-red-300',
  }
  const cls = map[status || ''] || 'bg-zinc-700 text-zinc-400'
  return <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${cls}`}>{status || 'UNMEASURED'}</span>
}

export function severityBadge(severity: string) {
  const map: Record<string, string> = {
    critical: 'bg-red-500/20 text-red-400',
    warn: 'bg-amber-500/20 text-amber-400',
    info: 'bg-zinc-700 text-zinc-400',
  }
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${map[severity] || ''}`}>
      {severity}
    </span>
  )
}
