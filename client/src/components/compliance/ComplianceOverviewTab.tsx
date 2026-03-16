import { Badge } from '../ui'
import type { ComplianceSummary, ComplianceAlert, PinnedRequirement } from '../../types/compliance'
import { CATEGORY_LABELS } from '../../types/compliance'

type Props = {
  summary: ComplianceSummary | null
  alerts: ComplianceAlert[]
  pinnedReqs: PinnedRequirement[]
  onViewAllAlerts: () => void
  onAlertAction: (alertId: string, action: 'read' | 'dismiss') => void
}

export function ComplianceOverviewTab({ summary, alerts, pinnedReqs, onViewAllAlerts, onAlertAction }: Props) {
  const topAlerts = alerts.filter((a) => a.severity === 'critical').length > 0
    ? alerts.filter((a) => a.severity === 'critical').slice(0, 3)
    : alerts.slice(0, 3)

  return (
    <div className="space-y-5">
      {summary && (
        <div className="grid gap-3 grid-cols-4">
          {([
            ['Locations', summary.total_locations],
            ['Requirements', summary.total_requirements],
            ['Unread Alerts', summary.unread_alerts],
            ['Critical', summary.critical_alerts],
          ] as const).map(([label, value]) => (
            <div key={label} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
              <p className="text-xl font-semibold text-zinc-100">{value}</p>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Recent alerts */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Recent Alerts</h2>
          {alerts.length > 3 && (
            <button type="button" onClick={onViewAllAlerts}
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">View all alerts &rarr;</button>
          )}
        </div>
        {topAlerts.length === 0 ? (
          <div className="border border-zinc-800 rounded-lg px-4 py-4">
            <p className="text-sm text-zinc-600">No unread alerts</p>
          </div>
        ) : (
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
            {topAlerts.map((alert) => (
              <div key={alert.id} className="px-4 py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm text-zinc-200">{alert.title}</p>
                  <span className={`text-[11px] shrink-0 ${alert.severity === 'critical' ? 'text-red-400' : alert.severity === 'warning' ? 'text-amber-400' : 'text-zinc-500'}`}>
                    {alert.severity}
                  </span>
                </div>
                <p className="text-xs text-zinc-500 mt-0.5 line-clamp-2">{alert.message}</p>
                <div className="flex items-center justify-between mt-1.5">
                  <span className="text-[11px] text-zinc-600">{new Date(alert.created_at).toLocaleDateString()}</span>
                  <div className="flex gap-1">
                    <button type="button" onClick={() => onAlertAction(alert.id, 'read')}
                      className="text-xs text-zinc-600 hover:text-zinc-300 px-1.5 py-0.5 transition-colors">Mark Read</button>
                    <button type="button" onClick={() => onAlertAction(alert.id, 'dismiss')}
                      className="text-xs text-zinc-600 hover:text-zinc-300 px-1.5 py-0.5 transition-colors">Dismiss</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent changes */}
      {summary && summary.recent_changes.length > 0 && (
        <div>
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Recent Changes</h2>
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
            {summary.recent_changes.slice(0, 5).map((change, i) => (
              <div key={i} className="px-4 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-zinc-200">{change.title}</span>
                  <Badge variant="neutral">{CATEGORY_LABELS[change.category] || change.category}</Badge>
                </div>
                <p className="text-xs text-zinc-500 mt-0.5">
                  {change.old_value} &rarr; <span className="text-zinc-300">{change.new_value}</span>
                </p>
                <span className="text-[11px] text-zinc-600">{change.location}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upcoming deadlines */}
      {summary && summary.upcoming_deadlines.length > 0 && (
        <div>
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Upcoming Deadlines</h2>
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
            {summary.upcoming_deadlines.map((d, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-zinc-200 truncate">{d.title}</p>
                  <p className="text-[11px] text-zinc-500 mt-0.5">{d.location} &middot; {new Date(d.effective_date).toLocaleDateString()}</p>
                </div>
                <span className={`text-lg font-mono font-semibold ml-3 ${d.days_until <= 30 ? 'text-red-400' : d.days_until <= 90 ? 'text-amber-400' : 'text-zinc-500'}`}>
                  {d.days_until <= 0 ? 'NOW' : `${d.days_until}d`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pinned requirements */}
      <div>
        <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Pinned Requirements</h2>
        {pinnedReqs.length === 0 ? (
          <div className="border border-zinc-800 rounded-lg px-4 py-4">
            <p className="text-sm text-zinc-600">No pinned requirements. Pin requirements in the Locations tab.</p>
          </div>
        ) : (
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
            {pinnedReqs.map((req) => (
              <div key={req.id} className="px-4 py-2.5">
                <p className="text-sm text-zinc-200">{req.title}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[11px] text-zinc-500">{req.location_name || `${req.city}, ${req.state}`}</span>
                  <span className="text-[11px] text-zinc-600">{CATEGORY_LABELS[req.category] || req.category}</span>
                  {req.current_value && <span className="text-[11px] text-zinc-500">{req.current_value}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
