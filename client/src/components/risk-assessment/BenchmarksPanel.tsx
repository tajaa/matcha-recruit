import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { BenchmarkResult } from '../../types/risk-assessment'

const METRIC_LABELS: Record<string, string> = {
  incident_rate_per_100: 'Incident Rate / 100 FTE',
  osha_trc_rate: 'OSHA TRC Rate',
  osha_dart_rate: 'OSHA DART Rate',
  er_case_rate_per_1000: 'ER Case Rate / 1,000',
  eeoc_charge_rate_per_1000: 'EEOC Charge Rate / 1,000',
}

type Props = {
  qs: string
}

export function BenchmarksPanel({ qs }: Props) {
  const [bm, setBm] = useState<BenchmarkResult | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.get<BenchmarkResult>(`/risk-assessment/benchmarks${qs}`)
      .then(setBm)
      .catch(() => setBm(null))
      .finally(() => setLoading(false))
  }, [qs])

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 space-y-4">
      <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Industry Benchmarks</div>

      {loading && <div className="text-[10px] text-zinc-600 animate-pulse font-mono">Loading...</div>}

      {!loading && !bm && (
        <div className="text-[10px] text-zinc-600 font-mono">No benchmark data available.</div>
      )}

      {bm && (
        <>
          <div className="text-[10px] text-zinc-600 font-mono">vs. {bm.naics_label} <span className="text-zinc-700">({bm.naics_code})</span></div>
          {bm.metrics.length === 0 ? (
            <div className="text-[10px] text-zinc-600 font-mono">No metrics to compare.</div>
          ) : (
            <div className="divide-y divide-white/5">
              {bm.metrics.map(m => {
                const ratioColor = m.ratio <= 1.2 ? 'text-emerald-400' : m.ratio <= 2 ? 'text-amber-400' : 'text-red-400'
                const barWidth = Math.min((m.company_value / (m.industry_median * 3)) * 100, 100)
                const medianBarWidth = Math.min((m.industry_median / (m.industry_median * 3)) * 100, 100)
                return (
                  <div key={m.metric} className="py-3">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[10px] text-zinc-400">{METRIC_LABELS[m.metric] ?? m.metric}</span>
                      <span className={`text-[10px] font-mono font-bold ${ratioColor}`}>{m.ratio.toFixed(1)}x</span>
                    </div>
                    <div className="relative h-1.5 bg-white/10 rounded-full">
                      {/* Industry median marker */}
                      <div
                        className="absolute top-0 h-full w-0.5 bg-zinc-500/60"
                        style={{ left: `${medianBarWidth}%` }}
                      />
                      {/* Company bar */}
                      <div
                        className={`absolute top-0 h-full rounded-full ${m.ratio <= 1.2 ? 'bg-emerald-500/60' : m.ratio <= 2 ? 'bg-amber-500/60' : 'bg-red-500/60'}`}
                        style={{ width: `${barWidth}%` }}
                      />
                    </div>
                    <div className="flex justify-between mt-1 text-[9px] font-mono text-zinc-600">
                      <span>You: {m.company_value.toFixed(1)}</span>
                      <span className="text-zinc-700">P{m.percentile}</span>
                      <span>Median: {m.industry_median.toFixed(1)}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}
    </div>
  )
}
