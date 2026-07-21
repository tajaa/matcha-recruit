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

// Re-exported from utils/format so the ~20 broker call sites keep working.
// The implementation moved because nine other files had their own copy and they
// had drifted apart.
export { relativeTime as formatRelative } from '../../../utils/format'
