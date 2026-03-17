import { useState, useEffect } from 'react'
import { useIRAnalysisStream } from '../../hooks/ir/useIRAnalysisStream'
import { Badge, Button } from '../ui'
import type { IRRecommendationsAnalysis } from '../../types/ir'

type Props = {
  incidentId: string
  result?: IRRecommendationsAnalysis | null
  onResult?: (r: IRRecommendationsAnalysis) => void
}

export function IRRecommendationsPanel({ incidentId, result: externalResult, onResult }: Props) {
  const stream = useIRAnalysisStream(incidentId)
  const [localResult, setLocalResult] = useState<IRRecommendationsAnalysis | null>(null)

  const result = externalResult ?? localResult

  useEffect(() => {
    if (!stream.streaming && stream.result && stream.analysisType === 'recommendations') {
      const res = stream.result as IRRecommendationsAnalysis
      setLocalResult(res)
      onResult?.(res)
    }
  }, [stream.streaming, stream.result, stream.analysisType]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">AI Recommendations</h3>
        <Button variant="ghost" size="sm" disabled={stream.streaming}
          onClick={() => stream.runAnalysis('recommendations')}>
          {stream.streaming ? 'Analyzing...' : 'Run'}
        </Button>
      </div>
      {stream.streaming && (
        <div className="border border-zinc-800 rounded-lg px-4 py-3">
          {stream.messages.map((m, i) => (
            <p key={i} className="text-xs text-zinc-500">{m}</p>
          ))}
        </div>
      )}
      {result && (
        <div className="border border-zinc-800 rounded-lg px-4 py-3 space-y-2">
          <p className="text-xs text-zinc-400">{result.summary}</p>
          <div className="space-y-2">
            {result.recommendations.map((rec, i) => (
              <div key={i} className="flex items-start gap-2">
                <Badge variant={rec.priority === 'immediate' ? 'danger' : rec.priority === 'short_term' ? 'warning' : 'neutral'}>
                  {rec.priority.replace(/_/g, ' ')}
                </Badge>
                <div>
                  <p className="text-sm text-zinc-200">{rec.action}</p>
                  {rec.responsible_party && <p className="text-[11px] text-zinc-500">{rec.responsible_party}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {stream.error && <p className="text-xs text-red-400 mt-1">{stream.error}</p>}
    </div>
  )
}
