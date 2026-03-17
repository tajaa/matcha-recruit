import { useState } from 'react'
import { api } from '../../api/client'
import { Button } from '../ui'
import type { IRCategorizationAnalysis } from '../../types/ir'
import { typeLabel } from '../../types/ir'

type Props = {
  incidentId: string
  result?: IRCategorizationAnalysis | null
  onResult?: (r: IRCategorizationAnalysis) => void
}

export function IRCategorizationPanel({ incidentId, result: externalResult, onResult }: Props) {
  const [localResult, setLocalResult] = useState<IRCategorizationAnalysis | null>(null)
  const [loading, setLoading] = useState(false)

  const result = externalResult ?? localResult

  async function run() {
    setLoading(true)
    try {
      const res = await api.post<IRCategorizationAnalysis>(`/ir/incidents/${incidentId}/analyze/categorize`)
      setLocalResult(res)
      onResult?.(res)
    }
    catch { /* silently fail */ }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">AI Categorization</h3>
        <Button variant="ghost" size="sm" disabled={loading} onClick={run}>
          {loading ? 'Running...' : 'Run'}
        </Button>
      </div>
      {result && (
        <div className="border border-zinc-800 rounded-lg px-4 py-3 space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="text-sm text-zinc-200">Suggested: {typeLabel(result.suggested_type)}</span>
            <span className="text-[11px] text-zinc-500">{Math.round(result.confidence * 100)}% confidence</span>
          </div>
          <p className="text-xs text-zinc-500">{result.reasoning}</p>
        </div>
      )}
    </div>
  )
}
