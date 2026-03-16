import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge } from '../ui'
import { fmt } from '../../types/risk-assessment'
import type { AnomalyResult } from '../../types/risk-assessment'

type Props = {
  qs: string
}

export function AnomaliesPanel({ qs }: Props) {
  const [anomalies, setAnomalies] = useState<AnomalyResult | null>(null)

  useEffect(() => {
    api.get<AnomalyResult>(`/risk-assessment/anomalies${qs}`)
      .then(setAnomalies)
      .catch(() => {})
  }, [qs])

  return (
    <div>
      <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-3">
        Anomalies
      </h2>
      {!anomalies || !anomalies.anomalies || anomalies.anomalies.length === 0 ? (
        <p className="text-sm text-zinc-500">No anomalies detected.</p>
      ) : (
        <div className="border border-zinc-800 rounded-xl divide-y divide-zinc-800/60">
          {anomalies.anomalies.map((a, i) => (
            <div key={i} className="px-4 py-3 flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-zinc-200">{a.metric.replace(/_/g, ' ')}</p>
                <p className="text-xs text-zinc-500 mt-0.5">
                  {fmt(a.detected_at)} · Value: {a.value} · Expected {a.expected_low}–{a.expected_high}
                </p>
              </div>
              <Badge variant={a.sigma > 3 ? 'danger' : 'warning'}>
                {a.sigma.toFixed(1)}σ
              </Badge>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
