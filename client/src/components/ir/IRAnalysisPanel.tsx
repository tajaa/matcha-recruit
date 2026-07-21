import { useState, useEffect, type ReactNode } from 'react'
import { useIRAnalysisStream, type IRStreamAnalysisType } from '../../hooks/ir/useIRAnalysisStream'
import { Button } from '../ui'

type Props<T> = {
  incidentId: string
  analysisType: IRStreamAnalysisType
  title: string
  runLabel?: string
  streamingLabel?: string
  result?: T | null
  onResult?: (r: T) => void
  renderResult: (r: T) => ReactNode
}

/**
 * Shared shell for the IR "run one AI analysis" panels (root-cause, recommendations,
 * similar-incidents). Owns the run-button + streaming box + error line + the
 * externalResult ?? localResult merge and the stream→local sync gated on analysisType.
 * Each caller supplies only its title/labels and a `renderResult` body.
 */
export function IRAnalysisPanel<T>({
  incidentId,
  analysisType,
  title,
  runLabel = 'Run',
  streamingLabel = 'Analyzing...',
  result: externalResult,
  onResult,
  renderResult,
}: Props<T>) {
  const stream = useIRAnalysisStream(incidentId)
  const [localResult, setLocalResult] = useState<T | null>(null)

  const result = externalResult ?? localResult

  useEffect(() => {
    if (!stream.streaming && stream.result && stream.analysisType === analysisType) {
      const res = stream.result as T
      setLocalResult(res)
      onResult?.(res)
    }
  }, [stream.streaming, stream.result, stream.analysisType]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">{title}</h3>
        <Button variant="ghost" size="sm" disabled={stream.streaming}
          onClick={() => stream.runAnalysis(analysisType)}>
          {stream.streaming ? streamingLabel : runLabel}
        </Button>
      </div>
      {stream.streaming && (
        <div className="border border-zinc-800 rounded-lg px-4 py-3">
          {stream.messages.map((m, i) => (
            <p key={i} className="text-xs text-zinc-500">{m}</p>
          ))}
        </div>
      )}
      {result && renderResult(result)}
      {stream.error && <p className="text-xs text-red-400 mt-1">{stream.error}</p>}
    </div>
  )
}
