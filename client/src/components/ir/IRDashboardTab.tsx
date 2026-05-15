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

const STAT_CARDS = [
  { key: 'total' as const, label: 'Total', tone: 'text-zinc-100' },
  { key: 'open' as const, label: 'Open', tone: 'text-amber-400' },
  { key: 'investigating' as const, label: 'Investigating', tone: 'text-orange-400' },
  { key: 'critical' as const, label: 'Critical', tone: 'text-red-400' },
]

export function IRDashboardTab({ incidents, summary, onNavigate }: Props) {
  const [trends, setTrends] = useState<IRTrendPoint[]>([])
  const [locations, setLocations] = useState<IRLocationData[]>([])

  useEffect(() => {
    api.get<{ period: string; data: IRTrendPoint[] }>('/ir/incidents/analytics/trends?period=weekly&days=90')
      .then((res) => setTrends(res.data))
      .catch(() => setTrends([]))
    api.get<{ hotspots: IRLocationData[] }>('/ir/incidents/analytics/locations?limit=5')
      .then((res) => setLocations(res.hotspots ?? []))
      .catch(() => setLocations([]))
  }, [])

  const trendMax = Math.max(...trends.map((t) => t.count), 1)
  const locMax = Math.max(...locations.map((l) => l.count), 1)

  return (
    <div className="space-y-8">
      {/* Stat strip */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
          {STAT_CARDS.map((card) => (
            <div key={card.key} className="bg-zinc-900 px-5 py-5 flex flex-col">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{card.label}</div>
              <div className={`text-3xl font-light font-mono mt-2 ${card.tone}`}>{summary[card.key]}</div>
            </div>
          ))}
        </div>
      )}

      {/* Weekly trends */}
      {trends.length > 0 && (
        <section>
          <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">Weekly Trends · 90 days</h2>
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-5 space-y-2">
            {trends.slice(-12).map((t) => (
              <div key={t.date} className="flex items-center gap-3">
                <span className="text-[11px] text-zinc-500 font-mono w-20 shrink-0">
                  {new Date(t.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                </span>
                <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-emerald-500/60 transition-all duration-700"
                    style={{ width: `${(t.count / trendMax) * 100}%` }}
                  />
                </div>
                <span className="text-[11px] text-zinc-400 font-mono w-6 text-right">{t.count}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Top locations */}
      {locations.length > 0 && (
        <section>
          <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">Top Locations</h2>
          <div className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden">
            {locations.map((loc, i) => (
              <div
                key={i}
                className={`flex items-center justify-between px-5 py-3 ${i > 0 ? 'border-t border-white/5' : ''}`}
              >
                <span className="text-[13px] text-zinc-200">{loc.location || 'Unknown'}</span>
                <div className="flex items-center gap-3 w-1/2">
                  <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-orange-500/50 transition-all duration-700"
                      style={{ width: `${(loc.count / locMax) * 100}%` }}
                    />
                  </div>
                  <span className="text-[12px] font-mono text-zinc-300 w-8 text-right">{loc.count}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Recent incidents */}
      {incidents.length > 0 && (
        <section>
          <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">Recent Incidents</h2>
          <div className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden">
            {incidents.slice(0, 5).map((inc, i) => (
              <div
                key={inc.id}
                onClick={() => onNavigate(inc.id)}
                className={`flex items-center justify-between px-5 py-3 cursor-pointer hover:bg-white/[0.02] transition-colors ${
                  i > 0 ? 'border-t border-white/5' : ''
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-[11px] text-zinc-500 font-mono shrink-0">{inc.incident_number}</span>
                  <span className="text-[13px] text-zinc-100 truncate">{inc.title}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant={SEVERITY_BADGE[inc.severity] ?? 'neutral'}>{severityLabel(inc.severity)}</Badge>
                  <Badge variant={STATUS_BADGE[inc.status] ?? 'neutral'}>{statusLabel(inc.status)}</Badge>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
