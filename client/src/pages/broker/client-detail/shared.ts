export const riskColors: Record<string, string> = {
  healthy: 'bg-zinc-500',
  watch: 'bg-zinc-700',
  at_risk: 'bg-zinc-800',
}

export const riskLabels: Record<string, string> = {
  healthy: 'Healthy',
  watch: 'Watch',
  at_risk: 'At Risk',
}

export const severityColors: Record<string, string> = {
  critical: 'bg-zinc-100 text-zinc-900',
  high: 'bg-zinc-300 text-zinc-900',
  medium: 'bg-zinc-500 text-zinc-100',
  low: 'bg-zinc-800 text-zinc-400',
}

export function complianceColor(rate: number) {
  if (rate >= 80) return 'text-zinc-100'
  if (rate >= 50) return 'text-zinc-400'
  return 'text-zinc-600'
}

export function formatRelative(ts: string) {
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  return new Date(ts).toLocaleDateString()
}
