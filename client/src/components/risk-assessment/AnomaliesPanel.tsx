import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { AnomalyDetectionResult } from '../../types/risk-assessment'

type Props = {
  qs: string
}

export function AnomaliesPanel({ qs }: Props) {
  const [result, setResult] = useState<AnomalyDetectionResult | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const sep = qs ? '&' : '?'
    api.get<AnomalyDetectionResult>(`/risk-assessment/anomalies${qs}${sep}months=24`)
      .then(setResult)
      .catch(() => setResult(null))
      .finally(() => setLoading(false))
  }, [qs])

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 space-y-4">
      <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Anomaly Detection</div>

      {loading && <div className="text-[10px] text-zinc-600 animate-pulse font-mono">Loading...</div>}

      {!loading && !result && (
        <div className="text-[10px] text-zinc-600 font-mono">No anomaly data available.</div>
      )}

      {result && !result.has_sufficient_data && (
        <div className="text-[10px] text-zinc-600 font-mono">
          Needs ≥ 6 months of history ({result.data_points_available} data points available).
        </div>
      )}

      {result && result.has_sufficient_data && (
        <>
          <div className="flex gap-4">
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 text-center">
              <div className="text-xl font-mono font-light text-red-400">{result.alert_count}</div>
              <div className="text-[9px] text-red-500/70 uppercase tracking-widest font-bold mt-0.5">Alerts</div>
            </div>
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 text-center">
              <div className="text-xl font-mono font-light text-amber-400">{result.warning_count}</div>
              <div className="text-[9px] text-amber-500/70 uppercase tracking-widest font-bold mt-0.5">Warnings</div>
            </div>
          </div>

          {result.total_anomalies === 0 ? (
            <div className="text-[10px] text-emerald-400 font-mono">No anomalies detected — all metrics within normal range.</div>
          ) : (
            <div className="divide-y divide-white/5">
              {result.metrics.flatMap(m => m.anomalies).map((a, i) => (
                <div key={i} className="py-2.5">
                  <div className="flex items-start gap-2">
                    <span className={`shrink-0 text-[9px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded ${
                      a.severity === 'alert'
                        ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                        : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    }`}>{a.severity}</span>
                    <div>
                      <div className="text-[11px] text-zinc-200">{a.description}</div>
                      <div className="text-[9px] text-zinc-600 font-mono mt-0.5">
                        {a.period} · value {a.value.toFixed(1)} · mean {a.rolling_mean.toFixed(1)} · z={a.z_score.toFixed(2)}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
