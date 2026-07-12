import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '../../../api/client'
import type { WcMetrics } from './IRWcMetricsCard'

type Scorecard = {
  location_id: string | null
  location_name: string
  city: string | null
  state: string | null
  metrics: WcMetrics
}

type ByLocationResponse = {
  period_days: number
  company: WcMetrics
  locations: Scorecard[]
  generated_at: string
}

/**
 * Per-establishment TRIR/DART scorecard. Multi-site buyers need to see which
 * site drives the composite safety number; the company-wide WcMetricsCard
 * can't. Renders only when there's more than one location. Best-effort.
 */
export function IRLocationScorecards() {
  const [data, setData] = useState<ByLocationResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get<ByLocationResponse>('/ir/incidents/analytics/wc-metrics/by-location')
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <section>
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 flex items-center justify-center text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading site scorecards…
        </div>
      </section>
    )
  }

  if (!data || data.locations.length < 2) return null

  const num = (n: number | null | undefined) => (n === null || n === undefined ? '—' : n)

  return (
    <section>
      <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">
        Per-Location Safety Scorecard
      </h2>
      <div className="bg-zinc-900 border border-white/10 rounded-2xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] text-zinc-500 uppercase tracking-wider border-b border-white/10">
              <th className="text-left font-semibold px-4 py-2.5">Location</th>
              <th className="text-right font-semibold px-3 py-2.5">TRIR</th>
              <th className="text-right font-semibold px-3 py-2.5">DART</th>
              <th className="text-right font-semibold px-3 py-2.5">Recordables</th>
              <th className="text-right font-semibold px-3 py-2.5">Lost days</th>
              <th className="text-right font-semibold px-4 py-2.5">Days since</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-white/10 bg-white/[0.02]">
              <td className="px-4 py-2.5 text-zinc-200 font-medium">All sites</td>
              <td className="px-3 py-2.5 text-right font-mono text-zinc-100">{num(data.company.trir)}</td>
              <td className="px-3 py-2.5 text-right font-mono text-zinc-100">{num(data.company.dart_rate)}</td>
              <td className="px-3 py-2.5 text-right font-mono text-zinc-300">{data.company.recordable_cases}</td>
              <td className="px-3 py-2.5 text-right font-mono text-zinc-300">{data.company.lost_days}</td>
              <td className="px-4 py-2.5 text-right font-mono text-zinc-300">{num(data.company.days_since_last_recordable)}</td>
            </tr>
            {data.locations.map((loc) => {
              const m = loc.metrics
              const place = [loc.city, loc.state].filter(Boolean).join(', ')
              return (
                <tr key={loc.location_id ?? loc.location_name} className="border-b border-white/5 last:border-0">
                  <td className="px-4 py-2.5 text-zinc-200">
                    {loc.location_name}
                    {place && <span className="text-zinc-500 text-[11px] ml-1">· {place}</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-zinc-100">{num(m.trir)}</td>
                  <td className="px-3 py-2.5 text-right font-mono text-zinc-100">{num(m.dart_rate)}</td>
                  <td className="px-3 py-2.5 text-right font-mono text-zinc-300">{m.recordable_cases}</td>
                  <td className="px-3 py-2.5 text-right font-mono text-zinc-300">{m.lost_days}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-zinc-300">{num(m.days_since_last_recordable)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-zinc-600 mt-2">
        TRIR/DART require a per-site headcount; sites without one show “—”. Rates use the same 200,000-hour basis as the company roll-up.
      </p>
    </section>
  )
}
