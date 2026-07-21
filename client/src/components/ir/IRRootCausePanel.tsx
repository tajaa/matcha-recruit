import { IRAnalysisPanel } from './IRAnalysisPanel'
import type { IRRootCauseAnalysis } from '../../types/ir'

type Props = {
  incidentId: string
  result?: IRRootCauseAnalysis | null
  onResult?: (r: IRRootCauseAnalysis) => void
}

export function IRRootCausePanel({ incidentId, result, onResult }: Props) {
  return (
    <IRAnalysisPanel<IRRootCauseAnalysis>
      incidentId={incidentId}
      analysisType="root-cause"
      title="Intelligent Theme Analysis · Root Cause"
      result={result}
      onResult={onResult}
      renderResult={(res) => (
        <div className="border border-zinc-800 rounded-lg px-4 py-3 space-y-2">
          <p className="text-sm text-zinc-200">{res.primary_cause}</p>
          {res.contributing_factors.length > 0 && (
            <div>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Contributing Factors</p>
              <ul className="space-y-0.5">
                {res.contributing_factors.map((f, i) => <li key={i} className="text-xs text-zinc-400">- {f}</li>)}
              </ul>
            </div>
          )}
          {res.prevention_suggestions.length > 0 && (
            <div>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Prevention</p>
              <ul className="space-y-0.5">
                {res.prevention_suggestions.map((s, i) => <li key={i} className="text-xs text-zinc-400">- {s}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    />
  )
}
