import { useState, useEffect } from 'react'
import { api } from '../../api/client'
import { Badge } from '../ui'
import type { IRIncident, IRAnalyticsSummary, IRTrendPoint, IRLocationData } from '../../types/ir'
import { severityLabel, statusLabel, SEVERITY_BADGE, STATUS_BADGE } from '../../types/ir'

type Props = {
  incidents: IRIncident[]
  summary: IRAnalyticsSummary | null
  onNavigate: (id: string) => void
}

export function IRDashboardTab({ incidents, summary, onNavigate }: Props) {
  const [trends, setTrends] = useState<IRTrendPoint[]>([])
  const [locations, setLocations] = useState<IRLocationData[]>([])

  useEffect(() => {
    api.get<{ interval: string; data: IRTrendPoint[] }>('/ir/incidents/analytics/trends?interval=weekly&days=90')
      .then((res) => setTrends(res.data))
      .catch(() => setTrends([]))
    api.get<{ locations: IRLocationData[] }>('/ir/incidents/analytics/locations?limit=5')
      .then((res) => setLocations(res.locations ?? []))
      .catch(() => setLocations([]))
  }, [])

  return (
    <div className="space-y-5">
      {summary && (
        <div className="grid gap-3 grid-cols-4">
          {([
            ['Total', summary.total],
            ['Open', summary.open],
            ['Investigating', summary.investigating],
            ['Critical', summary.critical],
          ] as const).map(([label, value]) => (
            <div key={label} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
              <p className="text-xl font-semibold text-zinc-100">{value}</p>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      )}

      {trends.length > 0 && (
        <div>
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Weekly Trends (90d)</h2>
          <div className="border border-zinc-800 rounded-lg p-4 space-y-2">
            {(() => {
              const max = Math.max(...trends.map((t) => t.count), 1)
              return trends.slice(-12).map((t) => (
                <div key={t.date} className="flex items-center gap-2">
                  <span className="text-xs text-zinc-500 w-20 shrink-0">{new Date(t.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                  <div className="flex-1 h-2 rounded-full bg-zinc-800 overflow-hidden">
                    <div className="h-full rounded-full bg-emerald-500/60" style={{ width: `${(t.count / max) * 100}%` }} />
                  </div>
                  <span className="text-[11px] text-zinc-500 w-6 text-right">{t.count}</span>
                </div>
              ))
            })()}
          </div>
        </div>
      )}

      {locations.length > 0 && (
        <div>
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Top Locations</h2>
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
            {locations.map((loc, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-2.5">
                <span className="text-sm text-zinc-200">{loc.location || 'Unknown'}</span>
                <span className="text-sm font-medium text-zinc-400">{loc.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {incidents.length > 0 && (
        <div>
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Recent Incidents</h2>
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
            {incidents.slice(0, 5).map((inc) => (
              <div key={inc.id} onClick={() => onNavigate(inc.id)}
                className="flex items-center justify-between px-4 py-2.5 hover:bg-zinc-900/30 cursor-pointer transition-colors">
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-xs text-zinc-500 font-mono shrink-0">{inc.incident_number}</span>
                  <span className="text-sm text-zinc-200 truncate">{inc.title}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant={SEVERITY_BADGE[inc.severity] ?? 'neutral'}>{severityLabel(inc.severity)}</Badge>
                  <Badge variant={STATUS_BADGE[inc.status] ?? 'neutral'}>{statusLabel(inc.status)}</Badge>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
