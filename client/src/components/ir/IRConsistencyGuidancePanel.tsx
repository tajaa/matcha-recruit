import { useState, useEffect, useCallback } from 'react'
import { api } from '../../api/client'
import { Card } from '../ui'
import type { IRConsistencyGuidance, IRActionProbability } from '../../types/ir'
import { typeLabel } from '../../types/ir'

type Props = { incidentId: string; status: string }

export function IRConsistencyGuidancePanel({ incidentId, status }: Props) {
  const [guidance, setGuidance] = useState<IRConsistencyGuidance | null>(null)
  const [loading, setLoading] = useState(false)

  const fetchGuidance = useCallback(async () => {
    setLoading(true)
    try { setGuidance(await api.get<IRConsistencyGuidance>(`/ir/incidents/${incidentId}/consistency-guidance`)) }
    catch { setGuidance(null) }
    finally { setLoading(false) }
  }, [incidentId])

  useEffect(() => {
    if (status === 'investigating' || status === 'action_required') {
      fetchGuidance()
    }
  }, [status, fetchGuidance])

  if (status !== 'investigating' && status !== 'action_required') return null

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-zinc-800/60 bg-zinc-900/40">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Consistency Guidance</h3>
      </div>
      <div className="px-5 py-4">
        {loading && !guidance ? (
          <p className="text-xs text-zinc-500">Loading guidance...</p>
        ) : !guidance || guidance.unprecedented ? (
          <p className="text-xs text-zinc-600">
            {guidance?.unprecedented ? 'No precedent found for this type of incident.' : 'No consistency guidance available.'}
          </p>
        ) : (
          <div className="space-y-3">
            {guidance.action_distribution && guidance.action_distribution.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-[11px] text-zinc-500 uppercase tracking-wide">Actions Taken</p>
                {(() => {
                  const max = Math.max(...guidance.action_distribution!.map((a: IRActionProbability) => a.probability), 0.01)
                  return guidance.action_distribution!.map((a: IRActionProbability) => (
                    <div key={a.category} className="flex items-center gap-2">
                      <span className="text-[11px] text-zinc-400 w-24 shrink-0 truncate">{typeLabel(a.category)}</span>
                      <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                        <div className="h-full rounded-full bg-emerald-500/60" style={{ width: `${(a.probability / max) * 100}%` }} />
                      </div>
                      <span className="text-[11px] text-zinc-600 w-8 text-right">{Math.round(a.probability * 100)}%</span>
                    </div>
                  ))
                })()}
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              {guidance.weighted_effectiveness_rate != null && (
                <div className="text-center">
                  <p className="text-sm font-semibold text-zinc-100">{Math.round(guidance.weighted_effectiveness_rate * 100)}%</p>
                  <p className="text-[11px] text-zinc-500">Effectiveness</p>
                </div>
              )}
              {guidance.weighted_avg_resolution_days != null && (
                <div className="text-center">
                  <p className="text-sm font-semibold text-zinc-100">{Math.round(guidance.weighted_avg_resolution_days)}d</p>
                  <p className="text-[11px] text-zinc-500">Avg Resolution</p>
                </div>
              )}
            </div>
            {guidance.consistency_insight && (
              <p className="text-xs text-zinc-400 italic">{guidance.consistency_insight}</p>
            )}
            <p className="text-[11px] text-zinc-600">
              Confidence: {guidance.confidence} ({guidance.sample_size} samples)
            </p>
          </div>
        )}
      </div>
    </Card>
  )
}
