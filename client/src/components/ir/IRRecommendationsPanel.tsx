import { IRAnalysisPanel } from './IRAnalysisPanel'
import { Badge } from '../ui'
import type { IRRecommendationsAnalysis } from '../../types/ir'

type Props = {
  incidentId: string
  result?: IRRecommendationsAnalysis | null
  onResult?: (r: IRRecommendationsAnalysis) => void
}

export function IRRecommendationsPanel({ incidentId, result, onResult }: Props) {
  return (
    <IRAnalysisPanel<IRRecommendationsAnalysis>
      incidentId={incidentId}
      analysisType="recommendations"
      title="Intelligent Theme Analysis · Recommendations"
      result={result}
      onResult={onResult}
      renderResult={(res) => (
        <div className="border border-zinc-800 rounded-lg px-4 py-3 space-y-2">
          <p className="text-xs text-zinc-400">{res.summary}</p>
          <div className="space-y-2">
            {res.recommendations.map((rec, i) => (
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
    />
  )
}
