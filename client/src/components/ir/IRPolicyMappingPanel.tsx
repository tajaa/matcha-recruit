import { useState, useEffect, useCallback } from 'react'
import { api } from '../../api/client'
import { Badge, Button, Card } from '../ui'
import type { IRPolicyMappingAnalysis } from '../../types/ir'
import { RELEVANCE_BADGE } from '../../types/ir'

export function IRPolicyMappingPanel({ incidentId }: { incidentId: string }) {
  const [mapping, setMapping] = useState<IRPolicyMappingAnalysis | null>(null)
  const [loading, setLoading] = useState(false)

  const fetchMapping = useCallback(async () => {
    setLoading(true)
    try { setMapping(await api.get<IRPolicyMappingAnalysis>(`/ir/incidents/${incidentId}/policy-mapping`)) }
    catch { setMapping(null) }
    finally { setLoading(false) }
  }, [incidentId])

  useEffect(() => { fetchMapping() }, [fetchMapping])

  async function refresh() {
    setLoading(true)
    try { setMapping(await api.post<IRPolicyMappingAnalysis>(`/ir/incidents/${incidentId}/analyze/policy-mapping`)) }
    catch { /* ignore */ }
    finally { setLoading(false) }
  }

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-zinc-800/60 bg-zinc-900/40 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Policy Mapping</h3>
        <Button variant="ghost" size="sm" disabled={loading} onClick={refresh}>
          {loading ? '...' : 'Refresh'}
        </Button>
      </div>
      <div className="px-5 py-4">
        {loading && !mapping ? (
          <p className="text-xs text-zinc-500">Analyzing policies...</p>
        ) : !mapping || mapping.no_matching_policies ? (
          <p className="text-xs text-zinc-600">{mapping?.summary || 'No policy mapping available.'}</p>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-zinc-400">{mapping.summary}</p>
            {mapping.matches.map((m) => (
              <div key={m.policy_id} className="border border-zinc-800 rounded-lg p-3 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-zinc-200">{m.policy_title}</span>
                  <Badge variant={RELEVANCE_BADGE[m.relevance] ?? 'neutral'}>{m.relevance}</Badge>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                    <div className="h-full rounded-full bg-emerald-500/60" style={{ width: `${m.confidence * 100}%` }} />
                  </div>
                  <span className="text-[11px] text-zinc-500">{Math.round(m.confidence * 100)}%</span>
                </div>
                <p className="text-xs text-zinc-500">{m.reasoning}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  )
}
