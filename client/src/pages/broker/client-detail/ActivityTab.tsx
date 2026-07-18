import { Clock } from 'lucide-react'
import { Card } from '../../../components/ui'
import type { BrokerClientDetailResponse } from '../../../types/broker'
import { formatRelative } from './shared'

export function ActivityTab({ activity }: { activity: BrokerClientDetailResponse['recent_activity'] }) {
  if (activity.length === 0) {
    return (
      <Card className="p-5">
        <p className="text-sm text-zinc-500">No recent activity.</p>
      </Card>
    )
  }

  const sourceBadge: Record<string, string> = {
    IR: 'bg-zinc-800 text-zinc-400',
    ER: 'bg-zinc-800 text-zinc-500',
  }

  return (
    <Card className="p-5">
      <div className="space-y-0">
        {activity.map((a, i) => (
          <div key={i} className="flex items-start gap-3 py-3 border-b border-zinc-800/30 last:border-0">
            <Clock className="h-4 w-4 text-zinc-600 mt-0.5 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-zinc-200">{a.action}</p>
              <p className="text-xs text-zinc-500 mt-0.5">{formatRelative(a.timestamp)}</p>
            </div>
            <span className={`text-[11px] px-2 py-0.5 rounded-full flex-shrink-0 ${
              sourceBadge[a.source] ?? 'bg-zinc-800 text-zinc-400'
            }`}>
              {a.source}
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}
