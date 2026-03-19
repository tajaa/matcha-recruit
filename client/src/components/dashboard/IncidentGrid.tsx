import { useNavigate } from 'react-router-dom'
import { Card, Badge } from '../ui'
import type { IncidentSummary } from '../../types/dashboard'

interface IncidentGridProps {
  summary: IncidentSummary | null
}

const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-blue-400',
}

export function IncidentGrid({ summary }: IncidentGridProps) {
  const navigate = useNavigate()

  if (!summary || summary.total_open === 0) {
    return (
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-2">Incidents</h3>
        <p className="text-xs text-zinc-600">No open incidents</p>
      </Card>
    )
  }

  const buckets = [
    { label: 'Critical', count: summary.critical, key: 'critical' },
    { label: 'High', count: summary.high, key: 'high' },
    { label: 'Medium', count: summary.medium, key: 'medium' },
    { label: 'Low', count: summary.low, key: 'low' },
  ]

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Incidents</h3>
        {summary.recent_7_days > 0 && (
          <Badge variant="warning">+{summary.recent_7_days} this week</Badge>
        )}
      </div>

      <div className="flex items-baseline gap-2 mb-4">
        <span className="text-3xl font-semibold text-zinc-100">{summary.total_open}</span>
        <span className="text-xs text-zinc-500">open</span>
      </div>

      <div className="grid grid-cols-4 gap-3">
        {buckets.map((b) => (
          <div key={b.key} className="text-center">
            <div className="flex items-center justify-center gap-1.5 mb-1">
              <span className={`h-2 w-2 rounded-full ${SEV_DOT[b.key]}`} />
              <span className="text-lg font-semibold text-zinc-100">{b.count}</span>
            </div>
            <span className="text-[10px] text-zinc-500 uppercase tracking-wide">{b.label}</span>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={() => navigate('/app/ir')}
        className="mt-4 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        View All &rarr;
      </button>
    </Card>
  )
}
