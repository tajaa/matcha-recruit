import { useState, useEffect } from 'react'
import { Badge, Card } from '../ui'
import { fetchSummary } from '../../api/compliance'
import type { ComplianceSummary } from '../../types/compliance'
import { CATEGORY_LABELS } from '../../types/compliance'

export function ComplianceWidget() {
  const [summary, setSummary] = useState<ComplianceSummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchSummary()
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <Card className="p-5">
        <p className="text-xs text-zinc-500 animate-pulse">Loading compliance...</p>
      </Card>
    )
  }

  if (!summary || summary.total_locations === 0) {
    return (
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 mb-1">Compliance</h3>
        <p className="text-xs text-zinc-600">Add business locations to track compliance requirements.</p>
      </Card>
    )
  }

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-zinc-200">Compliance</h3>
        <a href="/app/compliance" className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">View All &rarr;</a>
      </div>

      <div className="grid grid-cols-4 gap-3">
        {([
          ['Locations', summary.total_locations],
          ['Requirements', summary.total_requirements],
          ['Unread', summary.unread_alerts],
          ['Critical', summary.critical_alerts],
        ] as const).map(([label, value]) => (
          <div key={label} className="text-center">
            <p className="text-lg font-semibold text-zinc-100">{value}</p>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wide">{label}</p>
          </div>
        ))}
      </div>

      {summary.recent_changes.length > 0 && (
        <div>
          <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1.5">Recent Changes</p>
          <div className="space-y-1.5">
            {summary.recent_changes.slice(0, 3).map((change, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="text-xs text-zinc-200 truncate flex-1">{change.title}</span>
                <Badge variant="neutral">{CATEGORY_LABELS[change.category] || change.category}</Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {summary.upcoming_deadlines.length > 0 && (
        <div>
          <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1.5">Upcoming Deadlines</p>
          <div className="space-y-1.5">
            {summary.upcoming_deadlines.slice(0, 3).map((d, i) => (
              <div key={i} className="flex items-center justify-between">
                <span className="text-xs text-zinc-200 truncate flex-1">{d.title}</span>
                <span className={`text-xs font-mono ${d.days_until <= 30 ? 'text-red-400' : d.days_until <= 90 ? 'text-amber-400' : 'text-zinc-500'}`}>
                  {d.days_until <= 0 ? 'NOW' : `${d.days_until}d`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {summary.critical_alerts > 0 && (
        <p className="text-xs text-red-400">
          {summary.critical_alerts} critical alert{summary.critical_alerts > 1 ? 's' : ''} requiring attention
        </p>
      )}
    </Card>
  )
}
