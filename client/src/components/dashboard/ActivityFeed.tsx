import { Card } from '../ui'
import type { ActivityItem } from '../../types/dashboard'

interface ActivityFeedProps {
  activities: ActivityItem[]
}

const DOT_COLOR: Record<string, string> = {
  success: 'bg-emerald-500',
  warning: 'bg-amber-500',
  neutral: 'bg-zinc-500',
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

function formatDate(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

export function ActivityFeed({ activities }: ActivityFeedProps) {
  if (activities.length === 0) {
    return (
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-2">Activity</h3>
        <p className="text-xs text-zinc-600">No recent activity</p>
      </Card>
    )
  }

  return (
    <Card className="p-0">
      <div className="px-5 pt-4 pb-3">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Activity</h3>
      </div>
      <div className="divide-y divide-zinc-800">
        {activities.map((a, i) => (
          <div key={i} className="flex items-center gap-3 px-5 py-2.5">
            <span className="text-[11px] text-zinc-600 font-mono w-12 shrink-0">
              {formatTime(a.timestamp)}
            </span>
            <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${DOT_COLOR[a.type] || DOT_COLOR.neutral}`} />
            <span className="text-sm text-zinc-300 flex-1 truncate">{a.action}</span>
            <span className="text-[10px] text-zinc-600 shrink-0">{formatDate(a.timestamp)}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}
