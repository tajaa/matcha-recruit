import { useNavigate } from 'react-router-dom'
import { Card, Badge } from '../ui'
import type { UpcomingItem } from '../../types/dashboard'

interface UpcomingDeadlinesProps {
  items: UpcomingItem[]
  loading: boolean
}

const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-500',
  warning: 'bg-amber-500',
  info: 'bg-zinc-500',
}

const CATEGORY_LABEL: Record<string, string> = {
  compliance: 'Compliance',
  credential: 'Credential',
  training: 'Training',
  cobra: 'COBRA',
  policy: 'Policy',
  ir: 'Incident',
  er: 'ER Case',
  i9: 'I-9',
  separation: 'Separation',
  onboarding: 'Onboarding',
  legislation: 'Legislation',
  requirement: 'Requirement',
}

function daysColor(d: number): string {
  if (d < 0) return 'text-red-400'
  if (d <= 14) return 'text-amber-400'
  if (d <= 30) return 'text-yellow-400'
  return 'text-zinc-500'
}

export function UpcomingDeadlines({ items, loading }: UpcomingDeadlinesProps) {
  const navigate = useNavigate()

  if (loading) {
    return (
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 mb-2">Upcoming Deadlines</h3>
        <p className="text-xs text-zinc-500 animate-pulse">Loading...</p>
      </Card>
    )
  }

  if (items.length === 0) {
    return (
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 mb-2">Upcoming Deadlines</h3>
        <p className="text-xs text-zinc-600">No upcoming deadlines</p>
      </Card>
    )
  }

  return (
    <Card className="p-0">
      <div className="px-5 pt-4 pb-3">
        <h3 className="text-sm font-medium text-zinc-200">Upcoming Deadlines</h3>
      </div>
      <div className="divide-y divide-zinc-800">
        {items.slice(0, 8).map((item, i) => (
          <button
            key={i}
            type="button"
            onClick={() => navigate(item.link)}
            className="flex items-center gap-3 w-full px-5 py-2.5 text-left hover:bg-zinc-800/50 transition-colors"
          >
            <span className={`h-2 w-2 rounded-full shrink-0 ${SEV_DOT[item.severity] || SEV_DOT.info}`} />
            <span className="text-sm text-zinc-200 flex-1 truncate">{item.title}</span>
            <Badge variant="neutral">{CATEGORY_LABEL[item.category] || item.category}</Badge>
            <span className={`text-xs font-mono shrink-0 ${daysColor(item.days_until)}`}>
              {item.days_until < 0 ? `${Math.abs(item.days_until)}d ago` : `${item.days_until}d`}
            </span>
          </button>
        ))}
      </div>
    </Card>
  )
}
