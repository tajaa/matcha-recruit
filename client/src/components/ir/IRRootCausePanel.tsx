import { useState, useEffect } from 'react'
import { useIRAnalysisStream } from '../../hooks/ir/useIRAnalysisStream'
import { Button } from '../ui'
import type { IRRootCauseAnalysis } from '../../types/ir'

export function IRRootCausePanel({ incidentId }: { incidentId: string }) {
  const stream = useIRAnalysisStream(incidentId)
  const [result, setResult] = useState<IRRootCauseAnalysis | null>(null)

  useEffect(() => {
    if (!stream.streaming && stream.result && stream.analysisType === 'root-cause') {
      setResult(stream.result as IRRootCauseAnalysis)
    }
  }, [stream.streaming, stream.result, stream.analysisType])

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">AI Root Cause Analysis</h3>
        <Button variant="ghost" size="sm" disabled={stream.streaming}
          onClick={() => stream.runAnalysis('root-cause')}>
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
          <p className="text-sm text-zinc-200">{result.primary_cause}</p>
          {result.contributing_factors.length > 0 && (
            <div>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Contributing Factors</p>
              <ul className="space-y-0.5">
                {result.contributing_factors.map((f, i) => <li key={i} className="text-xs text-zinc-400">- {f}</li>)}
              </ul>
            </div>
          )}
          {result.prevention_suggestions.length > 0 && (
            <div>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Prevention</p>
              <ul className="space-y-0.5">
                {result.prevention_suggestions.map((s, i) => <li key={i} className="text-xs text-zinc-400">- {s}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
      {stream.error && <p className="text-xs text-red-400 mt-1">{stream.error}</p>}
    </div>
  )
}
