import { useState, useEffect } from 'react'
import { api } from '../../api/client'
import type { IRAnalyticsSummary, IRConsistencyAnalytics } from '../../types/ir'
import { typeLabel, severityLabel } from '../../types/ir'

export function IRConsistencyAnalyticsPanel() {
  const [summary, setSummary] = useState<IRAnalyticsSummary | null>(null)
  const [consistency, setConsistency] = useState<IRConsistencyAnalytics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get<IRAnalyticsSummary>('/ir/incidents/analytics/summary').catch(() => null),
      api.get<IRConsistencyAnalytics>('/ir/incidents/analytics/consistency').catch(() => null),
    ]).then(([s, c]) => {
      setSummary(s)
      setConsistency(c)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-sm text-zinc-500">Loading...</p>
  if (!summary) return <p className="text-sm text-zinc-500">Unable to load analytics.</p>

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">By Status</h2>
        <div className="grid gap-3 grid-cols-3">
          {([
            ['Open', summary.open],
            ['Investigating', summary.investigating],
            ['Closed', summary.closed + (summary.resolved ?? 0)],
          ] as const).map(([label, value]) => (
            <div key={label} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
              <p className="text-xl font-semibold text-zinc-100">{value}</p>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">By Severity</h2>
        <div className="grid gap-3 grid-cols-4">
          {([
            ['Critical', summary.critical],
            ['High', summary.high],
            ['Medium', summary.medium],
            ['Low', summary.low],
          ] as const).map(([label, value]) => (
            <div key={label} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
              <p className="text-xl font-semibold text-zinc-100">{value}</p>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      </div>

      {summary.by_type && Object.keys(summary.by_type).length > 0 && (
        <div>
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">By Type</h2>
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
            {Object.entries(summary.by_type)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => (
                <div key={type} className="flex items-center justify-between px-4 py-2.5">
                  <span className="text-sm text-zinc-200">{typeLabel(type)}</span>
                  <span className="text-sm font-medium text-zinc-400">{count}</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {consistency && (
        <div>
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Consistency Analytics</h2>
          <div className="border border-zinc-800 rounded-lg p-4 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center">
                <p className="text-lg font-semibold text-zinc-100">{consistency.total_resolved}</p>
                <p className="text-[11px] text-zinc-500 uppercase">Resolved</p>
              </div>
              <div className="text-center">
                <p className="text-lg font-semibold text-zinc-100">{consistency.total_with_actions}</p>
                <p className="text-[11px] text-zinc-500 uppercase">With Actions</p>
              </div>
            </div>

            {consistency.action_distribution.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Action Distribution</p>
                {(() => {
                  const max = Math.max(...consistency.action_distribution.map((a) => a.probability), 0.01)
                  return consistency.action_distribution.map((a) => (
                    <div key={a.category} className="flex items-center gap-2">
                      <span className="text-xs text-zinc-400 w-28 shrink-0 truncate">{typeLabel(a.category)}</span>
                      <div className="flex-1 h-2 rounded-full bg-zinc-800 overflow-hidden">
                        <div className="h-full rounded-full bg-emerald-500/60" style={{ width: `${(a.probability / max) * 100}%` }} />
                      </div>
                      <span className="text-[11px] text-zinc-500 w-10 text-right">{Math.round(a.probability * 100)}%</span>
                    </div>
                  ))
                })()}
              </div>
            )}

            {consistency.by_incident_type.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">By Incident Type</p>
                {consistency.by_incident_type.map((bt) => (
                  <div key={bt.incident_type} className="flex items-center justify-between px-2 py-1">
                    <span className="text-xs text-zinc-300">{typeLabel(bt.incident_type)}</span>
                    <span className="text-xs text-zinc-500">{bt.total} incidents</span>
                  </div>
                ))}
              </div>
            )}

            {consistency.by_severity.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">By Severity</p>
                {consistency.by_severity.map((bs) => (
                  <div key={bs.severity} className="flex items-center justify-between px-2 py-1">
                    <span className="text-xs text-zinc-300">{severityLabel(bs.severity)}</span>
                    <span className="text-xs text-zinc-500">{bs.total} incidents</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
